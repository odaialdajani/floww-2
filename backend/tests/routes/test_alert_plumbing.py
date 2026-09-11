"""Route-level plumbing: alert inputs must reach producers.

RED contract (fails on current main):
  - GET /api/alerts/{ticker}?momentum_score=N accepts N but never forwards it;
    MOMENTUM_EXTREME can never fire through the API.
  - POST /api/alerts/snapshot drops `volume_by_strike` (the GEXSnapshot field
    exists with a "should be populated by the caller" comment) and momentum;
    VOLUME_SPIKE can never fire through the snapshot path.

No threshold or scoring change is under test here — only that request inputs
arrive at the detectors that already declare them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app, headers={"X-API-Key": "test-secret-key"})


@pytest.fixture(autouse=True)
def _isolated_engine():
    """Reset the global alert singleton so seeded snapshots never leak
    into other modules (e.g. the empty-state summary tests)."""
    import routes.alerts as alert_routes

    alert_routes._alert_engine = None
    yield
    alert_routes._alert_engine = None


def _payload(ticker: str, **overrides):
    base = {
        "ticker": ticker,
        "spot_price": 500.0,
        "gamma_flip": 500.0,
        "call_wall": 520.0,
        "put_wall": 480.0,
        "max_pain": 500.0,
        "max_gamma_strike": 500.0,
        "total_gex": 1.0e9,
        "net_gex": 1.0e8,
        "regime": "POSITIVE",
        "gex_by_strike": {"500.0": 1.0e8},
    }
    base.update(overrides)
    return base


def _types(alerts):
    return [a.get("type") for a in alerts]


@pytest.mark.parametrize("value", ["inf", "-inf", 10 ** 400])
def test_nonfinite_momentum_uses_neutral_default(value):
    from routes.alerts import _parse_momentum_score
    assert _parse_momentum_score(value) == 50


def test_overflowed_strike_entry_does_not_drop_valid_entries():
    from routes.alerts import _parse_strike_map
    assert _parse_strike_map({"500": 10 ** 400, "505": 100}) == {505.0: 100.0}


class TestMomentumQueryPlumbing:
    def test_get_alerts_forwards_momentum_score(self, client):
        """momentum_score=95 through the API must surface MOMENTUM_EXTREME."""
        t = "PLUMB_MOM"
        r = client.post("/api/alerts/snapshot", json=_payload(t))
        assert r.status_code == 200, r.text

        r = client.get(f"/api/alerts/{t}", params={"momentum_score": 95})
        assert r.status_code == 200, r.text
        types = _types(r.json().get("alerts", []))
        assert "MOMENTUM_EXTREME" in types

    def test_get_alerts_default_momentum_fires_no_extreme(self, client):
        """Default path (no param) must not invent a momentum extreme."""
        t = "PLUMB_MOM_DEF"
        r = client.post("/api/alerts/snapshot", json=_payload(t))
        assert r.status_code == 200, r.text

        r = client.get(f"/api/alerts/{t}")
        assert r.status_code == 200, r.text
        assert "MOMENTUM_EXTREME" not in _types(r.json().get("alerts", []))


class TestSnapshotVolumePlumbing:
    def test_snapshot_volume_spike_reaches_detector(self, client):
        """Tripling near-spot contract volume across snapshots must fire VOLUME_SPIKE."""
        t = "PLUMB_VOL"
        r = client.post(
            "/api/alerts/snapshot",
            json=_payload(t, volume_by_strike={"500.0": 100, "505.0": 200}),
        )
        assert r.status_code == 200, r.text

        r = client.post(
            "/api/alerts/snapshot",
            json=_payload(t, volume_by_strike={"500.0": 100, "505.0": 800}),
        )
        assert r.status_code == 200, r.text
        assert "VOLUME_SPIKE" in _types(r.json().get("alerts", []))

    def test_snapshot_forwards_momentum_score(self, client):
        """momentum_score in the snapshot body must reach detect_alerts."""
        t = "PLUMB_SNAP_MOM"
        r = client.post(
            "/api/alerts/snapshot", json=_payload(t, momentum_score=95)
        )
        assert r.status_code == 200, r.text
        assert "MOMENTUM_EXTREME" in _types(r.json().get("alerts", []))
