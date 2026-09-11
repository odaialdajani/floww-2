"""
backend/routes/heatseeker_snapshots_api.py

REST API endpoints for Heatseeker snapshots, top movers, and historical playback.

I-7: Routes are registered WITHOUT a prefix on the APIRouter because
server.py mounts this router with prefix="/api/heatseeker". All paths here
are relative to that mount point.

Endpoints:
    GET /top-movers/{ticker}          → top N contracts by OI delta
    GET /history/{ticker}             → time series for a specific contract
    GET /latest/{ticker}              → latest snapshot for a ticker
    POST /snapshot/{ticker}           → trigger a live snapshot (admin)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

# I-7: No prefix here — server.py mounts with prefix="/api/heatseeker"
router = APIRouter(tags=["heatseeker-snapshots"])


def _get_duckdb_conn():
    """Get the global DuckDB connection from server.py."""
    from server import duckdb_engine
    return duckdb_engine.conn


# ---------------------------------------------------------------------------
# GET /top-movers/{ticker}
# ---------------------------------------------------------------------------

@router.get("/top-movers/{ticker}")
async def get_top_movers(
    ticker: str,
    top_n: int = Query(default=10, ge=1, le=50, description="Number of top movers to return"),
):
    """Return top N contracts by OI delta for the given ticker.

    Computes the delta between the two most recent snapshots in DuckDB.
    Returns contracts ranked by absolute OI change, with volume delta as tiebreaker.

    Response shape:
    {
        "ticker": "SPY",
        "asof": "2026-07-23T...",
        "n_contracts": 10,
        "movers": [
            {
                "ticker": "SPY",
                "expiry": "2026-07-24",
                "strike": 500.0,
                "type": "C",
                "oi": 1000,
                "volume": 500,
                "iv": 0.15,
                "delta": 0.5,
                "gamma": 0.02,
                "oi_delta": 200,
                "oi_delta_pct": 0.25,
                "volume_delta": 100,
                "score": 210.0
            },
            ...
        ]
    }
    """
    from datetime import datetime

    from services.heatseeker_snapshots import get_top_movers_from_db

    conn = _get_duckdb_conn()
    # DuckDB fetch runs pandas materialization — keep it off the event loop
    movers = await asyncio.to_thread(get_top_movers_from_db, conn, ticker, top_n=top_n)

    return {
        "ticker": ticker.upper(),
        "asof": datetime.now(UTC).isoformat(),
        "n_contracts": len(movers),
        "movers": movers,
    }


# ---------------------------------------------------------------------------
# GET /history/{ticker}
# ---------------------------------------------------------------------------

@router.get("/history/{ticker}")
async def get_history(
    ticker: str,
    expiry: str = Query(..., description="Expiry date (YYYY-MM-DD)"),
    strike: float = Query(..., description="Strike price"),
    type: str = Query(..., description="Option type: C or P", regex="^[CcPp]$"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max data points"),
):
    """Return time series for a specific contract.

    Response shape:
    {
        "ticker": "SPY",
        "expiry": "2026-07-24",
        "strike": 500.0,
        "type": "C",
        "n_points": 42,
        "history": [
            {
                "timestamp": "2026-07-23T10:00:00",
                "oi": 800,
                "volume": 400,
                "iv": 0.15,
                "delta_val": 0.5,
                "gamma_val": 0.02
            },
            ...
        ]
    }
    """
    from services.heatseeker_snapshots import get_history

    conn = _get_duckdb_conn()
    history = await asyncio.to_thread(
        get_history, conn, ticker, expiry, strike, type.upper(), limit=limit
    )

    return {
        "ticker": ticker.upper(),
        "expiry": expiry,
        "strike": float(strike),
        "type": type.upper(),
        "n_points": len(history),
        "history": history,
    }


# ---------------------------------------------------------------------------
# GET /latest/{ticker}
# ---------------------------------------------------------------------------

@router.get("/latest/{ticker}")
async def get_latest(
    ticker: str,
):
    """Return the most recent snapshot for a ticker.

    Response shape:
    {
        "ticker": "SPY",
        "n_contracts": 150,
        "contracts": [...]
    }
    """
    from services.heatseeker_snapshots import get_latest_snapshot

    conn = _get_duckdb_conn()
    contracts = await asyncio.to_thread(get_latest_snapshot, conn, ticker)

    return {
        "ticker": ticker.upper(),
        "n_contracts": len(contracts),
        "contracts": contracts,
    }


# ---------------------------------------------------------------------------
# POST /snapshot/{ticker}  (trigger live snapshot)
# ---------------------------------------------------------------------------

@router.post("/snapshot/{ticker}")
async def trigger_snapshot(
    ticker: str,
    source: str = Query(default="public_api", description="Data source: public_api (primary; legacy values yfinance/alphavantage ignored — chain always comes from fetch_spot_and_chains_merged)"),
    expiries: int = Query(default=4, ge=1, le=12),
):
    """Trigger a live snapshot of the options chain.

    Fetches the current chain from the data source and inserts into the
    shared DuckDB connection so that top-movers, history, and latest endpoints
    can read the data (previously wrote to a throwaway :memory: DB).

    This is an admin/debug endpoint. In production, snapshots are triggered
    by the scheduler/cron.
    """
    from server import fetch_spot_and_chains_merged
    from services.heatseeker_snapshots import (
        bulk_insert,
        contracts_to_recordbatch,
        create_snapshot_table,
    )

    conn = _get_duckdb_conn()
    create_snapshot_table(conn)

    raw = await fetch_spot_and_chains_merged(ticker, expiries)
    if not raw or raw.get("spot") != raw.get("spot"):  # NaN check
        return {
            "status": "error",
            "result": f"No options data for {ticker}",
        }

    batch = contracts_to_recordbatch(raw)
    n_rows = bulk_insert(conn, batch)

    return {
        "status": "ok",
        "result": {"inserted": n_rows, "ticker": ticker.upper()},
    }
