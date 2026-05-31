"""
backend/tests/services/test_data_quality.py

Tests for cross-source GEX consistency checking.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.data_quality import DataQualityChecker


class TestDataQualityChecker:
    """Test cross-source GEX consistency checking."""

    @pytest.mark.asyncio
    async def test_identical_chains_ok(self):
        """Identical chains should have 0% error."""
        checker = DataQualityChecker()
        chain = [
            {"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "call"},
            {"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "put"},
        ]
        result = await checker.check_gex_consistency(chain, chain, "SPY")
        assert result["status"] == "OK"
        assert result["rel_err"] == 0.0

    @pytest.mark.asyncio
    async def test_small_difference_warning(self):
        """5-20% difference should trigger WARNING."""
        checker = DataQualityChecker()
        schwab_chain = [
            {"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "call"},
        ]
        yf_chain = [
            {"gamma": 0.01, "oi": 1060, "spot": 500.0, "type": "call"},
        ]
        result = await checker.check_gex_consistency(schwab_chain, yf_chain, "SPY")
        assert result["status"] == "WARNING"
        assert 0.05 <= result["rel_err"] < 0.20

    @pytest.mark.asyncio
    async def test_large_difference_critical(self):
        """>20% difference should trigger CRITICAL."""
        checker = DataQualityChecker()
        schwab_chain = [
            {"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "call"},
        ]
        yf_chain = [
            {"gamma": 0.01, "oi": 1500, "spot": 500.0, "type": "call"},
        ]
        result = await checker.check_gex_consistency(schwab_chain, yf_chain, "SPY")
        assert result["status"] == "CRITICAL"
        assert result["rel_err"] > 0.20

    @pytest.mark.asyncio
    async def test_empty_chains_ok(self):
        """Empty chains should not crash."""
        checker = DataQualityChecker()
        result = await checker.check_gex_consistency([], [], "SPY")
        assert result["status"] == "OK"
        assert result["rel_err"] == 0.0

    @pytest.mark.asyncio
    async def test_yfinance_zero_gex(self):
        """If yfinance GEX is 0, rel_err should be 0 if Schwab is also 0."""
        checker = DataQualityChecker()
        result = await checker.check_gex_consistency([], [], "SPY")
        assert result["rel_err"] == 0.0

    @pytest.mark.asyncio
    async def test_history_tracking(self):
        """Checker should track history."""
        checker = DataQualityChecker()
        chain = [{"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "call"}]
        await checker.check_gex_consistency(chain, chain, "SPY")
        await checker.check_gex_consistency(chain, chain, "QQQ")
        history = checker.get_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_metrics(self):
        """Metrics should summarize history."""
        checker = DataQualityChecker()
        chain = [{"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "call"}]
        await checker.check_gex_consistency(chain, chain, "SPY")
        metrics = checker.get_metrics()
        assert metrics["checks"] == 1
        assert metrics["warnings"] == 0
        assert metrics["criticals"] == 0

    @pytest.mark.asyncio
    async def test_stale_spot_detection(self):
        """A stale spot price in one source should be detected."""
        checker = DataQualityChecker()
        schwab_chain = [
            {"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "call"},
        ]
        yf_chain = [
            {"gamma": 0.01, "oi": 1000, "spot": 480.0, "type": "call"},
        ]
        result = await checker.check_gex_consistency(schwab_chain, yf_chain, "SPY")
        assert result["status"] in ("WARNING", "OK")
        assert result["rel_err"] > 0

    @pytest.mark.asyncio
    async def test_call_put_sign_convention(self):
        """Calls should be positive GEX, puts negative."""
        checker = DataQualityChecker()
        calls_only = [
            {"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "call"},
        ]
        puts_only = [
            {"gamma": 0.01, "oi": 1000, "spot": 500.0, "type": "put"},
        ]
        result_calls = checker._compute_net_gex(calls_only)
        result_puts = checker._compute_net_gex(puts_only)
        assert result_calls > 0
        assert result_puts < 0
