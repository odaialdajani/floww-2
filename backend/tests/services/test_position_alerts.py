from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from services.position_alerts import PositionAlertConfig, PositionAlertService, PositionSnapshot

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


def position(**kwargs):
    values = dict(position_id="trade-1", symbol="SPY-option", side="LONG", quantity=2,
                  entry_price=10, premium_factor=100, entry_time=NOW - timedelta(minutes=60))
    values.update(kwargs)
    return PositionSnapshot(**values)


def test_option_loss_uses_contract_factor_and_explicit_price():
    svc = PositionAlertService()
    result = svc.evaluate_positions([position()], {"trade-1": 9}, now=NOW)
    event = result.alerts[0]
    assert event.alert_type.value == "STOP_LOSS"
    assert event.unrealized_pnl == -200
    assert event.unrealized_pnl_pct == pytest.approx(-0.1)


@pytest.mark.parametrize("bad", [None, True, "nan", "inf", -1])
def test_missing_or_bad_mark_never_becomes_entry_price(bad):
    result = PositionAlertService().evaluate_positions([position()], {"trade-1": bad}, now=NOW)
    assert not result.alerts
    assert result.unavailable["trade-1"] == ["current_price"]
    assert result.positions[0].unrealized_pnl is None


def test_no_symbol_fallback_and_factor_required():
    svc = PositionAlertService()
    result = svc.evaluate_positions([position(premium_factor=None)], {"SPY-option": 9}, now=NOW)
    assert set(result.unavailable["trade-1"]) == {"current_price", "premium_factor"}


def test_zero_mark_is_real_loss_and_fractional_short_is_supported():
    result = PositionAlertService().evaluate_positions([position()], {"trade-1": 0}, now=NOW)
    assert result.alerts[0].unrealized_pnl == -2000
    result = PositionAlertService().evaluate_positions(
        [position(side="SHORT", quantity=1.5, premium_factor=1)], {"trade-1": 8}, now=NOW)
    assert result.alerts[0].alert_type.value == "TAKE_PROFIT"
    assert result.alerts[0].unrealized_pnl == 3


@pytest.mark.parametrize("field,value", [("max_hold_minutes", 0), ("max_hold_minutes", -1),
    ("max_hold_minutes", True), ("stop_loss_pct", float("nan")), ("take_profit_pct", -1)])
def test_invalid_config_rejected(field, value):
    with pytest.raises(ValueError):
        PositionAlertConfig(**{field: value})


def test_hold_alert_does_not_need_quote_and_requires_aware_time():
    svc = PositionAlertService(PositionAlertConfig(max_hold_minutes=30))
    result = svc.evaluate_positions([position()], {}, now=NOW)
    assert [a.alert_type.value for a in result.alerts] == ["MAX_HOLD_TIME"]
    assert result.alerts[0].current_price is None
    result = PositionAlertService().evaluate_positions(
        [position(entry_time=NOW.replace(tzinfo=None))], {"trade-1": 10}, now=NOW)
    assert "entry_time" in result.unavailable["trade-1"]


def test_identity_dedup_reentry_and_acknowledgement():
    svc = PositionAlertService()
    first = svc.evaluate_positions([position()], {"trade-1": 9}, now=NOW)
    assert not svc.evaluate_positions([position()], {"trade-1": 8}, now=NOW).alerts
    assert svc.acknowledge(first.alerts[0].alert_id)
    assert svc.get_alert_history()[0]["acknowledged"]
    svc.evaluate_positions([], {}, now=NOW)
    assert svc.evaluate_positions([position()], {"trade-1": 9}, now=NOW).alerts
    with pytest.raises(ValueError):
        svc.evaluate_positions([position(), position()], {}, now=NOW)


def test_portfolio_drawdown_uses_only_explicit_account_values():
    svc = PositionAlertService()
    assert svc.evaluate_positions([], {}, now=NOW, portfolio_value=1000).drawdown_pct == 0
    unknown = svc.evaluate_positions([], {}, now=NOW)
    assert unknown.drawdown_pct is None
    assert not unknown.alerts
    loss = svc.evaluate_positions([], {}, now=NOW, portfolio_value=800)
    assert loss.alerts[0].alert_type.value == "DRAW_DOWN"
    assert loss.drawdown_pct == pytest.approx(-0.2)
    assert loss.alerts[0].unrealized_pnl is None
    assert loss.alerts[0].details["drawdown_ratio"] == pytest.approx(-0.2)


def test_independent_contracts_same_symbol_do_not_share_dedup():
    a, b = position(), position(position_id="trade-2")
    result = PositionAlertService().evaluate_positions([a, b], {"trade-1": 9, "trade-2": 12}, now=NOW)
    assert len(result.alerts) == 2
    assert len({a.alert_id for a in result.alerts}) == 2


def test_per_position_override_is_validated_and_zero_entry_has_unknown_percentage():
    svc = PositionAlertService()
    svc.set_position_thresholds("trade-1", stop_loss_pct=-20)
    assert not svc.evaluate_positions([position()], {"trade-1": 9}, now=NOW).alerts
    with pytest.raises(ValueError):
        svc.set_position_thresholds("trade-1", max_hold_minutes=0)
    result = PositionAlertService().evaluate_positions([position(entry_price=0)], {"trade-1": 2}, now=NOW)
    assert result.positions[0].unrealized_pnl == 400
    assert result.positions[0].unrealized_pnl_pct is None
    assert not result.alerts
