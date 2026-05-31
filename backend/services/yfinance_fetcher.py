"""
backend/services/yfinance_fetcher.py

YFinance Underlying Fetcher.
Fetches 1-minute OHLCV data for SPY, QQQ, SPX.
Stores in DuckDB ticks table.
"""

from __future__ import annotations

import logging
from typing import Optional

import duckdb
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

TICKERS = ["SPY", "QQQ", "SPX"]

# DuckDB path (file-based for persistence across restarts)
DB_PATH = ":memory:"


def get_duckdb_conn(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Get or create a DuckDB connection."""
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticks (
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


def fetch_underlying_ohlcv(
    ticker: str,
    period: str = "1d",
    interval: str = "1m",
) -> pd.DataFrame:
    """Fetch 1-minute OHLCV data for a single ticker.

    Args:
        ticker: Stock ticker symbol.
        period: Data period ('1d', '5d', '1mo').
        interval: Bar interval ('1m', '5m', '15m').

    Returns:
        DataFrame with columns: timestamp, symbol, open, high, low, close, volume.
        Returns empty DataFrame on failure.
    """
    try:
        yf_ticker = yf.Ticker(ticker)
        df = yf_ticker.history(period=period, interval=interval)

        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return pd.DataFrame()

        # Reset index to get timestamp as column
        df = df.reset_index()
        df["symbol"] = ticker

        # Normalize column names
        df = df.rename(columns={
            "Datetime": "timestamp",
            "Date": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })

        # Select only needed columns
        keep_cols = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
        df = df[[c for c in keep_cols if c in df.columns]]

        # Fill NaN values
        df = df.ffill().fillna(0)

        logger.info(f"Fetched {len(df)} 1-min bars for {ticker}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch {ticker}: {e}")
        return pd.DataFrame()


def store_ticks(df: pd.DataFrame, conn: Optional[duckdb.DuckDBPyConnection] = None) -> int:
    """Store OHLCV data in DuckDB ticks table.

    Args:
        df: DataFrame with OHLCV data.
        conn: DuckDB connection. If None, creates in-memory.

    Returns:
        Number of rows inserted.
    """
    if df.empty:
        return 0

    if conn is None:
        conn = get_duckdb_conn()

    try:
        # Add metadata columns
        df["data_source"] = "Yahoo"
        df["delay_seconds"] = 0

        # Insert using DuckDB's from_df
        conn.execute("INSERT INTO ticks SELECT * FROM df")
        rows_inserted = len(df)
        logger.info(f"Stored {rows_inserted} rows in ticks table")
        return rows_inserted
    except Exception as e:
        logger.error(f"Failed to store ticks: {e}")
        return 0


def fetch_and_store(
    tickers: Optional[list] = None,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
) -> dict:
    """Fetch and store OHLCV data for all tickers.

    Args:
        tickers: List of tickers. Defaults to TICKERS.
        conn: DuckDB connection.

    Returns:
        Dict of {ticker: rows_fetched}.
    """
    if tickers is None:
        tickers = TICKERS

    if conn is None:
        conn = get_duckdb_conn()

    results = {}
    for ticker in tickers:
        df = fetch_underlying_ohlcv(ticker)
        if not df.empty:
            rows = store_ticks(df, conn)
            results[ticker] = rows
        else:
            results[ticker] = 0

    return results


def get_latest_ticks(
    symbol: str,
    n: int = 10,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
) -> pd.DataFrame:
    """Get the latest n ticks for a symbol.

    Args:
        symbol: Ticker symbol.
        n: Number of rows.
        conn: DuckDB connection.

    Returns:
        DataFrame with latest ticks.
    """
    if conn is None:
        conn = get_duckdb_conn()

    try:
        result = conn.execute(
            "SELECT * FROM ticks WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
            [symbol, n],
        ).fetchdf()
        return result
    except Exception as e:
        logger.error(f"Query failed: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = get_duckdb_conn()
    results = fetch_and_store(conn=conn)
    logger.info(f"\nResults: {results}")
    for ticker in TICKERS:
        latest = get_latest_ticks(ticker, n=3, conn=conn)
        if not latest.empty:
            logger.info(f"\n{ticker} latest ticks:")
            logger.info(latest)
