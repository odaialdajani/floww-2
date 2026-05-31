"""
backend/scripts/snapshot_chain.py

Fetch an options chain from Alpha Vantage or yfinance and snapshot it to DuckDB.

Usage:
    # Snapshot SPY chain (default: yfinance)
    python -m scripts.snapshot_chain SPY

    # Use Alpha Vantage as data source
    python -m scripts.snapshot_chain SPY --source alphavantage

    # Custom DB path (default: in-memory for testing, file for production)
    python -m scripts.snapshot_chain SPY --db-path /data/heatseeker.duckdb

    # Specify number of expiries
    python -m scripts.snapshot_chain SPY --expiries 6
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

import duckdb

# Add parent dir to path so `services` is importable when run as script
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from services.heatseeker_snapshots import (
    bulk_insert,
    contracts_to_recordbatch,
    create_snapshot_table,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("snapshot_chain")

# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

async def _fetch_chain_yfinance(ticker: str, expiries: int = 4) -> dict:
    """Fetch chain via yfinance (sync → thread)."""
    import yfinance as yf

    def _do():
        t = yf.Ticker(ticker)
        spot = t.fast_info.last_price
        if not spot:
            return {"ticker": ticker, "spot": 0, "contracts": []}

        contracts = []
        try:
            exp_dates = t.options or []
        except Exception:
            return {"ticker": ticker, "spot": spot, "contracts": []}

        for exp_str in exp_dates[:expiries]:
            try:
                chain = t.option_chain(exp_str)
            except Exception:
                continue
            for _, row in chain.calls.iterrows():
                contracts.append({
                    "expiry": exp_str,
                    "strike": float(row.get("strike", 0)),
                    "type": "C",
                    "oi": int(row.get("openInterest", 0) or 0),
                    "volume": int(row.get("volume", 0) or 0),
                    "iv": float(row.get("impliedVolatility", 0) or 0),
                    "delta": float(row.get("delta", 0) or 0),
                    "gamma": float(row.get("gamma", 0) or 0),
                })
            for _, row in chain.puts.iterrows():
                contracts.append({
                    "expiry": exp_str,
                    "strike": float(row.get("strike", 0)),
                    "type": "P",
                    "oi": int(row.get("openInterest", 0) or 0),
                    "volume": int(row.get("volume", 0) or 0),
                    "iv": float(row.get("impliedVolatility", 0) or 0),
                    "delta": float(row.get("delta", 0) or 0),
                    "gamma": float(row.get("gamma", 0) or 0),
                })

        return {"ticker": ticker, "spot": spot, "contracts": contracts}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do)


async def _fetch_chain_alphavantage(ticker: str, expiries: int = 4) -> dict:
    """Fetch chain via Alpha Vantage options API."""
    from data_providers import ALPHA_VANTAGE_KEY

    if not ALPHA_VANTAGE_KEY:
        logger.warning("ALPHA_VANTAGE_KEY not set, falling back to yfinance")
        return await _fetch_chain_yfinance(ticker, expiries)

    import aiohttp

    # Alpha Vantage options chain endpoint
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "OPTION_CHAIN",
        "symbol": ticker,
        "apikey": ALPHA_VANTAGE_KEY,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.warning(f"AV returned {resp.status}, falling back to yfinance")
                    return await _fetch_chain_yfinance(ticker, expiries)
                data = await resp.json()
    except Exception as e:
        logger.warning(f"AV fetch failed ({e}), falling back to yfinance")
        return await _fetch_chain_yfinance(ticker, expiries)

    if not data or "data" not in data:
        logger.warning("AV returned empty data, falling back to yfinance")
        return await _fetch_chain_yfinance(ticker, expiries)

    spot = float(data.get("stock_price", 0) or 0)
    contracts = []
    for entry in data.get("data", []):
        exp = entry.get("expirationDate", "")
        if not exp:
            continue
        for side in ("call", "put"):
            prefix = side
            oi_key = f"{prefix}OpenInterest"
            vol_key = f"{prefix}Volume"
            strike_key = "strikePrice"
            iv_key = f"{prefix}ImpliedVolatility"
            delta_key = f"{prefix}Delta"
            gamma_key = f"{prefix}Gamma"

            oi = entry.get(oi_key, 0) or 0
            vol = entry.get(vol_key, 0) or 0
            strike = entry.get(strike_key, 0) or 0

            if strike <= 0:
                continue

            contracts.append({
                "expiry": exp,
                "strike": float(strike),
                "type": "C" if side == "call" else "P",
                "oi": int(oi),
                "volume": int(vol),
                "iv": float(entry.get(iv_key, 0) or 0),
                "delta": float(entry.get(delta_key, 0) or 0),
                "gamma": float(entry.get(gamma_key, 0) or 0),
            })

        if len(contracts) >= expiries * 200:
            break

    return {"ticker": ticker, "spot": spot, "contracts": contracts}


# ---------------------------------------------------------------------------
# Main snapshot workflow
# ---------------------------------------------------------------------------

async def snapshot_chain(
    ticker: str,
    source: str = "yfinance",
    db_path: str = ":memory:",
    expiries: int = 4,
) -> dict:
    """Fetch chain, convert to RecordBatch, insert into DuckDB.

    Returns a summary dict with row count and timing.
    """
    logger.info(f"Snapshotting {ticker} from {source} (expiries={expiries})")

    # 1. Fetch
    t0 = time.perf_counter()
    if source == "alphavantage":
        chain = await _fetch_chain_alphavantage(ticker, expiries)
    else:
        chain = await _fetch_chain_yfinance(ticker, expiries)
    fetch_ms = (time.perf_counter() - t0) * 1000

    contracts_count = len(chain.get("contracts") or [])
    logger.info(f"Fetched {contracts_count} contracts in {fetch_ms:.1f}ms")

    if contracts_count == 0:
        logger.warning("No contracts fetched, nothing to insert")
        return {"ticker": ticker, "contracts": 0, "inserted": 0, "fetch_ms": fetch_ms, "insert_ms": 0}

    # 2. Connect to DuckDB
    conn = duckdb.connect(db_path)
    try:
        create_snapshot_table(conn)

        # 3. Convert to RecordBatch (I-3: PyArrow, no Pandas)
        batch = contracts_to_recordbatch(chain)

        # 4. Bulk insert
        t1 = time.perf_counter()
        inserted = bulk_insert(conn, batch)
        insert_ms = (time.perf_counter() - t1) * 1000

        logger.info(f"Inserted {inserted} rows in {insert_ms:.1f}ms")

        # 5. Verify
        total = conn.execute(
            "SELECT COUNT(*) FROM heatseeker_snapshots WHERE ticker = ?",
            [ticker.upper()],
        ).fetchone()[0]

        return {
            "ticker": ticker.upper(),
            "spot": chain.get("spot"),
            "contracts": contracts_count,
            "inserted": inserted,
            "total_rows": total,
            "fetch_ms": round(fetch_ms, 2),
            "insert_ms": round(insert_ms, 2),
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Snapshot an options chain to DuckDB")
    parser.add_argument("ticker", help="Ticker symbol (e.g. SPY)")
    parser.add_argument("--source", choices=["yfinance", "alphavantage"], default="yfinance",
                        help="Data source (default: yfinance)")
    parser.add_argument("--db-path", default=":memory:",
                        help="DuckDB path (default: :memory:, use a file path for persistence)")
    parser.add_argument("--expiries", type=int, default=4,
                        help="Number of expiries to fetch (default: 4)")
    args = parser.parse_args()

    result = asyncio.run(snapshot_chain(
        ticker=args.ticker,
        source=args.source,
        db_path=args.db_path,
        expiries=args.expiries,
    ))

    logger.info(f"\n{'='*60}")
    logger.info(f"Snapshot complete for {result['ticker']}")
    logger.info(f"  Spot:        {result.get('spot', 'N/A')}")
    logger.info(f"  Contracts:   {result['contracts']}")
    logger.info(f"  Inserted:    {result['inserted']}")
    logger.info(f"  Total rows:  {result.get('total_rows', 'N/A')}")
    logger.info(f"  Fetch time:  {result['fetch_ms']}ms")
    logger.info(f"  Insert time: {result['insert_ms']}ms")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    main()
