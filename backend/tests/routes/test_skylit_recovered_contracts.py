"""Recovered cross-panel/outage checks using one fixed chain and isolated dependencies.

Historical source: 0f43e03e. No live-chain assumptions or shared-store writes.
"""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import heatseeker

PANELS = [("flip-zones", "flip_zones"), ("node-lifecycle", "nodes"), ("air-pockets", "air_pockets")]


@pytest.fixture
def panel_client(monkeypatch):
    from services import duckdb_engine

    monkeypatch.setitem(sys.modules, "server", SimpleNamespace(_sanitize=lambda value: value))
    monkeypatch.setattr(duckdb_engine, "db", SimpleNamespace(_conn=None))
    fetch = AsyncMock(return_value={"spot": 100.0, "contracts": [
        {"strike": 95.0, "type": "P", "gamma": 0.02, "oi": 100, "T": 30 / 365, "iv": 0.2},
        {"strike": 100.0, "type": "C", "gamma": 0.03, "oi": 200, "T": 30 / 365, "iv": 0.2},
        {"strike": 105.0, "type": "C", "gamma": 0.02, "oi": 100, "T": 30 / 365, "iv": 0.2},
    ]})
    monkeypatch.setattr(heatseeker, "_fetch_chain", fetch)
    monkeypatch.setattr(heatseeker, "_fetch_history", AsyncMock(return_value=[]))
    app = FastAPI()
    app.include_router(heatseeker.router)
    with TestClient(app) as client:
        yield client, fetch


@pytest.mark.parametrize("endpoint,list_key", PANELS)
def test_fixed_chain_response_shape(panel_client, endpoint, list_key):
    client, fetch = panel_client
    response = client.get("/api/heatseeker/" + endpoint, params={"ticker": "spy"})
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "SPY"
    assert body["spot"] == 100.0
    assert isinstance(body[list_key], list)
    assert body.get("status") != "degraded"
    fetch.assert_awaited_once()


def test_same_chain_has_exact_cross_panel_spot(panel_client):
    client, _ = panel_client
    bodies = [client.get("/api/heatseeker/" + endpoint).json() for endpoint, _ in PANELS]
    assert {body["ticker"] for body in bodies} == {"SPY"}
    assert {body["spot"] for body in bodies} == {100.0}


@pytest.mark.parametrize("endpoint,list_key", PANELS)
def test_outage_then_recovery_is_not_empty_success(panel_client, endpoint, list_key):
    client, fetch = panel_client
    fetch.side_effect = RuntimeError("fixture feed unavailable")
    failed = client.get("/api/heatseeker/" + endpoint).json()
    assert failed["status"] == "degraded"
    assert failed[list_key] == []
    fetch.side_effect = None
    recovered = client.get("/api/heatseeker/" + endpoint).json()
    assert recovered.get("status") != "degraded"
    assert recovered["spot"] == 100.0


@pytest.mark.parametrize("endpoint,list_key", PANELS)
def test_empty_chain_is_explicitly_absent(panel_client, endpoint, list_key):
    client, fetch = panel_client
    fetch.return_value = {"spot": 100.0, "contracts": []}
    response = client.get("/api/heatseeker/" + endpoint)
    assert response.status_code == 404
