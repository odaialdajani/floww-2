"""R18-C1: owning bounded 14–60 DTE analytical producer (range-analytics.v1).

Deterministic, no network, no server startup, no recorder writes except the
explicit persistence round-trip (own in-memory DuckDB handle). All vendor
seams are injected fakes bound to frozen fixture payloads; the analytical
surfaces are the REGISTERED services.gex_core kernels reused — never
recomputed or relabeled here.

Contract: docs/solstice/r18/CLINE_RANGE_ANALYTICS_V1.md (range-analytics.v1).
Rejection criteria exercised: this is not an expiry listing, not an edge
heuristic, not a global dte<=30 edit — it is the owning bounded window with
axes/cells/basis/units/identity and explicit partiality.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, "backend")

import duckdb
import pytest

from services.heatmap_history import record_range_envelope, replay_range_envelope
from services.solstice_range_analytics import (
    CONTRACT_VERSION,
    build_range_envelope,
    fetch_range_analytics,
    select_window_expiries,
)

FIXTURES = Path(__file__).parent / "fixtures" / "range_analytics_v1"
NOW = datetime(2026, 10, 5, 14, 0, 0, tzinfo=UTC)  # 10:00 ET → NY 2026-10-05
TODAY = date(2026, 10, 5)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _listing(**over):
    listing = dict(_fixture("listing.json"))
    listing.update(over)
    return listing


def _chain(**over):
    chain = dict(_fixture("chain_complete.json"))
    chain.update(over)
    return chain


def _run(ticker="SPY", min_dte=14, max_dte=60, *, as_of=None,
         listing=None, chain=None, persist_conn=None):
    async def listing_fetcher(_t):
        return listing if listing is not None else _listing()

    async def window_fetcher(_t, _dates):
        return chain if chain is not None else _chain()

    return asyncio.run(fetch_range_analytics(
        ticker, min_dte, max_dte, as_of=as_of,
        listing_fetcher=listing_fetcher, window_fetcher=window_fetcher,
        now_utc=NOW, persist_conn=persist_conn))


def test_complete_bounded_range_ok():
    env = _run()
    assert env["version"] == CONTRACT_VERSION
    assert env["status"] == "ok"
    assert env["refusals"] == []
    # The owning axes: exactly the listed expiries inside 14–60, sorted by DTE.
    assert [a["expiry"] for a in env["axes"]["expiries"]] == [
        "2026-10-26", "2026-11-09", "2026-12-04"]
    assert [a["dte"] for a in env["axes"]["expiries"]] == [21, 35, 60]
    assert env["axes"]["strike_keys"] == ["590", "600"]
    cov = env["coverage"]
    assert cov["complete"] is True and cov["complete_reason"] is None
    assert cov["n_listed"] == 7 and cov["n_admitted"] == 3
    assert cov["n_returned_expiries"] == 3 and cov["n_skipped_expiries"] == 0
    assert cov["lower_edge_observed"] and cov["upper_edge_observed"]
    # Registered distinct surfaces with explicit bases — never swapped.
    assert env["grids"]["raw_oi"]["metric_id"] == "gex_net_v1"
    assert env["grids"]["raw_oi"]["basis"] == "OI"
    assert env["grids"]["delta_weighted"]["metric_id"] == "dadgex_net_v1"
    assert env["grids"]["delta_weighted"]["basis"] == "OI_DELTA_WEIGHTED"
    assert env["grids"]["volume"]["metric_id"] == "volume_gamma_v1"
    assert env["grids"]["volume"]["basis"] == "VOLUME"
    win = env["grids"]["window"]
    assert win["status"] == "unavailable"
    assert win["reason"] == "HISTORY_NOT_YET_RECORDED"
    # Real cells, exact values from the registered kernels.
    from services.gex_core import compute_gex_grid, compute_gex_grid_delta_weighted
    expected = compute_gex_grid(600.0, _chain()["contracts"], "SPY")
    assert env["grids"]["raw_oi"]["cells"]["2026-10-26"]["590"] == \
        pytest.approx(expected["grid"]["2026-10-26"]["590"])
    expected_dw = compute_gex_grid_delta_weighted(600.0, _chain()["contracts"])
    assert env["grids"]["delta_weighted"]["cells"]["2026-12-04"]["600"] == \
        pytest.approx(expected_dw["grid"]["2026-12-04"]["600"])
    # Identity binds symbol/window/date/clocks.
    assert env["record_id"].startswith("rga1-")
    assert env["query"] == {"min_dte": 14, "max_dte": 60, "as_of_ny": "2026-10-05"}
    assert env["clocks"]["received_at"] == "2026-10-05T13:59:30+00:00"
    assert env["clocks"]["oi_effective_dates"] == ["2026-10-03"]


def test_reversed_window_refuses():
    env = _run(min_dte=60, max_dte=14)
    assert env["status"] == "refused"
    assert env["refusals"] == ["REVERSED_WINDOW"]
    assert env["record_id"] is None


def test_zero_admitted_refuses_honestly():
    env = _run(min_dte=14, max_dte=20)  # listing has nothing in (14, 20]
    assert env["status"] == "refused"
    assert "NO_ADMITTED_EXPIRY" in env["refusals"]
    verdicts = {r["expiry"]: r["reason"]
                for r in env["coverage"]["listing_verdicts"]}
    assert verdicts["2026-10-02"] == "EXPIRED"
    assert verdicts["NOT-A-DATE"] == "UNPARSEABLE_EXPIRY"
    assert verdicts["2026-12-05"] == "ABOVE_WINDOW"


def test_session_date_mismatch_refuses():
    env = _run(as_of="2026-10-01")
    assert env["status"] == "refused"
    assert env["refusals"] == ["SESSION_DATE_MISMATCH"]
    assert env["requested_as_of"] == "2026-10-01"


def test_window_out_of_range_refuses():
    env = _run(min_dte=0, max_dte=400)
    assert env["status"] == "refused"
    assert env["refusals"] == ["WINDOW_OUT_OF_RANGE"]


def test_skipped_expiry_is_partial_with_null_rows():
    # Vendor fetch for one admitted expiry fails — the map must stay partial,
    # the skip reason visible, and that expiry's row explicitly null (never
    # absent, never zero-filled).
    chain = _chain()
    chain["skipped"] = [{"expiry": "2026-12-04", "reason": "CHAIN_FETCH_FAILED"}]
    chain["contracts"] = [c for c in chain["contracts"]
                          if c["expiry"] != "2026-12-04"]
    chain["expiries"] = [e for e in chain["expiries"] if e != "2026-12-04"]
    env = _run(chain=chain)
    assert env["status"] == "partial"
    assert "PARTIAL_COVERAGE" in env["refusals"]
    cov = env["coverage"]
    assert cov["complete"] is False
    assert cov["complete_reason"] == "SKIPPED_EXPIRIES"
    assert cov["skipped"] == [{"expiry": "2026-12-04",
                               "reason": "CHAIN_FETCH_FAILED"}]
    # Admitted axis still lists the skipped expiry; its cells are null.
    assert "2026-12-04" in [a["expiry"] for a in env["axes"]["expiries"]]
    assert all(v is None for v in env["grids"]["raw_oi"]["cells"]["2026-12-04"].values())


def test_listing_capped_means_not_complete():
    listing = _listing(listing_capped=True)
    env = _run(listing=listing)
    assert env["status"] == "partial"
    assert env["coverage"]["complete"] is False
    assert env["coverage"]["complete_reason"] == "LISTING_CAPPED_WINDOW_MAY_EXTEND"


def test_missing_oi_greeks_never_zero_filled():
    chain = _chain()
    nulled = []
    for c in chain["contracts"]:
        if c["expiry"] == "2026-10-26" and c["strike"] == 590.0:
            # OI/gamma/delta all unknown → excluded from every surface.
            c = dict(c, oi=None, gamma=None, delta=None)
        elif c["expiry"] == "2026-11-09" and c["strike"] == 600.0 \
                and c["type"] == "call":
            # OI/gamma known, delta UNKNOWN → counted missing-delta exclusion,
            # raw cell still computed (different bases stay distinct).
            c = dict(c, delta=None)
        nulled.append(c)
    chain["contracts"] = nulled
    env = _run(chain=chain)
    # Missing OI/gamma → cell unavailable (null), never 0.0.
    assert env["grids"]["raw_oi"]["cells"]["2026-10-26"]["590"] is None
    dw = env["grids"]["delta_weighted"]
    assert dw["cells"]["2026-10-26"]["590"] is None
    assert dw["missing_delta"] == 1  # the lone delta-missing call
    assert dw["cells"]["2026-11-09"]["600"] is not None or dw["missing_delta"] == 2
    # Sibling values still real where inputs existed.
    assert env["grids"]["raw_oi"]["cells"]["2026-10-26"]["600"] is not None
    assert env["grids"]["raw_oi"]["cells"]["2026-11-09"]["600"] is not None


def test_stale_cache_is_disclosed():
    env = _run(chain=_chain(stale=True))
    assert env["status"] == "partial"
    assert "STALE_CACHE" in env["refusals"]
    assert env["provenance"]["stale"] is True


def test_listing_or_chain_failure_refuses():
    async def none_listing(_t):
        return None

    async def none_window(_t, _d):
        return None

    async def ok_listing(_t):
        return _listing()

    env = asyncio.run(fetch_range_analytics(
        "SPY", 14, 60, listing_fetcher=none_listing,
        window_fetcher=none_window, now_utc=NOW))
    assert env["status"] == "refused" and "VENDOR_UNAVAILABLE" in env["refusals"]

    env = asyncio.run(fetch_range_analytics(
        "SPY", 14, 60, listing_fetcher=ok_listing,
        window_fetcher=none_window, now_utc=NOW))
    assert env["status"] == "refused" and "CHAIN_UNAVAILABLE" in env["refusals"]


def test_identity_binds_window_and_symbol():
    env_a = _run(min_dte=14, max_dte=60)
    env_b = _run(min_dte=14, max_dte=59)
    chain_q = _chain(ticker="QQQ")
    env_c = _run(ticker="QQQ", chain=chain_q)
    assert env_a["record_id"] != env_b["record_id"]
    assert env_a["record_id"] != env_c["record_id"]
    # Identical inputs → identical identity (replays address the same record).
    assert env_a["record_id"] == _run()["record_id"]


def test_persistence_roundtrip_and_identity_conflict():
    conn = duckdb.connect(":memory:")
    try:
        env = _run(persist_conn=conn)
        assert env["persistence"]["status"] == "recorded"
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["digest"] == env["content_digest"]
        assert rep["envelope"]["axes"] == json.loads(json.dumps(env["axes"]))
        assert rep["envelope"]["grids"]["raw_oi"]["cells"] == \
            json.loads(json.dumps(env["grids"]["raw_oi"]["cells"]))
        assert rep["envelope"]["clocks"] == json.loads(json.dumps(env["clocks"]))
        # Same identity again → idempotent duplicate, not a second record.
        assert record_range_envelope(conn, env)["status"] == "duplicate"
        # Same record_id with a tampered digest refuses as identity conflict.
        tampered = dict(env, content_digest="0" * 64)
        res = record_range_envelope(conn, tampered)
        assert res["status"] == "refused" and res["reason"] == "IDENTITY_CONFLICT"
        assert replay_range_envelope(conn, "rga1-nonexistent") is None
    finally:
        conn.close()


def test_refused_envelope_is_not_persisted():
    conn = duckdb.connect(":memory:")
    try:
        res = record_range_envelope(conn, {"status": "refused",
                                           "refusals": ["REVERSED_WINDOW"]})
        assert res["status"] == "refused" and res["reason"] == "IDENTITY_INCOMPLETE"
    finally:
        conn.close()


def test_selection_pure_function():
    listing = _listing()
    sel = select_window_expiries(listing["expiries"], 14, 60, TODAY)
    assert [a["expiry"] for a in sel["admitted"]] == [
        "2026-10-26", "2026-11-09", "2026-12-04"]
    assert sel["n_expired"] == 1 and sel["n_unparseable"] == 1
    assert sel["lower_edge_observed"] and sel["upper_edge_observed"]


def test_build_envelope_is_pure_and_synthetic_marked():
    listing = _listing()
    sel = select_window_expiries(listing["expiries"], 14, 60, TODAY)
    env = build_range_envelope(symbol="SPY", min_dte=14, max_dte=60, asof=TODAY,
                               listing=listing, selection=sel, chain=_chain())
    assert env["status"] == "ok"
    assert env["synthetic"] is True  # fixture chain carries synthetic: true


