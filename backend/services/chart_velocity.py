"""Node velocity: per-strike d(GEX)/dt between adjacent recorded snapshots.

Pure function over recorded rows only — no provider reads, no spend. Only
strikes with a finite GEX on BOTH sides are comparable observations; added
or removed strikes keep unknown rates (None), never zero-filled. Growth
magnitude is undefined after a zero baseline (None), matching the
node-tracker discipline that deltas exist only between comparable points.
"""
from __future__ import annotations

import math
from typing import Any

VERSION = "node-velocity.v1"


def _gex(row: Any) -> float | None:
    if not isinstance(row, dict):
        return None
    value = row.get("gex", row.get("signed_value", row.get("strength")))
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _strike(row: Any) -> float | None:
    if not isinstance(row, dict):
        return None
    try:
        strike = row.get("strike", row.get("level"))
    except AttributeError:
        return None
    if isinstance(strike, bool):
        return None
    if isinstance(strike, (int, float)) and math.isfinite(strike):
        return float(strike)
    return None


def node_velocity(before: list[dict[str, Any]] | None,
                  after: list[dict[str, Any]] | None,
                  dt_seconds: float) -> list[dict[str, Any]]:
    """Per-strike velocity rows sorted by strike.

    Each row: {strike, before, after, delta, velocity, growth, status} with
    status one of retained/added/removed. Unknown rates are None.
    """
    known_dt = (isinstance(dt_seconds, (int, float))
                and not isinstance(dt_seconds, bool)
                and math.isfinite(dt_seconds) and dt_seconds > 0)
    old: dict[float, float] = {}
    for row in before or []:
        strike, gex = _strike(row), _gex(row)
        if strike is not None and gex is not None:
            old[strike] = gex
    new: dict[float, float] = {}
    for row in after or []:
        strike, gex = _strike(row), _gex(row)
        if strike is not None and gex is not None:
            new[strike] = gex
    out: list[dict[str, Any]] = []
    for strike in sorted(set(old) | set(new)):
        if strike in old and strike in new:
            delta = new[strike] - old[strike]
            out.append({"strike": strike, "before": old[strike],
                        "after": new[strike], "delta": delta,
                        "velocity": delta / dt_seconds if known_dt else None,
                        "growth": (delta / abs(old[strike])
                                   if old[strike] != 0 else None),
                        "status": "retained"})
        elif strike in new:
            out.append({"strike": strike, "before": None, "after": new[strike],
                        "delta": None, "velocity": None, "growth": None,
                        "status": "added"})
        else:
            out.append({"strike": strike, "before": old[strike], "after": None,
                        "delta": None, "velocity": None, "growth": None,
                        "status": "removed"})
    return out
