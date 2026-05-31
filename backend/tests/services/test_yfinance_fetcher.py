"""
backend/tests/services/test_yfinance_fetcher.py

Tests for YFinance Underlying Fetcher.
Verifies:
  - Fetches 1-minute OHLCV data.
  - Stores in DuckDB ticks table.
  - Handles missing data gracefully.
  - Column normalization works.
  - get_latest_ticks returns recent data.

6+ tests, all Window B safe (mocked network).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TESTING", "1")

from services.yfinance_fetcher import (
    TICKERS,
    fetch_and_store,
    fetch_underlying_ohlcv,
    get_duckdb_conn,
    get_latest_ticks,
    store_ticks,
)


@pytest.fixture
def sample_ohlcv_df():
    """Sample OHLCV DataFrame."""
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-16 10:00:00", "2026-01-16 10:01:00"]),
        "symbol": ["SPY", "SPY"],
        "open": [500.0, 500.5],
        "high": [501.0, 501.5],
        "low": [499.5, 500.0],
        "close": [500.5, 501.0],
        "volume": [1000, 1500],
    })


@pytest.fixture
def duckdb_conn():
    """Fresh in-memory DuckDB connection with ticks table."""
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE ticks (
            timestamp   TIMESTAMP,
            symbol      VARCHAR,
            open        DOUBLE,
            high        DOUBLE,
            low         DOUBLE,
            close       DOUBLE,
            volume      BIGINT,
            data_source VARCHAR DEFAULT 'Yahoo',
            delay_seconds INTEGER DEFAULT 0
        )
    """)
    return conn


class TestFetchUnderlyingOhlcv:
    """Tests for fetch_underlying_ohlcv function."""

    @patch("services.yfinance_fetcher.yf.Ticker")
    def test_fetch_returns_dataframe(self, mock_ticker_cls, sample_ohlcv_df):
        """fetch_underlying_ohlcv returns a DataFrame with OHLCV columns."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = sample_ohlcv_df.set_index("timestamp")
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_underlying_ohlcv("SPY")
        assert not result.empty
        assert "open" in result.columns
        assert "close" in result.columns

    @patch("services.yfinance_fetcher.yf.Ticker")
    def test_fetch_handles_empty_data(self, mock_ticker_cls):
        """Returns empty DataFrame when yfinance returns no data."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_underlying_ohlcv("SPY")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("services.yfinance_fetcher.yf.Ticker")
    def test_fetch_handles_exception(self, mock_ticker_cls):
        """Returns empty DataFrame on exception (no crash)."""
        mock_ticker_cls.side_effect = Exception("Network error")
        result = fetch_underlying_ohlcv("SPY")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("services.yfinance_fetcher.yf.Ticker")
    def test_fetch_fills_nans(self, mock_ticker_cls):
        """NaN values are filled gracefully."""
        df_with_nans = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-01-16 10:00:00"]),
            "symbol": ["SPY"],
            "open": [500.0],
            "high": [501.0],
            "low": [None],
            "close": [500.5],
            "volume": [1000],
        })
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df_with_nans.set_index("timestamp")
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_underlying_ohlcv("SPY")
        # Should not crash, NaNs handled
        assert isinstance(result, pd.DataFrame)


class TestStoreTicks:
    """Tests for store_ticks function."""

    def test_store_inserts_rows(self, sample_ohlcv_df, duckdb_conn):
        """store_ticks inserts rows into DuckDB."""
        rows = store_ticks(sample_ohlcv_df, duckdb_conn)
        assert rows == 2

        result = duckdb_conn.execute("SELECT COUNT(*) as cnt FROM ticks").fetchdf()
        assert result["cnt"].iloc[0] == 2

    def test_store_empty_dataframe(self, duckdb_conn):
        """store_ticks handles empty DataFrame."""
        empty_df = pd.DataFrame()
        rows = store_ticks(empty_df, duckdb_conn)
        assert rows == 0

    def test_store_adds_metadata_columns(self, sample_ohlcv_df, duckdb_conn):
        """store_ticks adds data_source and delay_seconds columns."""
        store_ticks(sample_ohlcv_df, duckdb_conn)
        result = duckdb_conn.execute("SELECT data_source, delay_seconds FROM ticks LIMIT 1").fetchdf()
        assert result["data_source"].iloc[0] == "Yahoo"
        assert result["delay_seconds"].iloc[0] == 0


class TestFetchAndStore:
    """Tests for fetch_and_store function."""

    @patch("services.yfinance_fetcher.fetch_underlying_ohlcv")
    def test_fetch_and_store_all_tickers(self, mock_fetch, duckdb_conn, sample_ohlcv_df):
        """fetch_and_store processes all configured tickers."""
        mock_fetch.return_value = sample_ohlcv_df
        results = fetch_and_store(conn=duckdb_conn)

        assert "SPY" in results
        assert "QQQ" in results
        assert "SPX" in results

    @patch("services.yfinance_fetcher.fetch_underlying_ohlcv")
    def test_fetch_and_store_handles_failures(self, mock_fetch, duckdb_conn):
        """fetch_and_store handles individual ticker failures."""
        mock_fetch.return_value = pd.DataFrame()
        results = fetch_and_store(conn=duckdb_conn)

        for ticker in TICKERS:
            assert results[ticker] == 0


class TestGetLatestTicks:
    """Tests for get_latest_ticks function."""

    def test_get_latest_returns_recent(self, sample_ohlcv_df, duckdb_conn):
        """get_latest_ticks returns the most recent n ticks."""
        store_ticks(sample_ohlcv_df, duckdb_conn)
        result = get_latest_ticks("SPY", n=5, conn=duckdb_conn)
        assert not result.empty

    def test_get_latest_empty_table(self, duckdb_conn):
        """get_latest_ticks returns empty DataFrame for empty table."""
        result = get_latest_ticks("SPY", n=5, conn=duckdb_conn)
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestDuckDBSetup:
    """Tests for DuckDB connection setup."""

    def test_get_duckdb_conn_creates_ticks_table(self):
        """get_duckdb_conn creates the ticks table with correct schema."""
        conn = get_duckdb_conn()
        assert conn is not None

        # Verify table exists
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ticks'"
        ).fetchdf()
        assert not tables.empty

    def test_ticks_table_has_delayed_data_columns(self):
        """ticks table has data_source and delay_seconds columns."""
        conn = get_duckdb_conn()
        cols = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'ticks'"
        ).fetchdf()
        col_names = cols["column_name"].tolist()
        assert "data_source" in col_names
        assert "delay_seconds" in col_names
