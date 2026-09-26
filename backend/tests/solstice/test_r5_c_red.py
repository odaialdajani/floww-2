"""R5-C red tests: causal wall lifecycle (G4/R09-R10,R16-R17)."""

import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime, timedelta

T0 = datetime(2030, 1, 2, 12, 0, tzinfo=UTC)
WALL = {"low": 498.0, "high": 502.0, "mid": 500.0, "wall_id": "w_c"}


def _step(state, spot, dt_s, **last):
    from services.wall_interaction import transition
    base = {"state": state, "at": (T0).isoformat()}
    base.update(last)
    return transition(state, spot, WALL, now=T0 + timedelta(seconds=dt_s), last=base)


def test_r09_full_path_beyond_then_invalidated():
    # Chronological: approach from above -> test -> leave above -> stay beyond
    # -> invalidated. Never accepted_beyond without continuous beyond dwell.
    s = _step("unobserved", 505.0, 0)
    assert s["state"] == "approaching"
    s = _step("approaching", 500.0, 10, approach_side="above")
    assert s["state"] == "testing"
    s = _step("testing", 510.0, 20, approach_side="above",
              inside_since=(T0 + timedelta(seconds=10)).isoformat())
    assert s["state"] == "retesting", s
    s = _step("retesting", 510.0, 200, approach_side="above",
              beyond_since=(T0 + timedelta(seconds=20)).isoformat(),
              beyond_side="above")
    assert s["state"] == "invalidated", s


def test_r10_leave_clears_inside_dwell():
    # 50s inside, leave 200s, return: must NOT confirm immediately.
    inside = (T0 + timedelta(seconds=10)).isoformat()
    s = _step("testing", 510.0, 60, approach_side="above", inside_since=inside)
    assert s["state"] == "retesting"
    assert s.get("inside_since") is None, s
    s2 = _step("retesting", 500.0, 260, approach_side="above",
               beyond_since=(T0 + timedelta(seconds=60)).isoformat(),
               beyond_side="above")
    assert s2["state"] == "retesting", s2


def test_r16_zero_mass_breaks_zones():
    from services.wall_structure import discover_walls
    rows = [{"strike": 500.0, "gex": 5e6, "call_gex": 5e6, "put_gex": 0.0},
            {"strike": 505.0, "gex": 0.0, "call_gex": 0.0, "put_gex": 0.0},
            {"strike": 510.0, "gex": 5e6, "call_gex": 5e6, "put_gex": 0.0}]
    walls = discover_walls(rows, 505.0, pct_threshold=0.0)
    assert len(walls) == 2, walls


def test_r16_scope_ids_bind_expiry_dimensions():
    from services.wall_interaction import scope_id_for
    a = scope_id_for("SPY", {"mode": "day", "dte": None, "scalp": False, "expiries": 4})
    b = scope_id_for("SPY", {"mode": "day", "dte": 0, "scalp": False, "expiries": 4})
    assert a != b


def test_r5c_gap_and_newest_wins():
    from services.wall_interaction import detect_wall_gap, is_newer_state
    old = {"state": "testing", "at": (T0 - timedelta(seconds=3600)).isoformat()}
    assert detect_wall_gap(old, T0, "public_api") is True
    assert detect_wall_gap(
        {"state": "testing", "at": T0.isoformat(), "data_source": "yfinance"},
        T0 + timedelta(seconds=10), "public_api") is True
    assert detect_wall_gap(
        {"state": "testing", "at": T0.isoformat(), "data_source": "public_api"},
        T0 + timedelta(seconds=10), "public_api") is False
    assert is_newer_state({"at": T0.isoformat()}, {"at": (T0 - timedelta(seconds=5)).isoformat()}) is True
    assert is_newer_state({"at": "bogus"}, {"at": T0.isoformat()}) is False


def test_r09_direction_aware_invalidation():
    # Holding (support) is invalidated only by adverse-side (below) acceptance;
    # a favorable-side excursion never invalidates.
    fav = _step("holding", 510.0, 500, approach_side="above",
                beyond_since=(T0 + timedelta(seconds=380)).isoformat(),
                beyond_side="above")
    assert fav["state"] != "invalidated", fav
    adv = _step("holding", 490.0, 500, approach_side="above",
                beyond_since=(T0 + timedelta(seconds=380)).isoformat(),
                beyond_side="below")
    assert adv["state"] == "invalidated", adv
