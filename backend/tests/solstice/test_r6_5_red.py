"""R6-5 red tests: prefix stability, geometry oracle, outcome job."""

import sys

sys.path.insert(0, "backend")


def test_b10_decided_label_prefix_stable():
    from services.solstice_labels import label_touch
    decided = label_touch([(0, 490.0), (50, 500.0), (70, 505.0)], (498, 502), 60, 505.0, 485.0)
    assert decided["label"] == "target_hit"
    extended = label_touch([(0, 490.0), (50, 500.0), (70, 505.0), (200, None)],
                           (498, 502), 60, 505.0, 485.0)
    assert extended == decided
    conflicted = label_touch([(0, 490.0), (50, 500.0), (70, 505.0), (90, 480.0)],
                             (498, 502), 60, 505.0, 485.0)
    assert conflicted["label"] == "target_hit"


def test_b10_touch_without_barrier_is_not_no_touch():
    from services.solstice_labels import label_touch
    r = label_touch([(0, 490.0), (30, 500.0), (60, 495.0), (90, 495.0)],
                    (498, 502), 60, 505.0, 485.0)
    assert r["label"] == "indeterminate" and r["censored"] is False, r


def test_b12_fixture_geometry_oracle():
    import json

    from services.wall_interaction import wall_position
    with open("backend/tests/solstice/fixtures/comprehension_v1.json") as fh:
        scenarios = json.load(fh)["scenarios"]
    for sc in scenarios:
        spot = sc["spot"]
        for key in ("nearest_below", "nearest_above"):
            w = sc.get(key)
            if not w:
                continue
            pos = wall_position({"low": w["low"], "high": w["high"]}, spot)
            assert pos == key.replace("nearest_", ""), (sc["id"], key, pos)
        inside = sc.get("inside_wall")
        if inside:
            assert wall_position({"low": inside["low"], "high": inside["high"]}, spot) == "inside"


def test_b11_outcome_job_idempotent_and_linked():
    import duckdb

    from services.heatmap_history import record_decision
    from services.solstice_labels import close_episodes
    conn = duckdb.connect(":memory:")
    did = record_decision(conn, {"ticker": "SPY", "snapshot_id": "s1",
                                 "scenario": "CALLS", "side": "CALLS",
                                 "eligible": True, "reason_codes": [],
                                 "features": {"spot": 500.0,
                                              "zone": [498, 502],
                                              "target": 505.0, "stop": 495.0,
                                              "horizon_s": 60}})
    paths = {did: [(0, 490.0), (50, 500.0), (70, 505.0)]}
    out = close_episodes(conn, paths)
    assert out["closed"] == [did] and out["results"][did]["label"] == "target_hit"
    again = close_episodes(conn, paths)
    assert again["closed"] == [] and again["skipped_idempotent"] == [did]
    n = conn.execute("SELECT COUNT(*) FROM outcome_labels_v1 WHERE decision_id = "
                     f"'{did}'").fetchone()[0]
    assert n == 1
