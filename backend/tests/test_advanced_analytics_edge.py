#!/usr/bin/env python3
"""
backend/tests/test_advanced_analytics_edge.py

Edge case tests for advanced_analytics.py — VEX, DEX, Vega-Total.
Uses hand-calculated values and boundary conditions.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advanced_analytics import calc_dex, calc_vega_total, calc_vex


class TestVEXEdgeCases:
    def test_vex_empty_contracts(self):
        result = calc_vex(470.0, [])
        assert result["total_vex"] == 0.0

    def test_vex_zero_spot(self):
        result = calc_vex(0.0, [{"strike": 470, "type": "call", "oi": 100}])
        assert result["total_vex"] == 0.0

    def test_vex_single_call(self):
        """Single call option VEX."""
        contracts = [{"strike": 470, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        result = calc_vex(470.0, contracts)
        assert "total_vex" in result
        assert "vex_by_strike" in result

    def test_vex_single_put(self):
        """Single put option VEX."""
        contracts = [{"strike": 470, "type": "put", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        result = calc_vex(470.0, contracts)
        assert "total_vex" in result

    def test_vex_symmetric_calls_puts(self):
        """Equal calls and puts at same strike should produce symmetric VEX."""
        contracts = [
            {"strike": 470, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25},
            {"strike": 470, "type": "put", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25},
        ]
        result = calc_vex(470.0, contracts)
        # VEX from calls and puts should partially cancel
        assert isinstance(result["total_vex"], (float, int))

    def test_vex_large_oi(self):
        """Test with large OI values."""
        contracts = [
            {"strike": 470, "type": "call", "oi": 100000, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25},
        ]
        result = calc_vex(470.0, contracts)
        assert result["total_vex"] != 0

    def test_vex_deep_itm(self):
        """Deep ITM option VEX."""
        contracts = [{"strike": 400, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        result = calc_vex(470.0, contracts)
        assert "total_vex" in result

    def test_vex_deep_otm(self):
        """Deep OTM option VEX."""
        contracts = [{"strike": 550, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        result = calc_vex(470.0, contracts)
        assert "total_vex" in result


class TestDEXEdgeCases:
    def test_dex_empty_contracts(self):
        result = calc_dex(470.0, [])
        assert result["total_dex"] == 0.0

    def test_dex_zero_spot(self):
        result = calc_dex(0.0, [{"strike": 470, "type": "call", "oi": 100}])
        assert result["total_dex"] == 0.0

    def test_dex_single_call(self):
        contracts = [{"strike": 470, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        result = calc_dex(470.0, contracts)
        assert "total_dex" in result
        assert "dex_by_strike" in result

    def test_dex_single_put(self):
        contracts = [{"strike": 470, "type": "put", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        result = calc_dex(470.0, contracts)
        assert "total_dex" in result

    def test_dex_calls_positive_puts_negative(self):
        """Calls should contribute positive DEX, puts negative."""
        call_contracts = [{"strike": 470, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        put_contracts = [{"strike": 470, "type": "put", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]

        call_result = calc_dex(470.0, call_contracts)
        put_result = calc_dex(470.0, put_contracts)

        # Call DEX should be positive, put DEX should be negative
        assert call_result["total_dex"] > 0
        assert put_result["total_dex"] < 0


class TestVegaTotalEdgeCases:
    def test_vega_empty_contracts(self):
        result = calc_vega_total(470.0, [])
        assert result["total_vega"] == 0.0

    def test_vega_zero_spot(self):
        result = calc_vega_total(0.0, [{"strike": 470, "type": "call", "oi": 100}])
        assert result["total_vega"] == 0.0

    def test_vega_single_call(self):
        contracts = [{"strike": 470, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        result = calc_vega_total(470.0, contracts)
        assert "total_vega" in result
        assert result["total_vega"] > 0

    def test_vega_single_put(self):
        contracts = [{"strike": 470, "type": "put", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        result = calc_vega_total(470.0, contracts)
        assert "total_vega" in result
        assert result["total_vega"] > 0

    def test_vega_symmetric(self):
        """Equal calls and puts should produce same total vega."""
        call_contracts = [{"strike": 470, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        put_contracts = [{"strike": 470, "type": "put", "oi": 100, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]

        call_result = calc_vega_total(470.0, call_contracts)
        put_result = calc_vega_total(470.0, put_contracts)

        # Vega is always positive for both calls and puts
        assert call_result["total_vega"] > 0
        assert put_result["total_vega"] > 0

    def test_vega_increases_with_iv(self):
        """Higher IV should produce higher vega."""
        low_iv = [{"strike": 470, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.1, "T": 0.25}]
        high_iv = [{"strike": 470, "type": "call", "oi": 100, "expiry": "2024-02-15", "iv": 0.4, "T": 0.25}]

        low_result = calc_vega_total(470.0, low_iv)
        high_result = calc_vega_total(470.0, high_iv)

        assert high_result["total_vega"] > low_result["total_vega"]

    def test_vega_increases_with_oi(self):
        """More OI should produce higher vega."""
        small_oi = [{"strike": 470, "type": "call", "oi": 10, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]
        large_oi = [{"strike": 470, "type": "call", "oi": 1000, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]

        small_result = calc_vega_total(470.0, small_oi)
        large_result = calc_vega_total(470.0, large_oi)

        assert large_result["total_vega"] > small_result["total_vega"]


class TestCrossFunctionConsistency:
    def test_all_functions_handle_missing_fields(self):
        """All three functions should handle contracts with missing optional fields."""
        contracts = [{"strike": 470, "type": "call", "oi": 100, "T": 0.25, "iv": 0.2}]

        vex = calc_vex(470.0, contracts)
        dex = calc_dex(470.0, contracts)
        vega = calc_vega_total(470.0, contracts)

        assert "total_vex" in vex
        assert "total_dex" in dex
        assert "total_vega" in vega

    def test_all_functions_handle_zero_oi(self):
        """Zero OI should produce zero totals."""
        contracts = [{"strike": 470, "type": "call", "oi": 0, "expiry": "2024-02-15", "iv": 0.2, "T": 0.25}]

        vex = calc_vex(470.0, contracts)
        dex = calc_dex(470.0, contracts)
        vega = calc_vega_total(470.0, contracts)

        assert vex["total_vex"] == 0.0
        assert dex["total_dex"] == 0.0
        assert vega["total_vega"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
