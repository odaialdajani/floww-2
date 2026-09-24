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


def _contract_mult(c: dict[str, Any]) -> float | None:
    """Per-contract multiplier; adjusted/nonstandard contracts are quarantined
    (None) — never silently forced to 100 (R4-16)."""
    if c.get("adjusted") or c.get("nonstandard"):
        return None
    try:
        m = float(c.get("multiplier", 100.0) or 100.0)
    except (TypeError, ValueError):
        return None
    return m if math.isfinite(m) and m > 0 else None


def gamma_curve(contracts: list[dict[str, Any]], spots: list[float],
                ticker: str = "", _quarantined: list | None = None) -> list[float]:
    """Net modeled GEX at each hypothetical spot (frozen OI + IV policy).

    Uses per-contract multipliers via _contract_mult; adjusted/nonstandard
    contracts are quarantined (appended to _quarantined when provided) and
    never silently forced to 100 (R4-16).
    """
    from services.gex_core import DIV_YIELD
    q = DIV_YIELD.get(ticker, 0.0)
    out = []
    for s in spots:
        total = 0.0
        for c in contracts:
            mult = _contract_mult(c)
            if mult is None:
                if _quarantined is not None and c not in _quarantined:
                    _quarantined.append(c)
                continue
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
            unit = g * oi * mult * s * s * 0.01
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
    """Evaluate modeled curve at current spot + bracket roots in coverage.

    R4-16/P03 contract: per-contract multipliers (quarantined adjusted/
    nonstandard never forced to 100); exact-zero observed curve returns
    ZERO/ZERO_CURVE; fully-quarantined population returns UNKNOWN with
    quarantined count. Sign alone never grants directional permission.
    """
    quarantined: list = []
    usable = [c for c in (contracts or []) if isinstance(c, dict)
              and _contract_mult(c) is not None]
    n_quarantined = len([c for c in (contracts or []) if isinstance(c, dict)]) - len(usable)
    # gamma_curve also appends to quarantined for audit parity.
    strikes = sorted({c.get("strike") for c in usable if c.get("strike")})
    if not strikes or spot <= 0:
        reason = "QUARANTINED" if (contracts and not usable) else "NO_COVERAGE"
        return {"sign": "UNKNOWN", "roots": [], "version": VERSION,
                "reason": reason, "quarantined": n_quarantined,
                "directional_permission": "NONE"}
    lo = max(min(strikes), spot * 0.85)
    hi = min(max(strikes), spot * 1.15)
    n = 100
    spots = [lo + (hi - lo) * i / n for i in range(n + 1)]
    vals = gamma_curve(usable, spots, ticker, _quarantined=quarantined)
    # n_quarantined reconciled with gamma_curve's own audit list.
    n_quarantined = max(n_quarantined, len(quarantined))
    at = gamma_curve(usable, [spot], ticker)[0] if spots else 0.0
    # Vendor residual at spot (model vs supplied gamma) — never spliced silently.
    # Uses the same per-contract multiplier; quarantined contracts excluded.
    vendor_total = 0.0
    vendor_has_nonzero = False
    for c in usable:
        try:
            g = float(c.get("gamma", 0) or 0)
            oi = float(c.get("oi", 0) or 0)
        except (TypeError, ValueError):
            continue
        if g < 0 or oi <= 0:
            continue
        if g > 0:
            vendor_has_nonzero = True
        mult = _contract_mult(c) or 100.0
        u = g * oi * mult * spot * spot * 0.01
        vendor_total += u if str(c.get("type", "")).lower().startswith("c") else -u
    # Exact-zero observed curve: no usable vendor exposure (all supplied
    # gamma zero / zero OI) → ZERO/ZERO_CURVE even when the frozen-input
    # model reprices non-zero. Both values reported; residual explains gap.
    if not vendor_has_nonzero and vendor_total == 0.0:
        return {
            "sign": "ZERO", "modeled_at_spot": at,
            "vendor_at_spot": vendor_total,
            "model_vendor_residual": at - vendor_total,
            "roots": find_roots(spots, vals),
            "bounds": [round(lo, 2), round(hi, 2)],
            "version": VERSION, "scope": scope,
            "inventory_basis": "CONVENTIONAL_PROXY",
            "reason": "ZERO_CURVE", "quarantined": n_quarantined,
            "directional_permission": "NONE",
            "guidance": "Transition/uncertain near a root; damping/amplification are "
                        "hypotheses under a declared positioning assumption, requiring "
                        "observed price confirmation.",
        }
    # Fully-flat modeled curve (within eps) is also a zero curve.
    if vals and max(abs(v) for v in vals) < 1e-9 and abs(at) < 1e-9:
        return {
            "sign": "ZERO", "modeled_at_spot": at,
            "vendor_at_spot": vendor_total,
            "model_vendor_residual": at - vendor_total,
            "roots": find_roots(spots, vals),
            "bounds": [round(lo, 2), round(hi, 2)],
            "version": VERSION, "scope": scope,
            "inventory_basis": "CONVENTIONAL_PROXY",
            "reason": "ZERO_CURVE", "quarantined": n_quarantined,
            "directional_permission": "NONE",
            "guidance": "Transition/uncertain near a root; damping/amplification are "
                        "hypotheses under a declared positioning assumption, requiring "
                        "observed price confirmation.",
        }
    return {
        "sign": "POSITIVE" if at > 0 else ("NEGATIVE" if at < 0 else "ZERO"),
        "modeled_at_spot": at,
        "vendor_at_spot": vendor_total,
        "model_vendor_residual": at - vendor_total,
        "roots": find_roots(spots, vals),
        "bounds": [round(lo, 2), round(hi, 2)],
        "version": VERSION, "scope": scope,
        "inventory_basis": "CONVENTIONAL_PROXY",
        "reason": "ZERO_CURVE" if at == 0 else "MODELED_SIGN",
        "quarantined": n_quarantined,
        # Corrected contract: sign alone never permits direction.
        "directional_permission": "NONE",
        "guidance": "Transition/uncertain near a root; damping/amplification are "
                    "hypotheses under a declared positioning assumption, requiring "
                    "observed price confirmation.",
    }
