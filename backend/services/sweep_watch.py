"""
backend/services/sweep_watch.py — Agent D (D5 dead-man sweep gauge).

The sweep loop (B-owned) calls `note_sweep()` once per completed sweep;
health reads `sweep_age_s()`. Until B wires the one-line hook, age is
None (unknown) — never a fabricated zero.
"""
from __future__ import annotations

import time

_last_sweep_wall: float | None = None


def note_sweep(ts: float | None = None) -> float:
    """Record a completed sweep. Returns the recorded wall timestamp."""
    global _last_sweep_wall
    _last_sweep_wall = time.time() if ts is None else ts
    try:
        from services.observability import sweep_last_unixtime

        sweep_last_unixtime.set(_last_sweep_wall)
    except Exception:
        pass  # metrics must never break the sweep path
    return _last_sweep_wall


def sweep_age_s(now: float | None = None) -> float | None:
    """Seconds since the last noted sweep; None if never (unknown)."""
    if _last_sweep_wall is None:
        return None
    now = time.time() if now is None else now
    return max(0.0, now - _last_sweep_wall)


def _reset() -> None:
    """Tests only: forget the last sweep."""
    global _last_sweep_wall
    _last_sweep_wall = None
