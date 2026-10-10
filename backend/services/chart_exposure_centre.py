"""G5 exposure centre from RECORDED strike rows (signed net GEX, S2 dollars).

Centre = sum(strike*w)/sum(|w|) with w the signed exposure weight; upper and
lower split the board at the centre (Atlas upper/lower semantics). Only
recorded rows feed it — no vendor recompute, no interpolation, no carry:
empty / zero-mass / unsigned-only / non-finite input yields None.
"""
from __future__ import annotations

import math
from typing import Any

VERSION = "gexvwap.v1"


def _weight(row: dict[str, Any]) -> float | None:
    if not isinstance(row, dict):
        return None
    gex = row.get("gex")
    if isinstance(gex, bool):
        return None
    if isinstance(gex, (int, float)) and math.isfinite(gex):
        return float(gex)
    call_gex, put_gex = row.get("call_gex"), row.get("put_gex")
    if (isinstance(call_gex, bool) or isinstance(put_gex, bool)):
        return None
    if isinstance(call_gex, (int, float)) and isinstance(put_gex, (int, float)):
        if math.isfinite(call_gex) and math.isfinite(put_gex):
            return float(call_gex) + float(put_gex)
    return None


def _strike(row: dict[str, Any]) -> float | None:
    try:
        strike = row.get("strike")
    except AttributeError:
        return None
    if isinstance(strike, bool):
        return None
    if isinstance(strike, (int, float)) and math.isfinite(strike) and strike > 0:
        return float(strike)
    return None


def exposure_centre(strike_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Signed board-weighted centre (+ upper/lower split) or explicit None."""
    pts: list[tuple[float, float]] = []
    for row in strike_rows or []:
        strike, weight = _strike(row), _weight(row)
        if strike is not None and weight is not None:
            pts.append((strike, weight))
    mass = sum(abs(weight) for _, weight in pts)
    if not pts or not math.isfinite(mass) or mass <= 0:
        return {"status": "recorded", "centre": None, "upper": None,
                "lower": None, "version": VERSION, "n": 0}
    centre = sum(strike * weight for strike, weight in pts) / mass
    if not math.isfinite(centre):
        return {"status": "recorded", "centre": None, "upper": None,
                "lower": None, "version": VERSION, "n": len(pts)}

    def _side(select) -> float | None:
        sub = [(strike, weight) for strike, weight in pts if select(strike)]
        sub_mass = sum(abs(weight) for _, weight in sub)
        if not sub or sub_mass <= 0:
            return None
        value = sum(strike * weight for strike, weight in sub) / sub_mass
        return value if math.isfinite(value) else None

    return {"status": "recorded", "centre": centre,
            "upper": _side(lambda strike: strike > centre),
            "lower": _side(lambda strike: strike <= centre),
            "version": VERSION, "n": len(pts)}
