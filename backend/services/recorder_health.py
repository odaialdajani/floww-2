"""
backend/services/recorder_health.py — honest recorder health (S4).

Answers the two questions an operator actually has, without conflating them:

1. Is the STORE durable? (file-backed DuckDB with tables vs a :memory:
   handle that looks durable because a path is configured). This is
   ``heatmap_history.recorder_status``; re-exported here so callers have one
   import.
2. Is a CAPTURE WORKER running, wired, or absent? These are three
   different states and the packet names which one it is:
     - "absent"      the capture path has no caller in this tree
     - "wired_off"   the worker exists and is scheduled, but switched off
     - "active"      the worker is running and has captured recently

Reporting "needs time" for both a missing producer and a disabled job is
the failure this module exists to prevent.

The worker in this module is DISABLED BY DEFAULT and is not started by this
import. Activation is a separate, explicit deployment act (see
FLOWW_RECORDER_WORKER=1 plus an operator-started scheduler); nothing here
auto-starts a service, and no existing recorder behaviour changes.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

RECORDER_HEALTH_VERSION = "recorder-health.v1"

# Opt-in flag. Absent or != "1" means the worker does not run.
WORKER_ENV_FLAG = "FLOWW_RECORDER_WORKER"
# Cadence for the capture loop, seconds. Only consulted when enabled.
WORKER_INTERVAL_S = 60.0

# One process-wide tally, updated only by the worker below. Kept in memory on
# purpose: this is observability about the worker, not the durable record.
_STATS: dict[str, Any] = {
    "worker_state": "absent",     # absent | wired_off | active
    "last_capture_at": None,      # epoch seconds of the last SUCCESS
    "last_error_at": None,
    "last_error": None,
    "captures": 0,
    "errors": 0,
    "gaps": 0,                    # capture attempts that returned no observation
}
_STATS_LOCK = threading.Lock()

_CAPTURE: Callable[[], Any] | None = None
_STOP = threading.Event()
_THREAD: threading.Thread | None = None


def worker_enabled() -> bool:
    """True only when the operator explicitly set the flag to "1"."""
    return os.environ.get(WORKER_ENV_FLAG, "") == "1"


def mark_worker_state(state: str) -> None:
    """Register the capture path's real state (absent/wired_off/active)."""
    if state not in ("absent", "wired_off", "active"):
        raise ValueError("state must be 'absent', 'wired_off' or 'active'")
    with _STATS_LOCK:
        _STATS["worker_state"] = state


def register_capture(capture: Callable[[], Any]) -> None:
    """Install the capture callable. Does NOT start anything."""
    global _CAPTURE
    _CAPTURE = capture
    if _CAPTURE is not None and _STATS["worker_state"] == "absent":
        mark_worker_state("wired_off")


def _note_success() -> None:
    with _STATS_LOCK:
        _STATS["last_capture_at"] = time.time()
        _STATS["captures"] += 1


def _note_gap() -> None:
    with _STATS_LOCK:
        _STATS["gaps"] += 1


def _note_error(exc: BaseException) -> None:
    with _STATS_LOCK:
        _STATS["errors"] += 1
        _STATS["last_error_at"] = time.time()
        _STATS["last_error"] = f"{type(exc).__name__}: {exc}"


def _loop() -> None:
    while not _STOP.is_set():
        capture = _CAPTURE
        if capture is None:
            _STOP.wait(WORKER_INTERVAL_S)
            continue
        try:
            result = capture()
        except Exception as exc:  # a failed capture must not kill the worker
            _note_error(exc)
        else:
            if result in (None, False, 0, "", [], {}):
                _note_gap()          # a real attempt that produced no observation
            else:
                _note_success()
        _STOP.wait(WORKER_INTERVAL_S)


def start_worker() -> dict[str, Any]:
    """Start the capture worker ONLY if explicitly enabled. Returns a receipt.

    Disabled-by-default. Calling this with the flag unset is a no-op that
    reports why, so an operator is never told a worker is running when it is
    not. No exception path can start it.
    """
    global _THREAD
    if not worker_enabled():
        mark_worker_state("wired_off" if _CAPTURE is not None else "absent")
        with _STATS_LOCK:
            state = _STATS["worker_state"]
        return {"started": False, "reason": f"{WORKER_ENV_FLAG}!=1", "worker_state": state}
    if _CAPTURE is None:
        mark_worker_state("absent")
        return {"started": False, "reason": "no capture registered", "worker_state": "absent"}
    with _STATS_LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return {"started": False, "reason": "already running", "worker_state": "active"}
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="solstice-recorder", daemon=True)
        _THREAD.start()
    mark_worker_state("active")
    return {"started": True, "interval_s": WORKER_INTERVAL_S, "worker_state": "active"}


def stop_worker(timeout: float = 5.0) -> dict[str, Any]:
    """Stop the worker if running. Safe to call when nothing was started."""
    global _THREAD
    _STOP.set()
    thread = _THREAD
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
    _THREAD = None
    state = _STATS["worker_state"]
    if state == "active":
        mark_worker_state("wired_off")
    return {"stopped": True, "worker_state": _STATS["worker_state"]}


def recorder_health(conn: Any = None, path: str | None = None) -> dict[str, Any]:
    """The health packet: durability and capture state, reported separately.

    ``durable`` describes the STORE. ``worker_state`` describes the JOB. A
    durable store with no capture worker is a perfectly good store that is
    collecting nothing, and this packet says exactly that.
    """
    from services.heatmap_history import recorder_status

    store = recorder_status(conn, path) if conn is not None else {"durable": False, "mode": "no_connection"}
    with _STATS_LOCK:
        stats = dict(_STATS)
    now = time.time()
    last = stats.get("last_capture_at")
    age = (now - last) if last else None
    return {
        "version": RECORDER_HEALTH_VERSION,
        "store": store,
        "durable": bool(store.get("durable")),
        "worker_state": stats["worker_state"],
        "worker_enabled": worker_enabled(),
        "worker_interval_s": WORKER_INTERVAL_S if worker_enabled() else None,
        "last_capture_at": last,
        "last_capture_age_s": age,
        "captures": stats["captures"],
        "gaps": stats["gaps"],
        "errors": stats["errors"],
        "last_error": stats["last_error"],
        "last_error_at": stats["last_error_at"],
        "capture_registered": _CAPTURE is not None,
        "stop_recovery": {
            "stop": "solstice_recorder.stop_worker() — idempotent, safe when not running",
            "recovery": "install a capture callable with register_capture(), set "
                        f"{WORKER_ENV_FLAG}=1, then start_worker(); the worker is "
                        "resumable and its counters survive the restart in-process",
            "note": "no automatic start exists; activation is an explicit operator act",
        },
    }


__all__ = [
    "RECORDER_HEALTH_VERSION",
    "WORKER_ENV_FLAG",
    "WORKER_INTERVAL_S",
    "worker_enabled",
    "mark_worker_state",
    "register_capture",
    "start_worker",
    "stop_worker",
    "recorder_health",
]
