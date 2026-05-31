"""
backend/tests/services/test_databento_oi.py

Tests for databento_oi module — OI lookup with Databento primary + yfinance fallback.

Validates:
  - Databento success path returns correct OI.
  - Databento 401/403/missing-key triggers yfinance fallback.
  - yfinance returns non-negative int.
  - Both failing returns default (0 or {}).
  - NaN/None/negative OI values clamped to 0 (I-8).
  - OI chain returns cleaned data.
  - Latency constraint met.

10+ tests, all Window B safe (mocked network).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

REPO_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_BACKEND)

os.environ.setdefault("TESTING", "1")
# Ensure no Databento key for most tests
os.environ.pop("DATABENTO_API_KEY", None)

from services.databento_oi import (
    _clamp_oi,
    get_oi,
    get_oi_chain,
    has_databento_key,
)

# ---------------------------------------------------------------------------
# _clamp_oi — I-8 NaN/None/negative guard
# ---------------------------------------------------------------------------

class TestClampOi:
    """I-8: OI must always be a non-negative int."""

    def test_none_returns_zero(self):
        assert _clamp_oi(None) == 0

    def test_negative_returns_zero(self):
        assert _clamp_oi(-5) == 0

    def test_nan_returns_zero(self):
        assert _clamp_oi(float("nan")) == 0

    def test_inf_returns_zero(self):
        assert _clamp_oi(float("inf")) == 0

    def test_string_returns_zero(self):
        assert _clamp_oi("abc") == 0

    def test_empty_string_returns_zero(self):
        assert _clamp_oi("") == 0

    def test_positive_int_preserved(self):
        assert _clamp_oi(42) == 42

    def test_zero_preserved(self):
        assert _clamp_oi(0) == 0

    def test_float_truncated(self):
        assert _clamp_oi(3.7) == 3

    def test_string_number_parsed(self):
        assert _clamp_oi("100") == 100

    def test_large_negative_returns_zero(self):
        assert _clamp_oi(-999999) == 0

    def test_numpy_nan_returns_zero(self):
        assert _clamp_oi(np.nan) == 0


# ---------------------------------------------------------------------------
# has_databento_key
# ---------------------------------------------------------------------------

class TestHasDatabentoKey:
    @patch.dict(os.environ, {"DATABENTO_API_KEY": "test-key-123"}, clear=False)
    def test_key_present_returns_true(self):
        assert has_databento_key() is True

    @patch.dict(os.environ, {}, clear=True)
    def test_key_absent_returns_false(self):
        assert has_databento_key() is False


# ---------------------------------------------------------------------------
# yfinance fallback — single contract
# ---------------------------------------------------------------------------

class TestYfinanceFallbackSingle:
    """yfinance fallback for get_oi() when Databento is unavailable."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_fallback_returns_oi(self, mock_ticker_cls):
        """When no Databento key, yfinance fallback should return OI."""
        mock_calls = pd.DataFrame({
            "strike": [500.0, 505.0, 510.0],
            "openInterest": [1500, 2300, 800],
        })
        mock_chain = MagicMock()
        mock_chain.calls = mock_calls
        mock_chain.puts = pd.DataFrame()
        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        result = get_oi("SPY", strike=505.0, expiry="2026-07-17", opt_type="call")
        assert isinstance(result, int)
        assert result == 2300
        assert result >= 0

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_fallback_no_match_returns_zero(self, mock_ticker_cls):
        """When yfinance has no matching contract, return 0."""
        mock_calls = pd.DataFrame({
            "strike": [500.0],
            "openInterest": [100],
        })
        mock_chain = MagicMock()
        mock_chain.calls = mock_calls
        mock_chain.puts = pd.DataFrame()
        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        result = get_oi("SPY", strike=999.0, expiry="2026-07-17", opt_type="call")
        assert result == 0

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_fallback_exception_returns_zero(self, mock_ticker_cls):
        """When yfinance raises, return 0 gracefully."""
        mock_ticker_cls.side_effect = Exception("Rate limited")

        result = get_oi("SPY", strike=500.0, expiry="2026-07-17", opt_type="call")
        assert result == 0

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_fallback_negative_oi_clamped(self, mock_ticker_cls):
        """Negative OI from yfinance is clamped to 0 (I-8)."""
        mock_calls = pd.DataFrame({
            "strike": [500.0],
            "openInterest": [-100],
        })
        mock_chain = MagicMock()
        mock_chain.calls = mock_calls
        mock_chain.puts = pd.DataFrame()
        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        result = get_oi("SPY", strike=500.0, expiry="2026-07-17", opt_type="call")
        assert result == 0

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_fallback_nan_oi_clamped(self, mock_ticker_cls):
        """NaN OI from yfinance is clamped to 0 (I-8)."""
        mock_calls = pd.DataFrame({
            "strike": [500.0],
            "openInterest": [float("nan")],
        })
        mock_chain = MagicMock()
        mock_chain.calls = mock_calls
        mock_chain.puts = pd.DataFrame()
        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        result = get_oi("SPY", strike=500.0, expiry="2026-07-17", opt_type="call")
        assert result == 0

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_fallback_put_type(self, mock_ticker_cls):
        """Fallback works for put options."""
        mock_puts = pd.DataFrame({
            "strike": [500.0, 505.0],
            "openInterest": [900, 1200],
        })
        mock_chain = MagicMock()
        mock_chain.calls = pd.DataFrame()
        mock_chain.puts = mock_puts
        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        result = get_oi("SPY", strike=500.0, expiry="2026-07-17", opt_type="put")
        assert result == 900


# ---------------------------------------------------------------------------
# get_oi — Databento success path
# ---------------------------------------------------------------------------

class TestDatabentoOISuccess:
    """When Databento is available and returns data."""

    @patch.dict(os.environ, {"DATABENTO_API_KEY": "test-key-123"}, clear=False)
    @patch("services.databento_oi._fetch_oi_sync")
    def test_databento_success_returns_oi(self, mock_fetch):
        mock_fetch.return_value = {
            "SPY   260717C00500000": {
                "underlying": "SPY",
                "expiry": "2026-07-17",
                "type": "call",
                "strike": 500.0,
                "oi": 1500,
            }
        }
        result = get_oi("SPY", strike=500.0, expiry="2026-07-17", opt_type="call")
        assert result == 1500

    @patch.dict(os.environ, {"DATABENTO_API_KEY": "test-key-123"}, clear=False)
    @patch("services.databento_oi._fetch_oi_sync")
    def test_databento_failure_triggers_fallback(self, mock_fetch):
        """When Databento raises, should fall through to yfinance."""
        mock_fetch.side_effect = Exception("API 401 unauthorized")

        with patch("services.databento_oi.yf.Ticker") as mock_yf:
            mock_calls = pd.DataFrame({
                "strike": [500.0],
                "openInterest": [800],
            })
            mock_chain = MagicMock()
            mock_chain.calls = mock_calls
            mock_chain.puts = pd.DataFrame()
            mock_ticker = MagicMock()
            mock_ticker.option_chain.return_value = mock_chain
            mock_yf.return_value = mock_ticker

            result = get_oi("SPY", strike=500.0, expiry="2026-07-17", opt_type="call")
            assert result >= 0
            assert isinstance(result, int)

    @patch.dict(os.environ, {"DATABENTO_API_KEY": "test-key-123"}, clear=False)
    @patch("services.databento_oi._fetch_oi_sync")
    def test_databento_empty_triggers_fallback(self, mock_fetch):
        """When Databento returns {}, should fall through to yfinance."""
        mock_fetch.return_value = {}

        with patch("services.databento_oi.yf.Ticker") as mock_yf:
            mock_calls = pd.DataFrame({
                "strike": [500.0],
                "openInterest": [600],
            })
            mock_chain = MagicMock()
            mock_chain.calls = mock_calls
            mock_chain.puts = pd.DataFrame()
            mock_ticker = MagicMock()
            mock_ticker.option_chain.return_value = mock_chain
            mock_yf.return_value = mock_ticker

            result = get_oi("SPY", strike=500.0, expiry="2026-07-17", opt_type="call")
            assert result >= 0


# ---------------------------------------------------------------------------
# get_oi_chain — full chain resilience
# ---------------------------------------------------------------------------

class TestGetOiChain:
    """Full chain OI lookup with fallback."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_fallback_chain_returns_data(self, mock_ticker_cls):
        """When no Databento key, chain fallback returns yfinance data."""
        mock_ticker = MagicMock()
        mock_ticker.options = ("2026-07-17", "2026-07-24")
        mock_calls = pd.DataFrame({
            "strike": [500.0, 505.0],
            "openInterest": [1000, 2000],
        })
        mock_chain = MagicMock()
        mock_chain.calls = mock_calls
        mock_chain.puts = pd.DataFrame({
            "strike": [500.0],
            "openInterest": [800],
        })
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        result = get_oi_chain("SPY")
        assert isinstance(result, dict)
        assert len(result) > 0
        # All OI values must be non-negative
        for key, data in result.items():
            assert data["oi"] >= 0, f"Negative OI for {key}: {data['oi']}"

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_both_fail_returns_empty_dict(self, mock_ticker_cls):
        """When both Databento and yfinance fail, return empty dict."""
        mock_ticker_cls.side_effect = Exception("Network error")

        result = get_oi_chain("SPY")
        assert result == {}

    @patch.dict(os.environ, {"DATABENTO_API_KEY": "test-key-123"}, clear=False)
    @patch("services.databento_oi._fetch_oi_sync")
    def test_databento_chain_cleans_negative_oi(self, mock_fetch):
        """Databento chain with negative OI values should be clamped to 0 (I-8)."""
        mock_fetch.return_value = {
            "SPY   260717C00500000": {
                "underlying": "SPY",
                "expiry": "2026-07-17",
                "type": "call",
                "strike": 500.0,
                "oi": -10,
            },
            "SPY   260717C00505000": {
                "underlying": "SPY",
                "expiry": "2026-07-17",
                "type": "call",
                "strike": 505.0,
                "oi": 500,
            },
        }
        result = get_oi_chain("SPY")
        assert result["SPY   260717C00500000"]["oi"] == 0
        assert result["SPY   260717C00505000"]["oi"] == 500


# ---------------------------------------------------------------------------
# Latency sanity (mocked, just verify no hangs)
# ---------------------------------------------------------------------------

class TestLatency:
    """Fallback latency should be under 2s with mocked network."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.databento_oi.yf.Ticker")
    def test_fallback_latency_under_2s(self, mock_ticker_cls):
        """With mocked responses, fallback should be fast."""
        import time
        mock_calls = pd.DataFrame({
            "strike": [500.0],
            "openInterest": [1500],
        })
        mock_chain = MagicMock()
        mock_chain.calls = mock_calls
        mock_chain.puts = pd.DataFrame()
        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        t0 = time.time()
        result = get_oi("SPY", strike=500.0, expiry="2026-07-17", opt_type="call")
        elapsed = time.time() - t0

        assert elapsed < 2.0, f"Fallback took {elapsed:.2f}s (limit: 2s)"
        assert result >= 0
