"""
backend/tests/routes/test_health.py

Tests for /api/health: DuckDB/Public API/WebSocket manager circuit breaker.
All external calls are mocked so tests run offline deterministically.

PUBLIC-API-ONLY (2026-09-03): the live check is `public_api`;
`alpha_vantage` is a deprecated disabled stub, excluded from the verdict.
"""
from __future__ import annotations

import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_externals():
    """Avoid calling real Public API/DuckDB/WebSocket singletons during tests."""
    # Public API key presence probe (routes.health reads PUBLIC_API_KEY env)
    with patch.dict(os.environ, {"PUBLIC_API_KEY": "test-key"}):
        # DuckDB DB connection
        with patch("routes.health.duckdb_engine") as mock_duck:
            mock_duck._conn = MagicMock()
            mock_duck._conn.execute.return_value.fetchone.return_value = (1,)

            # WebSocket manager
            with patch("routes.health.ws_manager") as mock_ws:
                mock_ws._all = {MagicMock(): MagicMock()}  # one active connection
                yield {
                    "duckdb": mock_duck,
                    "ws": mock_ws,
                }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.flaky_env
def test_all_healthy():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert set(body["checks"].keys()) >= {
        "duckdb",
        "public_api",
        "alpha_vantage",
        "websocket",
        "circuit_breaker",
    }
    assert body["checks"]["public_api"]["status"] == "healthy"
    # Retired provider stays visible but never flips the verdict.
    assert body["checks"]["alpha_vantage"]["status"] == "disabled"
    assert body["checks"]["alpha_vantage"].get("deprecated") is True


def test_duckdb_fails():
    import routes.health as health_mod
    health_mod.duckdb_engine._conn.execute.side_effect = RuntimeError("duckdb down")

    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["duckdb"]["status"] == "unhealthy"
    assert "error" in body["checks"]["duckdb"]


def test_av_fails():
    # Retired stub is always disabled and never degrades overall health.
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["alpha_vantage"]["status"] == "disabled"


def test_public_api_missing_key_degrades():
    import os

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PUBLIC_API_KEY", None)
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["public_api"]["status"] == "unhealthy"


def test_ws_manager_check():
    import routes.health as health_mod
    fake_ws = {MagicMock(): MagicMock(), MagicMock(): MagicMock()}
    health_mod.ws_manager._all = fake_ws

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["checks"]["websocket"]["active_connections"] == 2


def test_timeout_handling():
    import asyncio

    import routes.health as health_mod

    async def _slow():
        await asyncio.sleep(999)

    health_mod.duckdb_engine._conn.execute.side_effect = lambda *a, **kw: _slow()

    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["duckdb"]["status"] == "unhealthy"


def test_json_structure():
    resp = client.get("/api/health")
    body = resp.json()
    assert "status" in body
    assert "timestamp" in body
    assert isinstance(body["checks"], dict)
    for name, check in body["checks"].items():
        assert "status" in check
        if name == "websocket":
            assert "active_connections" in check
        if name == "circuit_breaker":
            assert "state" in check
