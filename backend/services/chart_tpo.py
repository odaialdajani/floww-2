"""TPO maturity: bar-occupancy letters as an EXPLICIT approximation of
time-at-price (one letter per occupied row per bar — bar granularity, not
tick residence). POC ties resolve downward. Single prints are admitted only
from the fifth period on. Daily composites use the last 20 bars.
"""
from __future__ import annotations

import math
from typing import Any

COMPOSITE_BARS = 20
ADMISSION_PERIOD = 4


def _bounds(bar: dict[str, Any]) -> tuple[float, float] | None:
    try:
        low, high = (bar or {}).get("low"), (bar or {}).get("high")
    except AttributeError:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) for v in (low, high)):
        return None
    if high < low:
        return None
    return float(low), float(high)


def tpo_profile(bars: list[dict[str, Any]], rows: int = 30) -> dict[str, Any]:
    """Occupancy letters per row over the bars' own range."""
    bars = list(bars or [])
    if rows < 1 or not bars:
        return {"status": "unavailable", "reason": "no input"}
    bounds = [_bounds(bar) for bar in bars]
    if any(b is None for b in bounds):
        return {"status": "unavailable", "reason": "bad prices"}
    lo = min(low for low, _ in bounds)
    hi = max(high for _, high in bounds)
    if not hi > lo:
        return {"status": "ok", "counts": [len(bars)],
                "poc": {"price": lo, "letters": len(bars)},
                "single_prints": [], "approximation": "bar-occupancy"}
    width = (hi - lo) / rows
    counts = [0] * rows
    first_seen: list[int | None] = [None] * rows
    for period, (low, high) in enumerate(bounds):
        for i in range(rows):
            if min(high, lo + (i + 1) * width) - max(low, lo + i * width) > 0:
                counts[i] += 1
                if first_seen[i] is None:
                    first_seen[i] = period
    peak = min(i for i, c in enumerate(counts) if c == max(counts))
    singles = [{"price": lo + (i + 0.5) * width, "period": first_seen[i]}
               for i in range(rows)
               if counts[i] == 1 and first_seen[i] is not None
               and first_seen[i] >= ADMISSION_PERIOD]
    return {"status": "ok", "counts": counts,
            "poc": {"price": lo + (peak + 0.5) * width, "letters": counts[peak]},
            "single_prints": singles, "approximation": "bar-occupancy"}


def composite(daily_bars: list[dict[str, Any]], n: int = COMPOSITE_BARS) -> dict[str, Any]:
    """Daily composite over the last n bars."""
    bars = list(daily_bars or [])[-n:]
    if not bars:
        return {"status": "unavailable", "reason": "no input"}
    out = tpo_profile(bars)
    out["periods_used"] = len(bars)
    return out
