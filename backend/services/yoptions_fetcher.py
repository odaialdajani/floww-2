"""
backend/services/yoptions_fetcher.py

YOptions Chain Fetcher with Retry Logic.
Fetches options chains for SPY, QQQ, SPX using yoptions library.
Implements tenacity retry with exponential backoff.
Saves raw JSON for debugging.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    import yoptions as yo
    HAS_YOPTIONS = True
except ImportError:
    yo = None
    HAS_YOPTIONS = False

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

if not HAS_YOPTIONS:
    logger.warning("yoptions module not installed — retail polling disabled. Install: pip install yoptions")

# Supported tickers
TICKERS = ["SPY", "QQQ", "SPX"]

# Dividend yield for SPY (approximate, updated quarterly)
DIVIDEND_YIELDS = {
    "SPY": 0.013,   # ~1.3% annual
    "QQQ": 0.005,   # ~0.5% annual
    "SPX": 0.013,   # Same as SPY (index approx)
}

# Raw data directory
RAW_CHAINS_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_chains"


def _save_raw_json(ticker: str, data: dict, expiry: str, option_type: str) -> None:
    """Save raw JSON response for debugging."""
    RAW_CHAINS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = RAW_CHAINS_DIR / f"{ticker}_{expiry}_{option_type}_{ts}.json"
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug(f"Saved raw chain to {filename}")
    except Exception as e:
        logger.warning(f"Failed to save raw JSON: {e}")



class YOptionsFetchError(Exception):
    """Raised when yoptions fetch fails after all retries."""
    pass

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _fetch_chain_with_retry(
    ticker: str,
    dividend_yield: float,
    option_type: str,
    expiry: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch a single option chain with tenacity retry logic.

    Args:
        ticker: Stock ticker symbol.
        dividend_yield: Annualized dividend yield.
        option_type: 'c' for calls, 'p' for puts.
        expiry: Optional expiration date 'YYYY-MM-DD'. If None, uses nearest.

    Returns:
        DataFrame with chain greeks.

    Raises:
        YOptionsFetchError: If all retries fail.
    """
    if not HAS_YOPTIONS:
        raise YOptionsFetchError("yoptions module not installed — install with: pip install yoptions")
    try:
        if expiry:
            df = yo.get_chain_greeks_date(ticker, dividend_yield, option_type, expiry)
        else:
            df = yo.get_chain_greeks(ticker, dividend_yield, option_type)

        if isinstance(df, str):
            # yoptions returns error strings
            raise YOptionsFetchError(f"yoptions error for {ticker}: {df}")

        return df

    except YOptionsFetchError:
        raise
    except Exception as e:
        # Wrap in ConnectionError/TimeoutError/OSError for tenacity to catch
        raise ConnectionError(f"yoptions fetch failed for {ticker}: {e}") from e


def fetch_options_chain(
    ticker: str,
    option_type: str = "both",
    expiry: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch options chain for a single ticker.

    Args:
        ticker: Stock ticker (SPY, QQQ, SPX).
        option_type: 'c' (calls), 'p' (puts), or 'both'.
        expiry: Optional expiration date 'YYYY-MM-DD'.

    Returns:
        DataFrame with columns: Symbol, Strike, Expiry, Type, Bid, Ask,
        Last, Volume, Open_Interest, IV, Delta, Gamma, Theta, Vega.
        Returns empty DataFrame on failure.
    """
    dividend_yield = DIVIDEND_YIELDS.get(ticker, 0.013)
    frames = []

    types_to_fetch = []
    if option_type in ("c", "both"):
        types_to_fetch.append("c")
    if option_type in ("p", "both"):
        types_to_fetch.append("p")

    for ot in types_to_fetch:
        try:
            df = _fetch_chain_with_retry(ticker, dividend_yield, ot, expiry)
            if df is not None and not df.empty:
                df["Type"] = "call" if ot == "c" else "put"
                df["Expiry"] = expiry or "nearest"
                df["Ticker"] = ticker
                # Save raw JSON for debugging
                _save_raw_json(ticker, {"data": df.to_dict("records")}, expiry or "nearest", ot)
                frames.append(df)
                logger.info(f"Fetched {len(df)} {ot} options for {ticker}")
            else:
                logger.warning(f"Empty chain for {ticker} {ot}")
        except Exception as e:
            logger.error(
                f"All retries failed for {ticker} {ot}: {e}. Returning partial data."
            )

    if frames:
        result = pd.concat(frames, ignore_index=True)
        # Normalize column names
        col_map = {
            "Symbol": "symbol",
            "Strike": "strike",
            "Last Price": "last",
            "Bid": "bid",
            "Ask": "ask",
            "Impl. Volatility": "iv",
            "Delta": "delta",
            "Gamma": "gamma",
            "Theta": "theta",
            "Vega": "vega",
            "Rho": "rho",
            "Volume": "volume",
            "Open Interest": "open_interest",
            "Ticker": "ticker",
            "Type": "type",
            "Expiry": "expiry",
        }
        result = result.rename(columns=col_map)
        return result

    logger.error(f"No data fetched for {ticker}. Returning empty DataFrame.")
    return pd.DataFrame(columns=[
        "symbol", "strike", "expiry", "type", "bid", "ask", "last",
        "volume", "open_interest", "iv", "delta", "gamma", "theta", "vega",
        "ticker",
    ])


def fetch_all_chains(
    tickers: Optional[list] = None,
    option_type: str = "both",
) -> pd.DataFrame:
    """Fetch options chains for all configured tickers.

    Args:
        tickers: List of tickers. Defaults to TICKERS.
        option_type: 'c', 'p', or 'both'.

    Returns:
        Combined DataFrame of all chains.
    """
    if tickers is None:
        tickers = TICKERS

    all_frames = []
    for ticker in tickers:
        df = fetch_options_chain(ticker, option_type)
        if not df.empty:
            all_frames.append(df)

    if all_frames:
        return pd.concat(all_frames, ignore_index=True)
    return pd.DataFrame()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Fetching SPY options chain...")
    df = fetch_options_chain("SPY")
    logger.info(f"Fetched {len(df)} rows")
    if not df.empty:
        logger.info(df.head())
        logger.info(f"\nColumns: {list(df.columns)}")
        logger.info("\nSample Greeks:")
        logger.info(df[["strike", "delta", "gamma", "theta", "vega"]].head(10))
