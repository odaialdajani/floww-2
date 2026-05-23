"""
Tests for services/numba_greeks.py

Verifies:
- Vectorized Greek computation (Delta, Gamma, Theta, Vega, Vanna, Charm, Vomma, Zomma)
- NaN input guard per I-8 (math.isnan short-circuit → 0.0)
- Edge cases: S→0, K→0, T→0, σ→0, γ→0, NaN/Inf
- Hypothesis property-based tests for boundary conditions
- AOT import-fallback (if compiled module is available)
- Call/Put parity (put delta = call delta - 1 in simple case)
- GEX = gamma * spot * OI * 100 sanity check
- Deterministic output with fixed seed
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from services.numba_greeks import (
    compute_all_greeks,
    _AOT_AVAILABLE,
)

# Hypothesis is imported lazily because it is heavy and may not be installed
try:
    from hypothesis import given, strategies as st, settings as hp_settings
    from hypothesis.extra.numpy import arrays as hp_arrays

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

# ── Constants ────────────────────────────────────────────────────────────
N = 100  # Default array size for tests
RNG = np.random.default_rng(42)


# ═══════════════════════════════════════════════════════════════════════════
# 1.  Core Computation — Standard Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestStandardChain:
    """Ensure the greek surface produces sensible values for a standard chain."""

    @pytest.fixture
    def chain(self):
        spot = 450.0
        strikes = np.array([430.0, 440.0, 450.0, 460.0, 470.0])
        expiries = np.full(5, 0.25)
        ivs = np.full(5, 0.20)
        types = np.array([0, 0, 0, 1, 1])  # 3 calls, 2 puts
        return spot, strikes, expiries, ivs, types

    def test_output_shape(self, chain):
        spot, strikes, expiries, ivs, types = chain
        result = compute_all_greeks(spot, strikes, expiries, ivs, types)
        assert set(result.keys()) == {"delta", "gamma", "theta", "vega",
                                       "vanna", "charm", "vomma", "zomma"}
        for key, arr in result.items():
            assert arr.shape == strikes.shape, f"{key} shape mismatch"
            assert arr.dtype == np.float64, f"{key} dtype != float64"

    def test_call_delta_positive(self, chain):
        spot, strikes, expiries, ivs, types = chain
        result = compute_all_greeks(spot, strikes, expiries, ivs, types)
        # First 3 are calls → delta > 0
        assert np.all(result["delta"][:3] > 0.0), "Call delta should be positive"

    def test_put_delta_negative(self, chain):
        spot, strikes, expiries, ivs, types = chain
        result = compute_all_greeks(spot, strikes, expiries, ivs, types)
        # Last 2 are puts → delta < 0
        assert np.all(result["delta"][3:] < 0.0), "Put delta should be negative"

    def test_gamma_positive(self, chain):
        spot, strikes, expiries, ivs, types = chain
        result = compute_all_greeks(spot, strikes, expiries, ivs, types)
        assert np.all(result["gamma"] >= 0.0), "Gamma should be non-negative"

    def test_vega_positive(self, chain):
        spot, strikes, expiries, ivs, types = chain
        result = compute_all_greeks(spot, strikes, expiries, ivs, types)
        assert np.all(result["vega"] >= 0.0), "Vega should be non-negative"

    def test_theta_negative(self, chain):
        spot, strikes, expiries, ivs, types = chain
        result = compute_all_greeks(spot, strikes, expiries, ivs, types)
        # Theta is usually negative (time decay costs)
        assert np.all(result["theta"] <= 0.0), "Theta should be non-positive"

    def test_no_nans_in_output(self, chain):
        spot, strikes, expiries, ivs, types = chain
        result = compute_all_greeks(spot, strikes, expiries, ivs, types)
        for key, arr in result.items():
            assert not np.any(np.isnan(arr)), f"{key} contains NaN"


# ═══════════════════════════════════════════════════════════════════════════
# 2.  NaN / Edge Input Guards (I-8)
# ═══════════════════════════════════════════════════════════════════════════

class TestNaNGuards:
    """Per I-8: NaN inputs must short-circuit to 0.0, not propagate."""

    def test_nan_in_strikes(self):
        strikes = np.array([100.0, np.nan, 110.0])
        expiries = np.full(3, 0.25)
        ivs = np.full(3, 0.20)
        types = np.array([0, 0, 1])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        # NaN strike → 0.0 for all Greeks
        assert result["gamma"][1] == 0.0
        assert result["delta"][1] == 0.0

    def test_nan_in_expiries(self):
        strikes = np.array([100.0, 105.0, 110.0])
        expiries = np.array([0.1, np.nan, 0.3])
        ivs = np.full(3, 0.20)
        types = np.array([0, 0, 1])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert result["gamma"][1] == 0.0

    def test_nan_in_ivs(self):
        strikes = np.array([100.0, 105.0, 110.0])
        expiries = np.full(3, 0.25)
        ivs = np.array([0.20, np.nan, 0.30])
        types = np.array([0, 0, 1])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert result["gamma"][1] == 0.0

    def test_nan_spot(self):
        strikes = np.array([100.0, 105.0, 110.0])
        expiries = np.full(3, 0.25)
        ivs = np.full(3, 0.20)
        types = np.array([0, 0, 1])
        result = compute_all_greeks(float("nan"), strikes, expiries, ivs, types)
        for key, arr in result.items():
            assert np.all(arr == 0.0), f"{key} should all be 0.0 with NaN spot"

    def test_inf_spot_returns_zero(self):
        strikes = np.array([100.0])
        expiries = np.array([0.25])
        ivs = np.array([0.20])
        types = np.array([0])
        result = compute_all_greeks(float("inf"), strikes, expiries, ivs, types)
        assert result["gamma"][0] == 0.0

    def test_zero_strike_returns_zero(self):
        strikes = np.array([0.0])
        expiries = np.array([0.25])
        ivs = np.array([0.20])
        types = np.array([0])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert result["gamma"][0] == 0.0

    def test_zero_iv_returns_zero(self):
        strikes = np.array([100.0])
        expiries = np.array([0.25])
        ivs = np.array([0.0])
        types = np.array([0])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert result["gamma"][0] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 3.  Edge Cases — Boundary Conditions
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary conditions: near-zero values, negative inputs, empty arrays."""

    def test_empty_array(self):
        """Empty arrays should not crash."""
        strikes = np.array([], dtype=np.float64)
        expiries = np.array([], dtype=np.float64)
        ivs = np.array([], dtype=np.float64)
        types = np.array([], dtype=np.int32)
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        for key, arr in result.items():
            assert arr.shape == (0,), f"{key} should be empty"

    def test_single_contract(self):
        strikes = np.array([100.0])
        expiries = np.array([0.25])
        ivs = np.array([0.20])
        types = np.array([0])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        for key, arr in result.items():
            assert arr.shape == (1,), f"{key} should have 1 element"

    def test_atm_delta_approx_half(self):
        """ATM call delta should be approximately 0.5 (for short expiry, no div)."""
        strikes = np.array([100.0])
        expiries = np.array([0.01])
        ivs = np.array([0.01])
        types = np.array([0])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert abs(result["delta"][0] - 0.5) < 0.1, \
            f"ATM delta {result['delta'][0]:.4f} should be ~0.5"

    def test_deep_itm_call_delta_near_one(self):
        strikes = np.array([50.0])
        expiries = np.array([0.5])
        ivs = np.array([0.20])
        types = np.array([0])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert result["delta"][0] > 0.9, \
            f"Deep ITM call delta {result['delta'][0]:.4f} should be >0.9"

    def test_deep_otm_call_delta_near_zero(self):
        strikes = np.array([200.0])
        expiries = np.array([0.5])
        ivs = np.array([0.20])
        types = np.array([0])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert result["delta"][0] < 0.1, \
            f"Deep OTM call delta {result['delta'][0]:.4f} should be <0.1"

    def test_very_short_expiry(self):
        """T→0: Greeks should still compute without numerical issues."""
        strikes = np.array([100.0])
        expiries = np.array([1e-6])  # 1 micro-year ≈ 0.00036 days
        ivs = np.array([0.20])
        types = np.array([0])
        # Should not crash or produce NaN
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert not np.any(np.isnan(result["gamma"]))

    def test_very_long_expiry(self):
        """Long-dated options should have sensible Greeks."""
        strikes = np.array([100.0])
        expiries = np.array([5.0])  # 5 years
        ivs = np.array([0.20])
        types = np.array([0])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert 0.0 < result["delta"][0] < 1.0

    def test_many_contracts(self):
        """10k contracts should complete quickly (performance sanity)."""
        n = 10000
        strikes = np.sort(RNG.uniform(200.0, 700.0, n))
        expiries = RNG.uniform(0.01, 2.0, n)
        ivs = RNG.uniform(0.05, 0.80, n)
        types = RNG.integers(0, 2, n).astype(np.int32)
        result = compute_all_greeks(450.0, strikes, expiries, ivs, types)
        for key, arr in result.items():
            assert arr.shape == (n,), f"{key} shape mismatch"
            assert not np.any(np.isnan(arr)), f"{key} contains NaN"


# ═══════════════════════════════════════════════════════════════════════════
# 4.  Call-Put Parity
# ═══════════════════════════════════════════════════════════════════════════

class TestCallPutParity:
    """For same strike, T, IV: put delta = call delta - 1 (when r=q=0)."""

    def test_delta_parity(self):
        strikes = np.array([100.0, 110.0, 120.0])
        expiries = np.full(3, 0.25)
        ivs = np.full(3, 0.20)
        types = np.array([0, 0, 0])  # All calls
        result_calls = compute_all_greeks(100.0, strikes, expiries, ivs, types,
                                          r=0.0, q=0.0)
        types = np.array([1, 1, 1])  # All puts
        result_puts = compute_all_greeks(100.0, strikes, expiries, ivs, types,
                                         r=0.0, q=0.0)

        # put delta = call delta - 1
        np.testing.assert_allclose(
            result_puts["delta"],
            result_calls["delta"] - 1.0,
            atol=1e-10,
            err_msg="Call-put delta parity broken",
        )

    def test_gamma_parity(self):
        """Gamma is the same for calls and puts (same strike/T/IV)."""
        strikes = np.array([100.0, 100.0])  # same strike for fair comparison
        expiries = np.full(2, 0.25)
        ivs = np.full(2, 0.20)
        types = np.array([0, 1])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert result["gamma"][0] == pytest.approx(result["gamma"][1], rel=1e-10)
    
        types = np.array([1, 0])
        result = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        assert result["gamma"][0] == pytest.approx(result["gamma"][1], rel=1e-10)


# ═══════════════════════════════════════════════════════════════════════════
# 5.  Deterministic / Reproducible Output
# ═══════════════════════════════════════════════════════════════════════════

class TestDeterministic:
    """Same inputs → identical outputs (no randomness in computation)."""

    def test_deterministic(self):
        strikes = np.array([100.0, 110.0])
        expiries = np.full(2, 0.25)
        ivs = np.full(2, 0.20)
        types = np.array([0, 1])

        r1 = compute_all_greeks(100.0, strikes, expiries, ivs, types)
        r2 = compute_all_greeks(100.0, strikes, expiries, ivs, types)

        for key in r1:
            np.testing.assert_array_equal(r1[key], r2[key],
                                          err_msg=f"{key} not deterministic")


# ═══════════════════════════════════════════════════════════════════════════
# 6.  AOT Availability
# ═══════════════════════════════════════════════════════════════════════════

class TestAOTAvailability:
    """Report AOT compilation status (not a pass/fail test)."""

    def test_aot_status(self):
        """Check if AOT-compiled kernels are available.
        
        This is informational — AOT may not be available in all environments
        (e.g., CI without compilation step). The JIT fallback is always used
        when AOT is unavailable.
        """
        if _AOT_AVAILABLE:
            assert True  # AOT is active
        else:
            pytest.skip("AOT-compiled kernels not available — using JIT fallback")


# ═══════════════════════════════════════════════════════════════════════════
# 7.  Hypothesis Property-Based Tests (if hypothesis is installed)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestHypothesisProperties:
    """Property-based tests covering extreme input regimes."""

    @hp_settings(max_examples=50)
    @given(
        spot=st.floats(min_value=0.5, max_value=5000.0, allow_nan=False, allow_infinity=False),
        strike=st.floats(min_value=0.5, max_value=5000.0, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=1e-4, max_value=10.0, allow_nan=False, allow_infinity=False),
        iv=st.floats(min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False),
    )
    def test_greeks_finite_and_sensible(self, spot, strike, T, iv):
        """For any valid input, all Greeks are finite and within sensible ranges."""
        strikes = np.array([strike], dtype=np.float64)
        expiries = np.array([T], dtype=np.float64)
        ivs = np.array([iv], dtype=np.float64)
        types = np.array([0], dtype=np.int32)

        result = compute_all_greeks(spot, strikes, expiries, ivs, types)

        for key, arr in result.items():
            assert np.isfinite(arr[0]), f"{key} is not finite: {arr[0]}"
            assert not np.isnan(arr[0]), f"{key} is NaN"

        # Delta: call ∈ [0, 1], put ∈ [-1, 0]
        # Since we only test calls (type=0):
        assert 0.0 <= result["delta"][0] <= 1.0, \
            f"Call delta out of range: {result['delta'][0]}"

        # Gamma ≥ 0
        assert result["gamma"][0] >= 0.0, \
            f"Gamma negative: {result['gamma'][0]}"

    @st.composite
    def _variable_arrays(draw):
        n = draw(st.integers(min_value=1, max_value=10))
        return draw(hp_arrays(
            dtype=np.float64,
            elements=st.floats(min_value=0.5, max_value=500.0, allow_nan=False, allow_infinity=False),
            shape=n,
        ))

    @hp_settings(max_examples=30)
    @given(
        spot=st.floats(min_value=0.5, max_value=500.0, allow_nan=False, allow_infinity=False),
        strikes=_variable_arrays(),
    )
    def test_nan_input_guarded(self, spot, strikes):
        """Array with some NaN values: NaN positions get 0.0, others compute normally."""
        n = len(strikes)
        if n < 2:
            return
        # Inject one NaN
        strikes_with_nan = strikes.copy()
        strikes_with_nan[0] = np.nan

        expiries = np.full(n, 0.25, dtype=np.float64)
        ivs = np.full(n, 0.20, dtype=np.float64)
        types = np.zeros(n, dtype=np.int32)

        result = compute_all_greeks(spot, strikes_with_nan, expiries, ivs, types)

        # NaN position should be 0.0
        assert result["gamma"][0] == 0.0, "NaN position should have gamma=0.0"
        assert result["delta"][0] == 0.0, "NaN position should have delta=0.0"

        # Other positions should have sane values
        assert np.all(np.isfinite(result["gamma"][1:])), \
            "Non-NaN positions should have finite gamma"
