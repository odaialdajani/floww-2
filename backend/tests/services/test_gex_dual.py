"""
Unit tests for the Dual-GEX + activity-ratio module
(steal-list rank #1).

Covers:
  * Empty input
  * Volume-fallback to OI when 'volume' key is missing (gflows convention)
  * Activity badge bands (quiet / active / live)
  * Sign convention (calls +, puts -)
  * Numerical sanity vs the existing aggregate_gex_1d
"""

import math

import numpy as np
import pytest

from services.gex_aggregator import aggregate_gex_1d
from services.gex_dual import (
    DualGexCalculator,
    _aggregate_volume_weighted,
    activity_badge_from_ratio,
)

SPOT = 580.0
GAMMA = 0.04  # typical ATM 30-day equity gamma


def _make(strike: float, type_: str, oi: int, volume: int = 0) -> dict:
    return {
        "strike": strike,
        "gamma": GAMMA,
        "oi": oi,
        "volume": volume,
        "type": type_,
        "expiry": "2026-08-15",
        "T": 30 / 365.0,
    }


def test_empty_input_returns_quiet():
    out = DualGexCalculator.compute(SPOT, [])
    # F14: unknown stays unknown — empty input is not quiet structure.
    assert out["activity_badge"] == "unknown"
    assert out["activity_ratio"] is None
    assert out["net_gex_volume"] == 0.0
    assert out["net_gex_oi"] == 0.0
    assert out["strikes"] == []
    assert out["gex_oi_1d"] == []
    assert out["gex_volume_1d"] == []


def test_invalid_spot_returns_quiet():
    contracts = [_make(SPOT, "call", 100, 50)]
    out = DualGexCalculator.compute(0.0, contracts)
    assert out["activity_badge"] == "unknown"
    out2 = DualGexCalculator.compute(-5.0, contracts)
    assert out2["activity_badge"] == "unknown"


def test_volume_falls_back_to_oi_when_missing():
    # F13 (corrected): missing volume is NOT OI-substituted. A contract with
    # no volume key is excluded from the volume leg with missing coverage.
    c_no_vol = _make(SPOT, "call", 1000)
    c_no_vol.pop("volume", None)
    out = DualGexCalculator.compute(SPOT, [c_no_vol])
    assert out["volume_coverage"]["usable"] == 0
    assert out["volume_coverage"]["missing"] == 1
    assert out["activity_ratio"] is None
    assert out["activity_badge"] == "unknown"


def test_signs_call_put():
    """Calls contribute +, puts contribute − for both OI and volume series."""
    contracts = [
        _make(SPOT, "call", 1000, 500),
        _make(SPOT, "put", 800, 400),
    ]
    out = DualGexCalculator.compute(SPOT, contracts)
    # Volume weighted: call contributes +, put contributes −.
    gv = np.array(out["gex_volume_1d"])
    gv_atm_call = gv[0]
    # Only one strike in unique strikes (SPOT); put contribution should
    # be the only negative half and call the positive half.
    # net = (call-vol − put-vol) × sign × gamma × volumes[call] vs put.
    # With our side: call contributes +, put contributes -. So net_gex_volume > 0.
    assert out["net_gex_volume"] > 0
    assert math.isclose(gv_atm_call, out["net_gex_volume"], rel_tol=1e-9, abs_tol=1e-6)


def test_activity_badge_band_quiet():
    """When volume is much smaller than OI, ratio < 0.3 → quiet."""
    contracts = [_make(SPOT, "call", 10000, 100)]  # tiny volume vs big OI
    out = DualGexCalculator.compute(SPOT, contracts)
    assert out["activity_ratio"] < 0.3
    assert out["activity_badge"] == "quiet"


def test_activity_badge_band_active():
    contracts = [_make(SPOT, "call", 1000, 700)]  # volume ~70% of OI
    out = DualGexCalculator.compute(SPOT, contracts)
    assert 0.3 <= out["activity_ratio"] <= 1.0
    assert out["activity_badge"] == "active"


def test_activity_badge_band_live():
    contracts = [_make(SPOT, "call", 100, 2000)]  # volume 20× OI
    out = DualGexCalculator.compute(SPOT, contracts)
    assert out["activity_ratio"] > 1.0
    assert out["activity_badge"] == "live"


def test_volume_weighted_matches_formula():
    strikes = np.array([SPOT - 5, SPOT, SPOT + 5])
    types = np.array([1, 0, 0])  # put, call, call
    gammas = np.full(3, GAMMA)
    vols = np.array([400.0, 1000.0, 1500.0])
    expected = _aggregate_volume_weighted(
        SPOT, strikes, gammas, vols, types, strikes
    )
    # Manual check: call signs +, put signs -
    spot_sq = SPOT * SPOT * 0.01 * 100.0  # DOLLAR_MOVE * CONTRACT_MULTIPLIER
    call1 = +1 * GAMMA * 1000.0 * spot_sq  # call
    call2 = +1 * GAMMA * 1500.0 * spot_sq
    put0 = -1 * GAMMA * 400.0 * spot_sq
    # But strike-order matters (we expect [put@−5, call@0, call@+5])
    expected_target = np.array([put0, call1, call2])
    np.testing.assert_allclose(expected, expected_target, rtol=1e-9)


def test_oi_series_matches_existing_aggregator():
    """The OI-series in compute() should be the same values aggregate_gex_1d returns."""
    contracts = [
        _make(SPOT - 5, "call", 100),
        _make(SPOT, "put", 200),
        _make(SPOT + 5, "call", 50),
    ]
    out = DualGexCalculator.compute(SPOT, contracts)
    strikes = np.array([SPOT - 5, SPOT, SPOT + 5])
    types = np.array([0, 1, 0])
    gammas = np.full(3, GAMMA)
    ois = np.array([100.0, 200.0, 50.0])
    expected = aggregate_gex_1d(SPOT, strikes, gammas, ois, types, strikes)
    actual = np.array(out["gex_oi_1d"])
    np.testing.assert_allclose(actual, expected, rtol=1e-9)


def test_activity_badge_helper():
    assert activity_badge_from_ratio(0.1) == "quiet"
    assert activity_badge_from_ratio(0.31) == "active"
    assert activity_badge_from_ratio(1.5) == "live"
    assert activity_badge_from_ratio(0.1, vol_nonzero=False) == "unknown"
    assert activity_badge_from_ratio(None) == "unknown"


def test_zero_oi_volumes_dont_crash():
    out = DualGexCalculator.compute(SPOT, [_make(SPOT, "call", 0, 0)])
    # F14: zero denominator returns unknown, never zero/quiet.
    assert out["activity_ratio"] is None
    assert out["activity_badge"] == "unknown"


@pytest.mark.parametrize("type_,expect_pos", [("call", True), ("put", False)])
def test_call_vs_put_direction(type_, expect_pos):
    out = DualGexCalculator.compute(SPOT, [_make(SPOT, type_, 100, 50)])
    assert (out["net_gex_volume"] > 0) is expect_pos
