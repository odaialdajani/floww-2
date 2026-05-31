"""
backend/routes/health.py

Health check endpoint that verifies all backend dependencies are operational.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

from config.secrets import get_alpha_vantage_key
from services.alpha_vantage_client import circuit as av_circuit
from services.duckdb_engine import db as duckdb_engine
from services.websocket_streamer import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"


@router.get("/api/health")
async def health_check():
    """Check status of all dependencies.

    Returns:
        {
            "status": "healthy" | "degraded",
            "timestamp": "<ISO8601 UTC>",
            "checks": {
                "duckdb": {"status": "healthy"},
                "alpha_vantage": {"status": "healthy"} | {"status": "unhealthy", "error": "..."},
                "websocket": {"status": "healthy", "active_connections": 0}
            }
        }
    """
    checks: dict = {}

    # DuckDB check
    try:
        duckdb_engine._conn.execute("SELECT 1").fetchone()
        checks["duckdb"] = {"status": "healthy"}
    except Exception as e:
        logger.warning(f"Health check: DuckDB unhealthy: {e}")
        checks["duckdb"] = {"status": "unhealthy", "error": str(e)}

    # Alpha Vantage check
    try:
        api_key = get_alpha_vantage_key()
        if not api_key:
            checks["alpha_vantage"] = {
                "status": "unhealthy",
                "error": "ALPHA_VANTAGE_KEY not configured",
            }
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    ALPHA_VANTAGE_BASE,
                    params={
                        "function": "GLOBAL_QUOTE",
                        "symbol": "SPY",
                        "apikey": api_key,
                    },
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    checks["alpha_vantage"] = {"status": "healthy"}
                else:
                    checks["alpha_vantage"] = {
                        "status": "unhealthy",
                        "error": f"HTTP {resp.status_code}",
                    }
    except Exception as e:
        logger.warning(f"Health check: Alpha Vantage unhealthy: {e}")
        checks["alpha_vantage"] = {"status": "unhealthy", "error": str(e)}

    # WebSocket check
    ws_count = len(ws_manager._all)
    checks["websocket"] = {"status": "healthy", "active_connections": ws_count}

    # Alpha Vantage Circuit Breaker check
    checks["circuit_breaker"] = {
        "status": "unhealthy" if av_circuit.state.value == "open" else "healthy",
        "state": av_circuit.state.value,
        "failure_count": av_circuit.failure_count,
        "success_count": av_circuit.success_count,
    }

    overall = (
        "healthy"
        if all(c.get("status") == "healthy" for c in checks.values())
        else "degraded"
    )

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
