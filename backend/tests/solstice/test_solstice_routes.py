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
    record_snapshot(conn, dict(base, asof="2030-01-02T01:00:00+00:00"), "q")
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
