"""R5-F red tests: encounter horizons, gap model, linked producers (G7/R14-R15)."""

import sys

sys.path.insert(0, "backend")


def test_r14_horizon_starts_at_encounter():
    from services.solstice_labels import label_touch
    # Encounter at t=50, target at t=70 with a 60s horizon: post-encounter
    # window runs to t=110, so this is a target_hit, not censored.
    path = [(0, 490.0), (50, 500.0), (70, 505.0)]
    r = label_touch(path, (498, 502), 60, 505.0, 485.0)
    assert r["label"] == "target_hit" and r["censored"] is False, r


def test_r14_sparse_path_censored_by_gap_model():
    from services.solstice_labels import label_touch
    # Widely separated observations cannot prove first passage order.
    path = [(0, 500.0), (300, 506.0)]
    r = label_touch(path, (498, 502), 60, 505.0, 490.0)
    assert r["censored"] is True, r


def test_r15_producers_link_decision_to_outcome():
    import duckdb

    from services.heatmap_history import record_decision, record_outcome
    conn = duckdb.connect(":memory:")
    did = record_decision(conn, {"ticker": "SPY", "snapshot_id": "snap_x",
                                 "scenario": "CALLS", "side": "CALLS",
                                 "eligible": False, "reason_codes": ["STALE_ASK"],
                                 "features": {"spot": 500.0},
                                 "candidate_quotes": []})
    assert did
    record_outcome(conn, did, "SPY", 60, "indeterminate", censored=True,
                   detail={"reason": "HORIZON_INCOMPLETE"})
    n = conn.execute("SELECT COUNT(*) FROM scenario_decisions_v1 WHERE decision_id = "
                     f"'{did}'").fetchone()[0]
    m = conn.execute("SELECT COUNT(*) FROM outcome_labels_v1 WHERE decision_id = "
                     f"'{did}'").fetchone()[0]
    assert n == 1 and m == 1


def test_r15_manifest_cadence_and_health():
    import duckdb

    from services.heatmap_history import record_snapshot, recorder_status, session_manifest
    conn = duckdb.connect(":memory:")
    assert recorder_status(conn, ":memory:")["durable"] is False
    p = {"ticker": "SPY", "expiries_used": [], "spot": 500.0, "data_source": "t",
         "exposure_basis": "OI", "formula_version": "gex.v2",
         "asof": "2030-01-02T14:00:00+00:00", "contracts": [], "strikes": [],
         "metrics": {"walls": []}}
    record_snapshot(conn, p, "q", snapshot_id="m1")
    man = session_manifest(conn, "SPY", "2030-01-02", expected_cadence_s=300)
    assert man["heartbeat"]["expected_cadence_s"] == 300
