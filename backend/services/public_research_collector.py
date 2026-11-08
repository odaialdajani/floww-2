"""One-cycle Public market-data evidence capture; no live transport or credential loader."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from services.public_api import PublicBroker
from services.public_budget import BudgetExhausted, PublicBudget
from services.public_request_pacer import pacer as shared_pacer
from services.public_research_store import (
    DEFAULT_LIMITS,
    PARSER_ID,
    ResearchRefusal,
    canonical,
    contains_sensitive,
    validate_manifest,
)
from services.solstice_calendar import ET
from services.solstice_capture_policy import capture_market_hours

HOST = "api.public.com"
PATHS = {
    "quotes": "/userapigateway/marketdata/{account}/quotes",
    "expirations": "/userapigateway/marketdata/{account}/option-expirations",
    "chain": "/userapigateway/marketdata/{account}/option-chain",
}


@dataclass(frozen=True)
class Limits:
    max_attempts: int = DEFAULT_LIMITS["max_attempts"]
    max_body_bytes: int = DEFAULT_LIMITS["max_body_bytes"]
    max_total_body_bytes: int = DEFAULT_LIMITS["max_total_body_bytes"]
    max_rows: int = DEFAULT_LIMITS["max_rows"]
    max_db_pages: int = DEFAULT_LIMITS["max_db_pages"]
    max_chunk_bytes: int = DEFAULT_LIMITS["max_chunk_bytes"]
    max_total_read_bytes: int = DEFAULT_LIMITS["max_total_read_bytes"]
    request_timeout_s: float = DEFAULT_LIMITS["request_timeout_s"]
    cycle_timeout_s: float = DEFAULT_LIMITS["cycle_timeout_s"]


@dataclass(frozen=True)
class RequestSpec:
    kind: str
    symbol: str
    expiry: str | None = None

    def __post_init__(self):
        if self.kind not in PATHS or self.symbol not in ("SPY", "QQQ"):
            raise ResearchRefusal("request_scope_invalid")
        if self.kind == "chain":
            try:
                if not isinstance(self.expiry, str) or datetime.strptime(self.expiry, "%Y-%m-%d").strftime("%Y-%m-%d") != self.expiry:
                    raise ValueError
            except ValueError:
                raise ResearchRefusal("request_scope_invalid") from None
        elif self.expiry is not None:
            raise ResearchRefusal("request_scope_invalid")

    @property
    def method(self):
        return "POST"

    @property
    def path_template(self):
        return PATHS[self.kind]

    @property
    def payload(self):
        instrument = {"symbol": self.symbol, "type": "EQUITY"}
        if self.kind == "quotes":
            return {"instruments": [instrument]}
        value = {"instrument": instrument}
        if self.kind == "chain":
            value["expirationDate"] = self.expiry
        return value

    def record(self):
        return {"kind": self.kind, "symbol": self.symbol, "expiry": self.expiry}


@dataclass
class RawReply:
    """A transport supplies one response context, no retry/refresh/redirect.

    chunks must be an async iterator with each chunk at most max_chunk_bytes.
    The transport is not supplied here and must be independently commissioned.
    """
    chunks: Any
    http_status: int = 200
    source_delivery: str = "network"
    media_type: str = "json"
    content_encoding: str = "identity"
    retry_after: str | None = None


class SystemClock:
    def now(self):
        return datetime.now(UTC)

    def monotonic(self):
        return time.monotonic()


def build_plan(expiries, limits=None):
    if limits is not None and not isinstance(limits, Limits):
        raise ResearchRefusal("manifest_invalid")
    return validate_manifest({
        "schema": "public-raw-research.v1", "parser_id": PARSER_ID, "symbols": ["SPY", "QQQ"],
        "expiries": list(expiries), "limits": asdict(limits or Limits()),
        "research_only": True, "trusted_for_admission": False, "executable": False,
    })


def requests_for(manifest):
    for symbol in manifest["symbols"]:
        yield RequestSpec("quotes", symbol)
        yield RequestSpec("expirations", symbol)
        for expiry in manifest["expiries"]:
            yield RequestSpec("chain", symbol, expiry)


def preview(expiries):
    manifest = build_plan(expiries)
    return {"status": "prepared", "live_transport": "absent", "provider_attempts": 0,
            "activation": False, "manifest": manifest,
            "requests": [{**request.record(), "method": request.method,
                          "path_template": request.path_template, "payload": request.payload}
                         for request in requests_for(manifest)],
            "budget_scope": "process_local_only; global_and_cross_process_quota_unverified",
            "missing_before_collection": ["reviewed_transparent_single_attempt_live_transport",
                                          "root_reviewed_destination_and_finite_collection_admission"]}


def _source_clock(value):
    if not isinstance(value, str) or len(value) > 80:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _size(value):
    if isinstance(value, str) and len(value) <= 19 and value.isascii() and value.isdecimal():
        value = int(value)
    return value if type(value) is int and 0 <= value < 2**63 else None


def _number(value):
    if value is None:
        return None
    if type(value) is bool or not isinstance(value, (int, float, str)):
        raise ValueError
    result = float(value)
    if not math.isfinite(result):
        raise ValueError
    return result


def _retry_after(value, now):
    if not isinstance(value, str) or len(value) > 128:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - now).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(1, min(86400, math.ceil(seconds))) if math.isfinite(seconds) else None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError


def _parse(request, body, response_hash, maximum):
    value = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(value, dict):
        raise ValueError
    rows, errors, truncated = [], 0, False
    if request.kind == "chain":
        groups = []
        for side in ("calls", "puts"):
            data = value.get(side)
            if not isinstance(data, list):
                errors += 1
            else:
                groups.extend((side, index, item) for index, item in enumerate(data))
    else:
        key = "quotes" if request.kind == "quotes" else "expirations"
        if not isinstance(value.get(key), list):
            raise ValueError
        groups = [(None, index, item) for index, item in enumerate(value[key])]
    for side, index, item in groups:
        if len(rows) >= maximum:
            truncated = True
            break
        try:
            record = {"kind": request.kind, "symbol": request.symbol, "raw_index": index,
                      "response_sha256": response_hash, "research_only": True,
                      "trusted_for_admission": False, "executable": False,
                      "source_event_freshness": "not_evaluated"}
            if request.kind == "expirations":
                if not isinstance(item, str) or datetime.strptime(item, "%Y-%m-%d").strftime("%Y-%m-%d") != item:
                    raise ValueError
                record.update(expiry=item, source_event_time=None)
            else:
                if not isinstance(item, dict) or not isinstance(item.get("instrument"), dict):
                    raise ValueError
                symbol = item["instrument"].get("symbol")
                raw_sizes = {name: item.get(name) for name in ("bidSize", "askSize")}
                record["raw_sizes"] = raw_sizes
                if request.kind == "chain":
                    match = re.fullmatch(r"(SPY|QQQ)(\d{6})[CP]\d{8}", str(symbol or ""))
                    if not match or match[1] != request.symbol or match[2] != request.expiry[2:].replace("-", ""):
                        raise ValueError
                    for key in ("bid", "ask", "last", "volume", "openInterest"):
                        _number(item.get(key))
                    details = item.get("optionDetails") or {}
                    if not isinstance(details, dict):
                        raise ValueError
                    greeks = details.get("greeks") or {}
                    if not isinstance(greeks, dict):
                        raise ValueError
                    for key in ("impliedVolatility", "delta", "gamma", "theta", "vega"):
                        _number(greeks.get(key))
                    contract = asdict(PublicBroker._parse_option_contract(None, item["instrument"], item))
                    for key in ("last", "bid", "ask", "volume", "open_interest", "iv", "delta", "gamma", "theta", "vega", "strike"):
                        if contract[key] is not None and not math.isfinite(float(contract[key])):
                            raise ValueError
                    for key in ("bid_timestamp", "ask_timestamp", "last_timestamp"):
                        contract[key] = _source_clock(contract[key])
                    date = contract["oi_effective_date"]
                    if date is not None:
                        try:
                            if not isinstance(date, str) or datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d") != date:
                                raise ValueError
                        except ValueError:
                            contract["oi_effective_date"] = None
                    record.update(expiry=request.expiry, raw_side=side, contract=contract,
                                  greeks_event_time=None, multiplier=None, adjusted=None,
                                  multiplier_raw=item.get("contractMultiplier"),
                                  adjusted_raw=item.get("adjusted"), size_unit="unverified",
                                  greeks_clock_authority="unverified")
                else:
                    if symbol != request.symbol:
                        raise ValueError
                    quote = {key: _number(item.get(key)) for key in ("bid", "ask", "last", "volume", "openInterest")}
                    quote.update(bid_size=_size(item.get("bidSize")), ask_size=_size(item.get("askSize")),
                                 bid_timestamp=_source_clock(item.get("bidTimestamp")),
                                 ask_timestamp=_source_clock(item.get("askTimestamp")),
                                 last_timestamp=_source_clock(item.get("lastTimestamp")))
                    record.update(quote=quote, greeks_event_time=None, oi_effective_date=None,
                                  multiplier=None, adjusted=None, size_unit="unverified")
            if len(canonical(record).encode()) > 4096:
                raise ValueError
            rows.append(record)
        except (ValueError, TypeError, OverflowError, AttributeError, ResearchRefusal):
            errors += 1
    return rows, errors, truncated


class _Stopped(Exception):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason


class ResearchCollector:
    """Caller-driven capture. No scheduler, server import, auth or live client."""

    def __init__(self, *, store, transport, budget, clock=None, session_gate=None,
                 pacer=None, should_stop=None):
        if not isinstance(budget, PublicBudget):
            raise ResearchRefusal("public_budget_required")
        self.store, self.transport, self.budget = store, transport, budget
        self.clock = clock or SystemClock()
        self.session_gate = session_gate or capture_market_hours
        self.pacer = pacer or shared_pacer
        self.should_stop = should_stop or (lambda: False)
        self.manifest = validate_manifest(store.manifest)
        self.limits = self.manifest["limits"]
        self._tasks = set()
        self._running = False
        self._quarantined = False
        self._invoked = 0
        self._cycle_deadline = None

    def _clock(self):
        now, mono = self.clock.now(), self.clock.monotonic()
        if (not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None
                or type(mono) not in (int, float) or not math.isfinite(mono)):
            raise ResearchRefusal("clock_invalid")
        return now, float(mono)

    def _gate(self, started_mono, started_wall):
        if asyncio.current_task().cancelling():
            raise asyncio.CancelledError
        now, mono = self._clock()
        if mono < started_mono:
            return "clock_invalid"
        if now < started_wall:
            return "clock_regressed"
        if mono - started_mono >= self.limits["cycle_timeout_s"]:
            return "cycle_deadline"
        if self._cycle_deadline is not None and asyncio.get_running_loop().time() >= self._cycle_deadline:
            return "cycle_deadline"
        try:
            paused = self.should_stop()
            opened = self.session_gate(now)
        except Exception:
            return "gate_unknown"
        if type(paused) is not bool or type(opened) is not bool:
            return "gate_unknown"
        if paused:
            return "paused"
        return None if opened else "session_closed_or_unknown"

    async def _receive(self, request, attempt_id, started_at, started_mono, cycle_mono, cycle_wall):
        reason = self._gate(cycle_mono, cycle_wall)
        if reason:
            raise _Stopped("pre_dispatch_stopped", reason)
        self.store._check_owner()
        # Same event-loop turn, no suspension: preserve precise injected time,
        # including subsecond cooldowns that status() intentionally rounds.
        if self.budget._cooldown_left_locked(HOST, self._clock()[1]) > 0:
            raise _Stopped("budget_refused", "public_cooldown")
        status = None
        buffer = bytearray()
        seen, complete, error, withholding = 0, False, None, None
        completed = None
        source, media, encoding = "unknown", "unsupported", "unsupported"
        try:
            self._invoked += 1
            async with self.transport.open(request, attempt_id) as reply:
                if (not isinstance(reply, RawReply) or type(reply.http_status) is not int
                        or not 100 <= reply.http_status <= 599
                        or reply.source_delivery not in {"network", "cache", "unknown"}
                        or reply.media_type not in {"json", "unsupported"}
                        or reply.content_encoding not in {"identity", "unsupported"}):
                    raise _Stopped("transport_failed", "transport_protocol_invalid")
                status, source, media, encoding = reply.http_status, reply.source_delivery, reply.media_type, reply.content_encoding
                if status == 429:
                    now, mono = self._clock()
                    self.budget.record_429(HOST, now=mono, retry_after=_retry_after(reply.retry_after, now))
                async for chunk in reply.chunks:
                    if type(chunk) is not bytes:
                        raise _Stopped("transport_failed", "transport_protocol_invalid")
                    seen += len(chunk)
                    if len(chunk) > self.limits["max_chunk_bytes"]:
                        error, withholding = "chunk_limit", "chunk_limit_exceeded"
                        break
                    if seen > self.limits["max_body_bytes"]:
                        error, withholding = "body_limit", "body_limit_exceeded"
                        break
                    buffer.extend(chunk)
                else:
                    complete = True
                completed = self._clock()[0]
        except (asyncio.CancelledError, _Stopped):
            raise
        except Exception:
            if status is None:
                raise _Stopped("transport_failed", "transport_failed") from None
            error = "transport_failed"
        if not complete:
            withholding = withholding or "incomplete_body"
        elif encoding != "identity":
            withholding = "unsupported_encoding"
        elif media != "json":
            withholding = "unsupported_media"
        else:
            try:
                buffer.decode("utf-8")
            except UnicodeDecodeError:
                withholding = "invalid_utf8"
            if contains_sensitive(buffer):
                withholding = "sensitive_body"
        body = bytes(buffer)
        metadata = {"http_status": status, "source_delivery": source, "media_type": media,
                    "content_encoding": encoding, "started_at": started_at.isoformat(),
                    "body_completed_at": completed.isoformat() if completed else None,
                    "wall_clock_regressed": completed is not None and completed < started_at,
                    "body_complete": complete, "bytes_observed": seen,
                    "source_body_sha256": hashlib.sha256(body).hexdigest() if complete else None,
                    "withholding_reason": withholding, "error_code": error}
        return metadata, body if withholding is None else b""

    async def _request(self, request, attempt, cycle_mono, cycle_wall):
        held = retained = False
        task = None
        budget = self.budget
        def remaining_cycle():
            return max(0, min(self.limits["cycle_timeout_s"] - (self._clock()[1] - cycle_mono),
                              self._cycle_deadline - asyncio.get_running_loop().time()))
        async def admit():
            nonlocal held
            await budget.acquire_n(1, HOST, now=self._clock()[1])
            held = True  # ownership must precede the task/timeout return seam
        try:
            await asyncio.wait_for(self.pacer.wait(), timeout=remaining_cycle())
            reason = self._gate(cycle_mono, cycle_wall)
            if reason:
                raise _Stopped("pre_dispatch_stopped", reason)
            await asyncio.wait_for(admit(), timeout=remaining_cycle())
            reason = self._gate(cycle_mono, cycle_wall)
            if reason:
                raise _Stopped("pre_dispatch_stopped", reason)
            now, mono = self._clock()
            self.store.mark_dispatch(attempt["attempt_id"], now.isoformat())
            self.store.retain_transport()
            retained = True
            task = asyncio.create_task(self._receive(request, attempt["attempt_id"], now, mono, cycle_mono, cycle_wall))
            self._tasks.add(task)
            cleaned = False

            def settled(done):
                nonlocal cleaned
                if cleaned:
                    return
                cleaned = True
                self._tasks.discard(done)
                with contextlib.suppress(BaseException):
                    done.exception()
                try:
                    budget.release()
                finally:
                    self.store.release_transport()

            task.add_done_callback(settled)
            held = retained = False  # only this task's settlement owns cleanup now
            remaining = min(self.limits["request_timeout_s"],
                            remaining_cycle())
            done, _ = await asyncio.wait({task}, timeout=max(0, remaining))
            if not done:
                self._quarantined = True
                task.cancel()
                raise _Stopped("unsettled", "request_timeout")
            settled(task)
            result = task.result()
            if self._clock()[1] - mono > remaining:
                self._quarantined = True
                raise _Stopped("timeout", "late_response")
            if result[0]["http_status"] == 200 and result[0]["body_complete"]:
                budget.record_ok(HOST, now=mono)
            return result
        except BudgetExhausted:
            raise _Stopped("budget_refused", "public_budget_refused") from None
        except TimeoutError:
            raise _Stopped("pre_dispatch_stopped", "cycle_deadline") from None
        except asyncio.CancelledError:
            if task is not None:
                self._quarantined = True
                task.cancel()
            raise
        finally:
            if held:
                budget.release()
            if retained:
                self.store.release_transport()

    async def capture_cycle(self, cycle_id):
        if self._running or self._quarantined:
            return {"status": "stopped", "reason": "collector_busy_or_quarantined",
                    "research_only": True, "trusted_for_admission": False, "executable": False}
        self._running = True
        initial_invocations = self._invoked
        receipt = {"cycle_id": cycle_id, "status": "collecting", "research_only": True,
                   "trusted_for_admission": False, "executable": False, "has_gaps": False,
                   "dispatch_attempts": 0, "responses_committed": 0, "parsed_rows": 0,
                   "source_event_freshness": "not_evaluated",
                   "budget_scope": "process_local_only_global_quota_unverified"}
        current = None
        began = False
        try:
            wall, mono = self._clock()
            self._cycle_deadline = asyncio.get_running_loop().time() + self.limits["cycle_timeout_s"]
            previous = self.store.begin_cycle(cycle_id, "XNYS:" + wall.astimezone(ET).date().isoformat())
            if previous is not None:
                return previous
            began = True
            for request in requests_for(self.manifest):
                reason = self._gate(mono, wall)
                if reason:
                    receipt.update(status="skipped" if self._invoked == initial_invocations else "stopped",
                                   reason=reason, has_gaps=True)
                    break
                if self.store.status()["rows"] >= self.limits["max_rows"]:
                    receipt.update(status="stopped", reason="row_cap", has_gaps=True)
                    break
                current = self.store.reserve_attempt(cycle_id, request.record())
                try:
                    metadata, body = await self._request(request, current, mono, wall)
                except _Stopped as stopped:
                    self.store.fail_attempt(current["attempt_id"], stopped.status)
                    receipt.update(status="stopped", reason=stopped.reason, has_gaps=True)
                    break
                self.store.record_response(current["attempt_id"], metadata, body)
                receipt["responses_committed"] += 1
                rows, errors, truncated = [], 0, False
                parse_status = "unavailable"
                if (metadata["body_complete"] and metadata["withholding_reason"] is None
                        and 200 <= metadata["http_status"] < 300):
                    try:
                        maximum = self.limits["max_rows"] - self.store.status()["rows"]
                        rows, errors, truncated = _parse(request, body, metadata["source_body_sha256"], maximum)
                        parse_status = "parsed" if rows else "parse_failed" if errors else "empty"
                    except (ValueError, TypeError, RecursionError, ResearchRefusal):
                        errors, parse_status = 1, "parse_failed"
                self.store.record_parsed(current["attempt_id"], rows,
                                         {"status": parse_status, "parsed_at": self._clock()[0].isoformat(),
                                          "errors": errors, "truncated": truncated})
                receipt["parsed_rows"] += len(rows)
                receipt["has_gaps"] |= (parse_status != "parsed" or bool(errors) or truncated
                                        or metadata["source_delivery"] != "network"
                                        or metadata["wall_clock_regressed"]
                                        or metadata["error_code"] is not None)
                if metadata["http_status"] == 429 or metadata["error_code"] == "chunk_limit":
                    receipt.update(status="stopped", reason="public_cooldown" if metadata["http_status"] == 429 else "transport_protocol_invalid")
                    break
            else:
                receipt["status"] = "committed"
        except asyncio.CancelledError:
            receipt.update(status="stopped", reason="cancelled", has_gaps=True)
            if current:
                with contextlib.suppress(ResearchRefusal):
                    self.store.fail_attempt(current["attempt_id"], "cancelled")
            if began:
                receipt["dispatch_attempts"] = self._invoked - initial_invocations
                with contextlib.suppress(ResearchRefusal):
                    self.store.finish_cycle(cycle_id, receipt)
            raise
        except ResearchRefusal as exc:
            receipt.update(status="stopped" if str(exc) in {"attempt_cap", "read_byte_cap", "row_cap"} else "failed",
                           reason=str(exc), has_gaps=True)
        except Exception:
            receipt.update(status="failed", reason="collector_failed", has_gaps=True)
        finally:
            self._running = False
        receipt["dispatch_attempts"] = self._invoked - initial_invocations
        if began:
            try:
                self.store.finish_cycle(cycle_id, receipt)
            except ResearchRefusal:
                receipt.update(status="failed", reason="cycle_commit_failed", has_gaps=True)
        return receipt
