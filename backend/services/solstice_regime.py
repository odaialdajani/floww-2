"""
backend/services/solstice_regime.py — corrected gamma regime / zero-gamma contract (T15).

G_model(s,t,scope,inventory,iv_policy) is SEPARATE from observed vendor-Greek
exposure. Roots are bracketed over hypothetical spot with retained assumptions;
multiple/no/tangent roots reported. Gamma sign NEVER sets directional
permission alone. Above/below shortcut corrected: orientation can reverse.
"""

from __future__ import annotations

import math
from typing import Any

from bs_greeks import bs_gamma

VERSION = "regime.v1"


def gamma_curve(contracts: list[dict[str, Any]], spots: list[float],
                ticker: str = "", iv_policy: str = "frozen_vendor_iv") -> list[float]:
    """Net modeled GEX at each hypothetical spot (frozen OI + IV policy)."""
    from services.gex_core import DIV_YIELD
    q = DIV_YIELD.get(ticker, 0.0)
    out = []
    for s in spots:
        total = 0.0
        for c in contracts:
            try:
                oi = float(c.get("oi", 0) or 0)
                strike = float(c.get("strike", 0) or 0)
                iv = float(c.get("iv", 0) or 0)
                T = float(c.get("T", 0) or 0)
            except (TypeError, ValueError):
                continue
            if oi <= 0 or strike <= 0 or iv <= 0 or T <= 0 or s <= 0:
                continue
            g = bs_gamma(s, strike, T, iv, q=q)
            if not math.isfinite(g) or g < 0:
                continue
            unit = g * oi * 100.0 * s * s * 0.01
            total += unit if str(c.get("type", "")).lower().startswith("c") else -unit
        out.append(total)
    return out


def find_roots(spots: list[float], values: list[float]) -> list[dict[str, Any]]:
    """Bracket sign-changing roots; classify tangent touches separately."""
    roots = []
    for i in range(1, len(spots)):
        a, b = values[i - 1], values[i]
        if a == 0:
            roots.append({"spot": spots[i - 1], "kind": "touch", "sign_change": False})
        elif a * b < 0:
            denom = (b - a)
            r = spots[i - 1] - a * (spots[i] - spots[i - 1]) / denom if denom else (spots[i - 1] + spots[i]) / 2
            roots.append({"spot": round(r, 4), "kind": "crossing",
                          "from_sign": "positive" if a > 0 else "negative",
                          "to_sign": "positive" if b > 0 else "negative",
                          "sign_change": True})
    return roots


def regime_at_spot(spot: float, contracts: list[dict[str, Any]], ticker: str = "",
                   scope: str = "") -> dict[str, Any]:
    """Evaluate modeled curve at current spot + bracket roots in coverage."""
    strikes = sorted({c.get("strike") for c in contracts if c.get("strike")})
    if not strikes or spot <= 0:
        return {"sign": "UNKNOWN", "roots": [], "version": VERSION,
                "reason": "NO_COVERAGE", "directional_permission": "NONE"}
    lo = max(min(strikes), spot * 0.85)
    hi = min(max(strikes), spot * 1.15)
    n = 100
    spots = [lo + (hi - lo) * i / n for i in range(n + 1)]
    vals = gamma_curve(contracts, spots, ticker)
    at = gamma_curve(contracts, [spot], ticker)[0] if spots else 0.0
    # Vendor residual at spot (model vs supplied gamma) — never spliced silently.
    vendor_total = 0.0
    for c in contracts:
        try:
            g = float(c.get("gamma", 0) or 0)
            oi = float(c.get("oi", 0) or 0)
        except (TypeError, ValueError):
            continue
        if g < 0 or oi <= 0:
            continue
        u = g * oi * 100.0 * spot * spot * 0.01
        vendor_total += u if str(c.get("type", "")).lower().startswith("c") else -u
    return {
        "sign": "POSITIVE" if at > 0 else ("NEGATIVE" if at < 0 else "ZERO"),
        "modeled_at_spot": at,
        "vendor_at_spot": vendor_total,
        "model_vendor_residual": at - vendor_total,
        "roots": find_roots(spots, vals),
        "bounds": [round(lo, 2), round(hi, 2)],
        "version": VERSION, "scope": scope,
        "inventory_basis": "CONVENTIONAL_PROXY",
        # Corrected contract: sign alone never permits direction.
        "directional_permission": "NONE",
        "guidance": "Transition/uncertain near a root; damping/amplification are "
                    "hypotheses under a declared positioning assumption, requiring "
                    "observed price confirmation.",
    }
