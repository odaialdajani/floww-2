"""Recovery regressions on the published base; no provider or server imports."""

import pytest

from domain.exposure_metrics import wall_metric_breakdown
from services.solstice_enrichment import window_contract_activity
from services.solstice_provenance import check_volume_window


def contract(**overrides):
    return {"osi": "TEST301115C00100000", "strike": 100, "expiry": "2030-11-15",
            "type": "call", "gamma": 0.01, "delta": 0.5,
            "multiplier": 100, "oi": 1000, "volume": 100, **overrides}


def window(**overrides):
    old = contract(**overrides)
    return window_contract_activity([old], [{**old, "volume": 120}], 100)


@pytest.mark.parametrize("field,value", [
    ("delta", True), ("delta", False), ("gamma", True),
    ("type", "unknown"), ("type", None),
    ("multiplier", None), ("multiplier", 0), ("multiplier", True),
    ("multiplier", -1), ("multiplier", float("nan")),
    ("adjusted", True),
])
def test_window_never_invents_valid_inputs(field, value):
    assert window(**{field: value})["contracts"] == []


@pytest.mark.parametrize("spot", [True, None, 0, -1, float("nan")])
def test_window_rejects_bad_spot_without_raising(spot):
    c = contract()
    out = window_contract_activity([c], [{**c, "volume": 120}], spot)
    assert out["status"] == "unavailable"
    assert out["reason"] == "SPOT_UNKNOWN"
    assert out["contracts"] == []


def test_window_current_delta_must_also_be_valid():
    c = contract()
    out = window_contract_activity([c], [{**c, "volume": 120, "delta": True}], 100)
    assert out["contracts"] == []


def test_window_put_uses_abs_delta_and_frozen_open_gamma():
    c = contract(type="put", delta=-0.5)
    out = window_contract_activity([c], [{**c, "volume": 120, "gamma": 0.99}], 100)
    assert out["contracts"][0]["window_daddex"] == -1000


def test_same_wall_volume_delta_is_distinct_and_local():
    walls = [{"wall_id": "w", "members": [100]}]
    wb = wall_metric_breakdown(walls, [contract(), contract(strike=200, volume=999999)], 100)["w"]
    assert wb["volume_net"] == 10000
    assert wb["session_delta_volume_net"] == 5000
    assert wb["session_delta_volume_gross"] == 5000
    assert wb["session_delta_volume_usable"] == 1


def test_wall_delta_volume_missing_is_not_measured_zero():
    wb = wall_metric_breakdown([{"wall_id": "w", "members": [100]}], [contract(delta=None)], 100)["w"]
    assert wb["volume_net"] == 10000
    assert wb["session_delta_volume_net"] is None
    assert wb["session_delta_volume_usable"] == 0
    assert wb["session_delta_volume_missing"] == 1


def test_wall_reported_zero_volume_keeps_observation_separate_from_missing():
    wb = wall_metric_breakdown([{"wall_id": "w", "members": [100]}], [contract(volume=0)], 100)["w"]
    assert wb["session_delta_volume_net"] == 0
    assert wb["session_delta_volume_usable"] == 1


@pytest.mark.parametrize("prev,cur", [(False, 1), (0, True)])
def test_boolean_volume_is_invalid_not_a_counter(prev, cur):
    assert check_volume_window(prev, cur)["valid"] is False
