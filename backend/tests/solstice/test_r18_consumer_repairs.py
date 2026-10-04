"""R18-C11: consumer-review repairs (Zed qualification-HOLD findings).

Failed-first pins for every defect in the 2026-10-04 PR106 review: the
metrics summary outside the canonical digest (rga-content.v3), duplicate
writes not validating the stored payload's own identity, the replay wrapper
not binding status/received-at headers, index/retrieve verdict divergence
and the NULL-window TypeError, borrowed vendor-gamma populations mis-stating
the BS raw surface, cold _get_broker auth/accounts preceding a denied debit,
inspector prefix/paper classification + envelope-integrity/cap/timezone
truth, and the metadata-only replay fixture. Deterministic; no network.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "backend")

import duckdb

import services.public_api_adapter as adapter
from services.heatmap_history import (
    ensure_range_tables,
    list_range_envelopes,
    record_range_envelope,
    replay_range_envelope,
)
from services.solstice_evidence_inspector import inspect_recorder_store
from services.solstice_range_analytics import (
    CONTENT_SCHEMA,
    build_range_envelope,
    select_window_expiries,
)

FIXTURES = Path(__file__).parent / "fixtures" / "range_analytics_v1"
TODAY = date(2026, 10, 5)
DOCS_FIXTURES = Path(__file__).resolve().parents[3] / "docs/solstice/r18/fixtures"


def _env(**chain_over):
    listing = json.loads((FIXTURES / "listing.json").read_text())
    chain = json.loads((FIXTURES / "chain_complete.json").read_text())
    chain.update(chain_over)
    sel = select_window_expiries(listing["expiries"], 14, 60, TODAY)
    return build_range_envelope(symbol="SPY", min_dte=14, max_dte=60,
                                asof=TODAY, listing=listing, selection=sel,
                                chain=chain)


def _recorded(conn, **kw):
    env = _env(**kw)
    res = record_range_envelope(conn, env)
    assert res["status"] == "recorded", res
    return env


def _update_payload(conn, env, payload):
    conn.execute("UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
                 "WHERE record_id = ?", [json.dumps(payload), env["record_id"]])


def _contracts():
    return json.loads((FIXTURES / "chain_complete.json").read_text())["contracts"]


def _legacy_tables(conn):
    from services.heatmap_history import ensure_tables as _et
    _et(conn)
    return conn


# ── C11-1: the metrics summary is inside the canonical digest ──────────────

def test_c11_metrics_summary_is_digest_bound():
    assert CONTENT_SCHEMA == "rga-content.v3"
    conn = duckdb.connect(":memory:")
    try:
        env = _recorded(conn)
        # Tamper ONLY the derived summary: a partial metric relabeled
        # admitted. Under rga-content.v2 this kept a valid digest.
        tampered = json.loads(json.dumps(env))
        tampered["metrics"]["admitted"] = ["raw_oi", "delta_weighted",
                                           "volume", "window"]
        tampered["metrics"]["partial"] = []
        _update_payload(conn, env, tampered)
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["error"] == "DIGEST_MISMATCH", rep
        idx = list_range_envelopes(conn, ticker="SPY")
        assert idx["rows"][0]["integrity"] == "refused:DIGEST_MISMATCH"
    finally:
        conn.close()


def test_c11_v2_payloads_are_refused_not_upgraded():
    conn = duckdb.connect(":memory:")
    try:
        env = _recorded(conn)
        legacy = json.loads(json.dumps(env))
        legacy["content_schema"] = "rga-content.v2"
        _update_payload(conn, env, legacy)
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["error"] == "INCOMPATIBLE_CONTENT_SCHEMA", rep
        res = record_range_envelope(conn, legacy)
        assert res["status"] == "refused"
        assert res["reason"] == "INCOMPATIBLE_CONTENT_SCHEMA"
    finally:
        conn.close()


# ── C11-2: duplicate write validates the STORED payload's own identity ────

def test_c11_duplicate_write_validates_stored_identity():
    conn = duckdb.connect(":memory:")
    try:
        env = _recorded(conn)
        # The content digest excludes record_id: tamper ONLY the stored
        # payload's record_id field (digest column + content stay equal). A
        # duplicate write of the SAME envelope must refuse — the stored
        # record's own identity no longer derives from its digest.
        tampered = json.loads(json.dumps(env))
        tampered["record_id"] = "rga1-000000000000000000000000"
        _update_payload(conn, env, tampered)
        res = record_range_envelope(conn, env)
        assert res["status"] == "refused", res
        assert res["reason"] == "STORED_RECORD_CORRUPT", res
        assert res.get("stored_defect") == "RECORD_ID_MISMATCH"
    finally:
        conn.close()


# ── C11-3: replay binds status + received_at; NULL window is typed ────────

def test_c11_replay_binds_status_and_received_headers():
    conn = duckdb.connect(":memory:")
    try:
        env = _recorded(conn)
        rid = env["record_id"]
        conn.execute("UPDATE range_analytics_envelopes_v1 SET status = "
                     "'partial' WHERE record_id = ?", [rid])
        rep = replay_range_envelope(conn, rid)
        assert rep["error"] == "ROW_HEADER_MISMATCH", rep
        conn.execute("UPDATE range_analytics_envelopes_v1 SET status = ? "
                     "WHERE record_id = ?", [env["status"], rid])
        conn.execute("UPDATE range_analytics_envelopes_v1 SET received_at = "
                     "'1999-01-01T00:00:00+00:00' WHERE record_id = ?", [rid])
        rep = replay_range_envelope(conn, rid)
        assert rep["error"] == "ROW_HEADER_MISMATCH", rep
    finally:
        conn.close()


def test_c11_null_window_is_typed_refusal():
    conn = duckdb.connect(":memory:")
    try:
        env = _recorded(conn)
        rid = env["record_id"]
        conn.execute("UPDATE range_analytics_envelopes_v1 SET window_min = "
                     "NULL WHERE record_id = ?", [rid])
        # A NULL window must be a typed refusal — never an int(None) TypeError.
        rep = replay_range_envelope(conn, rid)
        assert isinstance(rep, dict) and rep["error"] == "ROW_HEADER_MISMATCH"
        idx = list_range_envelopes(conn, ticker="SPY")
        assert idx["rows"][0]["integrity"] == "refused:ROW_HEADER_MISMATCH"
    finally:
        conn.close()


# ── C11-4: index and replay verdicts can never disagree ───────────────────

def test_c11_index_and_replay_verdicts_agree():
    conn = duckdb.connect(":memory:")
    try:
        clean = _recorded(conn)
        listing = json.loads((FIXTURES / "listing.json").read_text())
        chain = json.loads((FIXTURES / "chain_complete.json").read_text())
        # Row A: cell tamper -> DIGEST_MISMATCH in BOTH index and replay.
        sel_a = select_window_expiries(listing["expiries"], 14, 59, TODAY)
        env_a = build_range_envelope(symbol="SPY", min_dte=14, max_dte=59,
                                     asof=TODAY, listing=listing,
                                     selection=sel_a, chain=chain)
        assert record_range_envelope(conn, env_a)["status"] == "recorded"
        tampered_cell = json.loads(json.dumps(env_a))
        tampered_cell["grids"]["raw_oi"]["cells"]["2026-10-26"]["590"] = 9.0
        _update_payload(conn, env_a, tampered_cell)
        # Row B: foreign ticker header -> ROW_HEADER_MISMATCH in BOTH.
        sel_b = select_window_expiries(listing["expiries"], 15, 60, TODAY)
        env_b = build_range_envelope(symbol="SPY", min_dte=15, max_dte=60,
                                     asof=TODAY, listing=listing,
                                     selection=sel_b, chain=chain)
        assert record_range_envelope(conn, env_b)["status"] == "recorded"
        conn.execute("UPDATE range_analytics_envelopes_v1 SET ticker = 'QQQ' "
                     "WHERE record_id = ?", [env_b["record_id"]])
        # Row C: stored digest header tamper -> STORED_DIGEST_MISMATCH both.
        env_c = build_range_envelope(symbol="QQQ", min_dte=14, max_dte=60,
                                     asof=TODAY, listing=listing,
                                     selection=select_window_expiries(
                                         listing["expiries"], 14, 60, TODAY),
                                     chain=chain)
        assert record_range_envelope(conn, env_c)["status"] == "recorded"
        conn.execute("UPDATE range_analytics_envelopes_v1 SET digest = "
                     "'deadbeef' WHERE record_id = ?", [env_c["record_id"]])
        for env_x in (env_a, env_b, env_c):
            rep = replay_range_envelope(conn, env_x["record_id"])
            idx = list_range_envelopes(conn)
            row = next(r for r in idx["rows"]
                       if r["record_id"] == env_x["record_id"])
            assert rep.get("error") is not None
            assert row["integrity"] == f"refused:{rep['error']}", row
        # The clean row is verified in both.
        rep = replay_range_envelope(conn, clean["record_id"])
        assert rep.get("error") is None and rep["integrity"] == "verified"
        idx = list_range_envelopes(conn, ticker="SPY")
        clean_row = next(r for r in idx["rows"]
                         if r["record_id"] == clean["record_id"])
        assert clean_row["integrity"] == "verified"
    finally:
        conn.close()


def test_c11_mounted_route_serves_bound_wrapper_only():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes.solstice_price_paths import router
    conn = duckdb.connect(":memory:")
    try:
        env = _recorded(conn)
        app = FastAPI()
        app.include_router(router)
        with patch("routes.solstice_price_paths._store_conn", lambda: conn):
            client = TestClient(app, raise_server_exceptions=False)
            r = client.get(f"/api/solstice/price-paths/range-records/"
                           f"{env['record_id']}")
            assert r.status_code == 200
            body = r.json()
            # Wrapper fields are the BOUND payload's own values.
            assert body["status"] == env["status"]
            assert body["received_at"] == env["clocks"]["received_at"]
            assert body["window"] == {"min_dte": 14, "max_dte": 60}
            conn.execute(
                "UPDATE range_analytics_envelopes_v1 SET status = 'partial' "
                "WHERE record_id = ?", [env["record_id"]])
            r = client.get(f"/api/solstice/price-paths/range-records/"
                           f"{env['record_id']}")
            assert r.status_code == 422
            assert r.json()["reason"] == "ROW_HEADER_MISMATCH"
    finally:
        conn.close()


# ── C11-5: admission precedes broker init at all three seams ──────────────

def test_c11_failed_debit_never_touches_broker():
    """A failed REQUIRED debit performs ZERO provider calls — including the
    cold _get_broker() auth/accounts that used to precede the debit."""
    get_broker = AsyncMock(return_value=MagicMock())
    calls = (lambda: adapter.fetch_option_expiry_listing("TEST"),
             lambda: adapter.fetch_chain_for_expiries("TEST",
                                                      ["2026-10-26"]),
             lambda: adapter.fetch_chain_from_public_api("TEST", 2))
    for call in calls:
        adapter._clear_chain_cache()
        with patch.object(adapter, "_get_broker", new=get_broker), \
                patch.object(adapter._public_budget.budget, "acquire_n",
                             new=AsyncMock(side_effect=RuntimeError("down"))):
            assert asyncio.run(call()) is None
        assert get_broker.await_count == 0, "provider I/O before denied debit"
        get_broker.reset_mock()
    adapter._clear_chain_cache()


def test_c11_warm_broker_cache_serves_without_admission(monkeypatch):
    """The warm-singleton cache serve keeps cache hits debit-free and at
    zero provider calls: no acquire, no broker resolution, no vendor fetch."""
    import time as _time

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="A")
    monkeypatch.setattr(adapter, "BROKER", broker)
    monkeypatch.setattr(adapter, "_get_broker",
                        AsyncMock(return_value=broker))
    adapter._clear_chain_cache()
    try:
        adapter._CHAIN_CACHE[("TESTW", 1)] = (
            _time.monotonic(), broker,
            {"ticker": "TESTW", "contracts": [1], "stale": False})
        with patch.object(adapter._public_budget.budget, "acquire_n",
                          new=AsyncMock(side_effect=RuntimeError("down"))):
            served = asyncio.run(
                adapter.fetch_chain_from_public_api("TESTW", 1))
        assert served is not None and served["contracts"] == [1]
    finally:
        adapter._clear_chain_cache()
        monkeypatch.undo()


# ── C11-6: kernel-corresponding populations ────────────────────────────────

def test_c11_missing_iv_is_exclusion_not_admitted():
    contracts = _contracts()
    for c in contracts:
        if c["expiry"] == "2026-10-26" and c["strike"] == 590.0:
            # Vendor-gamma-valid but IV missing: the BS kernel drops it, so
            # the population must count an exclusion — never "admitted".
            c["iv"] = None
    env = _env(contracts=contracts)
    raw = env["grids"]["raw_oi"]
    assert raw["population"]["iv_missing_or_nonpositive"] == 2
    assert raw["population"]["usable"] == 10
    assert raw["status"] == "partial" and raw["metric_admitted"] is False
    assert "raw_oi" in env["metrics"]["partial"]
    assert "raw_oi" not in env["metrics"]["admitted"]


def test_c11_no_vendor_gamma_keeps_bs_surface_finite():
    contracts = _contracts()
    for c in contracts:
        # Vendor gamma absent everywhere: the delta/volume kernels lose
        # their input, but the BS raw surface still has iv/T — its cells
        # exist, so it can NEVER say "unavailable" with finite BS cells.
        c["gamma"] = None
    env = _env(contracts=contracts)
    raw = env["grids"]["raw_oi"]
    assert raw["population"]["usable"] == 12
    assert raw["status"] == "ok" and raw["metric_admitted"] is True
    assert raw["cells"]["2026-10-26"]["590"] is not None
    assert env["grids"]["delta_weighted"]["status"] == "unavailable"
    assert "raw_oi" in env["metrics"]["admitted"]
    assert "raw_oi" not in env["metrics"]["unavailable"]


def test_c11_delta_population_matches_kernel_counters():
    contracts = _contracts()
    for c in contracts:
        if c["expiry"] == "2026-11-09" and c["strike"] == 600.0 and \
                c["type"] == "call":
            c["delta"] = True
        if c["expiry"] == "2026-12-04" and c["strike"] == 590.0 and \
                c["type"] == "put":
            c["adjusted"] = True
    env = _env(contracts=contracts)
    dw = env["grids"]["delta_weighted"]
    pop = dw["population"]
    # The population IS the kernel's own counter set (correspondence), and
    # the section-level passthrough equals it.
    assert pop["invalid_delta"] == dw["invalid_delta"] == 1
    assert pop["quarantined"] == dw["quarantined"] == 1
    assert pop["input_contracts"] == 12
    assert dw["status"] == "partial" and dw["metric_admitted"] is False


def test_c11_volume_missing_volume_counts_as_exclusion():
    contracts = _contracts()
    for c in contracts:
        if c["expiry"] == "2026-10-26" and c["strike"] == 590.0:
            c["volume"] = None
    env = _env(contracts=contracts)
    vol = env["grids"]["volume"]
    assert vol["population"]["missing_volume"] == 2
    assert vol["status"] == "partial" and vol["metric_admitted"] is False


# ── C11-7: inspector classification/integrity/timezone/cap truth ──────────

def test_c11_paper_is_never_production_or_qualified(tmp_path):
    from services.heatmap_history import record_decision, record_price_path

    db = tmp_path / "paper.duckdb"
    conn = duckdb.connect(str(db))
    ensure_range_tables(conn)
    _legacy_tables(conn)
    base = 1796431200.0
    for i in range(2):
        record_price_path(conn, "SPY", base + 300.0 * i, 600.0 + i,
                          "public-paper")
    record_decision(conn, {"decision_id": "p1", "ticker": "SPY",
                           "scenario": "t", "side": "none", "eligible": False,
                           "reason_codes": [],
                           "features": {"source": "public-paper"}})
    conn.execute(
        "INSERT INTO outcome_labels_v1 (decision_id, ticker, horizon_s, "
        "label, label_version, at_ts, censored, detail, policy_version) "
        "VALUES ('p1', 'SPY', 900, 'bounce', 'outcome.v1', "
        "'2026-10-01T14:00:00+00:00', 0, '{}', NULL)")
    conn.close()
    rep = inspect_recorder_store(str(db))
    cls = rep["price_paths"]["classification"]
    assert cls["paper"] == 2 and cls["production"] == 0
    dec = rep["lineage"]["decision_classification"]
    assert dec["paper"] == 1 and dec["production"] == 0
    suf = rep["outcome_sufficiency"]
    # One terminal paper-linked label exists — but paper NEVER qualifies.
    assert suf["n_qualified_sessions"] == 0
    assert suf["n_unqualified_sessions"] == 1
    assert suf["verdict"] == "INSUFFICIENT EVIDENCE"


def test_c11_tampered_envelope_never_counts_as_production(tmp_path):
    db = tmp_path / "tampered.duckdb"
    conn = duckdb.connect(str(db))
    ensure_range_tables(conn)
    env = _env()
    assert record_range_envelope(conn, env)["status"] == "recorded"
    # Flip the synthetic flag WITHOUT recomputing anything.
    flipped = json.loads(json.dumps(env))
    flipped["synthetic"] = False
    conn.execute("UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
                 "WHERE record_id = ?",
                 [json.dumps(flipped), env["record_id"]])
    conn.close()
    rep = inspect_recorder_store(str(db))
    cls = rep["range_analytics"]["classification"]
    assert cls["production"] == 0
    assert cls["refused_or_corrupt"] == 1
    row = rep["range_analytics"]["envelopes"][0]
    assert row["integrity"].startswith("refused:")


def test_c11_fully_forged_envelope_still_refused(tmp_path):
    """Even a self-consistent forgery (recomputed digest + record_id) cannot
    pass: the stored row's digest/identity headers no longer match it."""
    from services.solstice_range_analytics import (
        compute_content_digest,
        record_id_for_digest,
    )

    db = tmp_path / "forged.duckdb"
    conn = duckdb.connect(str(db))
    ensure_range_tables(conn)
    env = _env()
    assert record_range_envelope(conn, env)["status"] == "recorded"
    forged = json.loads(json.dumps(env))
    forged["synthetic"] = False
    forged["content_digest"] = compute_content_digest(forged)
    forged["record_id"] = record_id_for_digest(forged["content_digest"])
    conn.execute("UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
                 "WHERE record_id = ?",
                 [json.dumps(forged), env["record_id"]])
    conn.close()
    rep = inspect_recorder_store(str(db))
    cls = rep["range_analytics"]["classification"]
    assert cls["production"] == 0 and cls["refused_or_corrupt"] == 1


def test_c11_census_discloses_cap_truncation(tmp_path):
    db = tmp_path / "capped.duckdb"
    conn = duckdb.connect(str(db))
    ensure_range_tables(conn)
    for i in range(501):
        conn.execute(
            "INSERT INTO range_analytics_envelopes_v1 VALUES (?, 'SPY', 14, "
            "60, '2026-10-05', '', 'ok', 'x', '{bad', '2026-10-05')",
            [f"rga1-cap{i:04d}"])
    conn.close()
    rep = inspect_recorder_store(str(db))
    ra = rep["range_analytics"]
    assert ra["n_groups_listed"] == 500
    assert ra["truncated"] is True
    assert ra["listing_cap"] == 500
    assert "never the whole store" in ra["truncation_note"]


def test_c11_naive_timestamps_are_utc_not_host_local(tmp_path):
    from services.heatmap_history import record_decision

    db = tmp_path / "naive.duckdb"
    conn = duckdb.connect(str(db))
    ensure_range_tables(conn)
    _legacy_tables(conn)
    record_decision(conn, {"decision_id": "n1", "ticker": "SPY",
                           "scenario": "t", "side": "none", "eligible": False,
                           "reason_codes": [],
                           "features": {"source": "public-mid"}})
    # 02:00 UTC is 22:00 ET the PREVIOUS day. One aware, one naive stamp of
    # the same instant: UTC interpretation => ONE NY day; a host-local read
    # would silently split them into two.
    conn.execute(
        "INSERT INTO outcome_labels_v1 (decision_id, ticker, horizon_s, "
        "label, label_version, at_ts, censored, detail, policy_version) "
        "VALUES ('n1', 'SPY', 900, 'bounce', 'outcome.v1', "
        "'2026-08-15T02:00:00+00:00', 0, '{}', NULL)")
    conn.execute(
        "INSERT INTO outcome_labels_v1 (decision_id, ticker, horizon_s, "
        "label, label_version, at_ts, censored, detail, policy_version) "
        "VALUES ('n1', 'SPY', 900, 'bounce', 'outcome.v1', "
        "'2026-08-15T02:00:00', 0, '{}', NULL)")
    conn.close()
    rep = inspect_recorder_store(str(db))
    suf = rep["outcome_sufficiency"]
    assert suf["n_sessions_observed_ny"] == 1
    assert suf["n_qualified_sessions"] == 1


# ── C11-8: frozen consumer fixtures carry full payloads ───────────────────

def test_c11_replay_fixtures_have_version_and_envelope():
    base = json.loads((DOCS_FIXTURES / "record_replay_v1.json").read_text())
    assert base["version"] == "range-records.v1"
    assert isinstance(base.get("envelope"), dict)
    assert base["envelope"]["content_schema"] == CONTENT_SCHEMA
    assert base["integrity"] == "verified"
    partial = json.loads(
        (DOCS_FIXTURES / "record_replay_partial_v1.json").read_text())
    assert partial["version"] == "range-records.v1"
    assert partial["envelope"]["status"] == "partial"
    refused = json.loads(
        (DOCS_FIXTURES / "record_replay_refused_v1.json").read_text())
    assert refused["version"] == "range-records.v1"
    assert refused["status"] == "refused"
    assert refused.get("envelope") is None
    assert refused["reason"] == "NO_RECORD"
