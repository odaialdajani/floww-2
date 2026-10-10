"""G6 bar-distributed volume profile: EXPLICIT approximation variant.

Built from real bar OHLC + measured volume only. Each bar's volume spreads
pro-rata over the rows its [low, high] range overlaps — this is range
allocation, never exact tape precision (approximation field says so).
POC ties resolve downward; value-area expansion ties go upward; expansion
stops when both adjacent rows are empty, reporting attained fraction.
Missing volume anywhere in the input yields unavailable, never zero-fill.
"""
from __future__ import annotations

import math
from typing import Any


def _bar_volume(bar: dict[str, Any]) -> float | None:
    volume = (bar or {}).get("volume")
    if isinstance(volume, bool):
        return None
    if isinstance(volume, (int, float)) and math.isfinite(volume) and volume >= 0:
        return float(volume)
    return None


def volume_profile(bars: list[dict[str, Any]], rows: int = 200,
                   value_area_pct: float = 0.70) -> dict[str, Any]:
    """Fixed-depth profile over the input bars' own range."""
    bars = list(bars or [])
    if rows < 1 or not bars:
        return {"status": "unavailable", "reason": "no input"}
    lows, highs = [], []
    for bar in bars:
        low, high = (bar or {}).get("low"), (bar or {}).get("high")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) for v in (low, high)):
            return {"status": "unavailable", "reason": "bad prices"}
        if _bar_volume(bar) is None:
            return {"status": "unavailable", "reason": "missing volume"}
        lows.append(float(low))
        highs.append(float(high))
    lo, hi = min(lows), max(highs)
    if hi <= lo:
        total = sum(_bar_volume(bar) for bar in bars)
        return {"status": "ok", "rows": [{"price": lo, "volume": total}],
                "poc": {"price": lo, "volume": total},
                "value_area": {"low": lo, "high": lo, "attained": 1.0},
                "total_volume": total, "approximation": "bar-range"}
    width = (hi - lo) / rows
    vols = [0.0] * rows
    for bar, low, high in zip(bars, lows, highs, strict=True):
        volume = _bar_volume(bar)
        span = high - low
        if span <= 0:
            idx = min(rows - 1, max(0, int((low - lo) / width)))
            vols[idx] += volume
            continue
        for i in range(rows):
            edge_lo, edge_hi = lo + i * width, lo + (i + 1) * width
            overlap = min(high, edge_hi) - max(low, edge_lo)
            if overlap > 0:
                vols[i] += volume * (overlap / span)
    total = sum(vols)
    if total <= 0:
        return {"status": "unavailable", "reason": "zero volume"}
    priced = [{"price": lo + (i + 0.5) * width, "volume": vols[i]} for i in range(rows)]
    peak = min(i for i, v in enumerate(vols) if v == max(vols))
    target = total * value_area_pct
    lo_i = hi_i = peak
    acc = vols[peak]
    while acc < target:
        up = vols[hi_i + 1] if hi_i + 1 < rows else None
        dn = vols[lo_i - 1] if lo_i - 1 >= 0 else None
        if up is None and dn is None:
            break
        if up is None:
            lo_i -= 1
            acc += dn
        elif dn is None or up >= dn:
            hi_i += 1
            acc += up
        else:
            lo_i -= 1
            acc += dn
        if up == 0 and dn == 0:
            break
    return {"status": "ok",
            "rows": [r for r in priced if r["volume"] > 0],
            "poc": {"price": priced[peak]["price"], "volume": vols[peak]},
            "value_area": {"low": lo + lo_i * width, "high": lo + (hi_i + 1) * width,
                           "attained": acc / total},
            "total_volume": total, "approximation": "bar-range"}
