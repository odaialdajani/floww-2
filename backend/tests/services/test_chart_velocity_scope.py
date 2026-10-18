"""Recorded change rates must belong to the chart's exact known-at scope."""
import json
from types import SimpleNamespace

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.heatmap_history import compare_snapshots, ensure_tables

SCOPE = "q|expiries=2030-01-15|gex.v2|OI"
CUTOFF = "2030-01-02T10:02:00+00:00"


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    ensure_tables(connection)
    yield connection
    connection.close()


def save(conn, sid, at, gex=100, **changes):
    row = {"snapshot_id": sid, "ticker": "TST", "query_key": "q",
           "expiries": json.dumps(["2030-01-15"]), "spot": 500,
           "data_source": "public_api", "exposure_basis": "OI", "formula_version": "gex.v2",
           "asof_ts": at, "received_at": at,
           "strikes_json": json.dumps([{"strike": 500, "gex": gex, "volume": gex}]),
           "walls_json": "[]"}
    row.update(changes)
    columns = list(row)
    conn.execute(f"INSERT INTO heatmap_snapshots_v2 ({','.join(columns)}) "
                 f"VALUES ({','.join('?' for _ in columns)})", list(row.values()))


def test_legacy_pair_never_crosses_expiry_scope(conn):
    save(conn, "a", "2030-01-02T10:00:00+00:00")
    save(conn, "b", "2030-01-02T10:01:00+00:00", expiries='["2030-01-16"]')
    result = compare_snapshots(conn, "TST", "2030-01-02")
    assert result["status"] == "history_unavailable"
    assert "scope" in result["reason"]
    assert result["reason_code"] == "COMPARABLE_PAIR_MISSING"


def test_legacy_pair_finds_latest_scope_not_last_two_rows(conn):
    save(conn, "a", "2030-01-02T10:00:00+00:00", 100)
    save(conn, "other", "2030-01-02T10:01:00+00:00", 1000, query_key="other")
    save(conn, "b", "2030-01-02T10:02:00+00:00", 220)
    result = compare_snapshots(conn, "TST", "2030-01-02")
    assert result["from"]["id"] == "a"
    assert result["to"]["id"] == "b"
    assert result["velocities"][0]["velocity"] == pytest.approx(1)


@pytest.mark.parametrize("changed", [{"data_source": "legacy"}, {"formula_version": "gex.v3"},
                                      {"exposure_basis": "session_volume"}, {"data_source": None},
                                      {"formula_version": None}, {"exposure_basis": None}])
def test_changed_or_missing_provenance_cannot_form_pair(conn, changed):
    save(conn, "a", "2030-01-02T10:00:00+00:00")
    save(conn, "b", "2030-01-02T10:01:00+00:00", **changed)
    result = compare_snapshots(conn, "TST", "2030-01-02")
    assert result["status"] == "history_unavailable"
    assert result["reason_code"] == ("SCOPE_UNVERIFIED" if None in changed.values()
                                     else "COMPARABLE_PAIR_MISSING")


def test_selected_cutoff_excludes_future_and_late_receipts(conn):
    save(conn, "a", "2030-01-02T10:00:00+00:00", 100)
    save(conn, "b", "2030-01-02T10:01:00+00:00", 160)
    save(conn, "late", "2030-01-02T10:01:30+00:00", 400,
         received_at="2030-01-02T10:03:00+00:00")
    save(conn, "future", "2030-01-02T10:04:00+00:00", 1000)
    result = compare_snapshots(conn, "TST", "", query_key=SCOPE, as_of=CUTOFF)
    assert result["status"] == "ok"
    assert result["day"] == "2030-01-02"
    assert result["query_key"] == SCOPE
    assert result["as_of"] == CUTOFF
    assert result["from"]["id"] == "a"
    assert result["to"]["id"] == "b"
    assert result["from"]["query_key"] == result["to"]["query_key"] == SCOPE
    assert result["to"]["received_at"] == "2030-01-02T10:01:00+00:00"
    assert result["velocity_dt_seconds"] == 60
    assert result["velocities"][0]["velocity"] == pytest.approx(1)


@pytest.mark.parametrize("cutoff", ["", "nonsense", "2030-01-02T10:02:00", "inf", None])
def test_scoped_request_requires_valid_aware_cutoff(conn, cutoff):
    save(conn, "a", "2030-01-02T10:00:00+00:00")
    save(conn, "b", "2030-01-02T10:01:00+00:00")
    result = compare_snapshots(conn, "TST", "2030-01-02", query_key=SCOPE, as_of=cutoff)
    assert result["status"] == "history_unavailable"
    assert "as_of" in result["reason"]
    assert result["reason_code"] == "CUTOFF_INVALID"
    assert "velocities" not in result


def test_equal_observation_times_do_not_create_zero_interval_rate(conn):
    save(conn, "a", "2030-01-02T10:00:00+00:00")
    save(conn, "revision", "2030-01-02T10:00:00+00:00", 200,
         received_at="2030-01-02T10:01:00+00:00")
    assert compare_snapshots(conn, "TST", "2030-01-02")["status"] == "history_unavailable"


def test_invalid_receipt_and_observation_clocks_are_not_known_at(conn):
    save(conn, "a", "2030-01-02T10:00:00+00:00")
    save(conn, "b", "2030-01-02T10:01:00+00:00", received_at=None)
    save(conn, "c", "2030-01-02T10:01:30", received_at="2030-01-02T10:01:30+00:00")
    result = compare_snapshots(conn, "TST", "", query_key=SCOPE, as_of=CUTOFF)
    assert result["status"] == "history_unavailable"


def test_endpoint_derives_historical_utc_day_and_echoes_bound_scope(conn, monkeypatch):
    from routes.solstice import router
    from services import duckdb_engine
    monkeypatch.setattr(duckdb_engine, "db", SimpleNamespace(conn=conn))
    save(conn, "a", "2030-01-02T10:00:00+00:00", 100)
    save(conn, "b", "2030-01-02T10:01:00+00:00", 160)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        result = client.get("/api/solstice/attribute/TST", params={
            "query_key": SCOPE, "as_of": CUTOFF}).json()
        assert result["status"] == "ok"
        assert result["day"] == "2030-01-02"
        assert result["from"]["query_key"] == SCOPE
        refused = client.get("/api/solstice/attribute/TST", params={
            "query_key": SCOPE, "as_of": "2030-01-02T10:02:00"}).json()
        assert refused["status"] == "history_unavailable"
        assert "as_of" in refused["reason"]


@pytest.mark.parametrize("changes", [{"expiries": '["2030-01-15,2030-01-16"]'},
                                     {"expiries": '["not-a-date"]'},
                                     {"expiries": '[]'}, {"expiries": '{}'},
                                     {"query_key": ""}])
def test_unvalidated_recorded_scope_cannot_support_change_rates(conn, changes):
    save(conn, "a", "2030-01-02T10:00:00+00:00", **changes)
    save(conn, "b", "2030-01-02T10:01:00+00:00", **changes)
    result = compare_snapshots(conn, "TST", "2030-01-02")
    assert result["status"] == "history_unavailable"
    assert "scope" in result["reason"]
    assert result["reason_code"] == "SCOPE_UNVERIFIED"


@pytest.mark.parametrize(("seconds", "status"), [(900, "ok"), (901, "history_unavailable")])
def test_scoped_latest_observation_must_be_recent_at_candle(conn, seconds, status):
    from datetime import UTC, datetime, timedelta
    save(conn, "a", "2030-01-02T09:00:00+00:00", 100)
    save(conn, "b", "2030-01-02T10:00:00+00:00", 160,
         received_at="2030-01-02T10:14:00+00:00")
    cutoff = (datetime(2030, 1, 2, 10, tzinfo=UTC) + timedelta(seconds=seconds)).isoformat()
    result = compare_snapshots(conn, "TST", "", query_key=SCOPE, as_of=cutoff)
    assert result["status"] == status
    if status == "ok":
        assert result["from"]["asof"] == "2030-01-02T09:00:00+00:00"
        assert result["velocity_dt_seconds"] == 3600
    else:
        assert "stale" in result["reason"]
        assert result["reason_code"] == "OBSERVATION_STALE"
        assert "velocities" not in result


def test_cutoff_utc_day_handles_recorded_timezone_offsets(conn):
    save(conn, "a", "2030-01-01T19:59:00-05:00", 100)
    save(conn, "b", "2030-01-01T20:00:00-05:00", 160)
    result = compare_snapshots(conn, "TST", "", query_key=SCOPE,
                               as_of="2030-01-01T20:01:00-05:00")
    assert result["status"] == "ok"
    assert result["day"] == "2030-01-02"
    assert result["from"]["id"] == "a"
    assert result["to"]["id"] == "b"
    assert result["velocity_dt_seconds"] == 60


def test_supplied_day_cannot_redirect_bound_chart_to_another_session(conn):
    save(conn, "a", "2030-01-02T10:00:00+00:00")
    save(conn, "b", "2030-01-02T10:01:00+00:00")
    result = compare_snapshots(conn, "TST", "2030-01-03", query_key=SCOPE, as_of=CUTOFF)
    assert result["status"] == "history_unavailable"
    assert "day" in result["reason"]
    assert result["reason_code"] == "DAY_MISMATCH"


def test_as_of_only_request_enforces_same_freshness_bound(conn):
    save(conn, "a", "2030-01-02T09:59:00+00:00", 100)
    save(conn, "b", "2030-01-02T10:00:00+00:00", 200)
    result = compare_snapshots(conn, "TST", as_of="2030-01-02T10:15:01+00:00")
    assert result["status"] == "history_unavailable"
    assert result["reason_code"] == "OBSERVATION_STALE"


@pytest.mark.parametrize("bad", [None, True, "bad"])
def test_invalid_exposure_never_fabricates_a_zero_delta(conn, bad):
    save(conn, "a", "2030-01-02T10:00:00+00:00", 100)
    save(conn, "b", "2030-01-02T10:01:00+00:00", bad)
    result = compare_snapshots(conn, "TST", query_key=SCOPE, as_of=CUTOFF)
    assert result["status"] == "ok"
    assert result["strike_deltas"] == []
    assert result["velocities"] == []
