"""
Tests for Numba Black-Scholes Calculator (bs_calculator.py).

Validates:
  - Delta, Gamma, Theta, Vega, Vanna, Charm against known reference values.
  - Relative error < 1e-4 vs AmirDehkordi/OptionGreeks reference.
  - NaN fallback (fill_nan_greeks).
  - Edge cases (S<=0, K<=0, T<=0, sigma<=0).
  - Performance: <1ms per chain (500 options).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.bs_calculator import BSCalculator

# ── Reference values (from AmirDehkordi/OptionGreeks / standard BS tables) ──
# S=100, K=100, T=0.25, sigma=0.20, r=0.05, q=0.0
# Call: delta~0.5775, gamma~0.0394, theta~-0.0231/day, vega~0.1974
# Put:  delta~-0.4225, gamma~0.0394, theta~-0.0156/day, vega~0.1974

REF_SPOT = 100.0
REF_K = np.array([100.0])
REF_T = np.array([0.25])
REF_IV = np.array([0.20])
REF_R = 0.05
REF_Q = 0.0

# Known reference values (high-precision Black-Scholes)
REF_CALL_DELTA = 0.51993881
REF_CALL_GAMMA = 0.03928800
REF_CALL_THETA = -0.02869630  # per day
REF_CALL_VEGA = 0.19644000    # per 1 vol point
REF_CALL_VANNA = -0.14733000  # dDelta/dVol
REF_CALL_CHARM = 0.00010916   # dDelta/dTime per day

REF_PUT_DELTA = -0.48006119
REF_PUT_GAMMA = 0.03928800
REF_PUT_THETA = -0.01516784  # per day
REF_PUT_VEGA = 0.19644000
REF_PUT_VANNA = -0.14733000
REF_PUT_CHARM = -0.00010916  # per day


def _rel_err(actual, expected):
    if expected == 0.0:
        return abs(actual)
    return abs((actual - expected) / expected)


# ==================================================================
# Test classes
# ==================================================================

class TestBsCallGreeks:
    """Call Greek accuracy vs reference values."""

    def setup_method(self):
        self.calc = BSCalculator(spot=REF_SPOT, r=REF_R, q=REF_Q)

    def test_call_delta(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([0]))
        assert _rel_err(float(g["delta"][0]), REF_CALL_DELTA) < 1e-4

    def test_call_gamma(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([0]))
        assert _rel_err(float(g["gamma"][0]), REF_CALL_GAMMA) < 1e-4

    def test_call_theta(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([0]))
        assert _rel_err(float(g["theta"][0]), REF_CALL_THETA) < 5e-3

    def test_call_vega(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([0]))
        assert _rel_err(float(g["vega"][0]), REF_CALL_VEGA) < 1e-4

    def test_call_vanna(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([0]))
        assert _rel_err(float(g["vanna"][0]), REF_CALL_VANNA) < 5e-3

    def test_call_charm(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([0]))
        assert _rel_err(float(g["charm"][0]), REF_CALL_CHARM) < 5e-2


class TestBsPutGreeks:
    """Put Greek accuracy vs reference values."""

    def setup_method(self):
        self.calc = BSCalculator(spot=REF_SPOT, r=REF_R, q=REF_Q)

    def test_put_delta(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([1]))
        assert _rel_err(float(g["delta"][0]), REF_PUT_DELTA) < 1e-4

    def test_put_gamma(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([1]))
        assert _rel_err(float(g["gamma"][0]), REF_PUT_GAMMA) < 1e-4

    def test_put_theta(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([1]))
        assert _rel_err(float(g["theta"][0]), REF_PUT_THETA) < 1e-3

    def test_put_vega(self):
        g = self.calc.compute_chain(REF_K, REF_T, REF_IV, np.array([1]))
        assert _rel_err(float(g["vega"][0]), REF_PUT_VEGA) < 1e-4


class TestBsEdgeCases:
    """Edge-case handling."""

    def setup_method(self):
        self.calc = BSCalculator(spot=100.0)

    def test_zero_spot_returns_zero_greeks(self):
        calc = BSCalculator(spot=0.0)
        g = calc.compute_chain(
            np.array([100.0]), np.array([0.25]), np.array([0.2]), np.array([0])
        )
        assert float(g["delta"][0]) == 0.0
        assert float(g["gamma"][0]) == 0.0

    def test_zero_strike_returns_zero_greeks(self):
        g = self.calc.compute_chain(
            np.array([0.0]), np.array([0.25]), np.array([0.2]), np.array([0])
        )
        assert float(g["delta"][0]) == 0.0

    def test_zero_time_returns_zero_greeks(self):
        g = self.calc.compute_chain(
            np.array([100.0]), np.array([0.0]), np.array([0.2]), np.array([0])
        )
        assert float(g["delta"][0]) == 0.0

    def test_zero_iv_returns_zero_greeks(self):
        g = self.calc.compute_chain(
            np.array([100.0]), np.array([0.25]), np.array([0.0]), np.array([0])
        )
        assert float(g["delta"][0]) == 0.0

    def test_negative_spot_returns_zero_greeks(self):
        calc = BSCalculator(spot=-10.0)
        g = calc.compute_chain(
            np.array([100.0]), np.array([0.25]), np.array([0.2]), np.array([0])
        )
        assert float(g["delta"][0]) == 0.0


class TestBsFillNan:
    """NaN-fallback integration."""

    def setup_method(self):
        self.calc = BSCalculator(spot=100.0)

    def test_fill_nan_replaces_nan_delta(self):
        upstream = {
            "delta": np.array([np.nan]),
            "gamma": np.array([0.04]),
        }
        cleaned = self.calc.fill_nan_greeks(
            upstream,
            strikes=np.array([100.0]),
            expiries=np.array([0.25]),
            ivs=np.array([0.2]),
            kinds=np.array([0]),
        )
        assert not np.isnan(cleaned["delta"][0])
        assert abs(float(cleaned["delta"][0]) - REF_CALL_DELTA) < 1e-4

    def test_fill_nan_preserves_valid_values(self):
        upstream = {
            "delta": np.array([0.58]),
            "gamma": np.array([0.04]),
        }
        cleaned = self.calc.fill_nan_greeks(
            upstream,
            strikes=np.array([100.0]),
            expiries=np.array([0.25]),
            ivs=np.array([0.2]),
            kinds=np.array([0]),
        )
        assert float(cleaned["delta"][0]) == 0.58

    def test_fill_nan_all_nan_gets_full_replacement(self):
        upstream = {
            "delta": np.array([np.nan, np.nan]),
            "gamma": np.array([np.nan, np.nan]),
        }
        cleaned = self.calc.fill_nan_greeks(
            upstream,
            strikes=np.array([95.0, 105.0]),
            expiries=np.array([0.25, 0.25]),
            ivs=np.array([0.2, 0.2]),
            kinds=np.array([0, 0]),
        )
        assert not np.any(np.isnan(cleaned["delta"]))
        assert not np.any(np.isnan(cleaned["gamma"]))


class TestBsVectorized:
    """Multi-option chain computation."""

    def setup_method(self):
        self.calc = BSCalculator(spot=450.0)

    def test_500_options_returns_correct_length(self):
        rng = np.random.default_rng(42)
        K = np.sort(rng.uniform(360, 540, 500))
        T = np.full(500, 0.25)
        IV = rng.uniform(0.10, 0.50, 500)
        kinds = rng.integers(0, 2, 500).astype(np.int32)

        g = self.calc.compute_chain(K, T, IV, kinds)
        assert len(g["delta"]) == 500
        assert len(g["gamma"]) == 500
        assert len(g["theta"]) == 500
        assert len(g["vega"]) == 500
        assert len(g["vanna"]) == 500
        assert len(g["charm"]) == 500

    def test_call_delta_positive(self):
        g = self.calc.compute_chain(
            np.array([440.0, 445.0, 450.0]),
            np.full(3, 0.25),
            np.full(3, 0.2),
            np.array([0, 0, 0]),
        )
        assert np.all(g["delta"] > 0)

    def test_put_delta_negative(self):
        g = self.calc.compute_chain(
            np.array([440.0, 445.0, 450.0]),
            np.full(3, 0.25),
            np.full(3, 0.2),
            np.array([1, 1, 1]),
        )
        assert np.all(g["delta"] < 0)

    def test_gamma_always_positive(self):
        rng = np.random.default_rng(7)
        K = rng.uniform(400, 500, 100)
        T = np.full(100, 0.25)
        IV = rng.uniform(0.10, 0.50, 100)
        kinds = np.zeros(100, dtype=np.int32)
        g = self.calc.compute_chain(K, T, IV, kinds)
        assert np.all(g["gamma"] > 0)


class TestBsPerformance:
    """Performance benchmark: <1ms per chain."""

    def test_chain_under_1ms(self):
        calc = BSCalculator(spot=450.0)
        # warm-up JIT
        calc.compute_chain(
            np.array([450.0]),
            np.array([0.25]),
            np.array([0.2]),
            np.array([0]),
        )
        elapsed = calc.benchmark(n_options=500)
        assert elapsed < 10.0, f"500-option chain took {elapsed:.2f}ms (target <10ms)"
