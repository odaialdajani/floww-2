"""C2-B served-level remainder (acting-OpenCode, 2026-10-23, lane
backend-lane-20261023 at frozen source 9b1d1179).

The 2026-10-22 C2-B evidence attested the three replay products as distinct
SOURCE mechanisms plus 36 focused unit regressions. What was still owed at
the served surface — and what this suite adds:

  * recorded-store bracketing via the real route reader (read_snapshots);
  * corrupt / late / foreign / out-of-age refusal discipline through the
    REAL focused-chart resolver (resolve_focused_chart) and the REAL
    /solstice/replay route coroutine (unknown id, quote-bearing id,
    recorder-unavailable);
  * expiry-scope selection refusals (next-listed bound + request_query
    combination refusals);
  * stored range-analytics replay through the actual router with its
    real status-code map (200 / 404 NO_RECORD / 422 DIGEST_MISMATCH,
    ROW_HEADER_MISMATCH, STORED_DIGEST_MISMATCH, CORRUPT_PAYLOAD).

Synthetic rows only. Isolated in-memory DuckDB. No provider, service,
port or user data is touched.
"""
import asyncio
import json
import sys
import types
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import duckdb
import pytest

_NY_DAY = "2026-10-21"

_ASOF_A = "2026-10-21T13:58:00+00:00"   # scope A, older revision
_RECV_A = "2026-10-21T13:58:30+00:00"
_ASOF_C = "2026-10-21T14:20:00+00:00"   # scope A, late receipt (event ok,
_RECV_C = "2026-10-21T14:50:00+00:00"   # receipt after cursor -> excluded)
_ASOF_B = "2026-10-21T14:28:00+00:00"   # scope A, freshest valid revision
_RECV_B = "2026-10-21T14:29:00+00:00"
_ASOF_F = "2026-10-21T14:29:30+00:00"   # FOREIGN scope, fresher than B
_RECV_F = "2026-10-21T14:29:50+00:00"


def _snap_conn():
    conn = duckdb.connect(":memory:")
    from services.heatmap_history import ensure_range_tables, ensure_tables
    ensure_tables(conn)
    ensure_range_tables(conn)
    return conn


def _snap_row(snapshot_id, ticker, query_key, asof, received, *,
              walls=None, strikes=None):
    return {
        "snapshot_id": snapshot_id, "ticker": ticker, "query_key": query_key,
        "expiries": json.dumps(["2026-11-20"]), "spot": 670.0,
        "data_source": "synthetic-test", "exposure_basis": "OI",
        "formula_version": "gex.v2", "asof_ts": asof, "received_at": received,
        "n_contracts": 1, "n_usable": 1, "digest": "digest-" + snapshot_id,
        "strikes_json": json.dumps(strikes or []),
        "walls_json": json.dumps(walls or []),
    }


def _insert_snap(conn, row):
    conn.execute(
        "INSERT INTO heatmap_snapshots_v2 (snapshot_id, ticker, query_key,"
        " expiries, spot, data_source, exposure_basis, formula_version,"
        " asof_ts, received_at, n_contracts, n_usable, digest, strikes_json,"
        " walls_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [row[c] for c in ("snapshot_id", "ticker", "query_key", "expiries",
                          "spot", "data_source", "exposure_basis",
                          "formula_version", "asof_ts", "received_at",
                          "n_contracts", "n_usable", "digest", "strikes_json",
                          "walls_json")])


def _seed_bracket(conn):
    """Two scope-A revisions, one scope-A late receipt, one foreign scope,
    one malformed clock, one foreign instrument."""
    _insert_snap(conn, _snap_row("snap-a", "SPY", "spy-day", _ASOF_A, _RECV_A))
    _insert_snap(conn, _snap_row("snap-foreign", "SPY", "other-scope-key",
                                 _ASOF_F, _RECV_F))
    _insert_snap(conn, _snap_row("snap-b", "SPY", "spy-day", _ASOF_B, _RECV_B))
    _insert_snap(conn, _snap_row("snap-late", "SPY", "spy-day", _ASOF_C,
                                 _RECV_C))
    _insert_snap(conn, _snap_row("snap-bad", "SPY", "spy-day", "broken",
                                 _RECV_A))
    _insert_snap(conn, _snap_row("snap-qqq", "QQQ", "spy-day", _ASOF_B,
                                 _RECV_B))


def _stub_engine(conn):
    def query_strict(sql, params):
        result = conn.execute(sql, params)
        names = [column[0] for column in result.description]
        return [dict(zip(names, row, strict=True)) for row in result.fetchall()]
    return SimpleNamespace(query_strict=query_strict)


def _duckdb_engine_module(conn=None):
    """A services.duckdb_engine stand-in the real route bodies import."""
    stub = types.ModuleType("services.duckdb_engine")
    stub.db = SimpleNamespace() if conn is None else SimpleNamespace(conn=conn)
    return stub


def _epoch(iso):
    from services.price_node_history import epoch
    value = epoch(iso)
    assert value is not None
    return float(value)


# --------------------------------------------------------------------------
# 1. Recorded-store bracket reader (real read_snapshots, real SQL bracket)
# --------------------------------------------------------------------------


def test_read_snapshots_bracket_filters_ticker_and_malformed_clock():
    from routes.price_history import read_snapshots
    conn = _snap_conn()
    _seed_bracket(conn)
    first = datetime(2026, 10, 21, 13, 30, tzinfo=UTC)
    last = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
    rows = read_snapshots(_stub_engine(conn), "SPY", first, last)
    ids = [row["snapshot_id"] for row in rows]
    # TRY_CAST bracket drops the malformed clock; the ticker filter drops
    # the QQQ row; everything else (both scopes) is returned asof-ordered:
    # snap-a 13:58, snap-late 14:20, snap-b 14:28, snap-foreign 14:29:30.
    assert ids == ["snap-a", "snap-late", "snap-b", "snap-foreign"], ids


def test_read_snapshots_strikes_column_fallback_keeps_rows_serving():
    """A legacy store whose table predates strikes_json: the real reader's
    first SQL genuinely raises on the real engine, and the real except
    branch re-queries without the column — rows keep serving, exposure
    centres simply stay null."""
    from routes.price_history import read_snapshots
    legacy = duckdb.connect(":memory:")
    # Hand-built pre-strikes_json schema (mirrors the takeover test's
    # legacy-table construction):
    legacy.execute("CREATE TABLE heatmap_snapshots_v2 (snapshot_id VARCHAR,"
                   " ticker VARCHAR, query_key VARCHAR, expiries VARCHAR,"
                   " formula_version VARCHAR, exposure_basis VARCHAR,"
                   " asof_ts VARCHAR, received_at VARCHAR, walls_json VARCHAR)")
    legacy.execute("INSERT INTO heatmap_snapshots_v2 VALUES"
                   " ('legacy-1','SPY','spy-day','[]','gex.v2','OI',"
                   "'2026-10-21T13:58:00+00:00',"
                   "'2026-10-21T13:58:30+00:00','[]')")
    first = datetime(2026, 10, 21, 13, 30, tzinfo=UTC)
    last = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
    rows = read_snapshots(_stub_engine(legacy), "SPY", first, last)
    assert [r["snapshot_id"] for r in rows] == ["legacy-1"], rows
    assert all("strikes_json" not in r for r in rows), rows


# --------------------------------------------------------------------------
# 2. Focused-chart served refusals (real resolve_focused_chart)
# --------------------------------------------------------------------------


def _resolve_case_rows():
    conn = _snap_conn()
    _seed_bracket(conn)
    def query(sql, params):
        result = conn.execute(sql, params)
        names = [column[0] for column in result.description]
        return [dict(zip(names, row, strict=True)) for row in result.fetchall()]
    return conn, query


def test_focused_chart_serves_freshest_revision_at_cursor_and_keeps_scopes_apart():
    from services.chart_context import resolve_focused_chart as resolve
    from services.price_node_history import scope_id
    conn, _ = _resolve_case_rows()
    from routes.price_history import read_snapshots
    first = datetime(2026, 10, 21, 13, 30, tzinfo=UTC)
    last = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
    # Real bracket reader feeds the real resolver — the served composition.
    rows = read_snapshots(_stub_engine(conn), "SPY", first, last)
    scope_a = scope_id(rows[0])           # rows[0] is snap-a (scope spy-day)
    out = resolve(rows, focus="SPY", scope=scope_a,
                  cursor=_epoch(_ASOF_B) + 150)
    assert out["status"] == "available", out
    # The freshest valid scope-A revision is served; the FRESHER foreign
    # scope row (14:29:30) never crosses the scope boundary; the late
    # receipt (14:20 event / 14:50 receipt > cursor) is never knowable.
    assert out["snapshot_id"] == "snap-b", out
    assert out["received_at"] == _RECV_B
    assert out["node_age_seconds"] == 150, out
    assert out["gaps"] == ["recorded_without_nodes",
                           "recorded_without_strikes"], out
    # snap-late's asof is 14:20 <= cursor but its receipt is 14:50: it is
    # neither chosen nor a silent gap-of-data; snap-b still owns the serve.
    assert out["snapshot_id"] != "snap-late"


def test_focused_chart_refuses_unrecorded_scope_and_foreign_focus():
    from services.chart_context import resolve_focused_chart as resolve
    from services.price_node_history import scope_id
    conn, _ = _resolve_case_rows()
    from routes.price_history import read_snapshots
    first = datetime(2026, 10, 21, 13, 30, tzinfo=UTC)
    last = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
    rows = read_snapshots(_stub_engine(conn), "SPY", first, last)
    out = resolve(rows, focus="SPY", scope="scope-never-recorded",
                  cursor=_epoch(_ASOF_B) + 120)
    assert out == {"status": "refused", "reason": "scope_not_recorded"}, out
    # All-QQQ window with an SPY focus: the focus is not in the saved scope.
    qqq_rows = [r for r in [_snap_row("snap-qqq-2", "QQQ", "qqq-only",
                                      _ASOF_B, _RECV_B)]]
    scope_qqq = scope_id(qqq_rows[0])
    out = resolve(qqq_rows, focus="SPY", scope=scope_qqq,
                  cursor=_epoch(_ASOF_B) + 120)
    assert out["status"] == "refused"
    assert out["reason"] == "focus is not recorded in the saved scope"


def test_focused_chart_counts_malformed_clock_as_gap_not_crash():
    from services.chart_context import resolve_focused_chart as resolve
    from services.price_node_history import scope_id
    # Resolver input is route-shaped rows: include one malformed clock
    # directly (reader brackets normally exclude it earlier).
    good = _snap_row("snap-g", "SPY", "spy-day", _ASOF_A, _RECV_A)
    malformed = _snap_row("snap-m", "SPY", "spy-day", "broken", _RECV_A)
    rows = [good, malformed]
    out = resolve(rows, focus="SPY", scope=scope_id(good),
                  cursor=_epoch(_ASOF_A) + 60)
    assert out["status"] == "available" and out["snapshot_id"] == "snap-g"
    assert "malformed_recorded_clock" in out["gaps"], out


# --------------------------------------------------------------------------
# 2b. Focused-chart cursor refusals (typed) — continued
# --------------------------------------------------------------------------


def test_focused_chart_cursor_refusals_are_typed_and_safe():
    from services.chart_context import resolve_focused_chart as resolve
    from services.price_node_history import scope_id
    conn, _ = _resolve_case_rows()
    from routes.price_history import read_snapshots
    first = datetime(2026, 10, 21, 13, 30, tzinfo=UTC)
    last = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
    rows = read_snapshots(_stub_engine(conn), "SPY", first, last)
    scope_a = scope_id(rows[0])
    out = resolve(rows, focus="SPY", scope=scope_a, cursor=None)
    assert out == {"status": "refused", "reason": "incomplete binding"}
    out = resolve(rows, focus="SPY", scope=scope_a, cursor=True)
    assert out == {"status": "refused", "reason": "invalid cursor"}
    out = resolve(rows, focus="SPY", scope=scope_a, cursor=-5)
    assert out == {"status": "refused", "reason": "invalid cursor"}
    # Cursor before every clock: honest not-yet-recorded, never zeros.
    out = resolve(rows, focus="SPY", scope=scope_a,
                  cursor=_epoch(_ASOF_A) - 1)
    assert out["status"] == "unavailable"
    assert out["reason"] == ("recorded scope exists but nothing was known "
                             "at this cursor; not yet recorded")
    # Out of the recorded node age cap: the observation is unavailable at
    # this cursor (stale), never re-projected from present-day chains.
    out = resolve(rows, focus="SPY", scope=scope_a,
                  cursor=_epoch(_ASOF_B) + 901)
    assert out["status"] == "unavailable"
    assert "out of age" in out["reason"] and "(901s)" in out["reason"], out


# --------------------------------------------------------------------------
# 3. /solstice/replay served route: known, unknown, corrupt-id, no-recorder
# --------------------------------------------------------------------------


def _run_replay_route(monkeypatch, snapshot_id, conn):
    monkeypatch.setitem(sys.modules, "services.duckdb_engine",
                        _duckdb_engine_module(conn))
    import routes.solstice
    return asyncio.run(routes.solstice.replay(snapshot_id))


def test_solstice_replay_route_returns_recorded_content_for_known_id():
    monkeypatch = pytest.MonkeyPatch()
    try:
        conn = _snap_conn()
        _seed_bracket(conn)
        conn.execute(
            "INSERT INTO contract_observations_v2 (snapshot_id, ticker, osi,"
            " expiry, strike, opt_type, multiplier, bid, ask, last, bid_ts,"
            " ask_ts, last_ts, received_at, volume, oi,oi_effective_date,"
            " iv, delta, gamma, theta, vega, greeks_source, provider,"
            " exposure_basis, calculated_at) VALUES"
            " ('snap-a','SPY','SPY261120C00670000','2026-11-20',670.0,'C',"
            "100.0, 1.0, 1.2, 1.1, '2026-10-21T13:58:00+00:00',"
            "'2026-10-21T13:58:00+00:00','2026-10-21T13:58:00+00:00',"
            "'2026-10-21T13:58:30+00:00', 10.0, 5000.0, '2026-11-20',"
            "0.30, 0.5, -0.001, 0.02, 0.05, 'synthetic','synthetic-test',"
            "'OI','2026-10-21T13:58:30+00:00')")
        out = _run_replay_route(monkeypatch, "snap-a", conn)
        assert out["snapshot"]["snapshot_id"] == "snap-a", out
        assert out["replay_note"].startswith("available-at join"), out
        # The recorded join is exactly the snapshot's own rows: no later
        # revision (snap-b) and no foreign scope merge.
        assert [c["osi"] for c in out["contracts"]] == [
            "SPY261120C00670000"], out
        assert out["walls"] == []
    finally:
        monkeypatch.undo()


def test_solstice_replay_route_refuses_unknown_and_quote_id_without_corruption():
    monkeypatch = pytest.MonkeyPatch()
    try:
        conn = _snap_conn()
        _seed_bracket(conn)
        before = conn.execute(
            "SELECT count(*) FROM heatmap_snapshots_v2").fetchone()[0]
        out = _run_replay_route(monkeypatch, "never-recorded-id", conn)
        assert out == {"snapshot_id": "never-recorded-id",
                       "error": "not_found"}, out
        # A quote-bearing id must never corrupt the store query or rows.
        out = _run_replay_route(monkeypatch, "x'--", conn)
        assert out == {"snapshot_id": "x'--", "error": "not_found"}, out
        after = conn.execute(
            "SELECT count(*) FROM heatmap_snapshots_v2").fetchone()[0]
        assert before == after == 6
    finally:
        monkeypatch.undo()


def test_solstice_replay_route_names_recorder_unavailable_not_not_found():
    monkeypatch = pytest.MonkeyPatch()
    try:
        # No conn on the engine stand-in: the route names the recorder
        # unavailable instead of fabricating a not_found (different truth).
        out = _run_replay_route(monkeypatch, "snap-a", None)
        assert out == {"snapshot_id": "snap-a",
                       "error": "recorder_unavailable"}, out
    finally:
        monkeypatch.undo()


# --------------------------------------------------------------------------
# 4. Expiry scope selection: next-listed bound + request_query refusals
# --------------------------------------------------------------------------


def test_next_listed_selection_picks_earliest_within_inclusive_bound():
    from services.solstice_scope import next_listed_selection
    selection = next_listed_selection(
        [{"expiry": "2026-11-08"}, {"expiry": "2026-11-20"},
         {"expiry": " 2026-11-25 "}, {"expiry": None},
         {"expiry": "not-a-date"}], "2026-10-21")
    assert selection["kind"] == "next"
    assert selection["selected_expiries"] == ["2026-11-08"], selection
    assert selection["invalid_listed_dates"] == 3, selection
    assert selection["status"] == "ok" and selection["reason"] is None
    # 30-day bound is inclusive of the boundary date:
    edge = next_listed_selection([{"expiry": "2026-11-20"}], "2026-10-21")
    assert edge["selected_expiries"] == ["2026-11-20"], edge


def test_next_listed_selection_names_unavailability_without_fabrication():
    from services.solstice_scope import next_listed_selection
    out = next_listed_selection([], "2026-10-21")
    assert out["status"] == "unavailable"
    assert out["reason"] == "NO_LISTED_EXPIRY_IN_BOUND"
    assert out["selected_expiries"] == []


def test_request_query_refuses_consumers_of_next_scope():
    from services.solstice_scope import request_query
    with pytest.raises(ValueError):
        request_query([], "day", 5, False, [], 10, expiry_scope="next",
                      session_date="2026-10-21")
    with pytest.raises(ValueError):
        request_query([], "swing", None, False, [], 10, expiry_scope="next",
                      session_date="2026-10-21")
    with pytest.raises(ValueError):
        request_query([], "day", None, True, [], 10, expiry_scope="next",
                      session_date="2026-10-21")
    with pytest.raises(ValueError):
        request_query([], "day", None, False, [], 10, expiry_scope="bogus")
    query = request_query(["2026-11-20"], "day", None, False, [], 10,
                          expiry_scope="next", session_date="2026-10-21")
    assert query["expiryScope"] == "next"
    assert query["sessionDate"] == "2026-10-21"
    # The loaded scope (default) keeps the legacy query identity exact:
    loaded = request_query(["2026-11-20"], "day", None, False, [], 10)
    assert "expiryScope" not in loaded and "sessionDate" not in loaded


# --------------------------------------------------------------------------
# 5. Stored range replay through the REAL router: 200 / 404 / 422 map
# --------------------------------------------------------------------------


def _valid_range_envelope():
    from services.solstice_range_analytics import CONTENT_SCHEMA, compute_content_digest, record_id_for_digest
    envelope = {
        "version": "range-analytics.v1",
        "status": "ok",
        "symbol": "SPY",
        "query": {"min_dte": 14, "max_dte": 60, "as_of_ny": _NY_DAY},
        "axes": {"window": "14-60 DTE"},
        "grids": {"raw_oi": {"cells": {"500": [1.0, 2.0]}}},
        "metric_registry": {"raw_oi": {"unit": "delta-dollars"}},
        "clocks": {"received_at": "2026-10-21T14:00:00+00:00"},
        "coverage": {"requested": 2, "returned": 2},
        "provenance": {"source": "synthetic-test"},
        "content_schema": CONTENT_SCHEMA,
    }
    digest = compute_content_digest(envelope)
    envelope["content_digest"] = digest
    envelope["record_id"] = record_id_for_digest(digest)
    return envelope


def _range_client(monkeypatch, conn):
    monkeypatch.setitem(sys.modules, "services.duckdb_engine",
                        _duckdb_engine_module(conn))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes import solstice_price_paths
    app = FastAPI()
    app.include_router(solstice_price_paths.router)
    return TestClient(app)


def test_range_record_replay_restores_exact_stored_envelope_200():
    monkeypatch = pytest.MonkeyPatch()
    try:
        conn = _snap_conn()
        envelope = _valid_range_envelope()
        from services.heatmap_history import record_range_envelope
        stored = record_range_envelope(conn, envelope)
        assert stored.get("status") != "refused", stored
        client = _range_client(monkeypatch, conn)
        response = client.get(
            f"/api/solstice/price-paths/range-records/{envelope['record_id']}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ok" and body["integrity"] == "verified"
        assert body["record_id"] == envelope["record_id"]
        assert body["window"] == {"min_dte": 14, "max_dte": 60}
        assert body["replay_note"].startswith("exact stored envelope restored")
        assert body["envelope"] == envelope
    finally:
        monkeypatch.undo()


def test_range_record_replay_404_for_unknown_identity():
    monkeypatch = pytest.MonkeyPatch()
    try:
        conn = _snap_conn()
        client = _range_client(monkeypatch, conn)
        response = client.get(
            "/api/solstice/price-paths/range-records/rga1-notarealrecord")
        assert response.status_code == 404, response.text
        assert response.json()["reason"] == "NO_RECORD"
    finally:
        monkeypatch.undo()


def test_range_record_replay_422_map_for_tampered_rows():
    monkeypatch = pytest.MonkeyPatch()
    try:
        conn = _snap_conn()
        envelope = _valid_range_envelope()
        from services.heatmap_history import record_range_envelope
        stored = record_range_envelope(conn, envelope)
        assert stored.get("status") != "refused", stored
        rid = envelope["record_id"]
        client = _range_client(monkeypatch, conn)

        # (a) payload tamper keeping the in-payload digest claim:
        payload = json.loads(json.dumps(envelope))
        payload["grids"]["raw_oi"]["cells"]["500"] = [9.9, 9.9]
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ?"
            " WHERE record_id = ?",
            [json.dumps(payload), rid])
        response = client.get(
            f"/api/solstice/price-paths/range-records/{rid}")
        assert response.status_code == 422, response.text
        assert response.json()["reason"] == "DIGEST_MISMATCH"
        # restore exact bytes for the next header case
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ?"
            " WHERE record_id = ?", [json.dumps(envelope), rid])

        # (b) row header tamper: stored ticker disagrees with the payload
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET ticker = 'QQQ'"
            " WHERE record_id = ?", [rid])
        response = client.get(
            f"/api/solstice/price-paths/range-records/{rid}")
        assert response.status_code == 422, response.text
        assert response.json()["reason"] == "ROW_HEADER_MISMATCH"
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET ticker = 'SPY'"
            " WHERE record_id = ?", [rid])

        # (c) stored digest column tamper (payload itself untouched):
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET digest = '0'"
            " WHERE record_id = ?", [rid])
        response = client.get(
            f"/api/solstice/price-paths/range-records/{rid}")
        assert response.status_code == 422, response.text
        assert response.json()["reason"] == "STORED_DIGEST_MISMATCH"
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET digest = ?"
            " WHERE record_id = ?", [envelope["content_digest"], rid])

        # (d) corrupt payload bytes are a typed refusal, never a crash:
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = '{no'"
            " WHERE record_id = ?", [rid])
        response = client.get(
            f"/api/solstice/price-paths/range-records/{rid}")
        assert response.status_code == 422, response.text
        assert response.json()["reason"] == "CORRUPT_PAYLOAD"
    finally:
        monkeypatch.undo()
