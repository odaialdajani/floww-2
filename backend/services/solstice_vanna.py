"""
backend/services/solstice_vanna.py — Vanna higher-timeframe + expiry-removal views (T17).

Vanna/Vomma strictly distinguished (F20). Attribution with matched-horizon
data; no dealer-intent labels. Expiry-removal scenario freezes spot/IV and
removes expiring series (does not predict rolls).
"""

from __future__ import annotations

import math
from typing import Any

from bs_greeks import bs_vanna, bs_vomma

VERSION = "vanna.v1"


def vanna_by_expiry(contracts: list[dict], spot: float, ticker: str = "") -> dict[str, Any]:
    """Per-expiry net Vanna (vanna units) + Vomma kept SEPARATE (never mixed)."""
    from services.gex_core import DIV_YIELD
    q = DIV_YIELD.get(ticker, 0.0)
    per: dict[str, dict[str, float]] = {}
    for c in contracts or []:
        try:
            oi = float(c.get("oi", 0) or 0); strike = float(c.get("strike", 0) or 0)
            iv = float(c.get("iv", 0) or 0); T = float(c.get("T", 0) or 0)
        except (TypeError, ValueError):
            continue
        if oi <= 0 or strike <= 0 or iv <= 0 or T <= 0 or spot <= 0:
            continue
        v = bs_vanna(spot, strike, T, iv, q=q)
        vm = bs_vomma(spot, strike, T, iv, q=q)
        if not math.isfinite(v):
            continue
        sgn = 1.0 if str(c.get("type", "")).lower().startswith("c") else -1.0
        exp = str(c.get("expiry", ""))
        b = per.setdefault(exp, {"vanna": 0.0, "vomma": 0.0, "n": 0})
        b["vanna"] += sgn * v * oi * 100.0          # per unit-vol, NOT dollar-GEX scale
        b["vomma"] += sgn * (vm if math.isfinite(vm) else 0.0) * oi * 100.0
        b["n"] += 1
    return {"by_expiry": per, "version": VERSION,
            "units": "vanna_per_unit_vol_separate_from_vomma",
            "note": "Higher-timeframe structure change requires matched-horizon data; no intent labels."}


def expiry_removal_view(contracts: list[dict], spot: float, expiries_to_remove: list[str],
                        ticker: str = "") -> dict[str, Any]:
    """After-expiry view: frozen spot/IV, expiring series removed. Hypotheses only."""
    from domain.exposure_metrics import compute_raw_oi
    keep = [c for c in (contracts or []) if str(c.get("expiry")) not in set(expiries_to_remove)]
    before = compute_raw_oi([c for c in contracts if isinstance(c, dict)], spot)
    after = compute_raw_oi(keep, spot)
    return {
        "removed_expiries": list(expiries_to_remove),
        "gross_before": before.gross, "gross_after": after.gross,
        "expiring_share": (before.gross - after.gross) / before.gross if before.gross > 0 else None,
        "retained": after.gross,
        "assumptions": "frozen spot/IV/remaining positions; no roll prediction",
        "version": VERSION,
    }
