"""Offline abl.v1 requires measured support and positive activity at that wall."""

import pytest

from services.solstice_ablation import run_ladder
from services.wall_structure import discover_walls
from tests.offline_network import deny_external_network  # noqa: F401


def _snapshot():
    strikes = [{"strike": 500, "gex": 1e6, "call_gex": 8e5, "put_gex": 2e5}]
    walls = discover_walls(strikes, 500)
    assert len(walls) == 1, "fixture must produce exactly one real wall"
    wid = walls[0]["wall_id"]
    return {"spot": 500, "strikes": strikes,
            "metrics": {"magnitude_ratio_delta_over_raw": 0.9,
                        "wall_delta_share": {wid: 0.2}},
            "volume_deltas": [{"strike": 500, "delta_volume": 100}]}, wid


@pytest.mark.parametrize("shares", [{}, {"some-other-wall": 0.9}, None])
def test_scope_ratio_cannot_fill_missing_selected_wall_support(shares):
    snapshot, _ = _snapshot()
    snapshot["metrics"]["wall_delta_share"] = shares
    result = run_ladder(snapshot)
    assert result["levels"]["L1_raw_wall"]["signals"]
    assert result["levels"]["L2_plus_delta"] == {
        "signals": [], "abstentions": 1, "reason": "DELTA_UNKNOWN"}
    assert result["levels"]["L3_plus_activity"]["signals"] == []


@pytest.mark.parametrize("delta_volume", [0, -1, float("nan"), float("inf"), -float("inf"), None])
def test_nonpositive_or_nonfinite_wall_volume_is_not_activity(delta_volume):
    snapshot, _ = _snapshot()
    snapshot["volume_deltas"][0]["delta_volume"] = delta_volume
    result = run_ladder(snapshot)
    assert result["levels"]["L2_plus_delta"]["signals"]
    assert result["levels"]["L3_plus_activity"] == {
        "signals": [], "abstentions": 1, "reason": "NO_WINDOW_ACTIVITY"}


def test_missing_volume_measurement_is_not_activity():
    snapshot, _ = _snapshot()
    del snapshot["volume_deltas"][0]["delta_volume"]
    assert run_ladder(snapshot)["levels"]["L3_plus_activity"]["signals"] == []


@pytest.mark.parametrize("delta_volume", [0.001, 100])
def test_measured_local_support_at_frozen_boundary_and_positive_volume_promote(delta_volume):
    snapshot, wid = _snapshot()
    snapshot["volume_deltas"][0]["delta_volume"] = delta_volume
    result = run_ladder(snapshot)
    assert result["version"] == "abl.v1"
    assert result["cost_assumption_bps"] == 20
    assert result["levels"]["L2_plus_delta"]["signals"] == [
        {"wall_id": wid, "delta_share": 0.2, "wall_local": True}]
    assert result["levels"]["L3_plus_activity"]["signals"] == [{"wall_id": wid}]


def test_activity_elsewhere_does_not_rescue_zero_local_delta():
    snapshot, _ = _snapshot()
    snapshot["volume_deltas"] = [{"strike": 500, "delta_volume": 0},
                                  {"strike": 999, "delta_volume": 100}]
    assert run_ladder(snapshot)["levels"]["L3_plus_activity"]["signals"] == []


def test_explicit_low_local_share_remains_below_support():
    snapshot, wid = _snapshot()
    snapshot["metrics"]["wall_delta_share"][wid] = 0.19
    result = run_ladder(snapshot)
    assert result["levels"]["L2_plus_delta"] == {
        "signals": [], "abstentions": 1, "reason": "DELTA_SHARE_BELOW_SUPPORT"}
