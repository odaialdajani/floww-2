"""P07 red-first tests (R4-13/18). Each fails on baseline behavior."""

import sys

sys.path.insert(0, "backend")


def _conn():
    import duckdb
    return duckdb.connect(":memory:")


def _payload(n=3):
    return {"ticker": "SPY", "expiries_used": ["2030-01-15"], "spot": 500.0,
            "data_source": "test", "exposure_basis": "OI", "formula_version": "gex.v2",
            "asof": "2030-01-02T14:00:00+00:00", "source_received_at": "2030-01-02T14:00:01+00:00",
            "contracts": [{"osi": f"C{i}", "expiry": "2030-01-15", "strike": 500 + i,
                           "type": "call", "multiplier": 100.0, "bid": 1.0, "ask": 1.2,
                           "volume": 10, "oi": 100, "iv": 0.2, "delta": 0.5, "gamma": 0.05}
                          for i in range(n)],
            "strikes": [{"strike": 500 + i, "gex": 1e6} for i in range(n)],
            "metrics": {"walls": [{"wall_id": "w_abc", "low": 500, "high": 502}]},
            "quality": {"state": "usable", "reasonCodes": []}}


def test_r4_13_atomic_retry_completes():
    from services.heatmap_history import record_snapshot, replay_snapshot
    conn = _conn()
    p = _payload(2)
    sid = record_snapshot(conn, p, "q1")
    assert sid is not None
    # Corrupt: delete contract rows to simulate crash after header.
    conn.execute(f"DELETE FROM contract_observations_v2 WHERE snapshot_id = '{sid}'")
    # Retry same payload must rewrite missing contracts, not skip via dedup.
    sid2 = record_snapshot(conn, p, "q1", snapshot_id=sid)
    assert sid2 == sid
    rep = replay_snapshot(conn, sid)
    assert rep is not None and len(rep["contracts"]) == 2, rep


def test_r4_13_coverage_explicit_no_silent_truncation():
    from services.heatmap_history import record_snapshot
    conn = _conn()
    p = _payload(5)
    p["coverage"] = {"requested": 10, "returned": 5}
    sid = record_snapshot(conn, p, "q1")
    row = conn.execute("SELECT n_contracts, n_usable FROM heatmap_snapshots_v2 "
                       f"WHERE snapshot_id = '{sid}'").fetchone()
    assert row[0] == 5 and row[1] == 5
    # Coverage table or snapshot row must carry requested/returned + truncated flag.
    cols = [d[1] for d in conn.execute("PRAGMA table_info(heatmap_snapshots_v2)").fetchall()]
    assert "requested" in cols or "coverage_json" in cols


def test_r4_13_replay_identical():
    from services.heatmap_history import record_snapshot, replay_snapshot
    conn = _conn()
    p = _payload(3)
    sid = record_snapshot(conn, p, "q1")
    rep = replay_snapshot(conn, sid)
    assert rep is not None
    assert len(rep["strikes"]) == 3 and len(rep["contracts"]) == 3
    assert rep["walls"][0]["wall_id"] == "w_abc"


def test_r4_13_durable_status_honest():
    from services.heatmap_history import recorder_status
    conn = _conn()
    s = recorder_status(conn, ":memory:")
    assert s["durable"] is False
    assert "mode" in s


def test_r4_13_gap_receipts():
    from services.heatmap_history import record_snapshot, session_manifest
    conn = _conn()
    p1 = _payload(1)
    p1["asof"] = "2030-01-02T14:00:00+00:00"
    p2 = _payload(1)
    p2["asof"] = "2030-01-02T14:10:00+00:00"
    record_snapshot(conn, p1, "q", snapshot_id="snap_gap_a")
    record_snapshot(conn, p2, "q", snapshot_id="snap_gap_b")
    m = session_manifest(conn, "SPY", "2030-01-02", expected_cadence_s=300)
    assert m["n_snapshots"] == 2
    assert "gaps" in m and len(m["gaps"]) >= 1
