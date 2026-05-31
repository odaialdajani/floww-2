"""
backend/tests/services/test_yoptions_fetcher.py

Tests for YOptions Chain Fetcher.
Verifies:
  - Retry logic works (tenacity exponential backoff).
  - Returns empty DataFrame on failure (no crash).
  - Raw JSON saved to disk.
  - Column normalization works.
  - Handles all 3 tickers (SPY, QQQ, SPX).
  - Handles 'c', 'p', and 'both' option types.

6+ tests, all Window B safe (mocked network).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TESTING", "1")

from services.yoptions_fetcher import (
    DIVIDEND_YIELDS,
    HAS_YOPTIONS,
    TICKERS,
    fetch_all_chains,
    fetch_options_chain,
)

pytestmark = pytest.mark.skipif(
    not HAS_YOPTIONS,
    reason="yoptions module not installed — install with: pip install yoptions",
)


# ---------- Fixtures ----------

@pytest.fixture
def sample_chain_df():
    """Sample options chain DataFrame mimicking yoptions output."""
    return pd.DataFrame({
        "Symbol": ["SPY260116C00500000", "SPY260116C00505000"],
        "Strike": [500.0, 505.0],
        "Last Price": [10.5, 8.2],
        "Bid": [10.3, 8.0],
        "Ask": [10.7, 8.4],
        "Impl. Volatility": [0.15, 0.16],
        "Delta": [0.75, 0.65],
        "Gamma": [0.02, 0.018],
        "Theta": [-0.05, -0.04],
        "Vega": [0.12, 0.11],
        "Rho": [0.08, 0.07],
        "Volume": [1000, 800],
        "Open Interest": [5000, 4000],
    })


@pytest.fixture
def mock_raw_dir(tmp_path):
    """Temporarily redirect RAW_CHAINS_DIR to a temp directory."""
    with patch("services.yoptions_fetcher.RAW_CHAINS_DIR", tmp_path):
        yield tmp_path


# ---------- Tests ----------

class TestFetchOptionsChain:
    """Tests for fetch_options_chain function."""

    @patch("services.yoptions_fetcher.yo.get_chain_greeks")
    def test_fetch_calls_returns_normalized_df(self, mock_get, sample_chain_df, mock_raw_dir):
        """fetch_options_chain returns normalized DataFrame with correct columns."""
        mock_get.return_value = sample_chain_df
        result = fetch_options_chain("SPY", option_type="c")

        assert not result.empty
        assert "strike" in result.columns
        assert "delta" in result.columns
        assert "gamma" in result.columns
        assert "theta" in result.columns
        assert "vega" in result.columns
        assert "ticker" in result.columns
        assert result["ticker"].iloc[0] == "SPY"

    @patch("services.yoptions_fetcher.yo.get_chain_greeks")
    def test_fetch_both_types(self, mock_get, sample_chain_df, mock_raw_dir):
        """option_type='both' fetches calls and puts."""
        mock_get.return_value = sample_chain_df
        result = fetch_options_chain("SPY", option_type="both")

        # Should have calls and puts
        mock_get.assert_called()
        assert len(result) > 0

    @patch("services.yoptions_fetcher._fetch_chain_with_retry")
    def test_fetch_returns_empty_on_failure(self, mock_fetch, mock_raw_dir):
        """Returns empty DataFrame when all retries fail."""
        mock_fetch.side_effect = Exception("Connection failed")
        result = fetch_options_chain("SPY")

        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("services.yoptions_fetcher.yo.get_chain_greeks")
    def test_fetch_saves_raw_json(self, mock_get, sample_chain_df, mock_raw_dir):
        """Raw JSON is saved to disk for debugging."""
        mock_get.return_value = sample_chain_df
        fetch_options_chain("SPY", option_type="c")

        # Check that a JSON file was created
        json_files = list(mock_raw_dir.glob("*.json"))
        assert len(json_files) > 0

    @patch("services.yoptions_fetcher.yo.get_chain_greeks")
    def test_greeks_present_in_result(self, mock_get, sample_chain_df, mock_raw_dir):
        """Result contains valid Greek values."""
        mock_get.return_value = sample_chain_df
        result = fetch_options_chain("SPY", option_type="c")

        # Check Greeks are numeric and present
        for greek in ["delta", "gamma", "theta", "vega"]:
            assert greek in result.columns
            assert result[greek].dtype in [float, int, "float64", "int64"]

    @patch("services.yoptions_fetcher.yo.get_chain_greeks")
    def test_all_tickers_configured(self, mock_get, sample_chain_df, mock_raw_dir):
        """All 3 tickers (SPY, QQQ, SPX) are configured."""
        assert "SPY" in TICKERS
        assert "QQQ" in TICKERS
        assert "SPX" in TICKERS

        for ticker in TICKERS:
            assert ticker in DIVIDEND_YIELDS

    @patch("services.yoptions_fetcher.yo.get_chain_greeks")
    def test_handles_yoptions_error_string(self, mock_get, mock_raw_dir):
        """Handles yoptions returning error string instead of DataFrame."""
        mock_get.return_value = "Error. No options for this symbol!"
        result = fetch_options_chain("INVALID")

        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestFetchAllChains:
    """Tests for fetch_all_chains function."""

    @patch("services.yoptions_fetcher.fetch_options_chain")
    def test_fetch_all_combines_results(self, mock_fetch):
        """fetch_all_chains combines results from all tickers."""
        mock_fetch.return_value = pd.DataFrame({
            "strike": [500.0],
            "delta": [0.75],
            "ticker": ["SPY"],
        })
        result = fetch_all_chains()
        assert not result.empty

    @patch("services.yoptions_fetcher.fetch_options_chain")
    def test_fetch_all_returns_empty_on_total_failure(self, mock_fetch):
        """Returns empty DataFrame when all tickers fail."""
        mock_fetch.return_value = pd.DataFrame()
        result = fetch_all_chains()
        assert result.empty


class TestRetryLogic:
    """Tests for tenacity retry behavior."""

    @patch("services.yoptions_fetcher.yo.get_chain_greeks")
    def test_retry_on_connection_error(self, mock_get, sample_chain_df, mock_raw_dir):
        """Retries on ConnectionError and eventually succeeds."""
        mock_get.side_effect = [
            ConnectionError("timeout"),
            ConnectionError("timeout"),
            sample_chain_df,
        ]
        result = fetch_options_chain("SPY", option_type="c")
        assert not result.empty
        assert mock_get.call_count == 3

    @patch("services.yoptions_fetcher.yo.get_chain_greeks")
    def test_retry_exhaustion_returns_empty(self, mock_get, mock_raw_dir):
        """After 3 failed retries, returns empty DataFrame (no crash)."""
        mock_get.side_effect = ConnectionError("timeout")
        result = fetch_options_chain("SPY", option_type="c")
        assert isinstance(result, pd.DataFrame)
        assert result.empty
        assert mock_get.call_count == 3  # 3 retries exhausted
