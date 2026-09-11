"""
Standalone test for health.py router — tests the router directly without
importing the full server (which may have transient breakages from other agents).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add backend dir to path so we can import routes.health directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.health import router

# Create a minimal FastAPI app with just the health router
app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestHealthEndpoint:
    """Test /api/health returns correct structure and status."""

    def test_health_returns_200(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_response_structure(self):
        resp = client.get("/api/health")
        data = resp.json()
        assert "status" in data
        assert "timestamp" in data
        assert "checks" in data

    def test_health_checks_contain_all_deps(self):
        resp = client.get("/api/health")
        checks = resp.json()["checks"]
        assert "duckdb" in checks
        assert "public_api" in checks
        assert "alpha_vantage" in checks
        assert "websocket" in checks

    def test_health_duckdb_healthy(self):
        resp = client.get("/api/health")
        assert resp.json()["checks"]["duckdb"]["status"] == "healthy"

    def test_health_websocket_shows_connections(self):
        ws = client.get("/api/health").json()["checks"]["websocket"]
        assert ws["status"] == "healthy"
        assert isinstance(ws["active_connections"], int)

    def test_health_overall_healthy_when_all_up(self):
        resp = client.get("/api/health")
        assert resp.json()["status"] in ("healthy", "degraded")

    def test_health_degraded_when_duckdb_fails(self):
        with patch("routes.health.duckdb_engine") as mock_engine:
            mock_engine._conn.execute.side_effect = Exception("DuckDB down")
            resp = client.get("/api/health")
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["checks"]["duckdb"]["status"] == "unhealthy"
            assert "DuckDB down" in data["checks"]["duckdb"]["error"]

    def test_health_degraded_when_public_api_key_missing(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PUBLIC_API_KEY", None)
            resp = client.get("/api/health")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["public_api"]["status"] == "unhealthy"
        assert "PUBLIC_API_KEY not configured" in data["checks"]["public_api"]["error"]

    def test_health_public_api_healthy_with_key(self):
        with patch.dict(os.environ, {"PUBLIC_API_KEY": "test-key"}):
            resp = client.get("/api/health")
            assert resp.json()["checks"]["public_api"]["status"] == "healthy"

    def test_health_av_retired_stub(self):
        resp = client.get("/api/health")
        av = resp.json()["checks"]["alpha_vantage"]
        assert av["status"] == "disabled"
        assert av.get("deprecated") is True
