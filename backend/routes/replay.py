"""
backend/routes/replay.py

Historical replay API routes.
POST /api/replay/start — start replaying historical data
POST /api/replay/stop — stop replay
GET /api/replay/status — current replay status
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

_replay_engine = None

def set_replay_engine(engine):
    """Called by server.py to inject the replay engine."""
    global _replay_engine
    _replay_engine = engine



logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/replay", tags=["replay"])

# Global replay engine instance (set by server.py on startup)
_replay_engine = None
_engine_task: Optional[asyncio.Task] = None


@router.post("/start")
async def start_replay(
    start: str = Query(..., description="ISO start datetime"),
    end: str = Query(..., description="ISO end datetime"),
    speed: float = Query(10.0, ge=0.1, le=1000.0),
):
    """Start replaying historical data from DuckDB/Mongo."""
    global _replay_engine
    if _replay_engine and _replay_engine.get_status()["running"]:
        raise HTTPException(409, "Replay already running")

    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "Invalid datetime format (use ISO 8601)")

    from services.duckdb_engine import db as duckdb_engine
    from services.replay_engine import ReplayEngine

    engine = ReplayEngine(db=duckdb_engine, start=start_dt, end=end_dt, speed=speed)

    # Wire into the ingestion pipeline if available
    try:
        from server import _ingestion_pipeline
        if _ingestion_pipeline:
            engine.on_tick(_ingestion_pipeline.enqueue_tick)
            engine.on_chain(_ingestion_pipeline.enqueue_chain)
            engine.on_lob(_ingestion_pipeline.enqueue_lob)
    except Exception as e:
        logger.warning(f"Failed to wire replay into ingestion pipeline: {e}")

    set_replay_engine(engine)
    global _engine_task
    _engine_task = asyncio.create_task(engine.start())
    return {"status": "started", "start": start, "end": end, "speed": speed}


@router.post("/stop")
async def stop_replay():
    """Stop the current replay."""
    global _replay_engine, _engine_task
    if not _replay_engine:
        raise HTTPException(404, "No replay running")
    if _engine_task is not None and not _engine_task.done():
        _engine_task.cancel()
        try:
            await _engine_task
        except asyncio.CancelledError:
            pass
    await _replay_engine.stop()
    _engine_task = None
    return {"status": "stopped"}


@router.get("/status")
async def replay_status():
    """Get current replay status."""
    global _replay_engine
    if not _replay_engine:
        return {"running": False}
    return _replay_engine.get_status()
