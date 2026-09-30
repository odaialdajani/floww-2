"""S5: the contract-detail ROUTE is the production caller (Spark).

The resolver tested in isolation proves nothing about delivery. This
exercises the real HTTP endpoint end to end, including the rule that
matters most: a wall midpoint or a first-expiry guess is refused, not
answered.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

duckdb = pytest.importorskip("duckdb")

NOW = datetime.now(UTC)
AGO = (NOW - timedelta(seconds=30)).isoformat()


def _c(osi, strike, expiry, otype="call"):
    return {"osi": osi, "strike": strike, "expiry": expiry, "type": otype,
            "bid": 1.00, "ask": 1.10, "last": 1.05,
            "bid_timestamp": AGO, "ask_timestamp": AGO, "last_timestamp": AGO,
            "oi": 100, "volume": 10, "gamma": 0.01, "delta": 0.5, "multiplier": 100,
            "data_source": "public_api"}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """One TestClient for the module.

    A per-test TestClient opens a new event loop each time, and the app's
    module-level connection/recorder locks bind to the first loop that uses
    them, so a second loop raises "bound to a different event loop". The
    store is isolated per module, not per test, and never the live one.
    """
    from fastapi.testclient import TestClient

    import routes.solstice_review  # noqa: F401  (registers the review routes)
    import server
    from services import duckdb_engine
    from services.heatmap_history import ensure_tables, record_snapshot

    store = tmp_path_factory.mktemp("contract_identity") / "store.duckdb"
    conn = duckdb.connect(str(store))
    try:
        ensure_tables(conn)
        record_snapshot(conn, {
            "ticker": "SPY", "spot": 300.0, "asof": NOW.isoformat(),
            "source_received_at": NOW.isoformat(), "data_source": "public_api",
            "exposure_basis": "OI", "formula_version": "gex.v2",
            "expiries_used": ["2030-02-21"], "strikes": [], "grid": {},
            "contracts": [
                _c("A-300-C", "300", "2030-02-21"),
                _c("A-300-P", "300", "2030-02-21", "put"),
                _c("A-300.25-C", "300.25", "2030-02-21"),
            ],
            "metrics": {}, "coverage": {"requested": 3, "returned": 3, "usable": 3,
                                        "truncated": False},
        }, "SPY:day:0:60")
    finally:
        conn.close()

    handle = _reopen(str(store))
    original = getattr(duckdb_engine.db, "_conn", None)
    duckdb_engine.db._conn = handle
    try:
        # `TestClient(app)` WITHOUT the context-manager form. Entering the
        # `with` block runs the app's startup events, which launch the
        # scheduler and _warm_default_heatmaps, and that reaches
        # api.public.com for real. This route test needs a request handler,
        # not a running application, so startup is deliberately not run -
        # the same convention every other route test in this repo uses.
        yield TestClient(server.app)
    finally:
        duckdb_engine.db._conn = original
        handle.close()


def _reopen(path: str):
    conn = duckdb.connect(path)
    from services.heatmap_history import ensure_tables

    ensure_tables(conn)
    return conn


def test_exact_osi_resolves_through_the_route(client):
    r = client.get("/api/solstice/SPY/contract", params={"osi": "A-300.25-C"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["matched_identity"]["strike"] == "300.25"
    assert body["snapshot_id"]
    assert body["quote"]["spread_absolute"] is not None
    # The recorded quote timestamp is fixed at import, so in a long run the
    # age is minutes rather than seconds. What is under test is that the
    # age is REPORTED and is positive, not that it sits in a wall-clock
    # window - a fixed upper bound made this fail only in the full suite.
    age = body["quote"]["ages_s"]["bid"]
    assert age is not None and age > 0, body["quote"]
    assert body["quote"]["age_reasons"]["bid"] is None
    assert body["quote"]["side_has_aggressor_identity"] is False


def test_strike_expiry_type_resolves_through_the_route(client):
    r = client.get("/api/solstice/SPY/contract",
                   params={"strike": 300, "expiry": "2030-02-21", "type": "put"})
    body = r.json()
    assert body["status"] == "ok"
    assert body["matched_identity"]["osi"] == "A-300-P"


def test_wall_midpoint_is_refused_by_the_route(client):
    r = client.get("/api/solstice/SPY/contract",
                   params={"strike": 300.5, "expiry": "2030-02-21", "type": "call"})
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "NO_MATCH"
    assert body["quote"] is None


def test_incomplete_identity_is_refused_with_a_usable_message(client):
    r = client.get("/api/solstice/SPY/contract", params={"strike": 300})
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "IDENTITY_INCOMPLETE"
    assert "midpoint" in body["note"]
    bare = client.get("/api/solstice/SPY/contract").json()
    assert bare["reason"] == "IDENTITY_INCOMPLETE"


def test_route_carries_the_observed_request_scope(client):
    body = client.get("/api/solstice/SPY/contract", params={"osi": "A-300-C"}).json()
    scope = body["scope"]
    assert scope["expiries_requested"] == 4
    assert scope["is_true_zero_dte"] is False
    assert scope["refreshes_periodically"] is False
    assert scope["window_basis_enabled"] is False


def test_unknown_ticker_is_a_reason_not_a_guess(client):
    body = client.get("/api/solstice/ZZZZ/contract", params={"osi": "A-300-C"}).json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "NO_RECORDED_SNAPSHOT"
