"""backend/domain/second_order_exposure.py — DUO/DVO oracle math (Command Code C1/C2).

Added, versioned registry entries only. This module does not replace or
rescale any existing canonical metric.

DUO (second spot derivative of dollar gamma)
============================================
Underlying quantity:

    D(S) = C * S^2 * gamma(S)

held fixed while differentiating with respect to spot S:

- C = OI * CONTRACT_MULTIPLIER * DOLLAR_MOVE_CONVENTION (fixed)
- S = spot, the derivative variable
- gamma(S) = Black-Scholes gamma at the same K/T/sigma/q/r

First and second derivatives:

    D'(S)  = C * (S^2*gamma' + 2*S*gamma)
    D''(S) = C * (S^2*gamma'' + 4*S*gamma' + 2*gamma)

Units: USD of dollar-GEX curvature per contract, per (1% move)^2.

Display Taylor convention (kept separate from the derivative itself): a
second-order price-move contribution is (1/2) * D''(S) * (move)^2. The
1/2 and the move size belong to the display layer, not to D''(S).

DVO (first vol derivative of dollar vega)
=========================================
Underlying quantity:

    V(sigma) = vega(sigma) * OI * CONTRACT_MULTIPLIER

so that, with fixed OI/multiplier,

    DVO = dV/dsigma = vomma * OI * CONTRACT_MULTIPLIER

Units: USD per unit-sigma, per contract. No spot factor and no 0.01
factor, exactly like the existing vomma/vega dollar convention.

VEX non-equivalence
===================
Canonical VEX remains ``vanna * OI * 100 * spot * 0.01`` with units USD
delta-notional per +1 vol point. It is not interchangeable with DUO,
DVO, or a dollar-GEX spot derivative. Historical factor language from
the private branch is intentionally not repeated here because it cannot
be pinned without that branch's complete original inputs/definition.
"""

from __future__ import annotations

FORMULA_VERSION = "gex.v2"
SECOND_ORDER_MODEL_VERSION = "local-bs-second-order.v1"

REGISTRY = {
    "duo_d2gex_dS2_v1": {
        "formula": "C*(S^2*gamma''+4*S*gamma'+2*gamma)",
        "units": "USD/(1% move)^2",
        "basis": "DUO_D2GEX_DS2",
        "version": FORMULA_VERSION,
        "model": SECOND_ORDER_MODEL_VERSION,
    },
    "dvo_dvega_dsigma_v1": {
        "formula": "vomma*OI*100",
        "units": "USD/unit-sigma",
        "basis": "DVO_DVEGA_DSIGMA",
        "version": FORMULA_VERSION,
        "model": SECOND_ORDER_MODEL_VERSION,
    },
}


def dollar_duo_second_derivative(
    gamma_2: float,
    gamma_1: float,
    gamma: float,
    oi: float,
    spot: float,
    multiplier: float = 100.0,
    move_convention: float = 0.01,
) -> float:
    """Return D''(S) for D(S)=C*S^2*gamma(S), with fixed C."""
    c = oi * multiplier * move_convention
    return c * (gamma_2 * spot * spot + 4.0 * spot * gamma_1 + 2.0 * gamma)


def dollar_dvo_vol_derivative(
    vomma: float,
    oi: float,
    multiplier: float = 100.0,
) -> float:
    """Return dV/dsigma for V=vega*OI*multiplier."""
    return vomma * oi * multiplier


def second_order_move_contribution(second_derivative: float, move: float) -> float:
    """Second-order Taylor contribution: (1/2)*D''*(move)^2."""
    return 0.5 * second_derivative * move * move
