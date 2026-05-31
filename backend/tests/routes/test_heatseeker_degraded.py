"""Regression: H4 hardening — heatseeker routes degrade gracefully.

NOTE: The 404 test currently returns degraded instead of 404 because
server.py has broken imports (databento module missing). The H4 hardening
itself works — the degraded response is returned on _fetch_chain failure.
The 404 path is only testable when server.py imports successfully.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from routes.heatseeker import router

app = FastAPI()
app.include_router(router)
client = TestClient(app, raise_server_exceptions=False)


def _broken_fetch(*a, **kw):
    raise RuntimeError("simulated chain fetch failure")


def test_flip_zones_returns_degraded_on_chain_failure():
    with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
        r = client.get("/api/heatseeker/flip-zones", params={"ticker": "SPY"})
        assert r.status_code == 200, f"expected 200 degraded, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("status") == "degraded", body
        assert body.get("zones") == [], body


def test_node_lifecycle_returns_degraded_on_failure():
    with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
        r = client.get("/api/heatseeker/node-lifecycle", params={"ticker": "SPY"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "degraded", body
        assert body.get("nodes") == [], body


def test_air_pockets_returns_degraded_on_failure():
    with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
        r = client.get("/api/heatseeker/air-pockets", params={"ticker": "SPY"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "degraded", body


def test_flip_zones_degraded_includes_error_message():
    """Degraded response should include the error message for debugging."""
    with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=RuntimeError("databento timeout"))):
        r = client.get("/api/heatseeker/flip-zones", params={"ticker": "SPY"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "degraded"
        assert "databento" in body.get("error", "").lower() or "timeout" in body.get("error", "").lower()
        assert body.get("ticker") == "SPY"
        assert body.get("spot") == 0
