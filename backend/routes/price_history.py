"""Read-only historical price/node chart. Never feeds replay into live data."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from services.price_node_history import build_history, epoch

router = APIRouter(prefix="/api/heatseeker", tags=["price-node-history"])


def read_snapshots(engine, ticker, first, last):
    return engine.query_strict(
        "SELECT snapshot_id, ticker, query_key, expiries, formula_version, exposure_basis, asof_ts, received_at, walls_json "
        "FROM heatmap_snapshots_v2 WHERE ticker = ? "
        "AND TRY_CAST(asof_ts AS TIMESTAMPTZ) >= ? "
        "AND TRY_CAST(asof_ts AS TIMESTAMPTZ) <= ? "
        "ORDER BY TRY_CAST(asof_ts AS TIMESTAMPTZ), snapshot_id LIMIT 50001",
        [ticker, first, last],
    )


def recording_summary(engine, ticker):
    """Actual backing and saved range, including records newer than the candles."""
    from services.connection_guard import connection_lock
    from services.heatmap_history import recorder_status

    with connection_lock(engine.conn):
        status = recorder_status(engine.conn)
    rows = engine.query_strict(
        "SELECT MIN(TRY_CAST(asof_ts AS TIMESTAMPTZ)) AS first_at, "
        "MAX(TRY_CAST(asof_ts AS TIMESTAMPTZ)) AS last_at, COUNT(*) AS count "
        "FROM heatmap_snapshots_v2 WHERE ticker = ?", [ticker],
    )
    saved = rows[0] if rows else {}
    return {"durable": status["durable"], "status": "available",
            "first_at": saved.get("first_at"), "last_at": saved.get("last_at"),
            "count": saved.get("count", 0)}


@router.get("/price-history/{ticker}")
async def price_history(ticker: str, days: int = Query(5, ge=1, le=20),
                        query_key: str | None = Query(None, max_length=2000)):
    from services.duckdb_engine import db
    from services.public_api_adapter import fetch_bars_by_interval
    from services.public_budget import BudgetExhausted, budget

    ticker = ticker.strip().upper()
    try:
        recording = await asyncio.to_thread(recording_summary, db, ticker)
    except Exception:
        recording = {"status": "unavailable", "durable": False}
    period, aggregation, bar_seconds = ("DAY", "ONE_MINUTE", 60) if days == 1 else ("WEEK", "FIVE_MINUTES", 300) if days <= 5 else ("MONTH", "ONE_HOUR", 3600)
    # This path deliberately does not use market_bars' stale-on-error cache:
    # a failed historical fetch must be visible, not labelled as a new read.
    try:
        await budget.acquire("api.public.com")
    except BudgetExhausted:
        bars = []
    else:
        try:
            bars = await fetch_bars_by_interval(ticker, period=period, aggregation=aggregation, sessions="regular") or []
        finally:
            budget.release()
    received_at = datetime.now(UTC).isoformat()
    price_only = build_history(ticker, bars, [], query_key)
    valid_times = [epoch(frame["time"]) for frame in price_only["frames"]]
    if not valid_times:
        return {**build_history(ticker, [], [], query_key), "price_status": "unavailable",
                "node_status": "not_loaded", "days": days, "recording": recording}
    first = datetime.fromtimestamp(min(valid_times), UTC) - timedelta(minutes=15)
    last = datetime.fromtimestamp(max(valid_times), UTC)
    node_status = "available"
    try:
        rows = await asyncio.to_thread(read_snapshots, db, ticker, first, last)
    except Exception:
        rows = []
        node_status = "unavailable"
    truncated = len(rows) > 50000
    if truncated:
        rows = rows[:50000]
    result = build_history(ticker, bars, rows, query_key)
    for frame in result["frames"]:
        frame["duration_seconds"] = bar_seconds
    return {**result, "price_status": "available", "node_status": node_status,
            "records_truncated": truncated, "days": days, "prices_received_at": received_at,
            "last_candle_at": datetime.fromtimestamp(max(valid_times), UTC).isoformat(),
            "bar_seconds": bar_seconds, "recording": recording}
