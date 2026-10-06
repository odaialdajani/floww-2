"""Oracle-backed DUO/DVO derivative checks against independent lower-order functions.

These tests do not test an analytic formula against itself. DUO is checked
against a central second difference of the trusted ``bs_gamma``; DVO is
checked against a central first difference of the trusted ``bs_vega``; and
the dollar DUO product rule is checked against a central second difference
of real dollar GEX. Guard clauses preserve invalid/expired inputs as 0.0.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs_greeks import (  # noqa: E402
    CONTRACT_MULTIPLIER,
    DOLLAR_MOVE_CONVENTION,
    bs_gamma,
    bs_vega,
    dollar_gex_per_contract,
)
from domain.second_order_exposure import (  # noqa: E402
    SECOND_ORDER_MODEL_VERSION,
    dollar_duo_second_derivative,
    dollar_dvo_vol_derivative,
    second_order_move_contribution,
)

CASES = [
    (100.0, 100.0, 0.25, 0.30),
    (580.0, 575.0, 0.10, 0.22),
    (95.0, 105.0, 1.50, 0.45),
]


def test_duo_product_rule_matches_dollar_gex_second_difference():
    """Fail first if only duo*OI*100*(S*0.01)^2 is used (missing 4Sg'+2g)."""
    from scipy.stats import norm

    S, K, T, sig, oi = 500.0, 500.0, 0.10, 0.30, 1000.0
    r = 0.05
    h = S * 1e-4

    def gamma_at(s: float) -> float:
        d1 = (math.log(s / K) + (r + 0.5 * sig**2) * T) / (sig * math.sqrt(T))
        return norm.pdf(d1) / (s * sig * math.sqrt(T))

    def gamma_prime_at(s: float) -> float:
        d1 = (math.log(s / K) + (r + 0.5 * sig**2) * T) / (sig * math.sqrt(T))
        g = norm.pdf(d1) / (s * sig * math.sqrt(T))
        return -g / s * (1.0 + d1 / (sig * math.sqrt(T)))

    def duo_at(s: float) -> float:
        d1 = (math.log(s / K) + (r + 0.5 * sig**2) * T) / (sig * math.sqrt(T))
        g = norm.pdf(d1) / (s * sig * math.sqrt(T))
        u = 1.0 + d1 / (sig * math.sqrt(T))
        return g * (u * u + u - 1.0 / (sig * sig * T)) / (s * s)

    def dollar_gex(s: float) -> float:
        return dollar_gex_per_contract(gamma_at(s), oi, s)

    fd = (dollar_gex(S + h) - 2 * dollar_gex(S) + dollar_gex(S - h)) / (h * h)
    got = dollar_duo_second_derivative(
        duo_at(S), gamma_prime_at(S), gamma_at(S), oi, S
    )
    assert got == pytest.approx(fd, rel=1e-4, abs=1e-6)

    # The old naive single-factor form is wrong by ~106x here. Keep this as
    # the regression tripwire: the test must fail on that old behavior.
    naive = duo_at(S) * oi * CONTRACT_MULTIPLIER * (S * DOLLAR_MOVE_CONVENTION) ** 2
    assert naive == pytest.approx(fd / 106.0, rel=0.05)


@pytest.mark.parametrize("S,K,T,sig", CASES)
def test_dvo_matches_vol_derivative_of_vega(S, K, T, sig):
    from scipy.stats import norm

    def vomma_closed() -> float:
        d1 = (math.log(S / K) + (0.05 + 0.5 * sig**2) * T) / (sig * math.sqrt(T))
        d2 = d1 - sig * math.sqrt(T)
        vega = S * norm.pdf(d1) * math.sqrt(T)
        return vega * d1 * d2 / sig

    h = sig * 1e-5
    fd = (bs_vega(S, K, T, sig + h) - bs_vega(S, K, T, sig - h)) / (2 * h)
    assert vomma_closed() == pytest.approx(fd, rel=1e-3, abs=1e-4)
    assert dollar_dvo_vol_derivative(vomma_closed(), 500.0) == pytest.approx(
        vomma_closed() * 500.0 * CONTRACT_MULTIPLIER
    )


@pytest.mark.parametrize("S,K,T,sig", CASES)
def test_gamma_and_vega_oracles_agree_with_canonical_module(S, K, T, sig):
    from scipy.stats import norm

    r = 0.05
    d1 = (math.log(S / K) + (r + 0.5 * sig**2) * T) / (sig * math.sqrt(T))
    assert bs_gamma(S, K, T, sig) == pytest.approx(
        norm.pdf(d1) / (S * sig * math.sqrt(T)), rel=1e-12
    )
    assert bs_vega(S, K, T, sig) == pytest.approx(
        S * norm.pdf(d1) * math.sqrt(T), rel=1e-12
    )


def test_taylor_factor_and_move_size_are_separate():
    assert second_order_move_contribution(-929.0, 5.0) == pytest.approx(
        0.5 * -929.0 * 25.0
    )


def test_registry_rows_carry_versioned_ids_units_and_basis():
    from domain.second_order_exposure import REGISTRY

    assert REGISTRY["duo_d2gex_dS2_v1"]["units"] == "USD/(1% move)^2"
    assert REGISTRY["duo_d2gex_dS2_v1"]["basis"] == "DUO_D2GEX_DS2"
    assert REGISTRY["dvo_dvega_dsigma_v1"]["units"] == "USD/unit-sigma"
    assert REGISTRY["dvo_dvega_dsigma_v1"]["basis"] == "DVO_DVEGA_DSIGMA"
    assert SECOND_ORDER_MODEL_VERSION == "local-bs-second-order.v1"


@pytest.mark.parametrize(
    "bad", [(0, 100, 0.25, 0.3), (100, 0, 0.25, 0.3), (100, 100, 0, 0.3)]
)
def test_invalid_inputs_stay_zero_not_nan(bad):
    S, K, T, sig = bad
    assert bs_gamma(S, K, T, sig) == 0.0
    assert bs_vega(S, K, T, sig) == 0.0
