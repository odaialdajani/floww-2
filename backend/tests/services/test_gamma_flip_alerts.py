"""Gamma-flip proximity alerts (dealer positioning edge: price pinned near the
flip behaves mean-reverting above / momentum below; approach = A+ trigger).

RED on main (no RULE_GAMMA_FLIP seam); GREEN with the rule. Fail-open:
None/non-numeric flip or spot, or distance beyond threshold, emits nothing.
"""
import pytest

from services.exposure_alerts import (
    RULE_GAMMA_FLIP,
    evaluate_exposure_events,
    events_to_alerts,
)


def _grid():
    return {"vex_grid": {}, "charm_grid": {}}


def test_rule_constant():
    assert RULE_GAMMA_FLIP == "GAMMA_FLIP"


def test_fires_within_one_percent_above():
    ev = evaluate_exposure_events(
        _grid(), None, flip_level=99.5, spot=100.0)
    assert [e["kind"] for e in ev] == ["gamma_flip_approach"]
    assert ev[0]["direction"] == "above"


def test_fires_within_one_percent_below():
    ev = evaluate_exposure_events(
        _grid(), None, flip_level=101.0, spot=100.0)
    assert [e["kind"] for e in ev] == ["gamma_flip_approach"]
    assert ev[0]["direction"] == "below"


def test_silent_beyond_threshold():
    ev = evaluate_exposure_events(
        _grid(), None, flip_level=110.0, spot=100.0)
    assert ev == []


def test_silent_on_missing():
    assert evaluate_exposure_events(_grid(), None) == []
    assert evaluate_exposure_events(_grid(), None, flip_level=None, spot=100.0) == []
    assert evaluate_exposure_events(_grid(), None, flip_level=100.0, spot=0) == []
    assert evaluate_exposure_events(_grid(), None, flip_level="x", spot=100.0) == []


def test_alert_shape_and_score_monotonic():
    near = events_to_alerts("SPY", 100.0, [
        {"kind": "gamma_flip_approach", "strike": 100.1, "expiry": "",
         "magnitude": 0.001, "direction": "above"}])
    far = events_to_alerts("SPY", 100.0, [
        {"kind": "gamma_flip_approach", "strike": 99.2, "expiry": "",
         "magnitude": 0.008, "direction": "below"}])
    assert near[0]["rule"] == "GAMMA_FLIP"
    assert near[0]["score"] > far[0]["score"]
    assert 50 <= far[0]["score"] <= 99
    assert "flip" in near[0]["why"].lower()
