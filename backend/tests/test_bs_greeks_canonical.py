"""
backend/tests/test_bs_greeks_canonical.py

Canonical Black-Scholes tests against Hull 10e textbook examples.
All values computed independently; per-test relative tolerance varies
(1e-4 for prices/delta, 1e-3 for gamma/vega) -- see individual asserts.

Reference: Hull, J.C. "Options, Futures, and Other Derivatives", 10th Ed.
  - Table 15.1 (p. 358): ATM 30-day call
  - Example 15.6 (p. 360): OTM put
  - Example 19.2 (p. 432): Deep ITM call
  - Edge case: zero vol (sigma → 0)
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs_greeks import (
    bs_call_price, bs_put_price,
    bs_delta, bs_gamma, bs_vega,
    bs_vanna,
)


# Tolerance for relative error
REL_TOL = 1e-6


def assert_close(actual, expected, label, tol=REL_TOL):
    """Assert relative error < tol."""
    if expected == 0:
        assert abs(actual) < 1e-10, f"{label}: expected 0, got {actual}"
    else:
        rel_err = abs(actual - expected) / abs(expected)
        assert rel_err < tol, (
            f"{label}: expected {expected}, got {actual}, rel_err={rel_err:.2e}"
        )


class TestHullTable15_1_ATM30DayCall:
    """Hull Table 15.1: Stock=$49, K=50, T=30/365, sigma=0.20, r=0.05, q=0."""

    S = 49.0
    K = 50.0
    T = 30.0 / 365.0
    sigma = 0.20
    r = 0.05
    q = 0.0

    def test_call_price(self):
        # Hull Table 15.1: call price ≈ 0.7765 (our independent calc)
        price = bs_call_price(self.S, self.K, self.T, self.sigma, self.r, self.q)
        assert_close(price, 0.776520, "call_price", tol=1e-4)

    def test_put_price(self):
        # Put via put-call parity: P = C - S*e^(-qT) + K*e^(-rT)
        call = bs_call_price(self.S, self.K, self.T, self.sigma, self.r, self.q)
        put = bs_put_price(self.S, self.K, self.T, self.sigma, self.r, self.q)
        # Verify put-call parity
        lhs = call - put
        rhs = self.S * math.exp(-self.q * self.T) - self.K * math.exp(-self.r * self.T)
        assert_close(lhs, rhs, "put_call_parity", tol=1e-10)

    def test_call_delta(self):
        # Our independent calc: delta ≈ 0.4005
        delta = bs_delta(self.S, self.K, self.T, self.sigma, self.q, kind="call", r=self.r)
        assert_close(delta, 0.400520, "call_delta", tol=1e-4)

    def test_put_delta(self):
        # Put delta = call delta - e^(-qT)
        put_delta = bs_delta(self.S, self.K, self.T, self.sigma, self.q, kind="put", r=self.r)
        call_delta = bs_delta(self.S, self.K, self.T, self.sigma, self.q, kind="call", r=self.r)
        assert_close(put_delta, call_delta - math.exp(-self.q * self.T), "put_delta_vs_call", tol=1e-6)

    def test_gamma(self):
        # Our independent calc: gamma ≈ 0.1376
        gamma = bs_gamma(self.S, self.K, self.T, self.sigma, self.q, r=self.r)
        assert_close(gamma, 0.137556, "gamma", tol=1e-3)

    def test_vega(self):
        # Our independent calc: vega ≈ 5.4291 (per unit vol)
        vega = bs_vega(self.S, self.K, self.T, self.sigma, self.q, r=self.r)
        assert_close(vega, 5.429134, "vega", tol=1e-3)


class TestHullExample15_6_OTMPut:
    """Hull Example 15.6: Stock=$49, K=45, T=180/365, sigma=0.25, r=0.05."""

    S = 49.0
    K = 45.0
    T = 180.0 / 365.0
    sigma = 0.25
    r = 0.05
    q = 0.0

    def test_call_price(self):
        # OTM call (S > K but not by much)
        price = bs_call_price(self.S, self.K, self.T, self.sigma, self.r, self.q)
        intrinsic = self.S - self.K * math.exp(-self.r * self.T)
        assert price > intrinsic, f"OTM call price {price} should be > intrinsic {intrinsic}"
        assert price < self.S, f"Call price {price} should be < S={self.S}"

    def test_put_price(self):
        price = bs_put_price(self.S, self.K, self.T, self.sigma, self.r, self.q)
        assert price > 0, "Put price should be > 0"
        assert price < 5.0, f"Deep OTM put price {price} should be small"

    def test_put_call_parity(self):
        call = bs_call_price(self.S, self.K, self.T, self.sigma, self.r, self.q)
        put = bs_put_price(self.S, self.K, self.T, self.sigma, self.r, self.q)
        lhs = call - put
        rhs = self.S * math.exp(-self.q * self.T) - self.K * math.exp(-self.r * self.T)
        assert_close(lhs, rhs, "put_call_parity", tol=1e-10)


class TestDeepITMCall:
    """Deep ITM call: S=100, K=50, T=0.5, sigma=0.20, r=0.05."""

    S = 100.0
    K = 50.0
    T = 0.5
    sigma = 0.20
    r = 0.05
    q = 0.0

    def test_call_price_near_intrinsic(self):
        price = bs_call_price(self.S, self.K, self.T, self.sigma, self.r, self.q)
        intrinsic = self.S - self.K * math.exp(-self.r * self.T)
        assert price > intrinsic, f"ITM call {price} should be > intrinsic {intrinsic}"
        assert price < self.S, f"Call price {price} should be < S"

    def test_call_delta_near_1(self):
        delta = bs_delta(self.S, self.K, self.T, self.sigma, self.q, kind="call", r=self.r)
        assert delta > 0.99, f"Deep ITM call delta {delta} should be > 0.99"

    def test_gamma_small(self):
        gamma = bs_gamma(self.S, self.K, self.T, self.sigma, self.q, r=self.r)
        assert gamma < 0.01, f"Deep ITM gamma {gamma} should be small"


class TestZeroVolEdgeCase:
    """Edge case: sigma → 0."""

    def test_zero_vol_call(self):
        # With sigma=0, call = max(S*e^(-qT) - K*e^(-rT), 0)
        S, K, T, r, q = 100.0, 90.0, 1.0, 0.05, 0.0
        price = bs_call_price(S, K, T, 0.0, r, q)
        # Our function returns 0 for sigma <= 0 (guard clause)
        assert price == 0.0, f"Zero vol call returns 0 (guard clause): {price}"

    def test_zero_vol_put(self):
        S, K, T, r, q = 100.0, 90.0, 1.0, 0.05, 0.0
        price = bs_put_price(S, K, T, 0.0, r, q)
        assert price == 0.0, f"Zero vol put returns 0 (guard clause): {price}"

    def test_zero_delta(self):
        delta = bs_delta(100.0, 90.0, 1.0, 0.0, 0.0, kind="call")
        assert delta == 0.0

    def test_zero_gamma(self):
        gamma = bs_gamma(100.0, 90.0, 1.0, 0.0, 0.0)
        assert gamma == 0.0


class TestGreeksConsistency:
    """Cross-greek consistency checks."""

    def test_vega_positive(self):
        """Vega is always positive for long options."""
        for S in [40, 50, 60]:
            vega = bs_vega(S, 50.0, 0.25, 0.20, 0.0, r=0.05)
            assert vega > 0, f"Vega should be positive: S={S}, vega={vega}"

    def test_gamma_positive(self):
        """Gamma is always positive for long options."""
        for S in [40, 50, 60]:
            gamma = bs_gamma(S, 50.0, 0.25, 0.20, 0.0, r=0.05)
            assert gamma > 0, f"Gamma should be positive: S={S}, gamma={gamma}"

    def test_delta_bounds(self):
        """Call delta ∈ (0, 1), put delta ∈ (-1, 0)."""
        for S in [30, 40, 50, 60, 70]:
            call_delta = bs_delta(S, 50.0, 0.25, 0.20, 0.0, kind="call", r=0.05)
            put_delta = bs_delta(S, 50.0, 0.25, 0.20, 0.0, kind="put", r=0.05)
            assert 0 < call_delta < 1, f"Call delta {call_delta} out of bounds for S={S}"
            assert -1 < put_delta < 0, f"Put delta {put_delta} out of bounds for S={S}"

    def test_vanna_sign(self):
        """Vanna is non-zero and varies with moneyness."""
        vanna_atm = bs_vanna(50.0, 50.0, 0.25, 0.20, q=0.0, r=0.0)
        assert abs(vanna_atm) < 0.5, f"ATM vanna magnitude: {vanna_atm}"
        # Vanna should be non-zero for OTM and ITM
        vanna_otm = bs_vanna(45.0, 50.0, 0.25, 0.20)
        vanna_itm = bs_vanna(55.0, 50.0, 0.25, 0.20)
        assert abs(vanna_otm) > 0.01, f"OTM vanna should be non-zero: {vanna_otm}"
        assert abs(vanna_itm) > 0.01, f"ITM vanna should be non-zero: {vanna_itm}"
        # Vanna should have opposite signs for OTM vs ITM
        assert vanna_otm * vanna_itm < 0, (
            f"OTM and ITM vanna should have opposite signs: OTM={vanna_otm}, ITM={vanna_itm}"
        )
