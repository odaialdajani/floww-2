"""Skew per expiry: |GEX| below vs above spot (GammaGrid convention).

Pure function over live chain contracts — rides the heatmap refresh, no new
spend class, no recording. Skew = larger absolute side / smaller side; a
missing side gives null (never 0/1 fabrications), at-the-money exposure is
tracked apart so it cannot silently pad a side.
"""
from __future__ import annotations

import math
from typing import Any

VERSION = "skew-expiry.v1"


def skew_by_expiry(contracts: list[dict[str, Any]] | None,
                   spot: float) -> dict[str, Any]:
    """Per-expiry {below, above, at, skew, n} keyed by expiry string."""
    from bs_greeks import bs_gamma

    per: dict[str, dict[str, float]] = {}
    try:
        spot_f = float(spot)
    except (TypeError, ValueError):
        spot_f = 0.0
    if not math.isfinite(spot_f) or spot_f <= 0:
        return {"by_expiry": {}, "version": VERSION,
                "units": "gex_dollars_absolute_sides",
                "note": "invalid spot; no sides computed"}
    for c in contracts or []:
        if not isinstance(c, dict):
            continue
        try:
            oi = float(c.get("oi", 0) or 0)
            strike = float(c.get("strike", 0) or 0)
            iv = float(c.get("iv", 0) or 0)
            T = float(c.get("T", 0) or 0)
        except (TypeError, ValueError):
            continue
        exp = str(c.get("expiry", "") or "")
        if oi <= 0 or strike <= 0 or iv <= 0 or T <= 0 or not exp:
            continue
        gamma = bs_gamma(spot_f, strike, T, iv)
        if not math.isfinite(gamma) or gamma == 0:
            continue
        signed = gamma if str(c.get("type", "")).lower().startswith("c") else -gamma
        dollars = abs(signed * oi * 100.0 * spot_f**2 * 0.01)
        bucket = per.setdefault(exp, {"below": 0.0, "above": 0.0, "at": 0.0, "n": 0})
        if strike < spot_f:
            bucket["below"] += dollars
        elif strike > spot_f:
            bucket["above"] += dollars
        else:
            bucket["at"] += dollars
        bucket["n"] += 1
    by_expiry: dict[str, dict[str, Any]] = {}
    for exp in sorted(per):
        below, above = per[exp]["below"], per[exp]["above"]
        smallest = min(below, above)
        by_expiry[exp] = {**per[exp],
                          "skew": (max(below, above) / smallest
                                   if smallest > 0 else None)}
    return {"by_expiry": by_expiry, "version": VERSION,
            "units": "gex_dollars_absolute_sides",
            "note": "larger |side| / smaller |side| per expiry; null when one side is empty"}
