"""Solstice routes: read-only, no broker writes, mocked heatmap fetch."""

import sys

sys.path.insert(0, "backend")

from unittest.mock import AsyncMock, patch


def _payload():
    return {"ticker": "SPY", "spot": 500.0, "expiries_used": ["2030-01-15"],
            "strikes": [{"strike": 500.0, "gex": 1e6, "call_gex": 6e5, "put_gex": 4e5,
                         "total_oi": 100}],
            "grid": {"expiries": ["2030-01-15"], "strikes": [500.0],
                     "grid": {"2030-01-15": {"500": 1e6}}},
            "nodes": {"regime": "positive",
                      "king": {"strike": 500.0, "gex": 1e6}, "floors": [], "ceilings": []},
            "patterns": [], "exposure_basis": "OI", "formula_version": "gex.v2",
            "data_source": "public_api", "mode": "day",
            "asof": "2030-01-02T00:00:00+00:00",
            "quality": {"setup_eligible": True, "reasonCodes": [],
                        "trade_side_capability": "none"}}


def test_snapshot_endpoint_returns_v2_and_legacy():
    from fastapi.testclient import TestClient

    import server
    with patch.object(server, "build_heatmap", new=AsyncMock(return_value=_payload())):
        c = TestClient(server.app)
        r = c.get("/api/solstice/snapshot/SPY")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot"]["schemaVersion"] == "2"
    assert body["data"]["ticker"] == "SPY"


def test_evidence_walls_patterns_scout_capability():
    from fastapi.testclient import TestClient

    import server
    with patch.object(server, "build_heatmap", new=AsyncMock(return_value=_payload())):
        c = TestClient(server.app)
        assert c.get("/api/solstice/evidence/SPY", params={"wall_id": "w_x"}).status_code == 200
        w = c.get("/api/solstice/walls/SPY").json()
        assert "walls" in w and "nearest" in w
        p = c.get("/api/solstice/patterns/SPY").json()
        assert "patterns" in p
    with patch("server.fetch_spot_and_chains_merged",
               new=AsyncMock(return_value={"spot": 500.0, "contracts": [],
                                           "expiries": ["2030-01-15"]})):
        from fastapi.testclient import TestClient as TC2

        import server as S2
        c2 = TC2(S2.app)
        assert c2.get("/api/solstice/scout/SPY", params={"side": "CALLS"}).status_code == 200
        assert c2.get("/api/solstice/regime/SPY").status_code == 200
        assert c2.get("/api/solstice/vanna/SPY").status_code == 200
    from fastapi.testclient import TestClient as TC3

    import server as S3
    c3 = TC3(S3.app)
    cap = c3.get("/api/solstice/capability").json()
    assert cap["registry"]["count"] == 27


def test_attribute_endpoint_needs_two_snapshots():
    import duckdb

    from services import heatmap_history as hh
    from services.heatmap_history import record_snapshot
    conn = duckdb.connect(":memory:")
    base = {"ticker": "TST", "expiries_used": ["2030-01-15"], "spot": 500.0,
            "data_source": "public_api", "exposure_basis": "OI",
            "formula_version": "gex.v2", "source_received_at": "2030-01-02T00:00:00+00:00",
            "contracts": [], "strikes": [{"strike": 500, "gex": 1e6}],
            "metrics": {"walls": []}}
    record_snapshot(conn, dict(base, asof="2030-01-02T00:00:00+00:00"), "q")
    assert hh.compare_snapshots(conn, "TST", "2030-01-02")["status"] == "history_unavailable"
    # A second observation must differ in content to be a distinct snapshot.
    record_snapshot(conn, dict(base, asof="2030-01-02T01:00:00+00:00",
                               strikes=[{"strike": 500, "gex": 2e6}]), "q")
    assert hh.compare_snapshots(conn, "TST", "2030-01-02")["status"] == "ok"


def test_capture_scheduler_off_by_default_opt_in():
    import server
    # Default: unset → None (no behavior change).
    assert server._solstice_capture_cfg() is None
    import os
    os.environ["FLOWW_SOLSTICE_CAPTURE"] = "1"
    os.environ["FLOWW_SOLSTICE_CAPTURE_TICKERS"] = "SPY, QQQ, EXTRA, X1, X2, X3, X4"
    os.environ["FLOWW_SOLSTICE_CAPTURE_SEC"] = "5"
    try:
        cfg = server._solstice_capture_cfg()
        assert cfg is not None
        assert cfg["tickers"] == ["SPY", "QQQ", "EXTRA", "X1", "X2", "X3"]  # capped at 6
        assert cfg["interval"] == 60  # floored at 60s
    finally:
        for k in ("FLOWW_SOLSTICE_CAPTURE", "FLOWW_SOLSTICE_CAPTURE_TICKERS",
                  "FLOWW_SOLSTICE_CAPTURE_SEC"):
            os.environ.pop(k, None)
    assert server._solstice_capture_cfg() is None


def test_evidence_packet_matches_ui_snapshot_identity():
    # AI explanations must cite the EXACT snapshot the UI displays: the
    # evidence packet id must equal the snapshot id for the same payload.
    from services.heatmap_snapshot import build_snapshot_v2
    from services.solstice_evidence import build_evidence_packet, validate_explainer_output
    payload = {"ticker": "SPY", "spot": 500.0, "expiries_used": ["2030-01-15"],
               "data_source": "public_api", "exposure_basis": "OI",
               "formula_version": "gex.v2", "asof": "2030-01-02T00:00:00+00:00",
               "nodes": {"regime": "positive"},
               "quality": {"setupEligible": True, "reasonCodes": [],
                           "trade_side_capability": "none"}}
    snap = build_snapshot_v2(payload, query_key="SPY|4|day|None|False")
    pkt = build_evidence_packet(snap, wall_id="w_x")
    assert pkt["snapshot_id"] == snap["snapshotId"]
    assert pkt["query_id"] == snap["queryKey"]
    # Validator rejects a stale-snapshot explanation.
    bad = dict(pkt)
    out = {"snapshot_id": "snap_other", "query_id": pkt["query_id"],
           "status": "Wait", "observations": []}
    assert validate_explainer_output(out, bad) != []


def _record_r5t_snapshot():
    """Record one R5T snapshot into the shared engine DB (unique IDs)."""
    from services.duckdb_engine import db as eng
    from services.heatmap_history import record_snapshot
    conn = eng.conn
    payload = {"ticker": "R5T", "expiries_used": ["2030-01-15"], "spot": 500.0,
               "mode": "day", "dte": None, "scalp": False,
               "data_source": "public_api", "exposure_basis": "OI",
               "formula_version": "gex.v2",
               "asof": "2030-01-02T14:00:00+00:00",
               "source_received_at": "2030-01-02T14:00:01+00:00",
               "contracts": [], "strikes": [{"strike": 500, "gex": 1e6}],
               "grid": {"grid": {"2030-01-15": {"500": 1e6}}},
               "metrics": {"walls": [{"wall_id": "w_r5", "low": 498, "high": 502,
                                      "gross": 1e6, "net": 1e5}]},
               "quality": {"state": "usable", "reasonCodes": [],
                           "setupEligible": False, "executionEligible": False,
                           "tradeSideCapability": "none"},
               "scenarios": [{"wall_id": "w_r5", "name": "Bounce watch"}],
               "interactions": [{"wall_id": "w_r5", "state": "testing"}]}
    return record_snapshot(conn, payload, "R5T:day:None:False", snapshot_id="snap_r5t_replay")


def test_evidence_replay_validates_ticker_and_wall():
    from fastapi.testclient import TestClient

    import server
    _record_r5t_snapshot()
    c = TestClient(server.app)
    bad_t = c.get("/api/solstice/evidence/WRONG", params={"snapshot_id": "snap_r5t_replay"})
    assert bad_t.json()["error"] == "ticker_mismatch"
    bad_w = c.get("/api/solstice/evidence/R5T",
                  params={"snapshot_id": "snap_r5t_replay", "wall_id": "w_nope"})
    assert bad_w.json()["error"] == "unknown_wall"
    good = c.get("/api/solstice/evidence/R5T",
                 params={"snapshot_id": "snap_r5t_replay", "wall_id": "w_r5"}).json()
    pkt = good["packet"]
    assert pkt["replay_of"] == "snap_r5t_replay"
    assert pkt["wall_id"] == "w_r5"
    kinds = {f["kind"] for f in pkt["facts"]}
    assert {"WALL", "INTERACTION", "SCENARIO", "QUALITY"} <= kinds


def test_recorder_health_truthful_and_unified_capability():
    from fastapi.testclient import TestClient

    import server
    _record_r5t_snapshot()
    c = TestClient(server.app)
    health = c.get("/api/solstice/recorder_health").json()
    assert health["durable"] is False  # :memory: never claims durable
    assert health["mode"] == "memory"
    cap = c.get("/api/solstice/capability").json()
    assert cap["registry"]["count"] == 27
    assert isinstance(cap["observed"], list)
    man = c.get("/api/solstice/manifest/R5T", params={"day": "2030-01-02"}).json()
    assert man["n_snapshots"] >= 1 and "gaps" in man
