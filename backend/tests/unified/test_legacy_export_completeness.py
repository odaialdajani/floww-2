"""U10: legacy decision export/import evidence — isolated copies only.

No live store, no service restart, no import into the original research DB.
The batch document shape below mirrors what a verified export must contain;
the parent exporter script is verified separately by its exact filename and its
digest contract here.
"""
import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from services.legacy_decision_recovery import import_summaries, load_export


def make_row(did, ticker="AAA", at="2026-09-04T15:00:00+00:00", nq=3):
    return {
        "decision_id": did, "ticker": ticker, "at_ts": at,
        "snapshot_id": "snap-" + did, "scenario": "s", "side": "buy",
        "eligible": True, "reason_codes": ["r1"], "features": {"k": 1},
        "n_quotes": nq, "outcome_labels": "win", "review_state": None,
    }


def make_export(tmp_path, rows_by_ticker):
    doc = []
    for ticker, rows in rows_by_ticker.items():
        doc.append({"path": f"/api/solstice/{ticker}/decisions", "status": 200,
                    "body": {"ticker": ticker, "decisions": rows, "count": len(rows)}})
    path = tmp_path / "export.json"
    path.write_bytes(json.dumps(doc).encode())
    return str(path), hashlib.sha256(path.read_bytes()).hexdigest()


def test_import_reopen_verify_and_quote_truth(tmp_path):
    src, digest = make_export(tmp_path, {"AAA": [make_row("d1"), make_row("d2")]})
    db = tmp_path / "copy.duckdb"
    conn = duckdb.connect(str(db))  # isolated synthetic copy
    result = import_summaries(conn, src, expected_sha256=digest)
    conn.execute("CHECKPOINT")
    conn.close()
    # complete-count + digest truth from the receipt itself
    assert result["inserted"] == 2
    assert result["quote_details_recovered"] == 0  # import can never restore quotes
    assert result["source_sha256"] == digest
    # independently reopen the destination and re-verify contents
    check = duckdb.connect(str(db), read_only=True)
    rows = check.execute("SELECT decision_id, summary_sha256, summary_json "
                         "FROM legacy_decision_summaries_v1 ORDER BY decision_id").fetchall()
    check.close()
    assert [r[0] for r in rows] == ["d1", "d2"]
    for _, digest_col, raw in rows:
        assert hashlib.sha256(raw.encode()).hexdigest() == digest_col


def test_import_is_atomic_and_refuses_conflicts_and_bad_digests(tmp_path):
    src, digest = make_export(tmp_path, {"AAA": [make_row("d1")]})
    # wrong digest refuses before any store is opened
    with pytest.raises(ValueError):
        load_export(src, expected_sha256="0" * 64)
    conn = duckdb.connect(str(tmp_path / "copy.duckdb"))
    conn.execute("CREATE TABLE scenario_decisions_v1 (decision_id VARCHAR, ticker VARCHAR)")
    conn.execute("INSERT INTO scenario_decisions_v1 VALUES ('d1', 'OTHER')")
    # native identity conflict -> typed refusal, zero rows inserted
    with pytest.raises(ValueError):
        import_summaries(conn, src, expected_sha256=digest)
    conn.execute("CHECKPOINT")
    leftover = conn.execute("SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_name = 'legacy_decision_summaries_v1'").fetchone()[0]
    if leftover:
        assert conn.execute("SELECT COUNT(*) FROM legacy_decision_summaries_v1").fetchone()[0] == 0
    conn.close()


def test_duplicate_input_and_missing_decisions_refused(tmp_path):
    # duplicate identical rows are counted, not double-imported
    row = make_row("d1")
    src, digest = make_export(tmp_path, {"AAA": [row, dict(row)]})
    batch = load_export(src, expected_sha256=digest)
    assert batch["duplicate_input"] == 1
    assert len(batch["rows"]) == 1
    # conflicting duplicate identity within one source refuses
    bad = make_row("d1", nq=9)
    src2, digest2 = make_export(tmp_path, {"AAA": [row, bad]})
    with pytest.raises(ValueError):
        load_export(src2, expected_sha256=digest2)
    # non-decision / non-200 responses refuse
    weird = tmp_path / "weird.json"
    weird.write_bytes(json.dumps([{"path": "/api/x", "status": 500, "body": {}}]).encode())
    with pytest.raises(ValueError):
        load_export(str(weird), expected_sha256=hashlib.sha256(weird.read_bytes()).hexdigest())


def test_malformed_stored_json_is_counted_not_silently_normalized(tmp_path):
    """Takeover addition: malformed reason_codes JSON exports with [] and is
    counted in the receipt instead of vanishing silently."""
    import subprocess
    import sys

    seed = duckdb.connect(str(tmp_path / "copy.duckdb"))
    seed.execute("CREATE TABLE scenario_decisions_v1 (decision_id VARCHAR, ticker VARCHAR, "
                 "at_ts VARCHAR, snapshot_id VARCHAR, scenario VARCHAR, side VARCHAR, "
                 "eligible BOOLEAN, reason_codes VARCHAR, features VARCHAR)")
    seed.execute("INSERT INTO scenario_decisions_v1 VALUES "
                 "('d1','AAA','2026-09-04T15:00:00+00:00','snap-d1','s','buy',TRUE,'broken{{{','{\"k\":1}')")
    seed.execute("CHECKPOINT")
    seed.close()
    out = tmp_path / "export.json"
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_legacy_decisions.py"
    run = subprocess.run(
        [sys.executable, str(script), "--database", str(tmp_path / "copy.duckdb"),
         "--out", str(out)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    receipt = json.loads(run.stdout)
    assert receipt["rows"] == 1 and receipt["normalized_rows"] == 1
    exported = json.loads(out.read_text())
    assert exported[0]["body"]["decisions"][0]["reason_codes"] == []


def test_missing_exporter_is_an_explicit_gap_not_silent_completion():
    """The U10 exporter write-path must exist before any completeness claim."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_legacy_decisions.py"
    assert script.is_file(), (
        "export_legacy_decisions.py is absent: no completeness receipt can be "
        "produced; U10 stays open on full source-store access"
    )


def test_export_import_roundtrip_on_isolated_copy(tmp_path):
    """Build a synthetic stopped-store copy, export it fully, re-import into a
    fresh isolated copy, and verify exact identities/digests both ways."""
    import hashlib as _h
    import subprocess
    import sys

    seed = duckdb.connect(str(tmp_path / "original_copy.duckdb"))
    seed.execute("CREATE TABLE scenario_decisions_v1 (decision_id VARCHAR, ticker VARCHAR, "
                 "at_ts VARCHAR, snapshot_id VARCHAR, scenario VARCHAR, side VARCHAR, "
                 "eligible BOOLEAN, reason_codes VARCHAR, features VARCHAR)")
    seed.execute("CREATE TABLE candidate_quotes_v1 (decision_id VARCHAR, osi VARCHAR)")
    seed.execute("INSERT INTO scenario_decisions_v1 VALUES "
                 "('d1','AAA','2026-09-04T15:00:00+00:00','snap-d1','s','buy',TRUE,'[\"r1\"]','{\"k\":1}'),"
                 "('d2','AAA','2026-09-04T16:00:00+00:00','snap-d2','s','sell',FALSE,'[]','{}'),"
                 "('e1','BBB','2026-09-04T15:30:00+00:00','snap-e1','s','buy',TRUE,'[]','{}')")
    seed.execute("INSERT INTO candidate_quotes_v1 VALUES ('d1','Q1'),('d1','Q2')")
    seed.execute("CHECKPOINT")
    seed.close()

    out = tmp_path / "export.json"
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_legacy_decisions.py"
    run = subprocess.run(
        [sys.executable, str(script), "--database", str(tmp_path / "original_copy.duckdb"),
         "--out", str(out)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    receipt = json.loads(run.stdout)
    assert receipt["rows"] == 3 and receipt["tickers"] == 2
    assert receipt["quote_table_present"] is True and receipt["review_table_present"] is False

    dest = duckdb.connect(str(tmp_path / "dest_copy.duckdb"))
    result = import_summaries(dest, str(out), expected_sha256=receipt["sha256"])
    dest.close()
    assert result["inserted"] == 3
    assert result["quote_details_recovered"] == 0  # no fabrication, ever
    recheck = duckdb.connect(str(tmp_path / "dest_copy.duckdb"), read_only=True)
    got = recheck.execute("SELECT decision_id, ticker, at_ts FROM legacy_decision_summaries_v1 "
                          "ORDER BY decision_id").fetchall()
    recheck.close()
    assert [g[0] for g in got] == ["d1", "d2", "e1"]
    # d1 carried its real quote COUNT through the summary, but quote rows
    # themselves were not recovered and are never claimed recovered
    recheck2 = duckdb.connect(str(tmp_path / "dest_copy.duckdb"), read_only=True)
    raw = recheck2.execute("SELECT summary_json FROM legacy_decision_summaries_v1 "
                           "WHERE decision_id = 'd1'").fetchone()[0]
    recheck2.close()
    assert json.loads(raw)["n_quotes"] == 2
