"""Recover actual exported summaries without inventing quote details or dates."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    from services.heatmap_history import ensure_tables
    ensure_tables(connection)
    yield connection
    connection.close()


def summary(identity="old-saved", ticker="SPY", at="2026-09-27T22:53:26.867301+00:00", **changes):
    return {"decision_id": identity, "ticker": ticker, "at_ts": at,
            "snapshot_id": "original-snapshot", "scenario": "CALLS", "side": "CALLS",
            "eligible": False, "reason_codes": ["ORIGINAL_REASON"],
            "features": {"spot": 432.1, "zone": [430, 435]}, "n_quotes": 20,
            "outcome_labels": "", "review_state": None, **changes}


def source(tmp_path, rows, *, ticker="SPY", name="legacy.json"):
    document = [{"path": f"/api/solstice/{ticker}/decisions?limit=200", "status": 200,
                 "body": {"ticker": ticker, "decisions": rows, "count": len(rows),
                          "checked_at": "2026-10-06T09:48:00Z"}}]
    file = tmp_path / name
    file.write_text(json.dumps(document, allow_nan=False), encoding="utf-8")
    return file, hashlib.sha256(file.read_bytes()).hexdigest()


def recover(connection, file, digest):
    from services.legacy_decision_recovery import import_summaries
    return import_summaries(connection, file, expected_sha256=digest)


def page(connection, ticker="SPY", **kwargs):
    from services.solstice_decision_history import decision_page
    return decision_page(connection, ticker, **kwargs)


def add_native(connection, identity, at="2026-10-07T04:00:00Z", ticker="SPY"):
    connection.execute("INSERT INTO scenario_decisions_v1 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       [identity, ticker, at, "native-snapshot", "PUTS", "PUTS", True,
                        '["NATIVE_REASON"]', '{"spot": 500}'])


def legacy_count(connection):
    return connection.execute("SELECT COUNT(*) FROM legacy_decision_summaries_v1").fetchone()[0]


def test_original_values_survive_in_a_separate_summary_table(conn, tmp_path):
    original = summary()
    file, digest = source(tmp_path, [original])
    result = recover(conn, file, digest)
    assert result["inserted"] == 1 and result["already_present"] == 0
    row = conn.execute("SELECT decision_id, ticker, at_ts, snapshot_id, summary_json, summary_sha256, "
                       "source_sha256, source_file, imported_at FROM legacy_decision_summaries_v1").fetchone()
    assert row[:4] == ("old-saved", "SPY", original["at_ts"], "original-snapshot")
    assert json.loads(row[4]) == original
    assert row[5] == hashlib.sha256(row[4].encode()).hexdigest()
    assert row[6] == digest and row[7] == str(file.resolve()) and row[8]
    assert conn.execute("SELECT COUNT(*) FROM scenario_decisions_v1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM candidate_quotes_v1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM decision_reviews_v1").fetchone()[0] == 0


def test_repeating_the_same_summary_is_a_noop_without_rewriting_provenance(conn, tmp_path):
    file, digest = source(tmp_path, [summary()])
    recover(conn, file, digest)
    before = conn.execute("SELECT * FROM legacy_decision_summaries_v1").fetchall()
    assert recover(conn, file, digest)["already_present"] == 1
    different_file, different_digest = source(tmp_path, [summary()], name="another-copy.json")
    assert recover(conn, different_file, different_digest)["already_present"] == 1
    assert legacy_count(conn) == 1
    assert conn.execute("SELECT * FROM legacy_decision_summaries_v1").fetchall() == before


def test_conflicting_existing_identity_refuses_the_entire_new_batch(conn, tmp_path):
    file, digest = source(tmp_path, [summary()])
    recover(conn, file, digest)
    before = conn.execute("SELECT * FROM legacy_decision_summaries_v1").fetchall()
    bad_file, bad_digest = source(tmp_path, [summary("new-one"), summary(features={"spot": 999})], name="conflict.json")
    with pytest.raises(ValueError, match="conflict"):
        recover(conn, bad_file, bad_digest)
    assert conn.execute("SELECT * FROM legacy_decision_summaries_v1").fetchall() == before


def test_exact_duplicates_within_source_collapse_and_conflicts_do_not_write(conn, tmp_path):
    file, digest = source(tmp_path, [summary(), summary()])
    assert recover(conn, file, digest)["inserted"] == 1
    assert legacy_count(conn) == 1
    other = duckdb.connect(":memory:")
    try:
        conflict, sha = source(tmp_path, [summary(), summary(eligible=True)], name="batch-conflict.json")
        with pytest.raises(ValueError, match="conflict"):
            recover(other, conflict, sha)
        assert other.execute("SHOW TABLES").fetchall() == []
    finally:
        other.close()


@pytest.mark.parametrize("at", [None, "unknown", "2026-09-27T22:53:26", "2026-02-30T14:00:00Z",
                                "20261006T140000Z", "2026-10-06x14:00:00Z"])
def test_invalid_clock_in_later_record_refuses_all_rows_before_writing(tmp_path, at):
    connection = duckdb.connect(":memory:")
    try:
        file, digest = source(tmp_path, [summary("good"), summary("bad", at=at)])
        with pytest.raises(ValueError):
            recover(connection, file, digest)
        assert connection.execute("SHOW TABLES").fetchall() == []
    finally:
        connection.close()


def test_mismatched_ticker_and_unexpected_private_fields_cannot_enter_history(conn, tmp_path):
    for rows in ([summary("good"), summary("bad", ticker="QQQ")], [summary(owner="private-owner")]):
        file, digest = source(tmp_path, rows)
        with pytest.raises(ValueError):
            recover(conn, file, digest)
        assert "legacy_decision_summaries_v1" not in [row[0] for row in conn.execute("SHOW TABLES").fetchall()]


@pytest.mark.parametrize("digest", [None, "", "not-a-digest", "0" * 64])
def test_matching_whole_source_digest_is_required_before_writing(conn, tmp_path, digest):
    file, _ = source(tmp_path, [summary()])
    with pytest.raises(ValueError):
        recover(conn, file, digest)
    assert "legacy_decision_summaries_v1" not in [row[0] for row in conn.execute("SHOW TABLES").fetchall()]


def test_database_failure_rolls_back_new_summary_rows(conn, tmp_path):
    from services.legacy_decision_recovery import LEGACY_TABLE_DDL
    conn.execute(LEGACY_TABLE_DDL.replace("decision_id VARCHAR PRIMARY KEY",
                                         "decision_id VARCHAR PRIMARY KEY CHECK (decision_id != 'fail')"))
    file, digest = source(tmp_path, [summary("good"), summary("fail")])
    with pytest.raises(RuntimeError):
        recover(conn, file, digest)
    assert legacy_count(conn) == 0


def test_recovered_summary_is_accessible_but_never_claims_physical_quotes(conn, tmp_path):
    original = summary()
    file, digest = source(tmp_path, [original])
    recover(conn, file, digest)
    result = page(conn, order="oldest")
    row = result["decisions"][0]
    assert row["decision_id"] == original["decision_id"] and row["at_ts"] == original["at_ts"]
    assert row["features"] == original["features"] and row["eligible"] is False
    assert row["reason_codes"] == original["reason_codes"]
    assert row["quote_status"] == "summary_only" and row["n_quotes"] is None
    assert row["reported_n_quotes"] == 20 and row["recovery_source"]["source_sha256"] == digest
    assert row["snapshot_status"] == "unavailable"
    assert result["status"] == "partial"


def test_native_records_win_same_identity_without_changing_either_source(conn, tmp_path):
    file, digest = source(tmp_path, [summary("overlap"), summary("only-summary")])
    recover(conn, file, digest)
    add_native(conn, "overlap")
    native_before = conn.execute("SELECT * FROM scenario_decisions_v1").fetchall()
    archive_before = conn.execute("SELECT * FROM legacy_decision_summaries_v1").fetchall()
    result = page(conn, order="oldest")
    assert len(result["decisions"]) == 2
    native = next(row for row in result["decisions"] if row["decision_id"] == "overlap")
    assert native["features"] == {"spot": 500} and native["eligible"] is True
    assert native["quote_status"] == "available" and native["n_quotes"] == 0
    assert conn.execute("SELECT * FROM scenario_decisions_v1").fetchall() == native_before
    assert conn.execute("SELECT * FROM legacy_decision_summaries_v1").fetchall() == archive_before


def test_paging_filters_and_clock_order_cover_native_and_recovered_records(conn, tmp_path):
    rows = [summary(f"legacy-{index:03}", at="2026-10-06T09:00:00-04:00") for index in range(241)]
    file, digest = source(tmp_path, rows)
    recover(conn, file, digest)
    add_native(conn, "native-before", at="2026-10-06T12:00:00Z")
    add_native(conn, "native-after", at="2026-10-06T14:00:00Z")
    cursor = None
    seen = []
    for _ in range(10):
        result = page(conn, order="oldest", limit=67, cursor=cursor)
        seen.extend(row["decision_id"] for row in result["decisions"])
        if not result["has_more"]:
            break
        cursor = result["next_cursor"]
    assert seen == ["native-before", *[f"legacy-{index:03}" for index in range(241)], "native-after"]
    assert len(set(seen)) == 243
    conn.execute("INSERT INTO decision_reviews_v1 VALUES (?, ?, ?, ?, ?)",
                 ["legacy-005", "reviewed", None, None, "2026-10-06T14:00:00Z"])
    reviewed = page(conn, state="reviewed")
    assert [row["decision_id"] for row in reviewed["decisions"]] == ["legacy-005"]


def test_optional_archive_absence_does_not_create_tables_or_hide_native_rows(conn):
    add_native(conn, "normal")
    before = conn.execute("SHOW TABLES").fetchall()
    assert page(conn)["decisions"][0]["decision_id"] == "normal"
    assert conn.execute("SHOW TABLES").fetchall() == before


def test_real_page_route_opens_restored_september_reading_without_orders(conn, tmp_path, monkeypatch):
    import sys

    from routes.solstice_review import register_review_routes
    file, digest = source(tmp_path, [summary()])
    recover(conn, file, digest)
    add_native(conn, "latest")
    monkeypatch.setitem(sys.modules, "services.duckdb_engine", SimpleNamespace(db=SimpleNamespace(conn=conn)))
    router = APIRouter(prefix="/api/solstice")
    register_review_routes(router)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/solstice/SPY/decisions/page", params={"order": "oldest", "limit": 1})
    assert response.status_code == 200, response.text
    assert response.json()["decisions"][0]["at_ts"].startswith("2026-09-27")
    assert response.json()["decisions"][0]["n_quotes"] is None
    assert conn.execute("SELECT COUNT(*) FROM execution_events_v1").fetchone()[0] == 0


def test_synthetic_mixed_stock_export_recovers_every_summary_without_quotes(conn, tmp_path):
    document = []
    for ticker, count in (("SPY", 200), ("QQQ", 2), ("IWM", 4)):
        rows = [summary(f"fixture-{ticker}-{index:03}", ticker=ticker, at="2026-09-27T22:53:32.571039+00:00")
                for index in range(count)]
        document.append({"path": f"/api/solstice/{ticker}/decisions?limit=200", "status": 200,
                         "body": {"ticker": ticker, "decisions": rows, "count": count}})
    file = tmp_path / "synthetic-mixed-stock.json"
    file.write_text(json.dumps(document, allow_nan=False), encoding="utf-8")
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    result = recover(conn, file, digest)
    assert result["inserted"] == 206
    assert conn.execute("SELECT ticker, COUNT(*) FROM legacy_decision_summaries_v1 GROUP BY ticker ORDER BY ticker").fetchall() == [("IWM", 4), ("QQQ", 2), ("SPY", 200)]
    assert conn.execute("SELECT COUNT(*) FROM candidate_quotes_v1").fetchone()[0] == 0
    assert page(conn, "QQQ", order="oldest")["decisions"][0]["at_ts"] == "2026-09-27T22:53:32.571039+00:00"


def test_offline_command_requires_expected_digest_before_opening_target(conn, tmp_path, monkeypatch):
    file, _ = source(tmp_path, [summary()])
    script = Path(__file__).resolve().parents[2] / "scripts" / "import_legacy_decision_summaries.py"
    spec = importlib.util.spec_from_file_location("legacy_import_command_under_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(duckdb, "connect", lambda *args, **kwargs: calls.append((args, kwargs)))
    result = module.main(["--source", str(file), "--expected-sha256", "0" * 64,
                          "--database", str(tmp_path / "missing.duckdb")])
    assert result != 0 and calls == []
    with pytest.raises(SystemExit):
        module.main(["--source", str(file), "--database", str(tmp_path / "missing.duckdb")])


@pytest.mark.parametrize("labels", [None, ""])
def test_recovered_outcome_absence_stays_distinct_from_empty(conn, tmp_path, labels):
    file, digest = source(tmp_path, [summary(outcome_labels=labels)])
    recover(conn, file, digest)
    assert page(conn)["decisions"][0]["outcome_labels"] == labels
