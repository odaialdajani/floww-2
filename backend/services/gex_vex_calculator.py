"""
VEX (Vomma Exposure) Calculator
================================

Implements vomma exposure computation - dealers' delta sensitivity to
implied volatility changes. This is GEX's "evil twin" - when positive
and large, it makes volatility a feedback mechanism that can destabilize
markets.

Key insights from SqueezeMetrics "Implied Order Book":
- VEX can be negative (unlike GEX which is rarely negative)
- Negative VEX ~ $-400mm per point in 2020 "corona crash"
- VEX is GEX's "evil twin" - amplifies volatility instead of providing liquidity

Paper Reference:
- Barbon & Buraschi (2021) "Gamma Fragility" - discusses VEX interaction
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class VEXState:
    """VEX analysis state"""
    net_vex: float
    positive_vex_strikes: list[float]
    negative_vex_strikes: list[float]
    total_oi: float


def compute_vex_surface(
    spot: float,
    strikes: np.ndarray,
    vommas: np.ndarray,
    ois: np.ndarray,
    types: np.ndarray,
) -> np.ndarray:
    """
    Compute VEX (Vomma Exposure) surface.

    VEX_per_unit = vomma * OI * 100 * spot^2 * 0.01
    Same scaling as GEX but with vomma instead of gamma.

    NOTE: this is the GEX-parity display scale, NOT the per-unit-σ scale
    documented in ``bs_greeks`` (vomma * OI * 100). The two differ by
    exactly spot^2 * 0.01, pinned by
    ``backend/tests/services/test_vex_scale_parity.py``. Do not mix them.

    Sign convention: same as GEX (calls +, puts -)

    Args:
        spot: Current underlying price
        strikes: Strike prices (1D array)
        vommas: Vomma values (1D array, same shape as strikes)
        ois: Open interest (1D array, same shape as strikes)
        types: Option types (0=call, 1=put, 1D array)

    Returns:
        1D array of VEX per strike
    """
    n = len(strikes)
    vex_per_strike = np.zeros(n, dtype=np.float64)

    spot_sq_scale = spot * spot * 0.01 * 100.0

    for i in range(n):
        sign = 1.0 if types[i] == 0 else -1.0
        vex_per_strike[i] = sign * vommas[i] * ois[i] * spot_sq_scale

    return vex_per_strike


def compute_gex_plus(
    net_gex: float,
    net_vex: float,
) -> dict[str, Any]:
    """
    Compute GEX+ - the combined liquidity measure from GEX and VEX.

    GEX+ = GEX + VEX

    This gives the "implied order book" - total option-originated liquidity.

    Interpretation:
    - GEX+ > 0: Dealers providing liquidity (stabilizing)
    - GEX+ < 0: Dealers taking liquidity (destabilizing)
    - Large negative VEX: Will cause volatility feedback loops

    Args:
        net_gex: Net dollar GEX
        net_vex: Net dollar VEX

    Returns:
        GEX+ analysis
    """
    gex_plus = net_gex + net_vex

    # Classification
    if gex_plus > 5e9:  # $5B
        regime = "strong_liquidity"
        interpretation = (
            "DEX+ is strongly positive — dealers are providing substantial liquidity. "
            "Market is well-supplied with dealer hedging. Favorability for: "
            "selling premium, short volatility."
        )
    elif gex_plus > 1e9:  # $1B
        regime = "positive_liquidity"
        interpretation = (
            "GEX+ positive — dealers providing liquidity. "
            "Slight mean-reversion bias in market structure."
        )
    elif gex_plus > -1e8:  # -$100M
        regime = "neutral_liquidity"
        interpretation = (
            "GEX+ near zero — liquidity from options is balanced. "
            "Other factors dominate price action."
        )
    elif gex_plus > -5e8:  # -$500M
        regime = "negative_liquidity"
        interpretation = (
            "GEX+ significantly negative — dealers taking liquidity via hedging. "
            "Expect elevated volatility. Momentum bias."
        )
    else:
        regime = "extreme_negative_liquidity"
        interpretation = (
            "DEX+ severely negative — extreme liquidity drain. "
            "VEX likely driving this. High flash crash risk. "
            "Avoid short volatility positions."
        )

    return {
        "gex_plus": gex_plus,
        "net_gex": net_gex,
        "net_vex": net_vex,
        "regime": regime,
        "interpretation": interpretation,
        "gex_ratio": net_gex / (abs(net_vex) + 1e-10) if net_vex != 0 else float('inf'),
    }


def vex_classification(
    net_vex: float,
    spot: float,
) -> dict[str, Any]:
    """
    Classify VEX state and its implications.

    Per SqueezeMetrics:
    - Negative VEX ~ $-400mm in 2020 "corona crash"
    - VEX becomes positive when dealers are short IV (selling options cheaply)

    Args:
        net_vex: Net dollar VEX
        spot: Underlying price

    Returns:
        VEX state classification
    """
    if net_vex > 1e9:
        vex_state = "strong_positive"
        risk_level = "low"
        interpretation = (
            "VEX strongly positive — dealers short implied volatility. "
            "They are selling options cheaply, providing stabilization. "
            "But when VIX rises, VEX will force them to buy (destabilizing)."
        )
    elif net_vex > 0:
        vex_state = "moderate_positive"
        risk_level = "low"
        interpretation = (
            "VEX positive — dealers short IV. "
            "Stabilizing force, but watch for VIX spike feedback."
        )
    elif net_vex > -5e8:
        vex_state = "negative_warning"
        risk_level = "moderate"
        interpretation = (
            "VEX negative and material — dealers have long implied volatility. "
            "When IVs rise (as they do in turmoil), VEX forces dealers to sell "
            "the underlying, compounding the decline. Risk of volatility feedback loop."
        )
    elif net_vex > -1e9:
        vex_state = "strongly_negative"
        risk_level = "high"
        interpretation = (
            "VEX strongly negative — dealers have substantial long IV exposure. "
            "High likelihood of volatility-driven liquidity drain. "
            "Similar pattern to 2020 'corona crash' regime."
        )
    else:
        vex_state = "extreme_negative"
        risk_level = "extreme"
        interpretation = (
            "VEX extreme negative — potential volatility cascade. "
            "Dealers forced to sell further during IV spikes. "
            "Flash crash risk very high. Consider long vol positioning."
        )

    # IV-VEX feedback loop detection
    iv_vex_risk = "LOW"
    if net_vex < 0:
        iv_vex_risk = "ACTIVE"
        # Check if this could amplify IV moves
        if abs(net_vex) > 5e8:
            iv_vex_risk = "STRONG"

    return {
        "vex_state": vex_state,
        "net_vex": net_vex,
        "risk_level": risk_level,
        "interpretation": interpretation,
        "iv_vex_feedback": iv_vex_risk,
    }


def full_liquidity_analysis(
    net_gex: float,
    net_vex: float,
    spot: float,
    adv_shares: float | None = None,
) -> dict[str, Any]:
    """
    Complete liquidity analysis combining GEX, VEX, and Gamma Imbalance.

    This provides the full "implied order book" picture from both
    the practitioner (SqueezeMetrics) and academic (Barbon-Buraschi)
    perspectives.
    """
    # GEX+ analysis
    gex_plus_result = compute_gex_plus(net_gex, net_vex)

    # VEX state
    vex_result = vex_classification(net_vex, spot)

    # Gamma Imbalance if ADV provided
    gib_result = None
    if adv_shares and adv_shares > 0:
        # Recompute using GEX module
        from services.gex_paper_accurate import compute_gamma_imbalance
        gib_result = compute_gamma_imbalance(net_gex, spot, adv_shares)

    return {
        "gex_plus": gex_plus_result,
        "vex_analysis": vex_result,
        "gamma_imbalance": gib_result,
        "combined_liquidity_score": (
            gex_plus_result["gex_plus"] +
            gex_plus_result["net_vex"]
        ) / 1e9 if (gex_plus_result["gex_plus"] != 0 or gex_plus_result["net_vex"] != 0) else 0.0,
    }
