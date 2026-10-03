"""R17 read-only coverage routes: sessions, expiries, comparable.

No writes by the routes under test; seeds go straight to the store through
the real recorder seam on isolated ZZZ tickers. No broker calls (chain fetch
is monkeypatched); no activation."""

import sys

sys.path.insert(0, "backend")


def _snap(conn, sid, ticker, asof):
    from services.heatmap_history import record_snapshot

    return record_snapshot(conn, {
        "ticker": ticker, "snapshot_id": sid, "asof": asof, "spot": 500.0,
        "contracts": [], "strikes": [], "walls": [], "metrics": {},
        "quality": {}, "scenarios": [], "interactions": [],
        "coverage": {}, "expiries_used": [], "data_source": "t",
        "exposure_basis": "OI", "formula_version": "gex.v2"}, "q", sid)


def _seed_zzz():
    from services.duckdb_engine import db as eng

    conn = eng.conn
    _snap(conn, "s-zzz-day1", "ZZZ", "2030-01-02T15:00:00+00:00")
    _snap(conn, "s-zzz-day1b", "ZZZ", "2030-01-02T18:00:00+00:00")
    _snap(conn, "s-zzz-day2", "ZZZ", "2030-01-03T15:00:00+00:00")
    _snap(conn, "s-zzy-day1", "ZZY", "2030-01-02T15:00:00+00:00")


def test_sessions_enumerates_stored_days():
    from fastapi.testclient import TestClient

    from server import app

    _seed_zzz()
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/solstice/price-paths/sessions", params={"ticker": "ZZZ"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ticker"] == "ZZZ" and body["n_days"] == 2
    assert [d["date"] for d in body["days"]] == ["2030-01-02", "2030-01-03"]
    assert [d["n_snapshots"] for d in body["days"]] == [2, 1]
    assert body["days"][0]["latest_snapshot_id"] == "s-zzz-day1b"


def test_sessions_unknown_ticker_is_empty_not_error():
    from fastapi.testclient import TestClient

    from server import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/solstice/price-paths/sessions", params={"ticker": "ZZQ"})
    assert r.status_code == 200, r.text
    assert r.json() == {"version": "coverage-read.v1", "ticker": "ZZQ", "days": [], "n_days": 0}


def test_comparable_admits_matching_pair_and_refuses_mismatch():
    from fastapi.testclient import TestClient

    from server import app

    _seed_zzz()
    client = TestClient(app, raise_server_exceptions=False)
    ok = client.get("/api/solstice/price-paths/comparable",
                    params={"baseline_id": "s-zzz-day1", "snapshot_id": "s-zzz-day1b"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["admitted"] is True
    cross = client.get("/api/solstice/price-paths/comparable",
                       params={"baseline_id": "s-zzz-day1", "snapshot_id": "s-zzy-day1"})
    assert cross.json()["admitted"] is False
    assert cross.json()["reason"] == "TICKER_MISMATCH"
    missing = client.get("/api/solstice/price-paths/comparable",
                         params={"baseline_id": "s-nope", "snapshot_id": "s-zzz-day1"})
    assert missing.json() == {"admitted": False, "reason": "NO_BASELINE",
                              "detail": "baseline s-nope not stored",
                              "version": "coverage-read.v1"}


def test_comparable_refuses_session_roll_and_reversal():
    from fastapi.testclient import TestClient

    from server import app

    _seed_zzz()
    client = TestClient(app, raise_server_exceptions=False)
    roll = client.get("/api/solstice/price-paths/comparable",
                      params={"baseline_id": "s-zzz-day1", "snapshot_id": "s-zzz-day2"})
    assert roll.json()["reason"] == "SESSION_ROLL"
    rev = client.get("/api/solstice/price-paths/comparable",
                     params={"baseline_id": "s-zzz-day1b", "snapshot_id": "s-zzz-day1"})
    assert rev.json()["reason"] == "SOURCE_OUT_OF_ORDER"


def test_expiries_admits_window_with_reasons():
    from datetime import datetime, timedelta
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from server import app
    from services import public_api_adapter as ada

    today = datetime.now(ZoneInfo("America/New_York")).date()

    past = (today - timedelta(days=400)).isoformat()
    zero = today.isoformat()
    inside = (today + timedelta(days=20)).isoformat()
    above = (today + timedelta(days=200)).isoformat()

    async def fake_chain(ticker, max_expiries=6):
        return {"ticker": ticker, "spot": 500.0, "fetched_at": "2026-10-02T15:59:00+00:00",
                "stale": False, "expiries": [past, zero, inside, above]}

    with patch.object(ada, "fetch_chain_from_public_api", side_effect=fake_chain):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/solstice/price-paths/expiries",
                       params={"ticker": "SPY", "min_dte": 14, "max_dte": 60})
    assert r.status_code == 200, r.text
    body = r.json()
    by_exp = {row["expiry"]: row for row in body["expiries"]}
    assert by_exp[past]["reason"] == "EXPIRED"
    assert by_exp[zero]["reason"] == "BELOW_WINDOW"  # 0DTE kept, not admitted
    assert by_exp[inside]["admitted"] is True
    assert by_exp[above]["reason"] == "ABOVE_WINDOW"
    assert body["n_admitted"] == 1
    assert body["version"] == "coverage-read.v1"


def test_expiries_vendor_unavailable_is_502():
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from server import app
    from services import public_api_adapter as ada

    with patch.object(ada, "fetch_chain_from_public_api", return_value=None):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/solstice/price-paths/expiries", params={"ticker": "SPY"})
    assert r.status_code == 502, r.text


def test_sessions_prefix_attribution_with_overnight_offset():
    from fastapi.testclient import TestClient

    from server import app
    from services.duckdb_engine import db as eng

    _seed_zzz()
    _snap(eng.conn, "s-zzz-night1", "ZZZ", "2030-01-06T02:00:00+00:00")
    _snap(eng.conn, "s-zzz-night1b", "ZZZ", "2030-01-06T15:00:00+00:00")
    _snap(eng.conn, "s-zzz-naive", "ZZZ", "2030-01-07T00:30:00")
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/solstice/price-paths/sessions", params={"ticker": "ZZZ"})
    assert r.status_code == 200, r.text
    body = r.json()
    by_day = {d["date"]: d for d in body["days"]}
    # Prefix attribution is canonical (the same day key session_manifest
    # matches with LIKE day%): the 02:00Z stamp crosses ET midnight but stays
    # on its stored prefix day. Mixed ET attribution discloses ny_date null.
    night = by_day["2030-01-06"]
    assert night["n_snapshots"] == 2
    assert night["overnight"] is True
    assert night["ny_date"] is None  # 21:00 ET prior day + 10:00 ET same day
    naive = by_day["2030-01-07"]
    # Naive stamps adopt the owning UTC convention: 00:30 naive is 19:30 ET on
    # the prior day — offset disclosed, prefix day unchanged.
    assert naive["overnight"] is True
    assert naive["ny_date"] == "2030-01-06"
    assert naive["n_snapshots"] == 1
    # ET-local stamps agree with the prefix and never flag overnight.
    assert by_day["2030-01-02"]["overnight"] is False
    assert by_day["2030-01-02"]["ny_date"] == "2030-01-02"


def test_expiries_refuses_reversed_bounds_before_fetch():
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from server import app
    from services import public_api_adapter as ada

    with patch.object(ada, "fetch_chain_from_public_api") as mock_chain:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/solstice/price-paths/expiries",
                       params={"ticker": "SPY", "min_dte": 60, "max_dte": 14})
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "REVERSED_WINDOW"
    assert r.json()["version"] == "coverage-read.v1"
    mock_chain.assert_not_called()


def test_expiries_projects_display_envelope_and_coverage():
    from datetime import datetime, timedelta
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from server import app
    from services import public_api_adapter as ada

    today = datetime.now(ZoneInfo("America/New_York")).date()
    near = (today + timedelta(days=10)).isoformat()
    inside = (today + timedelta(days=20)).isoformat()
    mid = (today + timedelta(days=45)).isoformat()
    far = (today + timedelta(days=90)).isoformat()

    async def fake_chain(ticker, max_expiries=12):
        return {"ticker": ticker, "spot": 500.0, "fetched_at": "2026-10-03T00:00:00+00:00",
                "stale": False, "expiries": [near, inside, mid, far]}

    with patch.object(ada, "fetch_chain_from_public_api", side_effect=fake_chain):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/solstice/price-paths/expiries",
                       params={"ticker": "SPY", "min_dte": 14, "max_dte": 60})
    assert r.status_code == 200, r.text
    body = r.json()
    by_exp = {row["expiry"]: row for row in body["expiries"]}
    # Owning display envelope (dte le=30) projected per row — a DIFFERENT
    # constraint from the admitted 14–60 policy window (near is below the
    # policy window yet still inside the display envelope).
    assert by_exp[near]["admitted"] is False
    assert by_exp[near]["display_envelope"] is True
    assert by_exp[inside]["display_envelope"] is True
    assert by_exp[mid]["display_envelope"] is False
    assert by_exp[far]["display_envelope"] is False
    cov = body["coverage"]
    assert body["n_admitted"] == 2
    assert cov["n_listed"] == 4
    assert cov["n_display_envelope"] == 2
    assert cov["lower_edge_observed"] is True
    assert cov["upper_edge_observed"] is True
    assert cov["listing_capped"] is False
