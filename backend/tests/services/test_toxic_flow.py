"""VPIN toxicity alerts in the exposure pipeline (prop-desk edge: toxic flow
precedes maker repricing; Easley-Lopez de Prado-O'Hara VPIN >= 0.7 high regime).

RED on main (no vpin_state seam); GREEN with the rule. Fail-open throughout:
absent/malformed VPIN state emits nothing, never raises.
"""
import pytest

from services.exposure_alerts import (
    RULE_TOXIC_FLOW,
    TOXIC_VPIN,
    evaluate_exposure_events,
    events_to_alerts,
)


def _grid():
    return {"vex_grid": {}, "charm_grid": {}}


def test_threshold_constant_documented():
    assert TOXIC_VPIN == 0.7


def test_toxic_fires_at_high_vpin():
    ev = evaluate_exposure_events(
        _grid(), None, vpin_state={"vpin": 0.85, "cdf": 0.9, "n_buckets": 50})
    kinds = [e["kind"] for e in ev]
    assert "toxic_flow" in kinds
    toxic = next(e for e in ev if e["kind"] == "toxic_flow")
    assert toxic["magnitude"] == pytest.approx(0.85)


def test_silent_below_threshold():
    ev = evaluate_exposure_events(
        _grid(), None, vpin_state={"vpin": 0.4, "cdf": 0.3, "n_buckets": 50})
    assert [e["kind"] for e in ev] == []


def test_silent_without_state():
    assert evaluate_exposure_events(_grid(), None) == []
    assert evaluate_exposure_events(_grid(), None, vpin_state=None) == []


def test_silent_on_malformed_state():
    assert evaluate_exposure_events(_grid(), None, vpin_state={}) == []
    assert evaluate_exposure_events(_grid(), None, vpin_state={"vpin": "x"}) == []
    assert evaluate_exposure_events(_grid(), None, vpin_state="junk") == []


def test_cdf_optional_vpin_only_gate():
    ev = evaluate_exposure_events(
        _grid(), None, vpin_state={"vpin": 0.9, "n_buckets": 50})
    assert [e["kind"] for e in ev] == ["toxic_flow"]


def test_cdf_gate_blocks_mediocre_tail():
    ev = evaluate_exposure_events(
        _grid(), None, vpin_state={"vpin": 0.8, "cdf": 0.3, "n_buckets": 50})
    assert [e["kind"] for e in ev] == []


def test_cold_engine_silent():
    ev = evaluate_exposure_events(
        _grid(), None, vpin_state={"vpin": 0.9, "cdf": 0.95, "n_buckets": 3})
    assert [e["kind"] for e in ev] == []


def test_alert_shape():
    ev = [{"kind": "toxic_flow", "strike": 100.0, "expiry": "", "magnitude": 0.85}]
    out = events_to_alerts("SPY", 100.0, ev)
    assert len(out) == 1
    a = out[0]
    assert a["rule"] == RULE_TOXIC_FLOW == "TOXIC_FLOW"
    assert a["under"] == "SPY" and a["side"] == "FLOW"
    assert 50 <= a["score"] <= 99
    assert "toxic" in a["why"].lower()
    assert a["premium"] is None and a["tier"] == "SILVER"


def test_snapshot_helper_cold_returns_none():
    from routes.vpin import snapshot_vpin_state
    assert snapshot_vpin_state("NOPE_NOTRACKED_XYZ") is None
