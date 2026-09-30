"""Solstice-owned scanner delivery; no lifespan, provider or legacy state."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import server
from services import solstice_scan as scan
from services.solstice_rank import KeyedScanCache


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "r11-fixture-only")
    monkeypatch.setattr(scan, "_CACHE", KeyedScanCache())
    monkeypatch.setattr(scan, "_CURSOR", {})
    return TestClient(server.app)


def test_read_is_not_scanned_and_never_starts_a_sweep(client, monkeypatch):
    run = AsyncMock(side_effect=AssertionError("GET must not scan"))
    monkeypatch.setattr(scan, "run_scan", run)
    res = client.get("/api/solstice/scan/leaderboard", params={"limit": 2})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "not-scanned"
    assert res.json()["leaderboard"] == []
    run.assert_not_awaited()


def test_scan_requires_authentication_and_has_bounded_admission(client, monkeypatch):
    run = AsyncMock(return_value={"rows": [], "coverage": {}, "status": "no-eligible-rows"})
    monkeypatch.setattr(scan, "run_scan", run)
    res = client.post("/api/solstice/scan", json={"limit": 2})
    assert res.status_code == 401
    run.assert_not_awaited()
    invalid = client.post("/api/solstice/scan", headers={"X-API-Key": "r11-fixture-only"}, json={"limit": 10000})
    assert invalid.status_code == 422
    run.assert_not_awaited()


def test_scan_delivers_coordinator_rows_and_named_rank_method(client, monkeypatch):
    run = AsyncMock(return_value={"rows": [{"ticker": "SPY", "conviction": 55.5}],
                                 "coverage": {"requested": 2, "usable": 1}, "status": "partial-budget"})
    monkeypatch.setattr(scan, "run_scan", run)
    res = client.post("/api/solstice/scan", headers={"X-API-Key": "r11-fixture-only"}, json={"limit": 2})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["leaderboard"][0]["conviction"] == 55.5
    assert body["status"] == "partial-budget"
    assert body["rank_method"] == "solstice-rank.v1"
    assert body["calibration_state"] == "unvalidated_research_ranking"
    assert run.await_args.kwargs["limit"] == 2


def test_missing_auth_configuration_disables_scan(client, monkeypatch):
    monkeypatch.delenv("API_SECRET_KEY")
    res = client.post("/api/solstice/scan", json={"limit": 2})
    assert res.status_code == 503


def test_get_cannot_spend_via_refresh_parameter(client, monkeypatch):
    run = AsyncMock(side_effect=AssertionError("no refresh via read"))
    monkeypatch.setattr(scan, "run_scan", run)
    assert client.get("/api/solstice/scan/leaderboard?refresh=true").status_code == 200
    run.assert_not_awaited()
