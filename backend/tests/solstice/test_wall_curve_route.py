"""Mounted read for the recorded same-wall curve.

The route is the consumer half of `recorded-wall-curve.v1`: it serves stored
observations of one raw wall in one declared scope and refuses an undeclared
scope. It never calls a provider, never recomputes and never forward-fills.

Seeding goes through the real recorder seam on an isolated ticker.
"""

import sys

import pytest

sys.path.insert(0, "backend")

TICKER = "WCV"
QUERY_KEY = "WCV|4|day|None|False"
WALL = {"wall_id": "w_route_curve", "low": 500.0, "high": 510.0, "mid": 505.0,
        "members": [500.0, 505.0, 510.0], "exposure_basis": "OI",
        "formula_version": "gex.v2"}


def _entry(**overrides):
    entry = {"daddex_net": 1500.0, "daddex_gross": 3000.0,
             "daddex_usable": 3, "daddex_missing": 0, "daddex_invalid": 0,
             "n_contracts": 3, "unreadable_strike": 0, "not_a_member": 0}
    entry.update(overrides)
    return entry


def _seed():
    from services.duckdb_engine import db as eng
    from services.heatmap_history import record_snapshot

    conn = eng.conn
    for snapshot_id, asof in (("wcv-obs-1", "2030-01-02T15:00:05+00:00"),
                              ("wcv-obs-2", "2030-01-02T15:05:05+00:00")):
        received = asof.replace("05+00:00", "02+00:00")
        record_snapshot(conn, {
            "ticker": TICKER,
            "asof": asof,
            "source_received_at": received,
            "event_time": received,
            "spot": 500.0,
            "contracts": [],
            "strikes": [{"strike": 500.0, "gex": 1000.0}],
            "metrics": {"walls": [WALL],
                        "wall_metrics": {WALL["wall_id"]: _entry()}},
            "quality": {},
            "scenarios": [],
            "interactions": [],
            "coverage": {"requested": 3, "returned": 3, "truncated": False},
            "expiries_used": ["2030-01-19"],
            "data_source": "public_api",
            "exposure_basis": "OI",
            "formula_version": "gex.v2",
        }, QUERY_KEY, snapshot_id)
    return conn


def _client():
    from fastapi.testclient import TestClient

    from server import app

    return TestClient(app, raise_server_exceptions=False)


def test_route_serves_the_stored_same_wall_curve():
    _seed()
    r = _client().get(f"/api/solstice/wall-curve/{TICKER}",
                      params={"wall_id": WALL["wall_id"], "query_key": QUERY_KEY})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == "recorded-wall-curve.v1"
    assert body["status"] == "ok"
    assert [point["observation_id"] for point in body["points"]] == ["wcv-obs-1", "wcv-obs-2"]
    assert body["points"][0]["value"] == pytest.approx(1500.0)
    assert body["series_key"]["wall_id"] == WALL["wall_id"]
    assert body["series_key"]["metric_id"] == "dadgex_net_v1"


def test_route_refuses_an_undeclared_scope():
    _seed()
    r = _client().get(f"/api/solstice/wall-curve/{TICKER}",
                      params={"wall_id": WALL["wall_id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "history_unavailable"
    assert body["reason"] == "SCOPE_UNVERIFIED"
    assert body["points"] == []


def test_route_never_answers_with_another_wall():
    _seed()
    r = _client().get(f"/api/solstice/wall-curve/{TICKER}",
                      params={"wall_id": "w_not_recorded", "query_key": QUERY_KEY})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "history_unavailable"
    assert body["reason"] == "WALL_NOT_PRESENT"
    assert body["points"] == []


def test_route_requires_a_wall_id():
    r = _client().get(f"/api/solstice/wall-curve/{TICKER}",
                      params={"query_key": QUERY_KEY})
    assert r.status_code == 422, r.text
