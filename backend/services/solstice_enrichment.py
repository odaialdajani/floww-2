"""
backend/services/solstice_enrichment.py — attached-research enrichment (T08).

Capability-aware: moneyness buckets, OI-change ranking (effective-date gated),
relative volume vs matched DTE/moneyness cohort baselines, multi-horizon
context. Never infers opening/closing, buyer direction, sweeps, or premium
VWAP from snapshots.
"""

from __future__ import annotations

import math
from typing import Any


def moneyness_buckets(contracts: list[dict], spot: float) -> dict[str, Any]:
    """Call/put × delta-band concentration + activity distribution (no speculation labels)."""
    buckets: dict[str, dict[str, float]] = {}
    for c in contracts or []:
        try:
            d = abs(float(c.get("delta"))) if c.get("delta") is not None else None
            oi = float(c.get("oi", 0) or 0)
            vol = float(c.get("volume", 0) or 0)
        except (TypeError, ValueError):
            continue
        if d is None or not math.isfinite(d):
            band = "delta_unknown"
        elif d < 0.2:
            band = "far_otm"
        elif d < 0.4:
            band = "otm"
        elif d <= 0.6:
            band = "atm"
        elif d <= 0.8:
            band = "itm"
        else:
            band = "deep_itm"
        side = "call" if str(c.get("type", "")).lower().startswith("c") else "put"
        key = f"{side}_{band}"
        b = buckets.setdefault(key, {"oi": 0.0, "volume": 0.0, "n": 0})
        b["oi"] += oi if math.isfinite(oi) and oi > 0 else 0.0
        b["volume"] += vol if math.isfinite(vol) and vol > 0 else 0.0
        b["n"] += 1
    return {"buckets": buckets, "note": "distribution only; OTM activity is not directional speculation evidence"}


def oi_changes(current: list[dict], previous: list[dict]) -> dict[str, Any]:
    """Effective-date OI comparisons; ranked changes. Net change classifies nothing."""
    def key(c):
        return (str(c.get("expiry")), str(c.get("strike")), str(c.get("type")).lower())
    prev = {key(c): c for c in (previous or []) if isinstance(c, dict)}
    rows = []
    for c in current or []:
        if not isinstance(c, dict):
            continue
        p = prev.get(key(c), {})
        try:
            co = float(c.get("oi", 0) or 0)
            po = float(p.get("oi", 0) or 0)
        except (TypeError, ValueError):
            continue
        eff = c.get("oi_effective_date") or p.get("oi_effective_date")
        if eff is None:
            continue  # no fabrication of effective date from request date
        rows.append({"key": key(c), "oi": co, "prev_oi": po, "delta": co - po,
                     "oi_effective_date": eff})
    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return {"changes": rows[:20], "n_compared": len(rows),
            "note": "net OI change does not classify opening/closing or buyer direction"}


def relative_volume(contracts: list[dict], baselines: dict[str, float]) -> dict[str, Any]:
    """Relative activity vs matched DTE/moneyness cohort baselines.

    baselines: {(expiry, band): median_volume} with cohort sizes. 0DTE series
    without 10 prior sessions use smaller cohorts + report baseline size.
    """
    rows = []
    for c in contracts or []:
        band = str(c.get("band", "atm"))
        key = f"{c.get('expiry')}|{band}"
        base = baselines.get(key)
        try:
            v = float(c.get("volume", 0) or 0)
        except (TypeError, ValueError):
            continue
        if base is None or base <= 0:
            rows.append({"osi": c.get("osi"), "rvol": None, "reason": "NO_BASELINE"})
        else:
            rows.append({"osi": c.get("osi"), "rvol": round(v / base, 2), "baseline": base})
    rows.sort(key=lambda r: (r.get("rvol") or -1), reverse=True)
    return {"relative": rows[:20], "note": "matched cohorts; baseline size reported by caller"}
