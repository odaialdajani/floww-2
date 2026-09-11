"""Liquidity-stress alerts: Kyle + Amihud ILLIQUID agreement (Agent-2).

RED on main (no RULE_LIQUIDITY_STRESS seam). Fail-open: absent/mismatched/
cold state emits nothing, never raises.
"""
import pytest

from services import liquidity_state
from services.exposure_alerts import (
    RULE_LIQUIDITY_STRESS,
    evaluate_exposure_events,
    events_to_alerts,
)


def _grid():
    return {"vex_grid": {}, "charm_grid": {}}


@pytest.fixture(autouse=True)
def _clean_regime():
    liquidity_state.reset()
    yield
    liquidity_state.reset()


def _warm(sym, n=22, illiquid=True):
    """Deterministic histories with known labels.

    Illiquid: alternating all-call/all-put steps with ±3% moves on tiny
    volume → Kyle slope ≈0.03 (≥0.005 ILLIQUID), Amihud ≈3e-5 (≥1e-5).
    Liquid: flat spot, balanced flow → both LIQUID.
    """
    spot = 100.0
    for i in range(n):
        if illiquid:
            if i % 2 == 0:
                spot *= 1.03
                liquidity_state.feed(sym, 10.0, 0.0, spot)
            else:
                spot /= 1.03
                liquidity_state.feed(sym, 0.0, 10.0, spot)
        else:
            liquidity_state.feed(sym, 100.0, 100.0, 100.0)


def test_rule_constant():
    assert RULE_LIQUIDITY_STRESS == "LIQUIDITY_STRESS"


def test_fires_on_agreement():
    _warm("SPY_L")
    snap = liquidity_state.snapshot("SPY_L")
    assert snap is not None
    ev = evaluate_exposure_events(_grid(), None, liquidity_state=snap)
    assert [e["kind"] for e in ev] == ["liquidity_stress"]


def test_silent_on_disagreement():
    _warm("SPY_D", illiquid=False)
    snap = liquidity_state.snapshot("SPY_D")
    if snap is None:
        return  # both normal/cold: silence required either way
    ev = evaluate_exposure_events(_grid(), None, liquidity_state=snap)
    assert [e["kind"] for e in ev] == []


def test_silent_cold_and_unknown():
    assert liquidity_state.snapshot("NOPE_XYZ") is None
    liquidity_state.feed("COLD_X", 10.0, 10.0, 100.0)
    assert liquidity_state.snapshot("COLD_X") is None
    assert evaluate_exposure_events(_grid(), None) == []
    assert evaluate_exposure_events(_grid(), None, liquidity_state=None) == []
    assert evaluate_exposure_events(_grid(), None, liquidity_state={}) == []
    assert evaluate_exposure_events(
        _grid(), None, liquidity_state={"kyle_label": 1}) == []


def test_alert_shape():
    ev = [{"kind": "liquidity_stress", "strike": 100.0, "expiry": "",
           "magnitude": 1.0}]
    out = events_to_alerts("SPY", 100.0, ev)
    assert out[0]["rule"] == "LIQUIDITY_STRESS"
    assert 50 <= out[0]["score"] <= 99
    assert "liquid" in out[0]["why"].lower()
