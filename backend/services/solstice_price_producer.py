"""
backend/services/solstice_price_producer.py — default-off scheduled price-path producer.

Fills the one genuinely missing producer named in MUSE_STATE M3: nothing in the
tree feeds `price_paths_v1` on a schedule (the outcome worker only closes WITH
stored paths; `POST outcomes/close` takes caller-supplied paths). This module is
the commissioned producer seam, DISABLED BY DEFAULT and never auto-started on
import. Activation is an explicit operator act (`FLOWW_PRICE_PATH_PRODUCER=1`
plus `register_store` + `register_capture` + `start_worker`).

Design (contract `price-path-producer.v1`):
- Supported price observations only (injected `fetch_one`), tied to the correct
  exchange session and symbol via an injected `session_gate`. Closed sessions
  skip WITHOUT a provider call and WITHOUT fabrication; gaps stay unknown.
- Vendor observation time (`event_time` → `at_ts`) is stored separately from
  fetch time (`fetched_at` → `received_at`). No interpolation, no synthetic
  history, no reconstructed Greeks.
- 5-minute default cadence (`cadence_s=300`) for swing research. A sparse
  five-minute path MUST NOT claim intraminute 0DTE resolution
  (`RESOLUTION_CLAIM = "5min-swing-only"`).
- Session calendars (America/New_York DST, holidays, early closes) belong to the
  injected gate (default uses `solstice_calendar.exchange_day_info` + NY wall
  clock); the producer never invents session state.
- Idempotent writes: exact `(ticker, at_ts)` duplicates are skipped via an
  in-process set + a DB existence check. Storage itself stays append-only
  (`record_price_path` never dedups); ordering/gap semantics belong to the
  labeling layer.
- Concurrency: single-writer only. All writes go through
  `heatmap_history`'s single-writer lock. Multi-process DuckDB writers are NOT
  safe and NOT claimed; the supported proof is: a second process reopens the
  persisted file AFTER the producer exits with identical digests + replay.
- Request budget: optional `budget` (e.g. `public_budget.budget`) is debited
  per symbol per tick; refusal skips the tick with `budget_refusals`, never a
  retry storm.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

PRODUCER_VERSION = "price-path-producer.v1"
WORKER_ENV_FLAG = "FLOWW_PRICE_PATH_PRODUCER"
WORKER_INTERVAL_S = 300.0
RESOLUTION_CLAIM = "5min-swing-only"
RESOLUTION_LIMIT = "not suitable for 0DTE-intraminute reaction or stop-ordering analysis"
POLICY_NOTE = "swing-5min; NOT intraminute-0DTE"
ET = ZoneInfo("America/New_York")
MAX_SYMBOLS = 32
# In-process duplicate fast-path bound: restart idempotency always rechecks the
# DB, so dropping old keys here only costs one SELECT per re-observation.
_SEEN_MAX = 10000

__all__ = [
    "PRODUCER_VERSION",
    "WORKER_ENV_FLAG",
    "RESOLUTION_CLAIM",
    "RESOLUTION_LIMIT",
    "PricePathProducer",
    "default_session_gate",
    "worker_enabled",
    "register_store",
    "register_capture",
    "start_worker",
    "stop_worker",
]


def worker_enabled() -> bool:
    """True only when the operator explicitly set the flag to "1"."""
    return os.environ.get(WORKER_ENV_FLAG, "") == "1"


def _parse_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        import math as _math

        return f if _math.isfinite(f) else None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                f = float(s)
            except (TypeError, ValueError):
                return None
            import math as _math

            return f if _math.isfinite(f) else None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    return None


def default_session_gate(symbol: str, now_epoch: float) -> tuple[bool, str]:
    """Exchange-session gate using the maintained XNYS calendar + NY wall clock.

    Closed (holiday, weekend, outside open-close, unknown calendar) returns
    (False, reason) so the tick skips without a provider call. Never invents
    an open session.
    """
    try:
        from services.solstice_calendar import exchange_day_info

        now_ny = datetime.fromtimestamp(float(now_epoch), tz=UTC).astimezone(ET)
        info = exchange_day_info(now_ny.strftime("%Y-%m-%d"))
        if not info.get("is_open"):
            return False, str(info.get("reason") or "CLOSED")
        open_et = str(info.get("open_et") or "09:30")
        close_et = str(info.get("close_et") or "16:00")
        cur = now_ny.strftime("%H:%M")
        if not (open_et <= cur < close_et):
            return False, "OUTSIDE_SESSION"
        return True, "open"
    except Exception as exc:  # fail closed on any calendar failure
        log.debug("price producer session gate failed for %s: %s", symbol, exc)
        return False, "CALENDAR_UNKNOWN"


def _drive_maybe_async(fn: Callable, *args: Any) -> Any:
    """Call fn(*args); drive the result to completion if awaitable.

    Ticks run synchronously (background thread + unit tests have no running
    loop). If the injected seam is async, run it to completion here. If a loop
    is already running (async caller), fall back to a fail-closed gap rather
    than deadlocking.
    """
    result = fn(*args)
    if not inspect.isawaitable(result):
        return result
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(result)
    # Already inside a loop: do not block; treat as a missed observation.
    log.debug("price producer async seam called from running loop — gap")
    return None


class PricePathProducer:
    """One scheduled price-path capture process (single-writer, default-off)."""

    def __init__(
        self,
        conn: Any,
        symbols: list[str],
        cadence_s: float = WORKER_INTERVAL_S,
        fetch_one: Callable[[str], Any] | None = None,
        session_gate: Callable[[str, float], tuple[bool, str]] | None = None,
        budget: Any | None = None,
        budget_host: str = "api.public.com",
        generation: str | None = None,
    ) -> None:
        if conn is None:
            raise ValueError("conn is required (throwaway test handle or file DB)")
        syms = [str(s or "").upper() for s in (symbols or []) if str(s or "").strip()]
        if len(syms) > MAX_SYMBOLS:
            raise ValueError(f"too many symbols ({len(syms)} > {MAX_SYMBOLS})")
        self.conn = conn
        self.symbols = syms
        self.cadence_s = float(cadence_s or WORKER_INTERVAL_S)
        self.fetch_one = fetch_one
        self.session_gate = session_gate or default_session_gate
        self.budget = budget
        self.budget_host = budget_host
        self.generation = generation or uuid.uuid4().hex[:12]
        self._seen: set[tuple[str, float]] = set()
        self._last_at: dict[str, float] = {}
        self._lock = threading.Lock()
        self.captures = 0
        self.gaps = 0
        self.errors = 0
        self.duplicates = 0
        self.out_of_order = 0
        self.closed_skips = 0
        self.budget_refusals = 0
        self.last_tick_at: float | None = None
        self.last_latency_ms: float | None = None

    def _budget_allowed(self) -> bool:
        if self.budget is None:
            return True
        try:
            acquire = getattr(self.budget, "acquire_n", None) or getattr(self.budget, "acquire", None)
            if acquire is None:
                return True
            try:
                _drive_maybe_async(acquire, 1, self.budget_host)
            except TypeError:
                _drive_maybe_async(acquire, self.budget_host)
            return True
        except Exception as exc:
            name = type(exc).__name__
            if name == "BudgetExhausted" or "budget" in str(exc).lower() or "exhaust" in str(exc).lower():
                with self._lock:
                    self.budget_refusals += 1
                return False
            log.debug("price producer budget error: %s", exc)
            with self._lock:
                self.errors += 1
            return False

    def tick(self, now_epoch: float | None = None) -> dict[str, Any]:
        """One capture cycle over all symbols. Never raises; returns a receipt."""
        from services.heatmap_history import ensure_tables, record_price_path

        t0 = time.monotonic()
        now = float(now_epoch) if now_epoch is not None else time.time()
        out = {
            "written": 0, "gaps": 0, "duplicates": 0, "out_of_order": 0,
            "closed_skips": 0, "budget_refusals": 0, "errors": 0,
            "generation": self.generation,
        }
        if self.fetch_one is None:
            out["errors"] = len(self.symbols)
            with self._lock:
                self.errors += len(self.symbols)
            return out
        try:
            ensure_tables(self.conn)
        except Exception as exc:  # store unavailable: clear refusal per symbol
            log.debug("price producer ensure_tables failed: %s", exc)
            out["errors"] = len(self.symbols)
            with self._lock:
                self.errors += len(self.symbols)
            return out
        for symbol in self.symbols:
            try:
                open_, _reason = self.session_gate(symbol, now)
            except Exception as exc:
                log.debug("price producer gate failed for %s: %s", symbol, exc)
                open_ = False
            if not open_:
                out["closed_skips"] += 1
                with self._lock:
                    self.closed_skips += 1
                continue
            if not self._budget_allowed():
                out["budget_refusals"] += 1
                continue
            try:
                obs = _drive_maybe_async(self.fetch_one, symbol)
            except Exception as exc:
                log.debug("price producer fetch failed for %s: %s", symbol, exc)
                out["gaps"] += 1
                with self._lock:
                    self.gaps += 1
                continue
            if not isinstance(obs, dict):
                out["gaps"] += 1
                with self._lock:
                    self.gaps += 1
                continue
            try:
                price = obs.get("price")
                price_f = float(price) if price is not None else None
                import math as _math

                if price_f is None or not _math.isfinite(price_f):
                    raise ValueError("non-finite price")
            except (TypeError, ValueError):
                out["gaps"] += 1
                with self._lock:
                    self.gaps += 1
                continue
            at_ts = _parse_epoch(obs.get("event_time"))
            fetched_at = obs.get("fetched_at")
            if at_ts is None:
                # No vendor observation time: refuse, never substitute fetch time
                # as a source event. Gaps stay gaps.
                out["gaps"] += 1
                with self._lock:
                    self.gaps += 1
                continue
            source = str(obs.get("source") or "unknown")
            received_at = str(fetched_at) if isinstance(fetched_at, str) and fetched_at else datetime.fromtimestamp(
                now, tz=UTC).isoformat()
            key = (symbol, float(at_ts))
            with self._lock:
                if key in self._seen:
                    self.duplicates += 1
                    out["duplicates"] += 1
                    continue
            # Restart idempotency: skip exact (ticker, at_ts) already stored.
            try:
                existing = self.conn.execute(
                    "SELECT COUNT(*) FROM price_paths_v1 WHERE ticker = ? AND at_ts = ?",
                    [symbol, float(at_ts)],
                ).fetchone()
                if existing and int(existing[0]) > 0:
                    with self._lock:
                        self._seen.add(key)
                        self.duplicates += 1
                    out["duplicates"] += 1
                    continue
            except Exception as exc:
                log.debug("price producer duplicate check failed for %s: %s", symbol, exc)
            prev_max = self._last_at.get(symbol)
            if prev_max is None:
                # Fresh process: seed the high-water mark from the durable store
                # so a restarted producer still flags out-of-order observations
                # instead of silently resetting the sequence.
                try:
                    row = self.conn.execute(
                        "SELECT MAX(at_ts) FROM price_paths_v1 WHERE ticker = ?",
                        [symbol],
                    ).fetchone()
                    if row and row[0] is not None:
                        prev_max = float(row[0])
                        with self._lock:
                            self._last_at[symbol] = prev_max
                except Exception as exc:
                    log.debug("price producer high-water seed failed for %s: %s", symbol, exc)
                    prev_max = self._last_at.get(symbol)
            is_ooo = prev_max is not None and float(at_ts) < prev_max
            try:
                ok = record_price_path(self.conn, symbol, float(at_ts), float(price_f), source, received_at)
            except Exception as exc:
                log.debug("price producer write failed for %s: %s", symbol, exc)
                out["errors"] += 1
                with self._lock:
                    self.errors += 1
                continue
            if not ok:
                out["gaps"] += 1
                with self._lock:
                    self.gaps += 1
                continue
            with self._lock:
                self._seen.add(key)
                self._last_at[symbol] = max(prev_max or float("-inf"), float(at_ts))
                self.captures += 1
                if is_ooo:
                    self.out_of_order += 1
                if len(self._seen) > _SEEN_MAX:
                    # Drop oldest observations first; DB recheck covers restarts.
                    for old in sorted(self._seen, key=lambda item: item[1])[: len(self._seen) - _SEEN_MAX]:
                        self._seen.discard(old)
            out["written"] += 1
            if is_ooo:
                out["out_of_order"] += 1
        latency_ms = (time.monotonic() - t0) * 1000.0
        with self._lock:
            self.last_tick_at = now
            self.last_latency_ms = latency_ms
            # All cumulative counters are incremented inline above (exactly once
            # per event); nothing is mirrored here. A previous revision mirrored
            # gaps a second time (double-count); pinned by regression test.
        out["latency_ms"] = latency_ms
        return out

    def health(self) -> dict[str, Any]:
        try:
            from services.heatmap_history import recorder_status

            store = recorder_status(self.conn)
            durable = bool(store.get("durable"))
        except Exception:
            durable = False
        with self._lock:
            return {
                "version": PRODUCER_VERSION,
                "enabled": worker_enabled(),
                "cadence_s": self.cadence_s,
                "symbols": list(self.symbols),
                "generation": self.generation,
                "captures": self.captures,
                "gaps": self.gaps,
                "errors": self.errors,
                "duplicates": self.duplicates,
                "out_of_order": self.out_of_order,
                "closed_skips": self.closed_skips,
                "budget_refusals": self.budget_refusals,
                "last_tick_at": self.last_tick_at,
                "last_latency_ms": self.last_latency_ms,
                "durable": durable,
                "policy": POLICY_NOTE,
                "resolution": RESOLUTION_CLAIM,
                "resolution_limit": RESOLUTION_LIMIT,
            }


# ---------------------------------------------------------------------------
# Module-level default-off worker lifecycle (mirrors recorder_health pattern).
# ---------------------------------------------------------------------------

_STORE_CONN: Any = None
_CAPTURE: dict[str, Any] | None = None
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_PRODUCER: PricePathProducer | None = None
_WORKER_STATE = "absent"  # absent | wired_off | active
_STATE_LOCK = threading.Lock()


def _set_state(state: str) -> None:
    global _WORKER_STATE
    if state not in ("absent", "wired_off", "active"):
        raise ValueError("bad worker state")
    with _STATE_LOCK:
        _WORKER_STATE = state


def register_store(conn: Any) -> None:
    """Register the DuckDB store handle. Does NOT start anything."""
    global _STORE_CONN
    _STORE_CONN = conn
    if _CAPTURE is not None and _WORKER_STATE == "absent":
        _set_state("wired_off")


def register_capture(
    symbols: list[str],
    fetch_one: Callable[[str], Any] | None = None,
    session_gate: Callable[[str, float], tuple[bool, str]] | None = None,
    cadence_s: float = WORKER_INTERVAL_S,
    budget: Any | None = None,
    budget_host: str = "api.public.com",
) -> None:
    """Install the capture configuration. Does NOT start anything."""
    global _CAPTURE
    _CAPTURE = {
        "symbols": [str(s or "").upper() for s in (symbols or []) if str(s or "").strip()],
        "fetch_one": fetch_one,
        "session_gate": session_gate,
        "cadence_s": float(cadence_s or WORKER_INTERVAL_S),
        "budget": budget,
        "budget_host": budget_host,
    }
    if _WORKER_STATE == "absent":
        _set_state("wired_off")


def _loop() -> None:
    assert _PRODUCER is not None
    interval = _PRODUCER.cadence_s
    while not _STOP.is_set():
        try:
            _PRODUCER.tick()
        except Exception as exc:  # a failed tick must not kill the worker
            log.debug("price producer tick failed: %s", exc)
        _STOP.wait(interval)


def start_worker() -> dict[str, Any]:
    """Start the scheduled producer ONLY if explicitly enabled. Returns a receipt."""
    global _THREAD, _PRODUCER
    if not worker_enabled():
        _set_state("wired_off" if _CAPTURE is not None else "absent")
        with _STATE_LOCK:
            state = _WORKER_STATE
        return {"started": False, "reason": f"{WORKER_ENV_FLAG}!=1", "worker_state": state}
    if _CAPTURE is None:
        _set_state("absent")
        return {"started": False, "reason": "no capture registered", "worker_state": "absent"}
    if _STORE_CONN is None:
        _set_state("wired_off")
        return {"started": False, "reason": "no store registered", "worker_state": "wired_off"}
    with _STATE_LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return {"started": False, "reason": "already running", "worker_state": "active"}
        _STOP.clear()
        _PRODUCER = PricePathProducer(
            conn=_STORE_CONN,
            symbols=_CAPTURE["symbols"],
            cadence_s=_CAPTURE["cadence_s"],
            fetch_one=_CAPTURE["fetch_one"],
            session_gate=_CAPTURE["session_gate"],
            budget=_CAPTURE["budget"],
            budget_host=_CAPTURE["budget_host"],
        )
        _THREAD = threading.Thread(target=_loop, name="solstice-price-paths", daemon=True)
        _THREAD.start()
    _set_state("active")
    return {"started": True, "interval_s": _PRODUCER.cadence_s, "worker_state": "active",
            "generation": _PRODUCER.generation}


def stop_worker(timeout: float = 5.0) -> dict[str, Any]:
    """Stop the worker if running. Safe to call when nothing was started."""
    global _THREAD, _PRODUCER
    _STOP.set()
    thread = _THREAD
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
    _THREAD = None
    _PRODUCER = None
    with _STATE_LOCK:
        state = _WORKER_STATE
    if state == "active":
        _set_state("wired_off")
        state = "wired_off"
    return {"stopped": True, "worker_state": state}


def _reset_for_tests() -> None:
    """Test isolation only: drop singleton store/capture/thread state."""
    global _STORE_CONN, _CAPTURE, _PRODUCER, _THREAD
    import contextlib as _ctx

    with _ctx.suppress(Exception):
        stop_worker()
    _STORE_CONN = None
    _CAPTURE = None
    _PRODUCER = None
    _THREAD = None
    _STOP.clear()
    _set_state("absent")
