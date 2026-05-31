"""
backend/tests/routes/test_health.py

Tests for /api/health: DuckDB/AlphaVantage/WebSocket manager circuit breaker.
All external calls are mocked so tests run offline deterministically.
"""
from __future__ import annotations

import logging
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
    """Avoid calling real AV/DuckDB/WebSocket singletons during tests."""
    # Alpha Vantage network call
    with patch("routes.health.httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Global Quote": {"01. symbol": "SPY", "05. price": "450.00"}
        }
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        # DuckDB DB connection
        with patch("routes.health.duckdb_engine") as mock_duck:
            mock_duck._conn = MagicMock()
            mock_duck._conn.execute.return_value.fetchone.return_value = (1,)

            # WebSocket manager
            with patch("routes.health.ws_manager") as mock_ws:
                mock_ws._all = {MagicMock(): MagicMock()}  # one active connection
                yield {
                    "client_cls": mock_client_cls,
                    "duckdb": mock_duck,
                    "ws": mock_ws,
                }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_all_healthy():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert set(body["checks"].keys()) >= {
        "duckdb",
        "alpha_vantage",
        "websocket",
        "circuit_breaker",
    }


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
    import routes.health as health_mod
    health_mod.httpx.AsyncClient.return_value.get.side_effect = RuntimeError(
        "AV offline"
    )

    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["alpha_vantage"]["status"] == "unhealthy"


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
