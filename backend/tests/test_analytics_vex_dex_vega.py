"""
backend/tests/test_analytics_vex_dex_vega.py

Unit tests for calc_vex, calc_dex, calc_vega_total.
Uses hand-calculated examples and the FlashAlpha sample chain fixture.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from advanced_analytics import calc_dex, calc_vega_total, calc_vex
from bs_greeks import bs_delta, bs_vanna, bs_vega

# ============================================================================
# Test fixtures
# ============================================================================

def make_contracts_from_chain(chain_csv_path):
    """Load contracts from a CSV chain file, adding T and iv fields."""
    import csv
    from datetime import datetime, timezone
    contracts = []
    today = datetime.now(timezone.utc).date()
    with open(chain_csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            strike = float(row["strike"])
            expiry = row["expiry"]
            ctype = row["type"].upper()
            oi = int(row["oi"])
            bid = float(row["bid"])
            ask = float(row["ask"])
            spot = float(row["underlying_price"])

            # Compute T from expiry
            try:
                exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                T = max((exp_date - today).days / 365.0, 0.001)
            except Exception:
                T = 0.25  # default 3 months

            # Estimate IV from mid-price using BS inversion approximation
            # For testing, use a reasonable IV estimate
            mid = (bid + ask) / 2.0
            moneyness = strike / spot
            # Rough IV estimate: higher for OTM, lower for ITM
            iv = 0.20 + 0.05 * abs(moneyness - 1.0)
            iv = max(iv, 0.05)  # floor at 5%

            contracts.append({
                "strike": strike,
                "expiry": expiry,
                "type": ctype,
                "oi": oi,
                "bid": bid,
                "ask": ask,
                "iv": iv,
                "T": T,
            })
    return contracts, spot


@pytest.fixture
def sample_chain():
    """Load the FlashAlpha sample chain."""
    chain_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "github-repos", "cloned", "FlashAlpha-lab_gex-explained",
        "data", "sample_chain.csv"
    )
    if not os.path.exists(chain_path):
        pytest.skip(f"Sample chain not found: {chain_path}")
    return make_contracts_from_chain(chain_path)


@pytest.fixture
def simple_contracts():
    """Hand-crafted contracts for deterministic testing."""
    spot = 590.0
    T = 30.0 / 365.0
    iv = 0.20
    return [
        {"strike": 540, "expiry": "2026-06-01", "type": "C", "oi": 1250, "iv": iv, "T": T},
        {"strike": 550, "expiry": "2026-06-01", "type": "C", "oi": 2100, "iv": iv, "T": T},
        {"strike": 560, "expiry": "2026-06-01", "type": "C", "oi": 3400, "iv": iv, "T": T},
        {"strike": 570, "expiry": "2026-06-01", "type": "C", "oi": 5800, "iv": iv, "T": T},
        {"strike": 580, "expiry": "2026-06-01", "type": "C", "oi": 4200, "iv": iv, "T": T},
        {"strike": 590, "expiry": "2026-06-01", "type": "C", "oi": 3000, "iv": iv, "T": T},
        {"strike": 600, "expiry": "2026-06-01", "type": "P", "oi": 2800, "iv": iv, "T": T},
        {"strike": 610, "expiry": "2026-06-01", "type": "P", "oi": 1900, "iv": iv, "T": T},
        {"strike": 620, "expiry": "2026-06-01", "type": "P", "oi": 1500, "iv": iv, "T": T},
        {"strike": 630, "expiry": "2026-06-01", "type": "P", "oi": 800, "iv": iv, "T": T},
    ], spot


# ============================================================================
# calc_vex tests
# ============================================================================

class TestCalcVex:
    def test_empty_contracts(self):
        result = calc_vex(100.0, [])
        assert result["total_vex"] == 0

    def test_zero_spot(self):
        result = calc_vex(0, [{"strike": 100, "oi": 100, "iv": 0.2, "T": 0.25, "type": "C"}])
        assert result["total_vex"] == 0

    def test_returns_dict_keys(self, simple_contracts):
        contracts, spot = simple_contracts
        result = calc_vex(spot, contracts)
        assert "total_vex" in result
        assert "vex_by_strike" in result
        assert "call_vex" in result
        assert "put_vex" in result
        assert "abs_vex" in result
        assert "spot" in result

    def test_vex_by_strike_populated(self, simple_contracts):
        contracts, spot = simple_contracts
        result = calc_vex(spot, contracts)
        assert len(result["vex_by_strike"]) > 0

    def test_total_equals_sum(self, simple_contracts):
        contracts, spot = simple_contracts
        result = calc_vex(spot, contracts)
        total_from_strikes = sum(result["vex_by_strike"].values())
        assert abs(result["total_vex"] - total_from_strikes) < 1.0

    def test_abs_vex_positive(self, simple_contracts):
        contracts, spot = simple_contracts
        result = calc_vex(spot, contracts)
        assert result["abs_vex"] > 0

    def test_manual_calculation(self):
        """Verify VEX = vanna * OI * spot for a single contract."""
        spot = 100.0
        strike = 100.0
        T = 0.25
        iv = 0.20
        oi = 100

        vanna = bs_vanna(spot, strike, T, iv, q=0.0, r=0.045)
        expected_vex = vanna * oi * spot

        contracts = [{"strike": strike, "expiry": "2026-06-01", "type": "C",
                       "oi": oi, "iv": iv, "T": T}]
        result = calc_vex(spot, contracts)
        assert_close(result["total_vex"], expected_vex, "vex_manual", tol=0.01)

    def test_with_sample_chain(self, sample_chain):
        contracts, spot = sample_chain
        result = calc_vex(spot, contracts)
        assert result["total_vex"] != 0
        assert result["abs_vex"] > 0


# ============================================================================
# calc_dex tests
# ============================================================================

class TestCalcDex:
    def test_empty_contracts(self):
        result = calc_dex(100.0, [])
        assert result["total_dex"] == 0

    def test_returns_dict_keys(self, simple_contracts):
        contracts, spot = simple_contracts
        result = calc_dex(spot, contracts)
        assert "total_dex" in result
        assert "dex_by_strike" in result
        assert "call_dex" in result
        assert "put_dex" in result
        assert "abs_dex" in result

    def test_call_dex_positive(self, simple_contracts):
        """Calls have positive delta → positive DEX contribution."""
        contracts, spot = simple_contracts
        result = calc_dex(spot, contracts)
        assert result["call_dex"] > 0

    def test_put_dex_negative(self, simple_contracts):
        """Puts have negative delta → negative DEX contribution."""
        contracts, spot = simple_contracts
        result = calc_dex(spot, contracts)
        assert result["put_dex"] < 0

    def test_manual_calculation(self):
        """Verify DEX = delta * OI * multiplier * spot for a single contract."""
        spot = 100.0
        strike = 100.0
        T = 0.25
        iv = 0.20
        oi = 100
        multiplier = 100.0

        delta = bs_delta(spot, strike, T, iv, q=0.0, kind="call", r=0.045)
        expected_dex = delta * oi * multiplier * spot

        contracts = [{"strike": strike, "expiry": "2026-06-01", "type": "C",
                       "oi": oi, "iv": iv, "T": T}]
        result = calc_dex(spot, contracts, multiplier=multiplier)
        assert_close(result["total_dex"], expected_dex, "dex_manual")

    def test_multiplier_scales(self, simple_contracts):
        """DEX should scale linearly with multiplier."""
        contracts, spot = simple_contracts
        result_100 = calc_dex(spot, contracts, multiplier=100.0)
        result_1 = calc_dex(spot, contracts, multiplier=1.0)
        ratio = result_100["total_dex"] / result_1["total_dex"] if result_1["total_dex"] != 0 else 0
        assert_close(ratio, 100.0, "multiplier_ratio", tol=0.01)


# ============================================================================
# calc_vega_total tests
# ============================================================================

class TestCalcVegaTotal:
    def test_empty_contracts(self):
        result = calc_vega_total(100.0, [])
        assert result["total_vega"] == 0

    def test_returns_dict_keys(self, simple_contracts):
        contracts, spot = simple_contracts
        result = calc_vega_total(spot, contracts)
        assert "total_vega" in result
        assert "vega_by_strike" in result
        assert "call_vega" in result
        assert "put_vega" in result
        assert "avg_vega_per_contract" in result
        assert "total_contracts" in result

    def test_total_vega_positive(self, simple_contracts):
        """Vega is always positive for long options."""
        contracts, spot = simple_contracts
        result = calc_vega_total(spot, contracts)
        assert result["total_vega"] > 0

    def test_total_contracts(self, simple_contracts):
        contracts, spot = simple_contracts
        result = calc_vega_total(spot, contracts)
        expected_contracts = sum(c["oi"] for c in contracts)
        assert result["total_contracts"] == expected_contracts

    def test_manual_calculation(self):
        """Verify vega = vega * OI for a single contract."""
        spot = 100.0
        strike = 100.0
        T = 0.25
        iv = 0.20
        oi = 100

        vega = bs_vega(spot, strike, T, iv, q=0.0, r=0.045)
        expected_total = vega * oi

        contracts = [{"strike": strike, "expiry": "2026-06-01", "type": "C",
                       "oi": oi, "iv": iv, "T": T}]
        result = calc_vega_total(spot, contracts)
        assert_close(result["total_vega"], expected_total, "vega_manual")

    def test_avg_vega(self, simple_contracts):
        contracts, spot = simple_contracts
        result = calc_vega_total(spot, contracts)
        if result["total_contracts"] > 0:
            expected_avg = result["total_vega"] / result["total_contracts"]
            assert_close(result["avg_vega_per_contract"], expected_avg, "avg_vega", tol=0.01)


# ============================================================================
# Cross-function consistency
# ============================================================================

class TestCrossFunctionConsistency:
    def test_all_functions_handle_same_contracts(self, simple_contracts):
        """All three functions should process the same contract set without error."""
        contracts, spot = simple_contracts
        vex = calc_vex(spot, contracts)
        dex = calc_dex(spot, contracts)
        vega = calc_vega_total(spot, contracts)
        assert vex["total_vex"] != 0
        assert dex["total_dex"] != 0
        assert vega["total_vega"] != 0

    def test_all_functions_handle_missing_fields(self):
        """Contracts with missing T or iv should be skipped gracefully."""
        spot = 100.0
        contracts = [
            {"strike": 100, "type": "C", "oi": 100},  # missing T and iv
            {"strike": 100, "type": "C", "oi": 100, "iv": 0.2, "T": 0.25},  # valid
        ]
        result = calc_vex(spot, contracts)
        # Should process only the valid contract
        assert result["total_vex"] != 0

    def test_all_functions_handle_zero_oi(self):
        """Contracts with zero OI should be skipped."""
        spot = 100.0
        contracts = [
            {"strike": 100, "type": "C", "oi": 0, "iv": 0.2, "T": 0.25},
            {"strike": 100, "type": "C", "oi": 100, "iv": 0.2, "T": 0.25},
        ]
        result = calc_vex(spot, contracts)
        assert result["total_vex"] != 0


def assert_close(actual, expected, label, tol=1e-6):
    if expected == 0:
        assert abs(actual) < 1e-10, f"{label}: expected 0, got {actual}"
    else:
        rel_err = abs(actual - expected) / abs(expected)
        assert rel_err < tol, f"{label}: expected {expected}, got {actual}, rel_err={rel_err:.2e}"


# ============================================================================
# Spec-mandated assertions: two-strike hand-computed + sample-chain shape
# ============================================================================

class TestTwoStrikeHandComputed:
    """Hand-computed two-strike tests for each calculator (spec Step 6.a)."""

    def _setup(self):
        spot = 100.0
        T = 0.25
        iv = 0.20
        r = 0.045
        # Two strikes, one call and one put, with distinct OI
        contracts = [
            {"strike": 95.0, "expiry": "2026-06-01", "type": "C", "oi": 200, "iv": iv, "T": T},
            {"strike": 105.0, "expiry": "2026-06-01", "type": "P", "oi": 150, "iv": iv, "T": T},
        ]
        return spot, T, iv, r, contracts

    def test_vex_two_strike(self):
        spot, T, iv, r, contracts = self._setup()
        v_call = bs_vanna(spot, 95.0, T, iv, q=0.0, r=r) * 200 * spot
        v_put = bs_vanna(spot, 105.0, T, iv, q=0.0, r=r) * 150 * spot
        expected = v_call + v_put
        result = calc_vex(spot, contracts, risk_free_rate=r)
        assert_close(result["total_vex"], expected, "vex_two_strike", tol=0.01)
        assert len(result["vex_by_strike"]) == 2

    def test_dex_two_strike(self):
        spot, T, iv, r, contracts = self._setup()
        d_call = bs_delta(spot, 95.0, T, iv, q=0.0, kind="call", r=r) * 200 * 100 * spot
        d_put = bs_delta(spot, 105.0, T, iv, q=0.0, kind="put", r=r) * 150 * 100 * spot
        expected = d_call + d_put
        result = calc_dex(spot, contracts, multiplier=100.0, risk_free_rate=r)
        assert_close(result["total_dex"], expected, "dex_two_strike", tol=0.01)
        assert len(result["dex_by_strike"]) == 2

    def test_vega_two_strike(self):
        spot, T, iv, r, contracts = self._setup()
        vg_call = bs_vega(spot, 95.0, T, iv, q=0.0, r=r) * 200
        vg_put = bs_vega(spot, 105.0, T, iv, q=0.0, r=r) * 150
        expected = vg_call + vg_put
        result = calc_vega_total(spot, contracts, risk_free_rate=r)
        assert_close(result["total_vega"], expected, "vega_two_strike", tol=0.01)
        assert len(result["vega_by_strike"]) == 2
        # Vega is one-sided (positive for both calls and puts)
        assert result["total_vega"] >= 0


class TestSampleChainShape:
    """FlashAlpha sample-chain shape and finiteness checks (spec Step 6.b)."""

    def _unique_strikes(self, contracts):
        return {c["strike"] for c in contracts}

    def test_vex_sample_chain(self, sample_chain):
        contracts, spot = sample_chain
        result = calc_vex(spot, contracts)
        assert math.isfinite(result["total_vex"])
        assert math.isfinite(result["abs_vex"])
        assert len(result["vex_by_strike"]) == len(self._unique_strikes(contracts))
        for v in result["vex_by_strike"].values():
            assert math.isfinite(v)

    def test_dex_sample_chain(self, sample_chain):
        contracts, spot = sample_chain
        result = calc_dex(spot, contracts)
        assert math.isfinite(result["total_dex"])
        assert math.isfinite(result["abs_dex"])
        assert len(result["dex_by_strike"]) == len(self._unique_strikes(contracts))
        for v in result["dex_by_strike"].values():
            assert math.isfinite(v)

    def test_vega_sample_chain(self, sample_chain):
        contracts, spot = sample_chain
        result = calc_vega_total(spot, contracts)
        assert math.isfinite(result["total_vega"])
        # Vega is one-sided — total must be non-negative
        assert result["total_vega"] >= 0
        assert len(result["vega_by_strike"]) == len(self._unique_strikes(contracts))
        for v in result["vega_by_strike"].values():
            assert math.isfinite(v)
            assert v >= 0  # per-strike vega is also non-negative
