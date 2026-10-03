"""R18 repairs C5–C10: budget refusal, evidence integrity, governed population,
scoped/classified inspector, read-only replay API, guarded capture.

Deterministic; no network, broker, worker activation or app startup (routes
are exercised on a minimal FastAPI host with the read seams monkeypatched).
Fixture-built canonical envelopes are shared with the C1/C2 suites.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "backend")

import duckdb
import pytest

import services.public_api_adapter as adapter
from services.heatmap_history import (
    ensure_range_tables,
    list_range_envelopes,
    record_range_envelope,
    replay_range_envelope,
)
from services.solstice_range_analytics import CONTENT_SCHEMA, build_range_envelope, select_window_expiries

FIXTURES = Path(__file__).parent / "fixtures" / "range_analytics_v1"
NOW = datetime(2026, 10, 5, 14, 0, 0, tzinfo=UTC)
TODAY = date(2026, 10, 5)


def _env(**chain_over):
    listing = json.loads((FIXTURES / "listing.json").read_text())
    chain = json.loads((FIXTURES / "chain_complete.json").read_text())
    chain.update(chain_over)
    sel = select_window_expiries(listing["expiries"], 14, 60, TODAY)
    return build_range_envelope(symbol="SPY", min_dte=14, max_dte=60,
                                asof=TODAY, listing=listing, selection=sel,
                                chain=chain)


# ── C5: required budget debit failures refuse with ZERO vendor calls ────────

def test_c5_budget_exception_refuses_listing_with_zero_calls():
    broker = MagicMock()
    with patch.object(adapter, "_get_broker",
                      new=AsyncMock(return_value=broker)), \
            patch.object(adapter._public_budget.budget, "acquire_n",
                         new=AsyncMock(side_effect=RuntimeError("budget down"))):
        out = asyncio.run(adapter.fetch_option_expiry_listing("TEST"))
    assert out is None
    broker.get_option_expirations.assert_not_called()
    broker.get_option_chain_parsed.assert_not_called()
    broker.get_quotes.assert_not_called()


def test_c5_budget_exception_refuses_range_fetch_with_zero_calls():
    broker = MagicMock()
    with patch.object(adapter, "_get_broker",
                      new=AsyncMock(return_value=broker)), \
            patch.object(adapter._public_budget.budget, "acquire_n",
                         new=AsyncMock(side_effect=RuntimeError("budget down"))):
        out = asyncio.run(adapter.fetch_chain_for_expiries("TEST", ["2026-10-26"]))
    assert out is None
    broker.get_option_chain_parsed.assert_not_called()
    broker.get_quotes.assert_not_called()


def test_c5_budget_exception_refuses_legacy_chain_fetch():
    broker = MagicMock()
    adapter._clear_chain_cache()
    with patch.object(adapter, "_get_broker",
                      new=AsyncMock(return_value=broker)), \
            patch.object(adapter._public_budget.budget, "acquire_n",
                         new=AsyncMock(side_effect=RuntimeError("budget gone"))):
        out = asyncio.run(adapter.fetch_chain_from_public_api("TEST", 2))
    adapter._clear_chain_cache()
    assert out is None
    broker.get_option_expirations.assert_not_called()
    broker.get_option_chain_parsed.assert_not_called()


# ── C6: canonical content integrity (write + replay validation) ─────────────

def test_c6_valid_roundtrip_then_tampered_payload_refused():
    conn = duckdb.connect(":memory:")
    try:
        env = _env()
        assert env["content_schema"] == CONTENT_SCHEMA
        assert record_range_envelope(conn, env)["status"] == "recorded"
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["integrity"] == "verified"
        # Valid JSON, one cell altered, digest field untouched.
        tampered = json.loads(json.dumps(env))
        tampered["grids"]["raw_oi"]["cells"]["2026-10-26"]["590"] = 424242.0
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
            "WHERE record_id = ?", [json.dumps(tampered), env["record_id"]])
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["error"] == "DIGEST_MISMATCH"
    finally:
        conn.close()


def test_c6_digest_spoof_and_stale_provenance_refused(tmp_path):
    conn = duckdb.connect(":memory:")
    try:
        env = _env()
        assert record_range_envelope(conn, env)["status"] == "recorded"
        # Digest spoof: recompute digest over tampered content but keep the
        # original record_id — identity no longer derives from the digest.
        from services.solstice_range_analytics import compute_content_digest
        spoofed = json.loads(json.dumps(env))
        spoofed["provenance"]["data_source"] = "mysterious-feed"
        spoofed["content_digest"] = compute_content_digest(spoofed)
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
            "WHERE record_id = ?", [json.dumps(spoofed), env["record_id"]])
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["error"] == "RECORD_ID_MISMATCH"
        # Stale provenance + untouched stored digest column: header vs payload.
        stale = json.loads(json.dumps(env))
        stale["clocks"]["oi_effective_dates"] = ["1900-01-01"]
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
            "WHERE record_id = ?", [json.dumps(stale), env["record_id"]])
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["error"] == "DIGEST_MISMATCH"
        # Foreign row header under a known identity.
        fresh = _env()
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
            "WHERE record_id = ?", [json.dumps(fresh), env["record_id"]])
        conn.execute("UPDATE range_analytics_envelopes_v1 SET ticker = 'QQQ' "
                     "WHERE record_id = ?", [env["record_id"]])
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["error"] == "ROW_HEADER_MISMATCH"
    finally:
        conn.close()


def test_c6_legacy_schema_and_corrupted_duplicate_refused():
    conn = duckdb.connect(":memory:")
    try:
        env = _env()
        # Pre-C6 payload (no content_schema) is an explicit schema refusal.
        legacy = {k: v for k, v in env.items() if k != "content_schema"}
        res = record_range_envelope(conn, legacy)
        assert res["status"] == "refused"
        assert res["reason"] == "INCOMPATIBLE_CONTENT_SCHEMA"
        # Corrupted existing duplicate: valid row, then payload swapped for an
        # unrelated valid envelope → a rewrite of the true envelope refuses.
        assert record_range_envelope(conn, env)["status"] == "recorded"
        other = _env(spot=601.0)
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
            "WHERE record_id = ?", [json.dumps(other), env["record_id"]])
        res = record_range_envelope(conn, env)
        assert res["status"] == "refused"
        assert res["reason"] in ("IDENTITY_CONFLICT", "STORED_RECORD_CORRUPT")
        # And replay of that corrupted duplicate refuses too (digests differ).
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep.get("error") in ("DIGEST_MISMATCH", "STORED_DIGEST_MISMATCH",
                                    "ROW_HEADER_MISMATCH")
    finally:
        conn.close()


# ── C7: governed population + exclusion-driven partiality ───────────────────

def test_c7_populations_are_genuine_input_counts():
    env = _env()
    assert env["content_schema"] == CONTENT_SCHEMA
    for name in ("raw_oi", "delta_weighted", "volume"):
        pop = env["grids"][name]["population"]
        assert pop["input_contracts"] == 12  # raw inputs, not cell recount
        assert pop["usable"] == 12
        assert env["grids"][name]["metric_admitted"] is True
    # Window surface: explicitly unavailable, never admitted by a finite map.
    assert env["grids"]["window"]["metric_admitted"] is False
    assert env["metrics"]["admitted"] == ["delta_weighted", "raw_oi", "volume"]
    assert env["metrics"]["unavailable"] == ["window"]
    assert env["status"] == "ok"


def test_c7_excluded_inputs_force_partial_despite_finite_cells():
    contracts = json.loads((FIXTURES / "chain_complete.json").read_text())["contracts"]
    for c in contracts:
        if c["expiry"] == "2026-11-09" and c["strike"] == 600.0 and \
                c["type"] == "call":
            c["delta"] = True  # present-but-INVALID delta reading
        if c["expiry"] == "2026-12-04" and c["strike"] == 590.0 and \
                c["type"] == "put":
            c["adjusted"] = True  # quarantined, never defaulted to 100
    env = _env(contracts=contracts)
    dw = env["grids"]["delta_weighted"]
    # Aggregates are still finite (siblings carry the cells)…
    assert dw["cells"]["2026-11-09"]["600"] is not None
    # …but exclusion populations make the metric PARTIAL, never ok.
    assert dw["population"]["invalid_delta"] == 1
    assert dw["status"] == "partial" and dw["metric_admitted"] is False
    assert dw["quarantined"] == 1
    assert "delta_weighted" in env["metrics"]["partial"]
    assert env["grids"]["raw_oi"]["metric_admitted"] is True or \
        env["grids"]["raw_oi"]["status"] == "partial"


# ── C9: read-only range-record index/replay (service + mounted routes) ──────

def _stocked_conn():
    conn = duckdb.connect(":memory:")
    ensure_range_tables(conn)
    env_a = _env()
    listing = json.loads((FIXTURES / "listing.json").read_text())
    listing["ticker"] = "QQQ"
    chain = json.loads((FIXTURES / "chain_complete.json").read_text())
    chain["ticker"] = "QQQ"
    sel = select_window_expiries(listing["expiries"], 14, 60, TODAY)
    env_b = build_range_envelope(symbol="QQQ", min_dte=14, max_dte=60,
                                 asof=TODAY, listing=listing, selection=sel,
                                 chain=chain)
    assert record_range_envelope(conn, env_a)["status"] == "recorded"
    assert record_range_envelope(conn, env_b)["status"] == "recorded"
    return conn, env_a, env_b


def test_c9_index_filters_pagination_integrity():
    conn, env_a, env_b = _stocked_conn()
    try:
        res = list_range_envelopes(conn)
        assert res["status"] == "ok" and res["n_returned"] == 2
        assert {r["ticker"] for r in res["rows"]} == {"SPY", "QQQ"}
        assert all(r["integrity"] == "verified" for r in res["rows"])
        assert all(r["synthetic"] is True for r in res["rows"])
        # Identity-bound filter.
        res = list_range_envelopes(conn, ticker="QQQ", min_dte=14, max_dte=60)
        assert res["n_returned"] == 1
        assert res["rows"][0]["record_id"] == env_b["record_id"]
        assert list_range_envelopes(conn, as_of="2026-10-05",
                                    status="ok")["n_returned"] == 2
        # Bounded pagination.
        page = list_range_envelopes(conn, limit=1, offset=1)
        assert page["n_returned"] == 1 and page["limit"] == 1
        # Tampered row shows up with a refusal verdict in the index.
        tampered = json.loads(json.dumps(env_a))
        tampered["symbol"] = "MSFT"
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
            "WHERE record_id = ?", [json.dumps(tampered), env_a["record_id"]])
        res = list_range_envelopes(conn, ticker="SPY")
        assert res["rows"][0]["integrity"].startswith("refused:")
        # Store without the table → typed refusal, not an empty success.
        empty = duckdb.connect(":memory:")
        try:
            res2 = list_range_envelopes(empty)
        finally:
            empty.close()
        assert res2["status"] == "refused" and res2["reason"] == "STORE_READ_FAILED"
    finally:
        conn.close()


def test_c9_mounted_index_and_replay_routes(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes.solstice_price_paths import router
    conn, env_a, _ = _stocked_conn()
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr("routes.solstice_price_paths._store_conn", lambda: conn)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/solstice/price-paths/range-records", params={"limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "range-records.v1" and body["n_returned"] == 2
    rid = env_a["record_id"]
    r = client.get(f"/api/solstice/price-paths/range-records/{rid}")
    assert r.status_code == 200 and r.json()["integrity"] == "verified"
    assert r.json()["envelope"]["symbol"] == "SPY"
    r = client.get("/api/solstice/price-paths/range-records/rga1-nope")
    assert r.status_code == 404 and r.json()["reason"] == "NO_RECORD"
    # Tamper → typed integrity refusal at 422.
    tampered = json.loads(json.dumps(env_a))
    tampered["coverage"]["n_contracts"] = 999
    conn.execute("UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
                 "WHERE record_id = ?", [json.dumps(tampered), rid])
    r = client.get(f"/api/solstice/price-paths/range-records/{rid}")
    assert r.status_code == 422 and r.json()["reason"] == "DIGEST_MISMATCH"
    conn.close()
    # No recorder at all → refused, never a fabricated empty index.
    monkeypatch.setattr("routes.solstice_price_paths._store_conn", lambda: None)
    r = client.get("/api/solstice/price-paths/range-records")
    assert r.json()["reason"] == "recorder_unavailable"


# ── C10: capture guard on persist=true ──────────────────────────────────────

def test_c10_persist_requires_capture_policy_and_auth(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes.market_data import router as md_router
    app = FastAPI()
    app.include_router(md_router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.delenv("FLOWW_RANGE_CAPTURE_ENABLED", raising=False)

    r = client.get("/api/heatmap/SPY/range-analytics", params={"persist": "true"})
    assert r.status_code == 503 and r.json()["error"] == "CAPTURE_DISABLED"

    monkeypatch.setenv("FLOWW_RANGE_CAPTURE_ENABLED", "1")
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    r = client.get("/api/heatmap/SPY/range-analytics", params={"persist": "true"})
    assert r.status_code == 503  # auth not configured → fail closed

    monkeypatch.setenv("API_SECRET_KEY", "test-secret")
    r = client.get("/api/heatmap/SPY/range-analytics", params={"persist": "true"})
    assert r.status_code == 401  # authenticated admission required
    r = client.get("/api/heatmap/SPY/range-analytics",
                   params={"persist": "true"}, headers={"X-API-Key": "test-secret"})
    # Authenticated + enabled; this harness has no broker, so the answer is a
    # refusal (vendor unavailable 502 or recorder unavailable 503) — never a
    # write. Refusals persist NOTHING by construction.
    assert r.status_code in (502, 503)
    body = r.json()
    assert body.get("error") == "recorder_unavailable" or \
        "VENDOR_UNAVAILABLE" in (body.get("refusals") or [])

    # Default display read performs NO write and needs no auth; with no broker
    # configured the honest answer is the VENDOR_UNAVAILABLE refusal (502).
    monkeypatch.delenv("FLOWW_RANGE_CAPTURE_ENABLED", raising=False)
    r = client.get("/api/heatmap/SPY/range-analytics")
    assert r.status_code == 502
    assert "VENDOR_UNAVAILABLE" in (r.json().get("refusals")
                                    or [r.json().get("error")])
