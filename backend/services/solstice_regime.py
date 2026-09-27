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

VERSION = "regime.v2"


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _contract_mult(c: dict[str, Any]) -> float | None:
    if c.get("adjusted") or c.get("nonstandard"):
        return None
    value = _number(c.get("multiplier", 100.0))
    return value if value is not None and value > 0 else None


def _model_row(c):
    if not isinstance(c, dict):
        return None, "INVALID_CONTRACT"
    mult = _contract_mult(c)
    if mult is None:
        return None, "QUARANTINED"
    kind = str(c.get("type", "")).lower()
    if kind not in {"call", "put", "c", "p"}:
        return None, "MISSING_OPTION_TYPE"
    strike, oi = _number(c.get("strike")), _number(c.get("oi"))
    if strike is None or strike <= 0:
        return None, "MISSING_STRIKE"
    if oi is None or oi < 0:
        return None, "MISSING_OPEN_INTEREST"
    iv, remaining = _number(c.get("iv")), _number(c.get("T"))
    # Explicit zero interest has a known zero contribution, without repricing.
    if oi > 0 and (iv is None or iv <= 0):
        return None, "MISSING_VOLATILITY"
    if oi > 0 and (remaining is None or remaining <= 0):
        return None, "MISSING_TIME_TO_EXPIRY"
    return {**c, "type": "call" if kind in {"call", "c"} else "put",
            "strike": strike, "oi": oi, "iv": iv or 0.0, "T": remaining or 0.0,
            "multiplier": mult}, None


def _vendor_value(contracts, spot):
    total, usable = 0.0, 0
    for c in contracts:
        if not isinstance(c, dict):
            continue
        mult = _contract_mult(c)
        oi, gamma = _number(c.get("oi")), _number(c.get("gamma"))
        kind = str(c.get("type", "")).lower()
        if mult is None or oi is None or oi < 0 or kind not in {"call", "put", "c", "p"}:
            continue
        if oi == 0:
            usable += 1
            continue
        if gamma is None or gamma < 0:
            continue
        unit = gamma * oi * mult * spot * spot * .01
        if not math.isfinite(unit):
            continue
        total += unit if kind in {"call", "c"} else -unit
        usable += 1
    complete = bool(contracts) and usable == len(contracts) and math.isfinite(total)
    return (total if complete else None), {"requested": len(contracts), "usable": usable}


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
    """Publish a modeled sign only for a complete, validated input population.

    Missing inputs must not silently remove one side of the option book. Vendor
    gamma is a separate observed comparison and never overrides modeled sign.
    """
    contracts = contracts or []
    usable, reasons = [], {}
    for contract in contracts:
        row, reason = _model_row(contract)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            usable.append(row)
    coverage = {"requested": len(contracts), "usable": len(usable),
                "status": "complete" if usable and not reasons else "partial" if usable else "unavailable",
                "reasons": reasons}
    spot = _number(spot)
    vendor, vendor_coverage = _vendor_value(contracts, spot) if spot is not None and spot > 0 else (None, None)
    result = {
        "sign": "UNKNOWN", "modeled_at_spot": None, "vendor_at_spot": vendor,
        "model_vendor_residual": None, "roots": [], "bounds": None,
        "version": VERSION, "scope": scope, "sign_basis": "frozen_oi_iv_model",
        "inventory_basis": "CONVENTIONAL_PROXY", "directional_permission": "NONE",
        "quarantined": reasons.get("QUARANTINED", 0),
        "model_coverage": coverage, "vendor_coverage": vendor_coverage,
        "reason": "MODEL_INPUTS_INCOMPLETE" if reasons else "NO_COVERAGE",
        "guidance": "Model inputs are incomplete; the market regime and zero-gamma levels are unknown.",
    }
    if spot is None or spot <= 0:
        result["reason"] = "INVALID_SPOT"
        return result
    if reasons or not usable:
        return result
    strikes = sorted({row["strike"] for row in usable})
    lo, hi = max(min(strikes), spot * .85), min(max(strikes), spot * 1.15)
    spots = [lo + (hi - lo) * i / 100 for i in range(101)] if hi > lo else []
    try:
        at = gamma_curve(usable, [spot], ticker)[0]
        values = gamma_curve(usable, spots, ticker)
    except (ArithmeticError, ValueError):
        result["reason"] = "MODEL_CALCULATION_UNAVAILABLE"
        return result
    if not all(math.isfinite(value) for value in [at, *values]):
        result["reason"] = "MODEL_CALCULATION_UNAVAILABLE"
        return result
    flat = at == 0 and all(value == 0 for value in values)
    result.update(
        sign="POSITIVE" if at > 0 else "NEGATIVE" if at < 0 else "ZERO",
        modeled_at_spot=at, model_vendor_residual=at - vendor if vendor is not None else None,
        roots=[] if flat else find_roots(spots, values),
        bounds=[round(lo, 2), round(hi, 2)] if hi > lo else None,
        reason="ZERO_CURVE" if flat else "AT_ZERO" if at == 0 else "MODELED_SIGN",
        guidance="Damping/amplification are hypotheses under a declared positioning assumption, "
                 "requiring observed price confirmation. Sign alone does not grant trade direction.",
    )
    return result
