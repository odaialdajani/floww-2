"""P10 red-first tests (R4-11/17). Each fails on baseline behavior."""

import sys

sys.path.insert(0, "backend")


def test_r4_11_no_target_before_encounter():
    from services.solstice_labels import label_touch
    # Path hits target 505 without ever touching zone [498,502] -> must NOT be target_hit.
    path = [(0, 490.0), (10, 505.0)]
    r = label_touch(path, (498, 502), 60, 505.0, 480.0)
    assert r["label"] != "target_hit", r


def test_r4_11_horizon_coverage_censored():
    from services.solstice_labels import label_touch
    # Only 10s of 60s horizon observed, never near zone -> censored unknown, not no_touch.
    path = [(0, 490.0), (10, 490.5)]
    r = label_touch(path, (498, 502), 60, 505.0, 485.0)
    assert r["censored"] is True or r["label"] in ("indeterminate", "data_gap")


def test_r4_11_touch_search_bounded_by_horizon():
    from services.solstice_labels import label_touch
    # Zone touched only AFTER horizon (full 60s covered clean) -> no_touch.
    path = [(0, 490.0), (60, 490.0), (120, 500.0)]
    r = label_touch(path, (498, 502), 60, 505.0, 485.0)
    assert r["label"] == "no_touch", r


def test_r4_17_single_frozen_touch_pct():
    from services import solstice_ablation as ab
    assert ab.TOUCH_PCT == 0.001
    assert ab.NEAR_PCT == 0.003


def test_r4_17_wall_local_l2_l3():
    from services.solstice_ablation import run_ladder
    from services.wall_structure import discover_walls
    strikes = [{"strike": 500, "gex": 1e6, "call_gex": 8e5, "put_gex": 2e5}]
    walls = discover_walls(strikes, 500.0, pct_threshold=0.0)
    assert walls, "fixture must form a wall"
    wid = walls[0]["wall_id"]
    snap = {"spot": 500.0, "strikes": strikes,
            "metrics": {"magnitude_ratio_delta_over_raw": 0.9,
                        "wall_delta_share": {wid: 0.01}},
            "volume_deltas": [{"strike": 999, "delta_volume": 100}]}
    r = run_ladder(snap)
    # Scope-wide ratio high but wall-local share below support -> L2 abstains.
    assert r["levels"]["L2_plus_delta"]["abstentions"] == 1
    # Volume elsewhere (strike 999) is not wall-local activity -> L3 abstains.
    assert r["levels"]["L3_plus_activity"]["abstentions"] == 1
