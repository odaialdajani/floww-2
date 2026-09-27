"""Opt-in measurements for a NEW evaluation; never mutates exposed results.

These wrappers observe existing method boundaries without changing the model,
quota, retry policy, evidence, or output. A pipe write/accepted Codex turn is not
an upstream request count or an invoice. Browser display remains separately
unmeasured until a browser observer supplies evidence.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import time
from datetime import datetime

import httpx

from services.agent.codex_bridge import CodexBridge
from services.agent.read_budget import LIMIT, POLICY


class CaseTrace:
    def __init__(self, *, clock=time.perf_counter, sink=None):
        self.clock, self.sink = clock, sink
        self.clock_resolution_s = time.get_clock_info("perf_counter").resolution if clock is time.perf_counter else None
        self.started = clock()
        self.marks = {}
        self.model_outcomes = []
        self.measurement_complete = False
        self.measurement_failed = False
        self.bridge_pending = 0
        self.bridge_counts = dict(
            managed_turn_start_attempts=0, managed_turn_start_pipe_writes=0, managed_turn_start_acknowledgments=0
        )

    def _record(self):
        if self.sink is not None:
            try:
                self.sink(self.snapshot())
            except BaseException:
                self.measurement_failed = True
                self.measurement_complete = False
                raise

    def finish(self):
        if self.measurement_failed or self.bridge_pending or any(
            status in {"reserved", "entered"} for status in self.model_outcomes
        ):
            raise ValueError("Cannot close an incomplete measurement")
        self.measurement_complete = True
        self._record()

    def mark(self, name):
        if name not in self.marks:
            self.measurement_complete = False
            self.marks[name] = max(0, self.clock() - self.started)
            self._record()

    def count(self, name):
        self.measurement_complete = False
        self.bridge_counts[name] += 1
        self._record()

    def snapshot(self):
        entries = sum(status not in {"reserved", "not_entered"} for status in self.model_outcomes)
        entry_complete = "reserved" not in self.model_outcomes
        return copy.deepcopy(
            dict(
                version=1,
                model_invocations=entries if entry_complete else None,
                model_invocations_lower_bound=entries,
                model_entry_count_complete=entry_complete,
                measurement_complete=self.measurement_complete,
                measurement_failed=self.measurement_failed,
                count_interpretation="Saved counters are lower bounds until measurement_complete is true",
                model_outcomes=self.model_outcomes,
                **self.bridge_counts,
                timings_s=self.marks,
                upstream_model_requests=None,
                actual_cost_usd=None,
                first_browser_display_s=None,
                timing_origin="evaluation case start; client monotonic clock",
                clock_resolution_s=self.clock_resolution_s,
                model_count_scope="App model method entries, managed turn attempts, completed pipe writes and acknowledgments are distinct",
            )
        )


class MeasuredModel:
    def __init__(self, model, trace):
        self.model, self.trace = model, trace

    def __getattr__(self, name):
        return getattr(self.model, name)

    async def once(self, *args, **kwargs):
        index = len(self.trace.model_outcomes)
        self.trace.measurement_complete = False
        self.trace.model_outcomes.append("reserved")
        try:
            self.trace._record()  # Refuse work if its measurement cannot be preserved.
        except Exception:
            self.trace.model_outcomes[index] = "not_entered"
            raise
        self.trace.model_outcomes[index] = "entered"
        try:
            result = await self.model.once(*args, **kwargs)
        except asyncio.CancelledError:
            self.trace.model_outcomes[index] = "cancelled"
            self.trace._record()
            raise
        except Exception:
            self.trace.model_outcomes[index] = "error"
            self.trace._record()
            raise
        status = result.get("status") if isinstance(result, dict) else None
        self.trace.model_outcomes[index] = (
            status if status in {"ok", "invalid", "unavailable", "cost_limited"} else "returned"
        )
        self.trace._record()
        return result


def measured_bridge(trace):
    """Factory preserving CodexBridge isolation and exact request bodies."""

    class MeasuredBridge(CodexBridge):
        async def send(self, message):
            await super().send(message)
            if message.get("method") == "turn/start":
                trace.count("managed_turn_start_pipe_writes")

        async def request(self, method, params):
            tracked = method == "turn/start"
            if tracked:
                trace.bridge_pending += 1
            try:
                if tracked:
                    trace.count("managed_turn_start_attempts")
                result = await super().request(method, params)
                if tracked and isinstance(result, dict) and isinstance(result.get("turn"), dict):
                    if isinstance(result["turn"].get("id"), str) and result["turn"]["id"]:
                        trace.count("managed_turn_start_acknowledgments")
                return result
            finally:
                if tracked:
                    trace.bridge_pending -= 1

    return MeasuredBridge


def read_metrics(doc):
    activity = doc.get("read_activity")
    if activity is None:
        return dict(status="unmeasured", reserved=None, started=None, denied=None, entry_count_complete=False)
    if not isinstance(activity, dict) or activity.get("policy") != POLICY or activity.get("limit") != LIMIT:
        raise ValueError("Unknown capability accounting policy")
    attempts, denied = activity.get("attempts"), activity.get("denied")
    if (
        not isinstance(attempts, list)
        or not isinstance(denied, list)
        or any(not isinstance(a, dict) for a in attempts)
        or type(activity.get("reserved")) is not int
        or type(activity.get("started")) is not int
    ):
        raise ValueError("Invalid capability records")
    started = sum(isinstance(a, dict) and a.get("started_at") is not None for a in attempts)
    if (
        len(attempts) > LIMIT
        or activity.get("reserved") != len(attempts)
        or activity.get("started") != started
        or len(denied) > 32
    ):
        raise ValueError("Capability counts disagree with attempt records")
    complete = activity.get("entry_count_complete") is True and activity.get("closed") is True
    return dict(
        status="measured" if complete else "incomplete",
        reserved=len(attempts),
        started=started,
        denied=len(denied),
        entry_count_complete=complete,
        unresolved=sum(bool(a.get("worker_unresolved")) for a in attempts),
        policy=POLICY,
        limit=LIMIT,
    )


def _aware(value):
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if not isinstance(value, str):
        return None
    try:
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value if value.tzinfo is not None else None
    except ValueError:
        return None


def saved_progress_metrics(doc):
    created = _aware(doc.get("created_at"))
    event = next((e for e in doc.get("events", []) if e.get("type") == "progress"), {})
    recorded = _aware(event.get("recorded_at"))
    elapsed = (recorded - created).total_seconds() if created and recorded else None
    if elapsed is not None and elapsed < 0:
        elapsed = None
    return dict(
        first_progress_recorded_s=elapsed,
        clock="server wall clock; turn admission to pre-write timestamp of first saved progress event",
        limitation="Not storage acknowledgment, event receipt, DOM visibility, or first paint",
    )


async def usage_evidence(collection, owner, turn_id):
    """Read quota records by owned turn, never infer calls from successful answers."""
    guard = await collection.find_one({"_id": "turn:" + turn_id, "owner": owner})
    if guard is None:
        return dict(reservations=None, status="no_owned_admission_record", actual_cost_usd=None)
    day, identity = guard.get("day"), guard.get("request_id")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day or "") or not re.fullmatch(r"[a-f0-9-]{36}", identity or ""):
        raise ValueError("Invalid saved usage identity")
    row = await collection.find_one({"_id": "day:" + day}, {"_id": 0, f"entries.{identity}": 1})
    entry = (row or {}).get("entries", {}).get(identity)
    if entry is None:
        return dict(reservations=0, status="admission_guard_without_daily_reservation", actual_cost_usd=None)
    if entry.get("owner") != owner or entry.get("turn_id") != turn_id:
        raise ValueError("Saved usage does not match this owner and turn")
    return dict(
        reservations=1,
        status=entry.get("status", "uncertain"),
        completed_generation=bool(entry.get("generation_id") and entry.get("status") == "completed"),
        actual_cost_usd=entry.get("actual_cost"),
        accounting=entry.get("accounting"),
    )


async def observe_progress_stream(client, turn_id, trace, *, timeout=130):
    """Observe actual HTTP streaming. ASGI buffering cannot prove first receipt."""
    if not re.fullmatch(r"[a-f0-9-]{36}", turn_id):
        raise ValueError("Invalid turn identity")
    target = client.base_url.join(f"/api/agent/stream/{turn_id}")
    if not isinstance(client._transport_for_url(target), httpx.AsyncHTTPTransport):
        raise ValueError("Progress timing requires real HTTP transport, not a buffered test transport")
    payload = []
    size = 0
    async with asyncio.timeout(timeout):
        async with client.stream("GET", str(target), timeout=timeout) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    size += len(line)
                    if size > 65536:
                        raise ValueError("Progress event exceeds its bound")
                    payload.append(line[6:])
                elif not line and payload:
                    event = json.loads("\n".join(payload))
                    payload, size = [], 0
                    if event.get("type") == "progress":
                        trace.mark("first_stream_progress_received")
                    if event.get("type") in {"done", "error"}:
                        trace.mark("terminal_stream_received")
                        return event
    raise ValueError("Stream ended without a terminal event")
