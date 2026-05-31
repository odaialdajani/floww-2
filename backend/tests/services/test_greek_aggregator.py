"""
Tests for Greek Aggregator with Fallback.

Validates:
  - NaN filling from upstream Greeks.
  - Full aggregation pipeline (GEX, VEX, Vanna/Charm exposure).
  - Simple aggregation (no upstream data).
  - No NaN values in final output.
  - Edge cases (all NaN, empty, single contract).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.greek_aggregator import GreekAggregator

# ==================================================================
# Fixtures
# ==================================================================

@pytest.fixture
def spot():
    return 450.0


@pytest.fixture
def strikes():
    return np.array([440.0, 445.0, 450.0, 455.0, 460.0])


@pytest.fixture
def expiries():
    return np.full(5, 0.25)


@pytest.fixture
def ivs():
    return np.array([0.18, 0.17, 0.16, 0.17, 0.18])


@pytest.fixture
def ois():
    return np.array([1000.0, 1200.0, 1500.0, 800.0, 600.0])


@pytest.fixture
def types():
    return np.array([0, 0, 0, 1, 1])  # calls then puts


@pytest.fixture
def upstream_clean(strikes, ivs):
    """Clean upstream Greeks (no NaN)."""
    from services.numba_greeks import compute_all_greeks
    g = compute_all_greeks(450.0, strikes, np.full(5, 0.25), ivs, np.array([0, 0, 0, 1, 1]))
    return g


@pytest.fixture
def upstream_with_nan(strikes):
    """Upstream Greeks with NaN for vanna and charm."""
    n = len(strikes)
    return {
        "delta": np.array([0.7, 0.6, 0.5, -0.4, -0.3]),
        "gamma": np.full(n, 0.04),
        "theta": np.full(n, -0.02),
        "vega": np.full(n, 0.19),
        "vanna": np.full(n, np.nan),  # all NaN — will be filled
        "charm": np.full(n, np.nan),  # all NaN — will be filled
        "vomma": np.full(n, 0.01),
        "zomma": np.full(n, 0.001),
    }


# ==================================================================
# NaN Filling
# ==================================================================

class TestNanFilling:
    """BS fallback fills NaN values in upstream Greeks."""

    def test_vanna_filled_when_nan(self, spot, strikes, expiries, ivs, ois, types, upstream_with_nan):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_with_nan, strikes, expiries, ivs, ois, types)
        assert not np.any(np.isnan(snap.vanna))

    def test_charm_filled_when_nan(self, spot, strikes, expiries, ivs, ois, types, upstream_with_nan):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_with_nan, strikes, expiries, ivs, ois, types)
        assert not np.any(np.isnan(snap.charm))

    def test_n_filled_counts_replacements(self, spot, strikes, expiries, ivs, ois, types, upstream_with_nan):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_with_nan, strikes, expiries, ivs, ois, types)
        # vanna (5 NaN) + charm (5 NaN) = 10 filled
        assert snap.n_filled == 10

    def test_valid_values_preserved(self, spot, strikes, expiries, ivs, ois, types, upstream_with_nan):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_with_nan, strikes, expiries, ivs, ois, types)
        # Delta was provided (not NaN) — should be preserved
        np.testing.assert_array_almost_equal(
            snap.delta, np.array([0.7, 0.6, 0.5, -0.4, -0.3])
        )

    def test_partial_nan_filled_correctly(self, spot, strikes, expiries, ivs, ois, types):
        """Only some vanna values are NaN."""
        upstream = {
            "delta": np.array([0.7, 0.6, 0.5, -0.4, -0.3]),
            "gamma": np.full(5, 0.04),
            "theta": np.full(5, -0.02),
            "vega": np.full(5, 0.19),
            "vanna": np.array([0.1, np.nan, 0.1, np.nan, 0.1]),
            "charm": np.full(5, np.nan),
            "vomma": np.full(5, 0.01),
            "zomma": np.full(5, 0.001),
        }
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream, strikes, expiries, ivs, ois, types)
        # Non-NaN vanna values preserved
        assert snap.vanna[0] == 0.1
        assert snap.vanna[2] == 0.1
        assert snap.vanna[4] == 0.1
        # NaN vanna values filled
        assert not np.isnan(snap.vanna[1])
        assert not np.isnan(snap.vanna[3])


# ==================================================================
# Full Aggregation Pipeline
# ==================================================================

class TestFullAggregation:
    """End-to-end aggregation with clean upstream data."""

    def test_no_nan_in_output(self, spot, strikes, expiries, ivs, ois, types, upstream_clean):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_clean, strikes, expiries, ivs, ois, types)
        for key in ["delta", "gamma", "theta", "vega", "vanna", "charm", "vomma", "zomma"]:
            assert not np.any(np.isnan(getattr(snap, key))), f"NaN found in {key}"

    def test_gex_1d_populated(self, spot, strikes, expiries, ivs, ois, types, upstream_clean):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_clean, strikes, expiries, ivs, ois, types)
        assert len(snap.gex_1d) > 0

    def test_total_gex_positive(self, spot, strikes, expiries, ivs, ois, types, upstream_clean):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_clean, strikes, expiries, ivs, ois, types)
        assert snap.total_gex > 0

    def test_vanna_exposure_computed(self, spot, strikes, expiries, ivs, ois, types, upstream_clean):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_clean, strikes, expiries, ivs, ois, types)
        assert len(snap.vanna_exposure) == len(strikes)
        assert not np.any(np.isnan(snap.vanna_exposure))

    def test_charm_exposure_computed(self, spot, strikes, expiries, ivs, ois, types, upstream_clean):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_clean, strikes, expiries, ivs, ois, types)
        assert len(snap.charm_exposure) == len(strikes)
        assert not np.any(np.isnan(snap.charm_exposure))

    def test_snapshot_has_strikes_and_expiries(self, spot, strikes, expiries, ivs, ois, types, upstream_clean):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream_clean, strikes, expiries, ivs, ois, types)
        np.testing.assert_array_equal(snap.strikes, strikes)
        np.testing.assert_array_equal(snap.expiries, expiries)


# ==================================================================
# Simple Aggregation (No Upstream)
# ==================================================================

class TestSimpleAggregation:
    """aggregate_simple computes everything from scratch."""

    def test_all_greeks_computed(self, spot, strikes, expiries, ivs, ois, types):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate_simple(strikes, expiries, ivs, ois, types)
        for key in ["delta", "gamma", "theta", "vega", "vanna", "charm"]:
            assert len(getattr(snap, key)) == len(strikes)
            assert not np.any(np.isnan(getattr(snap, key)))

    def test_n_filled_equals_total_contracts(self, spot, strikes, expiries, ivs, ois, types):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate_simple(strikes, expiries, ivs, ois, types)
        # All 8 Greek arrays * 5 contracts = 40 filled
        assert snap.n_filled == 40

    def test_call_delta_positive(self, spot, expiries, ivs):
        agg = GreekAggregator(spot=spot)
        K = np.array([440.0, 445.0])
        T = expiries[:2]
        IV = ivs[:2]
        OI = np.array([1000.0, 1200.0])
        kind = np.array([0, 0])
        snap = agg.aggregate_simple(K, T, IV, OI, kind)
        assert np.all(snap.delta > 0)

    def test_put_delta_negative(self, spot, expiries, ivs):
        agg = GreekAggregator(spot=spot)
        K = np.array([455.0, 460.0])
        T = expiries[:2]
        IV = ivs[:2]
        OI = np.array([800.0, 600.0])
        kind = np.array([1, 1])
        snap = agg.aggregate_simple(K, T, IV, OI, kind)
        assert np.all(snap.delta < 0)


# ==================================================================
# Edge Cases
# ==================================================================

class TestEdgeCases:
    """Edge-case handling."""

    def test_single_contract(self, spot, ivs):
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate_simple(
            np.array([450.0]),
            np.array([0.25]),
            np.array([ivs[2]]),
            np.array([1000.0]),
            np.array([0]),
        )
        assert len(snap.delta) == 1
        assert not np.isnan(snap.delta[0])

    def test_all_nan_upstream_gets_full_fill(self, spot, strikes, expiries, ivs, ois, types):
        n = len(strikes)
        all_nan = {
            "delta": np.full(n, np.nan),
            "gamma": np.full(n, np.nan),
            "theta": np.full(n, np.nan),
            "vega": np.full(n, np.nan),
            "vanna": np.full(n, np.nan),
            "charm": np.full(n, np.nan),
            "vomma": np.full(n, np.nan),
            "zomma": np.full(n, np.nan),
        }
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(all_nan, strikes, expiries, ivs, ois, types)
        for key in ["delta", "gamma", "theta", "vega", "vanna", "charm", "vomma", "zomma"]:
            assert not np.any(np.isnan(getattr(snap, key))), f"NaN in {key}"

    def test_missing_keys_in_upstream_filled(self, spot, strikes, expiries, ivs, ois, types):
        """Upstream dict missing some keys entirely."""
        upstream = {
            "delta": np.array([0.7, 0.6, 0.5, -0.4, -0.3]),
            # gamma, theta, vega, vanna, charm, vomma, zomma all missing
        }
        agg = GreekAggregator(spot=spot)
        snap = agg.aggregate(upstream, strikes, expiries, ivs, ois, types)
        # All missing keys should be filled
        assert not np.any(np.isnan(snap.gamma))
        assert not np.any(np.isnan(snap.vanna))
        assert not np.any(np.isnan(snap.charm))
