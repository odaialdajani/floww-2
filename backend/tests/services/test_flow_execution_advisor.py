"""Agent C (C4): execution advisor — TAKE vs WORK vs SKIP + slippage est.

Urgency from Kyle-lambda + spread + velocity (Almgren-Chriss direction:
patient limit vs urgent take). Pure function; consumes lambda/spread/
velocity as inputs (B owns the bars-methodology producers per C13).
"""
import pytest

from services.flow_trade_bridge import advise_execution


def test_hot_deep_tape_says_take():
    out = advise_execution({}, kyle_lambda=0.0005, spread_bps=20.0, velocity=15.0)
    assert out["action"] == "TAKE"
    assert out["slippage_bps_est"] == pytest.approx(round(20.0 / 2 + 0.25 * 0.0005 * 10000, 1))


def test_wide_spread_says_work():
    out = advise_execution({}, kyle_lambda=0.0005, spread_bps=120.0, velocity=15.0)
    assert out["action"] == "WORK"


def test_illiquid_plus_xwide_says_skip():
    out = advise_execution({}, kyle_lambda=0.008, spread_bps=250.0, velocity=1.0)
    assert out["action"] == "SKIP"


def test_toxic_always_skips():
    out = advise_execution({}, kyle_lambda=0.0001, spread_bps=5.0, velocity=99.0, toxic=True)
    assert out["action"] == "SKIP"
    assert "toxic" in out["reason"].lower()


def test_no_inputs_patient_default():
    out = advise_execution({})
    assert out["action"] == "WORK"
    assert out["slippage_bps_est"] is None


def test_order_embeds_advice():
    from services.flow_trade_bridge import alert_to_order
    alert = dict(under="SPY", est_entry=5.0, kyle_lambda=0.0005,
                 spread_bps=20.0, velocity_per_min=15.0)
    order = alert_to_order(alert)
    assert order["metadata"]["execution"]["action"] == "TAKE"
