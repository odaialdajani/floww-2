"""B09 known-ratio derived levels: explicit clocks, no lookahead in live.

Direction convention (decided ONCE, per H3 V31): ratio = source price /
target price, so a mapped price on the target pane is source_level / ratio.
The live route is services/chart_mapped_levels.py
(GET /api/heatseeker/mapped-levels/{target}); this helper is the pure
clock/units gate reused by tests. Mirrors must use the same convention.
"""
from __future__ import annotations

import math


def _numeric_price(value) -> bool:
    """A usable close: never a bool, always a finite int/float (H3 V31)."""
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def derive_ratio(source: dict, target: dict):
    """Return ratio with known-at + units, or unavailable reason.

    Booleans are never numeric closes (bool subclasses int); non-finite
    refuses; a zero denominator is labeled 'zero denominator', never 'stale'
    (H3 V31 defect remediation). Stale/unknown denominator => unavailable.
    Historical ratio only during practice (replay flag); live historical
    ratio refused.
    """
    if not isinstance(source, dict) or not isinstance(target, dict):
        return {"status": "unavailable", "reason": "missing source"}
    num, den = source.get("price"), target.get("price")
    if not _numeric_price(num):
        return {"status": "unavailable", "reason": "non-numeric numerator"}
    if not _numeric_price(den):
        return {"status": "unavailable", "reason": "non-numeric denominator"}
    if den == 0:
        return {"status": "unavailable", "reason": "zero denominator"}
    for side in (source, target):
        if not side.get("known_at") or not side.get("units"):
            return {"status": "unavailable", "reason": "missing clock/units"}
    if source.get("units") != target.get("units") and not source.get("fx"):
        return {"status": "unavailable", "reason": "foreign units"}
    if source.get("historical") and not source.get("replay"):
        return {"status": "unavailable", "reason": "no historical into live"}
    return {"status": "available", "ratio": num / den,
            "known_at": max(str(source["known_at"]), str(target["known_at"])),
            "units": source["units"]}
