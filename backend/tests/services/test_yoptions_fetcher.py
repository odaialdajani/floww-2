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

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, call, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TESTING", "1")

# Import a private copy with a short-lived fake optional library. Never enable
# or replace the production fetch module or install the retired provider.
_library = ModuleType("yoptions")
_library.get_chain_greeks = Mock(side_effect=AssertionError("Missing local quote fixture"))
_library.get_chain_greeks_date = Mock(side_effect=AssertionError("Missing local dated quote fixture"))
_source = Path(__file__).resolve().parents[2] / "services" / "yoptions_fetcher.py"
_spec = importlib.util.spec_from_file_location("_isolated_yoptions_fetcher_tests", _source)
_fetcher = importlib.util.module_from_spec(_spec)
_library_before = sys.modules.get("yoptions")
_production_before = sys.modules.get("services.yoptions_fetcher")
with patch.dict(sys.modules, {"yoptions": _library}):
    _spec.loader.exec_module(_fetcher)
assert sys.modules.get("yoptions") is _library_before
assert sys.modules.get("services.yoptions_fetcher") is _production_before
DIVIDEND_YIELDS, TICKERS = _fetcher.DIVIDEND_YIELDS, _fetcher.TICKERS
fetch_all_chains, fetch_options_chain = _fetcher.fetch_all_chains, _fetcher.fetch_options_chain


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
    with patch.object(_fetcher, "RAW_CHAINS_DIR", tmp_path):
        yield tmp_path


@pytest.fixture(autouse=True)
def retry_sleep(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(_fetcher._fetch_chain_with_retry.retry, "sleep", sleep)
    return sleep


# ---------- Tests ----------

class TestFetchOptionsChain:
    """Tests for fetch_options_chain function."""

    @patch.object(_fetcher.yo, "get_chain_greeks")
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
        mock_get.assert_called_once_with("SPY", DIVIDEND_YIELDS["SPY"], "c")
        assert result["strike"].tolist() == [500.0, 505.0]

    @patch.object(_fetcher.yo, "get_chain_greeks")
    def test_fetch_both_types(self, mock_get, sample_chain_df, mock_raw_dir):
        """option_type='both' fetches calls and puts."""
        mock_get.side_effect = lambda *args: sample_chain_df.copy(deep=True)
        result = fetch_options_chain("SPY", option_type="both")
        assert result["type"].value_counts().to_dict() == {"call": 2, "put": 2}
        assert mock_get.call_args_list == [call("SPY", DIVIDEND_YIELDS["SPY"], "c"),
                                           call("SPY", DIVIDEND_YIELDS["SPY"], "p")]

    @patch.object(_fetcher, "_fetch_chain_with_retry")
    def test_fetch_returns_empty_on_failure(self, mock_fetch, mock_raw_dir):
        """Returns empty DataFrame when all retries fail."""
        mock_fetch.side_effect = Exception("Connection failed")
        result = fetch_options_chain("SPY")

        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch.object(_fetcher.yo, "get_chain_greeks")
    def test_fetch_saves_raw_json(self, mock_get, sample_chain_df, mock_raw_dir):
        """Raw JSON is saved to disk for debugging."""
        mock_get.return_value = sample_chain_df
        fetch_options_chain("SPY", option_type="c")

        # Check that a JSON file was created
        json_files = list(mock_raw_dir.glob("*.json"))
        assert len(json_files) == 1
        raw = json.loads(json_files[0].read_text())
        assert len(raw["data"]) == 2
        assert raw["data"][0]["Strike"] == 500.0
        assert raw["data"][0]["Type"] == "call"

    @patch.object(_fetcher.yo, "get_chain_greeks")
    def test_greeks_present_in_result(self, mock_get, sample_chain_df, mock_raw_dir):
        """Result contains valid Greek values."""
        mock_get.return_value = sample_chain_df
        result = fetch_options_chain("SPY", option_type="c")

        # Check Greeks are numeric and present
        for greek in ["delta", "gamma", "theta", "vega"]:
            assert greek in result.columns
            assert result[greek].dtype in [float, int, "float64", "int64"]

    @patch.object(_fetcher.yo, "get_chain_greeks")
    def test_all_tickers_configured(self, mock_get, sample_chain_df, mock_raw_dir):
        """All 3 tickers (SPY, QQQ, SPX) are configured."""
        assert "SPY" in TICKERS
        assert "QQQ" in TICKERS
        assert "SPX" in TICKERS

        for ticker in TICKERS:
            assert ticker in DIVIDEND_YIELDS

    @patch.object(_fetcher.yo, "get_chain_greeks")
    def test_handles_yoptions_error_string(self, mock_get, mock_raw_dir):
        """Handles yoptions returning error string instead of DataFrame."""
        mock_get.return_value = "Error. No options for this symbol!"
        result = fetch_options_chain("INVALID")

        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestFetchAllChains:
    """Tests for fetch_all_chains function."""

    @patch.object(_fetcher, "fetch_options_chain")
    def test_fetch_all_combines_results(self, mock_fetch):
        """fetch_all_chains combines results from all tickers."""
        mock_fetch.side_effect = lambda ticker, kind: pd.DataFrame({
            "strike": [500.0], "delta": [0.75], "ticker": [ticker]})
        result = fetch_all_chains()
        assert result["ticker"].tolist() == TICKERS
        assert mock_fetch.call_args_list == [call(t, "both") for t in TICKERS]

    @patch.object(_fetcher, "fetch_options_chain")
    def test_fetch_all_returns_empty_on_total_failure(self, mock_fetch):
        """Returns empty DataFrame when all tickers fail."""
        mock_fetch.return_value = pd.DataFrame()
        result = fetch_all_chains()
        assert result.empty
        assert mock_fetch.call_args_list == [call(t, "both") for t in TICKERS]


class TestRetryLogic:
    """Tests for tenacity retry behavior."""

    @patch.object(_fetcher.yo, "get_chain_greeks")
    def test_retry_on_connection_error(self, mock_get, sample_chain_df, mock_raw_dir, retry_sleep):
        """Retries on ConnectionError and eventually succeeds."""
        mock_get.side_effect = [
            ConnectionError("timeout"),
            ConnectionError("timeout"),
            sample_chain_df,
        ]
        result = fetch_options_chain("SPY", option_type="c")
        assert not result.empty
        assert retry_sleep.call_args_list == [call(1.0), call(2.0)]
        assert mock_get.call_count == 3

    @patch.object(_fetcher.yo, "get_chain_greeks")
    def test_retry_exhaustion_returns_empty(self, mock_get, mock_raw_dir, retry_sleep):
        """After 3 failed retries, returns empty DataFrame (no crash)."""
        mock_get.side_effect = ConnectionError("timeout")
        result = fetch_options_chain("SPY", option_type="c")
        assert isinstance(result, pd.DataFrame)
        assert result.empty
        assert retry_sleep.call_args_list == [call(1.0), call(2.0)]
        assert mock_get.call_count == 3  # 3 retries exhausted
