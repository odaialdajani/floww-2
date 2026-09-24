"""P04 red-first tests (R4-05/06). Each fails on baseline behavior."""

import sys

sys.path.insert(0, "backend")


def _wall(lo=498.0, hi=502.0, wid="w_test"):
    return {"low": lo, "high": hi, "mid": (lo + hi) / 2, "wall_id": wid}


def test_r4_05_side_vocabulary_not_reversed():
    from datetime import UTC, datetime, timedelta

    from services.wall_interaction import transition
    t0 = datetime(2030, 1, 2, 12, 0, tzinfo=UTC)
    wall = _wall()
    # Lower wall approached from above (price came down) -> holding/support.
    s = transition("testing", 500.0, wall, now=t0 + timedelta(seconds=61),
                   last={"state": "testing", "at": t0.isoformat(),
                         "approach_side": "above",
                         "inside_since": t0.isoformat()})
    assert s["state"] == "holding", s
    # Upper wall approached from below (price came up) -> rejecting/resistance.
    s2 = transition("testing", 500.0, wall, now=t0 + timedelta(seconds=61),
                    last={"state": "testing", "at": t0.isoformat(),
                          "approach_side": "below",
                          "inside_since": t0.isoformat()})
    assert s2["state"] == "rejecting", s2


def test_r4_05_acceptance_needs_continuous_beyond_dwell():
    from datetime import UTC, datetime, timedelta

    from services.wall_interaction import transition
    t0 = datetime(2030, 1, 2, 12, 0, tzinfo=UTC)
    wall = _wall()
    # 120s inside, then 1s beyond -> must NOT accept (needs continuous beyond).
    s = transition("testing", 510.0, wall, now=t0 + timedelta(seconds=121),
                   last={"state": "testing", "at": t0.isoformat(),
                         "approach_side": "above",
                         "inside_since": t0.isoformat(),
                         "beyond_since": (t0 + timedelta(seconds=120)).isoformat()})
    assert s["state"] != "accepted_beyond", s
    # Continuous 120s beyond same boundary -> accept.
    s2 = transition("testing", 510.0, wall, now=t0 + timedelta(seconds=121),
                    last={"state": "testing", "at": t0.isoformat(),
                          "approach_side": "above",
                          "inside_since": t0.isoformat(),
                          "beyond_since": t0.isoformat()})
    assert s2["state"] == "accepted_beyond", s2


def test_r4_05_gap_breaks_continuity():
    from datetime import UTC, datetime

    from services.wall_interaction import transition
    t0 = datetime(2030, 1, 2, 12, 0, tzinfo=UTC)
    wall = _wall()
    s = transition("testing", 500.0, wall, now=t0,
                   last={"state": "testing", "at": t0.isoformat(), "gap": True})
    assert s["state"] == "unobserved" and s["event"] == "continuity_break"


def test_r4_06_history_not_always_unobserved():
    from services import wall_interaction as wi
    wi.save_last("SPY", "scope-a", "w_hist", {"state": "testing", "at": "2030-01-02T12:00:00+00:00"})
    got = wi.load_last("SPY", "scope-a", "w_hist")
    assert got is not None and got["state"] == "testing"
    assert wi.load_last("SPY", "scope-a", "w_missing") is None
    assert wi.load_last("QQQ", "scope-a", "w_hist") is None  # no cross-symbol leak


def test_r4_06_scenarios_carry_scoped_wall_id():
    from services.wall_interaction import scenario_for, wall_position
    wall = _wall(lo=490.0, hi=495.0, wid="w_below")
    assert wall_position(wall, 500.0) == "below"
    sc = scenario_for(wall, 500.0, wall_position="below", wall_id="w_below", scope="SPY:swing")
    assert len(sc) == 2
    for s in sc:
        assert s["wall_id"] == "w_below" and s["wall_position"] == "below"
    assert wall_position(_wall(lo=505.0, hi=510.0), 500.0) == "above"
    assert wall_position(_wall(lo=498.0, hi=502.0), 500.0) == "inside"
