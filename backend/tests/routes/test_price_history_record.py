"""G11 record-now: POST builds fresh, awaits the recorded row, returns identity.

RED first: route does not exist (405/404). Synthetic payloads only, provider
functions monkeypatched — no network, no real spend.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server import app
from tests.offline_network import deny_external_network  # noqa: F401

client = TestClient(app)

PAYLOAD = {
    "ticker": "SPY", "spot": 500.0, "asof": "2026-10-06T14:00:00+00:00",
    "expiries_used": ["2026-10-17"], "strikes": [], "contracts": [],
    "nodes": {}, "grid": {}, "metrics": {}, "quality": {},
}


def test_record_returns_snapshot_identity(monkeypatch):
    import services.heatmap_history as hh
    from services.heatmap_history import observation_id_for
    monkeypatch.setenv("API_SECRET_KEY", "test-key")
    with patch("server._build_heatmap_impl", new=AsyncMock(return_value=dict(PAYLOAD))), \
         patch.object(hh, "replay_snapshot", return_value={"snapshot_id": "x"}):
        resp = client.post("/api/heatseeker/record/SPY", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Identity comes from the observation itself, not from the read-back.
    assert body["snapshot_id"] == observation_id_for(PAYLOAD)
    assert body["ticker"] == "SPY"
    assert "asof" in body and "scope" in body


def test_record_rejects_bad_scope(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "test-key")
    resp = client.post("/api/heatseeker/record/SPY", params={"mode": "nope"},
                       headers={"X-API-Key": "test-key"})
    assert resp.status_code == 422


def test_record_rejects_missing_key():
    resp = client.post("/api/heatseeker/record/SPY")
    assert resp.status_code == 401
