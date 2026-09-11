"""A9: server-side Roll effective-spread service (Agent A, institutional loop).

Faithful port of scanLogic.js rollSpread/rollPooled/pushCapped (Roll 1984:
s = 2*sqrt(-cov(dP_t, dP_{t+1})), defined only for negative autocovariance).
Same return shapes so frontend/backend agree. Pure — no network.
"""

from services.roll_spread import push_capped, roll_pooled, roll_spread


def test_needs_three_mids():
    assert roll_spread([1.0, 2.0]) == {"spread": None, "n": 2, "truncated": False}
    assert roll_spread([])["spread"] is None


def test_flat_series_truncates_to_zero():
    out = roll_spread([5.0, 5.0, 5.0, 5.0])
    assert out == {"spread": 0, "n": 4, "truncated": True}


def test_alternating_series_measures_bounce():
    # d = [1,-1,1,-1,1], mu = 0.2, cov = -0.96 -> s = 2*sqrt(0.96)
    out = roll_spread([1.0, 2.0, 1.0, 2.0, 1.0, 2.0])
    assert abs(out["spread"] - 1.9595917942265424) < 1e-9
    assert out["truncated"] is False


def test_drops_nonpositive_and_nonfinite():
    out = roll_spread([1.0, 0.0, -2.0, 2.0, 1.0, 2.0, 1.0])
    assert out["n"] == 5  # only positive finite mids count


def test_pooled_building_state_under_30_deltas():
    out = roll_pooled([[1.0, 2.0, 1.0]])
    assert out["building"] is True and out["spread"] is None
    assert out["nd"] == 2 and out["n"] == 3


def test_pooled_aggregates_rings():
    rings = [[1.0, 2.0] * 12, [2.0, 1.0] * 12, [1.0, 2.0] * 12]
    out = roll_pooled(rings)
    assert out["building"] is False and out["nd"] == 69
    assert out["spread"] is not None and out["spread"] > 0


def test_push_capped_ring():
    ring = push_capped(None, 1.5)
    assert ring == [1.5]
    ring = push_capped([1.0, 2.0], -3.0)
    assert ring == [1.0, 2.0]  # non-positive never enters
    big = list(range(1, 100))
    assert push_capped(big, 100, cap=60) == list(range(41, 101))
