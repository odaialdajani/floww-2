"""B09 known-ratio derived levels: explicit clocks, no lookahead in live."""
from __future__ import annotations


def derive_ratio(source: dict, target: dict):
    """Return ratio with known-at + units, or unavailable reason.

    Stale/unknown denominator => unavailable. Historical ratio only during
    practice (replay flag); live historical ratio refused.
    """
    if not isinstance(source, dict) or not isinstance(target, dict):
        return {"status": "unavailable", "reason": "missing source"}
    num, den = source.get("price"), target.get("price")
    if not (isinstance(num, (int, float)) and isinstance(den, (int, float))):
        return {"status": "unavailable", "reason": "unknown denominator"}
    if den == 0:
        return {"status": "unavailable", "reason": "stale denominator"}
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
