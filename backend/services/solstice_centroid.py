"""
backend/services/solstice_centroid.py — experimental exposure centroid (P12).

Optional original Floww implementation over the declared complete scope:
  centroid = sum(strike * gross_OI_GEX) / sum(gross_OI_GEX)
Gross mass (not net) so call/put cancellation never erases structure. Null on
zero/unknown support. Upper/lower centroids split at the centroid, not at
spot. No continuous line across missing samples. Experimental: not a target,
not VWAP, no production confidence without held-out evidence.
"""

from __future__ import annotations

import math
from typing import Any

VERSION = "centroid.v1"


def _gross(r: dict[str, Any]) -> float | None:
    try:
        g = abs(float(r.get("call_gex", 0) or 0)) + abs(float(r.get("put_gex", 0) or 0))
        if g > 0:
            return g
        g2 = abs(float(r.get("gex", 0) or 0))
        return g2 if g2 > 0 else None
    except (TypeError, ValueError):
        return None


def exposure_centroid(strike_rows: list[dict[str, Any]], scope: str = "") -> dict[str, Any]:
    """Gross-weighted exposure centroid (experimental)."""
    pts: list[tuple[float, float]] = []
    for r in strike_rows or []:
        try:
            s = float(r.get("strike"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(s) or s <= 0:
            continue
        g = _gross(r)
        if g is None or not math.isfinite(g) or g <= 0:
            continue
        pts.append((s, g))
    if not pts:
        return {"status": "experimental", "centroid": None, "scope": scope,
                "formula": "sum(strike*gross)/sum(gross)", "version": VERSION,
                "reason": "ZERO_OR_UNKNOWN_SUPPORT"}
    tot = sum(g for _, g in pts)
    c = sum(s * g for s, g in pts) / tot
    lower = [(s, g) for s, g in pts if s <= c]
    upper = [(s, g) for s, g in pts if s > c]
    def _c(sub: list[tuple[float, float]]) -> float | None:
        t = sum(g for _, g in sub)
        return sum(s * g for s, g in sub) / t if t > 0 else None
    return {"status": "experimental", "centroid": c,
            "lower_centroid": _c(lower), "upper_centroid": _c(upper),
            "scope": scope, "formula": "sum(strike*gross)/sum(gross)",
            "version": VERSION, "n": len(pts),
            "note": "gross-weighted landmark, not a target or VWAP"}
