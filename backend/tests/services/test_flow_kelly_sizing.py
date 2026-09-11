"""Agent C (C3): Kelly-capped sizing in the trade bridge.

Fraction from calibrated p + key-level reward:risk, hard-capped.
Uncalibrated p (None / uncalibrated*) ⇒ legacy flat schedule, min 1.
"""
import pytest

from services.flow_trade_bridge import alert_to_order, kelly_size


def _alert(**kw):
    base = dict(
        under="SPY", type="call", strike=700.0, exp="2026-09-18", dte=10,
        tier="GOLD", side="BUY", est_entry=5.0, conviction=80,
        ckey="SPY|call|700|2026-09-18", key="score|SPY|call|700|2026-09-18",
        premium=5000.0, vol_oi=6.0, sigma=6.5,
        key_levels={"entry": 5.0, "invalidation": 3.0, "target": 9.0},
        p_move=0.60, p_method="decile",
    )
    base.update(kw)
    return base


def test_kelly_table_hand_worked():
    # p=0.6, b=(9-5)/(5-3)=2 → f*=(0.6*2-0.4)/2=0.4 → quarter=0.10
    # capped at SINGLE_NAME_CAP 0.05 → risk=100k*0.05=5000 → 5000/500=10
    out = kelly_size(_alert(), account_equity=100_000.0)
    assert out["qty"] == 10
    assert out["size_basis"]["method"] == "kelly_capped"
    assert out["size_basis"]["p_move"] == pytest.approx(0.60)
    assert out["size_basis"]["payoff_ratio"] == pytest.approx(2.0)
    assert out["size_basis"]["kelly_f"] == pytest.approx(0.10)


def test_uncalibrated_falls_back_to_flat_schedule():
    a = _alert(p_move=None, p_method="uncalibrated")
    out = kelly_size(a, account_equity=100_000.0)
    assert out["size_basis"]["method"] == "flat"
    # legacy numbers preserved exactly: 2% * full conviction scale, min 1
    assert out["qty"] == 4  # floor(100000*0.02*1.0/500)


def test_missing_key_levels_falls_back_with_reason():
    a = _alert(key_levels=None)
    out = kelly_size(a, account_equity=100_000.0)
    assert out["size_basis"]["method"] == "flat"
    assert "key_levels" in out["size_basis"]["reason"]


def test_negative_edge_sizes_zero():
    # p=0.3, b=2 → f*=(0.6-0.7)/2<0 → no edge → refuse (qty 0, not 1)
    a = _alert(p_move=0.30)
    out = kelly_size(a, account_equity=100_000.0)
    assert out["qty"] == 0
    assert out["size_basis"]["method"] == "kelly_capped"


def test_earnings_protocol_caps_risk():
    a = _alert(earnings_protocol=True)
    out = kelly_size(a, account_equity=100_000.0)
    assert out["size_basis"]["risk_frac"] == pytest.approx(0.01)
    assert out["qty"] == 2  # floor(100000*0.01/500)


def test_order_carries_size_basis():
    order = alert_to_order(_alert(), account_equity=100_000.0)
    assert order["quantity"] == 10
    assert order["metadata"]["size_basis"]["method"] == "kelly_capped"
    assert order["metadata"]["p_move"] == pytest.approx(0.60)
    assert order["metadata"]["p_method"] == "decile"
