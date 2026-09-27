"""R7-07 red tests: episode policy, pending/final lifecycle, no-touch gap fix."""

import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime, timedelta

import duckdb

from services.heatmap_history import record_decision, record_outcome
from services.solstice_labels import HORIZONS_S, close_episodes, label_touch


def test_r7_07_no_touch_requires_gap_free_coverage():
    """R7-F07: no_touch must not be returned when a large observation gap
    exists, even when the full horizon elapsed without an encounter."""
    # 300s path, no encounter (price below zone), but a 100s gap.
    # max_gap_s=5: the gap censors — we cannot prove no touch happened.
    path = [(0, 490.0), (10, 490.0), (110, 490.0), (300, 490.0)]
    r = label_touch(path, (498, 502), 300, 505.0, 495.0, max_gap_s=5)
    assert r["label"] != "no_touch", r
    assert r["censored"] is True, r
    assert r["detail"] == "OBSERVATION_GAP", r

    # Gap-free 300s path with no encounter: genuine no_touch is valid.
    # Use max_gap_s=200 so the 180s observation spacing is within tolerance.
    gf = [(0, 490.0), (30, 490.0), (60, 490.0), (120, 490.0),
          (300, 490.0)]
    r2 = label_touch(gf, (498, 502), 300, 505.0, 495.0, max_gap_s=200)
    assert r2["label"] == "no_touch" and r2["censored"] is False, r2

    # Gap-free 300s path WITH encounter but no barrier hit: indeterminate,
    # never no_touch (the touch proves contact happened). Path must cover the
    # full window (to t=330) with gaps within max_gap_s=250. Prices stay
    # strictly inside the zone (499.0) — never hit target (505) or stop (495).
    gf2 = [(0, 490.0), (30, 499.0), (60, 499.0), (120, 499.0), (330, 499.0)]
    r3 = label_touch(gf2, (498, 502), 300, 505.0, 495.0, max_gap_s=250)
    assert r3["label"] == "indeterminate" and r3["censored"] is False, r3
    assert r3["detail"] == "TOUCH_NO_BARRIER", r3


def test_r7_07_censored_outcome_reexamined_not_sealed():
    """R7-F07: an incomplete (censored/indeterminate) outcome must NOT be
    treated as final — a later fuller path should re-process it.

    Terminal outcomes (target_hit/stop_hit) stay idempotent."""
    conn = duckdb.connect(":memory:")
    did = record_decision(conn, {"ticker": "SPY", "snapshot_id": "s1",
                                  "scenario": "CALLS", "side": "CALLS",
                                  "eligible": True, "reason_codes": [],
                                  "features": {"spot": 500.0,
                                               "zone": [498, 502],
                                               "target": 505.0, "stop": 490.0,
                                               "horizon_s": 60}})

    # Initial path: touch (encounter at t=50) but no barrier hit by t=70.
    # Stop is 490; price stays above it. Window is 60s, so t=70 < 110 —
    # indeterminate, censored (HORIZON_INCOMPLETE).
    out = close_episodes(conn, {did: [(0, 490.0), (50, 500.0), (70, 495.0)]})
    assert out["closed"] == [did]
    assert out["results"][did]["label"] == "indeterminate"
    assert out["results"][did]["censored"] is True
    assert out["results"][did]["detail"] == "HORIZON_INCOMPLETE_no_decision"

    # Re-run with SAME short path: should be skipped (no new data).
    again = close_episodes(conn, {did: [(0, 490.0), (50, 500.0), (70, 495.0)]})
    assert again["closed"] == []
    assert again["skipped_idempotent"] == [did]

    # Re-run with EXTENDED path that completes the window: touch + target hit.
    # The censored outcome must be overwritten, not sealed forever.
    extended = close_episodes(conn, {did: [(0, 490.0), (50, 500.0),
                                            (70, 495.0), (110, 505.0)]})
    assert extended["closed"] == [did], extended
    assert extended["results"][did]["label"] == "target_hit", extended
    assert extended["results"][did]["censored"] is False

    # Terminal outcome is now idempotent.
    terminal_again = close_episodes(conn, {did: [(0, 490.0), (50, 500.0),
                                                   (70, 495.0), (110, 505.0)]})
    assert terminal_again["closed"] == []
    assert terminal_again["skipped_idempotent"] == [did]


def test_r7_07_initial_touch_then_later_target():
    """R7-F07: an initial touch followed later by target contact must complete
    correctly — the first incomplete result must not seal forever.

    This is the concrete regression: touch at t=50, then target at t=110
    (within 300s horizon)."""
    conn = duckdb.connect(":memory:")
    did = record_decision(conn, {"ticker": "SPY", "snapshot_id": "s1",
                                  "scenario": "CALLS", "side": "CALLS",
                                  "eligible": True, "reason_codes": [],
                                  "features": {"spot": 500.0,
                                               "zone": [498, 502],
                                               "target": 505.0, "stop": 495.0,
                                               "horizon_s": 300}})

    # Step 1: only the initial touch is available. Window not complete.
    step1 = close_episodes(conn, {did: [(0, 490.0), (50, 500.0)]})
    assert step1["closed"] == [did]
    assert step1["results"][did]["label"] == "indeterminate"
    assert step1["results"][did]["censored"] is True

    # Step 2: later data shows target contact. Must re-process and close.
    step2 = close_episodes(conn, {did: [(0, 490.0), (50, 500.0),
                                         (110, 505.0)]})
    assert step2["closed"] == [did], step2
    assert step2["results"][did]["label"] == "target_hit"
    assert step2["results"][did]["censored"] is False


def test_r7_07_terminal_outcome_idempotent_by_decision():
    """Terminal outcomes (target_hit/stop_hit) are idempotent — same decision
    + horizon + policy version cannot be rewritten by irrelevant future data."""
    conn = duckdb.connect(":memory:")
    did = record_decision(conn, {"ticker": "SPY", "snapshot_id": "s1",
                                  "scenario": "CALLS", "side": "CALLS",
                                  "eligible": True, "reason_codes": [],
                                  "features": {"spot": 500.0,
                                               "zone": [498, 502],
                                               "target": 505.0, "stop": 495.0,
                                               "horizon_s": 60}})
    out = close_episodes(conn, {did: [(0, 490.0), (50, 500.0), (70, 505.0)]})
    assert out["closed"] == [did]
    assert out["results"][did]["label"] == "target_hit"

    # Irrelevant future data after the terminal event must not change it.
    out2 = close_episodes(conn, {did: [(0, 490.0), (50, 500.0), (70, 505.0),
                                        (900, 480.0), (901, 510.0)]})
    assert out2["closed"] == []
    assert out2["skipped_idempotent"] == [did]


def test_r7_07_horizon_choices_unchanged():
    """HORIZONS_S stays at the established research default."""
    assert HORIZONS_S == (60, 180, 300, 900)


def test_r7_07_research_default_barrier_distance():
    """research_barriers.v1: default barrier distance d = max(zone_half_width,
    2 * underlying_tick). Unknown inputs → policy_unavailable."""
    from services.episode_policy import default_barrier_distance, research_default_features

    # Both known: d = max(2.0, 2*0.01) = max(2.0, 0.02) = 2.0
    d = default_barrier_distance(zone_half_width=4.0, underlying_tick=0.01)
    assert d["distance"] == 4.0, d  # max(4.0, 0.02)
    assert d["status"] == "usable"

    # Zone dominates tick: d = max(10.0, 2*0.01) = 10.0
    d2 = default_barrier_distance(zone_half_width=10.0, underlying_tick=0.01)
    assert d2["distance"] == 10.0

    # Tick dominates: d = max(0.5, 2*1.0) = 2.0
    d3 = default_barrier_distance(zone_half_width=0.5, underlying_tick=1.0)
    assert d3["distance"] == 2.0

    # Unknown zone, known tick: d = 2*underlying_tick
    d4 = default_barrier_distance(zone_half_width=None, underlying_tick=0.01)
    assert d4["distance"] == 0.02
    assert d4["status"] == "usable"

    # Both unknown: policy_unavailable
    d5 = default_barrier_distance(zone_half_width=None, underlying_tick=None)
    assert d5["status"] == "policy_unavailable"
    assert d5["distance"] is None


def test_r7_07_research_default_features():
    """research_barriers.v1: features from a zone encounter produce symmetric
    target/stop around encounter_price."""
    from services.episode_policy import research_default_features

    # Zone (498, 502), encounter at 500, tick 0.01
    # hw = 2.0, d = max(2.0, 0.02) = 2.0
    # target = 502.0, stop = 498.0
    f = research_default_features((498, 502), 500.0, underlying_tick=0.01)
    assert f["status"] == "usable"
    assert f["experimental"] is True
    assert f["policy_version"] == "research_barriers.v1"
    assert f["target"] == 502.0
    assert f["stop"] == 498.0
    assert f["barrier_distance"] == 2.0
    assert len(f["horizon_s"]) == 4

    # Zone half-width dominates: hw = 20.0, d = 20.0
    f2 = research_default_features((480, 520), 500.0, underlying_tick=0.01)
    assert f2["barrier_distance"] == 20.0
    assert f2["target"] == 520.0
    assert f2["stop"] == 480.0

    # Unknown tick and zone → policy_unavailable
    f3 = research_default_features((0, 0), 500.0)
    assert f3["status"] == "policy_unavailable"

    # Invalid zone (hi <= lo) → policy_unavailable
    f4 = research_default_features((502, 498), 500.0)
    assert f4["status"] == "policy_unavailable"


def test_r7_07_layout_from_features():
    """layout_from_features validates complete episodes and rejects degenerate
    ones (mirrors close_episodes validation)."""
    from services.episode_policy import layout_from_features

    # Complete layout
    lf = layout_from_features({
        "zone": [498, 502], "target": 505.0, "stop": 495.0,
        "horizon_s": 60, "policy_version": "research_barriers.v1"})
    assert lf["status"] == "usable"
    assert lf["zone"] == [498.0, 502.0]
    assert lf["target"] == 505.0
    assert lf["stop"] == 495.0

    # Missing zone → NEED_EPISODE
    assert layout_from_features({})["status"] == "NEED_EPISODE"
    assert layout_from_features({"zone": [498, 502]})["status"] == "NEED_EPISODE"
    assert layout_from_features({"zone": [498, 502], "target": 505.0})["status"] == "NEED_EPISODE"

    # Degenerate: target == stop → NEED_EPISODE
    assert layout_from_features({
        "zone": [498, 502], "target": 500.0, "stop": 500.0,
        "horizon_s": 60})["status"] == "NEED_EPISODE"

    # Invalid zone → NEED_EPISODE
    assert layout_from_features({
        "zone": [502, 498], "target": 505.0, "stop": 495.0,
        "horizon_s": 60})["status"] == "NEED_EPISODE"


def test_r7_07_setup_review_features():
    """setup_review.v1: read-only structural preview, no target/stop invented."""
    from services.episode_policy import setup_review_features

    sr = setup_review_features((498, 502), 500.0,
                               next_zone_above={"low": 510, "high": 514},
                               next_zone_below={"low": 490, "high": 494})
    assert sr["policy_version"] == "setup_review.v1"
    assert sr["status"] == "usable"
    assert sr["zone"] == [498, 502]
    assert sr["spot"] == 500.0
    assert sr["next_above"] == {"low": 510, "high": 514}
    assert sr["next_below"] == {"low": 490, "high": 494}
    assert "target" not in sr  # no target invented
    assert "stop" not in sr   # no stop invented


def test_r7_07_episode_status_from_outcome():
    """Map label_touch results to episode lifecycle status."""
    from services.episode_policy import episode_status_from_outcome

    # Terminal outcomes
    assert episode_status_from_outcome("target_hit", False)["status"] == "final_observed"
    assert episode_status_from_outcome("stop_hit", False)["status"] == "final_observed"
    assert episode_status_from_outcome("target_hit", True)["status"] == "pending"

    # Non-terminal
    assert episode_status_from_outcome("indeterminate", False)["status"] == "pending"
    assert episode_status_from_outcome("no_touch", False)["status"] == "pending"
    assert episode_status_from_outcome("data_gap", True)["status"] == "pending"
    assert episode_status_from_outcome("simultaneous_unknown", True)["status"] == "pending"
