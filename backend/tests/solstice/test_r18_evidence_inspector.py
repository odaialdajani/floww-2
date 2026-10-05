"""R18-C3: read-only recorder evidence inspector + outcome data sufficiency.

Isolated temp file-backed stores only; the inspector opens them read_only and
never imports server startup. A missing/unreadable store produces a useful
refusal, never a fabricated healthy census. Censored/missing outcomes stay
UNKNOWN — never zero losses or invented wins.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "backend")

import duckdb

from services.heatmap_history import (
    ensure_tables,
    record_decision,
    record_outcome,
    record_price_path,
    record_snapshot,
)
from services.solstice_evidence_inspector import INSPECTOR_VERSION, inspect_recorder_store


def test_missing_and_unreadable_stores_refuse_usefully(tmp_path):
    r = inspect_recorder_store(None)
    assert r["status"] == "refused" and r["reason"] == "STORE_PATH_REQUIRED"
    r = inspect_recorder_store(str(tmp_path / "nope.duckdb"))
    assert r["status"] == "refused" and r["reason"] == "STORE_MISSING"
    junk = tmp_path / "junk.duckdb"
    junk.write_text("not a duckdb file")
    r = inspect_recorder_store(str(junk))
    assert r["status"] == "refused" and r["reason"] == "STORE_UNREADABLE"


def _populated_store(path: Path) -> None:
    conn = duckdb.connect(str(path))
    ensure_tables(conn)
    # Price path: 5-minute cadence with ONE 15-minute gap.
    base = 1796431200.0
    for i, price in enumerate([600.0, 600.5, 601.0, 601.5]):
        assert record_price_path(conn, "SPY", base + 300.0 * i, price)
    assert record_price_path(conn, "SPY", base + 300.0 * 3 + 900.0, 602.0)
    # Decisions + one terminal and one censored outcome label.
    record_decision(conn, {"decision_id": "d1", "ticker": "SPY",
                           "scenario": "test", "side": "none",
                           "eligible": False, "reason_codes": ["TEST"],
                           "features": {"source": "synthetic"}})
    record_decision(conn, {"decision_id": "d2", "ticker": "SPY",
                           "scenario": "test", "side": "none",
                           "eligible": False, "reason_codes": ["TEST"],
                           "features": {"source": "synthetic"}})
    record_outcome(conn, "d1", "SPY", 900, "bounce", censored=False)
    record_outcome(conn, "d2", "SPY", 900, "censored_end", censored=True)
    # One owning range envelope (synthetic, built by the real producer so the
    # canonical content schema validates).
    import json as _json
    from datetime import date as _date
    from pathlib import Path as _P

    from services.heatmap_history import record_range_envelope
    from services.solstice_range_analytics import build_range_envelope, select_window_expiries
    fix = _P(__file__).parent / "fixtures" / "range_analytics_v1"
    listing = _json.loads((fix / "listing.json").read_text())
    chain = _json.loads((fix / "chain_complete.json").read_text())
    sel = select_window_expiries(listing["expiries"], 14, 60, _date(2026, 10, 5))
    env = build_range_envelope(symbol="SPY", min_dte=14, max_dte=60,
                               asof=_date(2026, 10, 5), listing=listing,
                               selection=sel, chain=chain)
    assert record_range_envelope(conn, env)["status"] == "recorded"
    conn.close()


def test_populated_store_census_and_limits(tmp_path):
    db = tmp_path / "store.duckdb"
    _populated_store(db)
    rep = inspect_recorder_store(str(db), ticker="SPY")
    assert rep["version"] == INSPECTOR_VERSION
    assert rep["status"] == "ok"
    assert rep["store"]["backing"] == "file" and rep["store"]["durable"] is True
    assert rep["tables"]["price_paths_v1"]["rows"] == 5
    assert rep["tables"]["scenario_decisions_v1"]["rows"] == 2
    assert rep["tables"]["range_analytics_envelopes_v1"]["rows"] == 1
    # Cadence truth: median 300s, exactly one >2x gap.
    cad = rep["price_paths"]["per_ticker"]["SPY"]
    assert cad["n_points"] == 5
    assert cad["median_gap_s"] == 300.0
    assert cad["n_gaps_gt_2x_median"] == 1
    assert cad["max_gap_s"] == 900.0
    assert "NOT an intraminute 0DTE" in rep["price_paths"]["cadence_note"]
    # Lineage: both decisions have labels → zero unlabelled; ranges censused.
    assert rep["lineage"]["n_decisions"] == 2
    assert rep["lineage"]["n_decisions_without_outcome"] == 0
    assert rep["range_analytics"]["envelopes"][0]["n"] == 1
    # Sufficiency: far below the 30-session target → INSUFFICIENT EVIDENCE.
    suf = rep["outcome_sufficiency"]
    assert suf["n_outcome_labels"] == 2
    assert suf["n_censored"] == 1
    assert suf["verdict"] == "INSUFFICIENT EVIDENCE"
    # Fixed limits stay attached to every report.
    assert any("not option P&L" in s for s in rep["limits"])
    # Read-only guarantee: the inspector opened read_only, so a writer can
    # immediately reuse the file and no new tables appear.
    conn = duckdb.connect(str(db))
    conn.close()
    rep2 = inspect_recorder_store(str(db))
    assert rep2["tables"]["price_paths_v1"]["rows"] == 5


def test_unlabelled_decisions_are_unknown_not_zero(tmp_path):
    db = tmp_path / "store2.duckdb"
    conn = duckdb.connect(str(db))
    ensure_tables(conn)
    record_decision(conn, {"decision_id": "dX", "ticker": "SPY",
                           "scenario": "t", "side": "none", "eligible": False,
                           "reason_codes": [], "features": {}})
    conn.close()
    rep = inspect_recorder_store(str(db))
    assert rep["lineage"]["n_decisions_without_outcome"] == 1
    assert "never zero losses" in rep["lineage"]["note"]
    assert rep["outcome_sufficiency"]["verdict"] == "INSUFFICIENT EVIDENCE"


def test_c8_ticker_scoping_and_classification(tmp_path):
    """Ticker scope applies to every census; synthetic never counts as real."""
    db = tmp_path / "store3.duckdb"
    conn = duckdb.connect(str(db))
    ensure_tables(conn)
    base = 1796431200.0
    for i in range(3):
        record_price_path(conn, "SPY", base + 300.0 * i, 600.0 + i,
                          "synthetic-fixture")
        record_price_path(conn, "QQQ", base + 300.0 * i, 500.0 + i,
                          "public-mid")
    for i in range(30):
        # 30 DISTINCT NY days of SYNTHETIC decisions + terminal labels.
        record_decision(conn, {"decision_id": f"syn{i}", "ticker": "SPY",
                               "scenario": "t", "side": "none",
                               "eligible": False, "reason_codes": [],
                               "features": {"synthetic": True,
                                            "source": "synthetic-fixture"}})
        conn.execute(
            "INSERT INTO outcome_labels_v1 "
            "(decision_id, ticker, horizon_s, label, label_version, at_ts, "
            "censored, detail, policy_version) VALUES ("
            f"'syn{i}', 'SPY', 900, 'bounce', 'outcome.v1', "
            f"'2026-08-{i % 28 + 1:02d}T14:00:00+00:00', 0, '{{}}', NULL)")
    record_decision(conn, {"decision_id": "q1", "ticker": "QQQ",
                           "scenario": "t", "side": "none", "eligible": False,
                           "reason_codes": [], "features": {"source": "public-mid"}})
    conn.execute(
        "INSERT INTO outcome_labels_v1 (decision_id, ticker, horizon_s, label, "
        "label_version, at_ts, censored, detail, policy_version) VALUES ("
        "'q1', 'QQQ', 900, 'flush', 'outcome.v1', "
        "'2026-10-01T14:00:00+00:00', 0, '{}', NULL)")
    # R18-C12: qualification ALSO needs actual owning snapshot evidence for
    # the scoped ticker on that NY day (2026-10-01 is an open XNYS session).
    record_snapshot(conn, {
        "ticker": "QQQ", "snapshot_id": "snap-q1-owning",
        "asof": "2026-10-01T14:00:00+00:00", "spot": 500.0,
        "contracts": [], "strikes": [], "walls": [], "metrics": {},
        "quality": {}, "scenarios": [], "interactions": [],
        "coverage": {}, "expiries_used": [], "data_source": "public-mid",
        "exposure_basis": "OI", "formula_version": "gex.v2"},
        "q1-owning", "snap-q1-owning")
    conn.close()

    rep_all = inspect_recorder_store(str(db))
    assert rep_all["price_paths"]["classification"]["synthetic"] == 3
    assert rep_all["price_paths"]["classification"]["production"] == 3
    suf = rep_all["outcome_sufficiency"]
    # 30 unqualified (synthetic) days must NOT yield sufficiency anywhere.
    assert suf["verdict"] == "INSUFFICIENT EVIDENCE"
    assert suf["n_sessions_observed_ny"] >= 28
    assert suf["n_qualified_sessions"] == 1  # only the QQQ production-linked day
    assert suf["n_unqualified_sessions"] >= 28

    rep_spy = inspect_recorder_store(str(db), ticker="SPY")
    assert rep_spy["price_paths"]["per_ticker"].get("QQQ") is None
    assert rep_spy["price_paths"]["classification"]["production"] == 0
    assert rep_spy["outcome_sufficiency"]["n_qualified_sessions"] == 0
    rep_qqq = inspect_recorder_store(str(db), ticker="QQQ")
    assert rep_qqq["outcome_sufficiency"]["n_qualified_sessions"] == 1
    assert rep_qqq["outcome_sufficiency"]["verdict"] == "INSUFFICIENT EVIDENCE"
