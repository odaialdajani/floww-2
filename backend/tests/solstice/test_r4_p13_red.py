"""P13 resweep red tests. Each fails on pre-P13 behavior."""

import sys

sys.path.insert(0, "backend")


def test_p13_recorder_keeps_quality_scenarios_interactions():
    import duckdb

    from services.heatmap_history import record_snapshot, replay_snapshot
    conn = duckdb.connect(":memory:")
    payload = {"ticker": "SPY", "expiries_used": ["2030-01-15"], "spot": 500.0,
               "data_source": "test", "exposure_basis": "OI", "formula_version": "gex.v2",
               "asof": "2030-01-02T14:00:00+00:00", "source_received_at": "2030-01-02T14:00:01+00:00",
               "contracts": [], "strikes": [{"strike": 500, "gex": 1e6}],
               "metrics": {"walls": [{"wall_id": "w_1", "low": 498, "high": 502}]},
               "quality": {"state": "usable", "reasonCodes": []},
               "scenarios": [{"wall_id": "w_1", "name": "Bounce watch"}],
               "interactions": [{"wall_id": "w_1", "state": "testing"}]}
    sid = record_snapshot(conn, payload, "q")
    rep = replay_snapshot(conn, sid)
    assert rep["quality"] == {"state": "usable", "reasonCodes": []}
    assert rep["scenarios"][0]["wall_id"] == "w_1"
    assert rep["interactions"][0]["state"] == "testing"
