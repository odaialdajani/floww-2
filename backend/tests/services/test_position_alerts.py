"""
backend/tests/services/test_position_alerts.py

Tests for the PositionAlertService — 25+ tests covering threshold
evaluation, deduplication, WebSocket broadcast, AlertDispatcher
integration, configuration, and edge cases.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List, Optional

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.position_alerts import (
    PositionAlertService,
    PositionAlertConfig,
    PositionAlertEvent,
    PositionAlertType,
    PositionAlertSeverity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_position(
    symbol: str = "SPY",
    side: str = "LONG",
    quantity: int = 10,
    entry_price: float = 500.0,
    entry_time: Optional[str] = None,
    order_id: str = "TEST-0001",
    status: str = "open",
    exit_price: float = 0.0,
) -> MagicMock:
    """Create a mock PaperPosition."""
    pos = MagicMock()
    pos.symbol = symbol
    pos.side = side
    pos.quantity = quantity
    pos.entry_price = entry_price
    pos.entry_time = entry_time or datetime.now(timezone.utc).isoformat()
    pos.order_id = order_id
    pos.status = status
    pos.exit_price = exit_price
    pos.realized_pnl = 0.0
    return pos


def make_mock_trader(
    cash: float = 100_000.0,
    initial_capital: float = 100_000.0,
    positions: Optional[Dict[str, Any]] = None,
) -> MagicMock:
    """Create a mock PaperTrader with configurable state."""
    trader = MagicMock()
    trader.cash = cash
    trader.initial_capital = initial_capital
    if positions is not None:
        trader.positions = positions
    else:
        trader.positions = {}
    return trader


class MockWS:
    """Mock WebSocket client for testing."""
    def __init__(self):
        self.sent: List[Dict[str, Any]] = []
        self.closed = False

    async def send_json(self, data: Dict[str, Any]) -> None:
        self.sent.append(data)

    def __eq__(self, other):
        return id(self) == id(other)

    def __hash__(self):
        return id(self)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestPositionAlertConfig:
    """Test PositionAlertConfig defaults and env loading."""

    def test_defaults(self):
        cfg = PositionAlertConfig()
        assert cfg.stop_loss_pct == -5.0
        assert cfg.take_profit_pct == 10.0
        assert cfg.max_drawdown_pct == -15.0
        assert cfg.max_hold_minutes == 1440
        assert cfg.poll_seconds == 30
        assert cfg.enabled is True

    def test_to_dict(self):
        cfg = PositionAlertConfig(stop_loss_pct=-10.0)
        d = cfg.to_dict()
        assert d["stop_loss_pct"] == -10.0
        assert d["enabled"] is True

    def test_from_env(self):
        import os
        os.environ["POSITION_ALERT_STOP_LOSS_PCT"] = "-7.5"
        os.environ["POSITION_ALERT_MAX_HOLD_MINUTES"] = "60"
        try:
            cfg = PositionAlertConfig.from_env()
            assert cfg.stop_loss_pct == -7.5
            assert cfg.max_hold_minutes == 60
            assert cfg.take_profit_pct == 10.0  # default
        finally:
            del os.environ["POSITION_ALERT_STOP_LOSS_PCT"]
            del os.environ["POSITION_ALERT_MAX_HOLD_MINUTES"]

    def test_from_env_missing(self):
        """Missing env vars should fall back to defaults."""
        cfg = PositionAlertConfig.from_env()
        assert cfg.stop_loss_pct == -5.0
        assert cfg.take_profit_pct == 10.0


# ---------------------------------------------------------------------------
# Service initialization tests
# ---------------------------------------------------------------------------

class TestPositionAlertServiceInit:
    """Test service construction and wiring."""

    def test_init_default_config(self):
        svc = PositionAlertService()
        assert svc.config.stop_loss_pct == -5.0
        assert svc._running is False
        assert svc._task is None
        assert len(svc._ws_clients) == 0

    def test_init_custom_config(self):
        cfg = PositionAlertConfig(stop_loss_pct=-10.0, take_profit_pct=15.0)
        svc = PositionAlertService(config=cfg)
        assert svc.config.stop_loss_pct == -10.0
        assert svc.config.take_profit_pct == 15.0

    def test_set_paper_trader(self):
        svc = PositionAlertService()
        trader = make_mock_trader()
        svc.set_paper_trader(trader)
        assert svc._paper_trader is trader

    def test_set_price_provider(self):
        svc = PositionAlertService()
        async def fake_provider(sym: str) -> float:
            return 510.0
        svc.set_price_provider(fake_provider)
        assert svc._price_provider is not None


# ---------------------------------------------------------------------------
# Threshold management tests
# ---------------------------------------------------------------------------

class TestPositionThresholds:
    """Test per-position threshold overrides."""

    def test_global_defaults(self):
        svc = PositionAlertService()
        t = svc.get_position_thresholds("SPY")
        assert t["stop_loss_pct"] == -5.0
        assert t["take_profit_pct"] == 10.0
        assert t["max_hold_minutes"] == 1440

    def test_set_position_thresholds(self):
        svc = PositionAlertService()
        svc.set_position_thresholds("SPY", stop_loss_pct=-3.0, take_profit_pct=8.0)
        t = svc.get_position_thresholds("SPY")
        assert t["stop_loss_pct"] == -3.0
        assert t["take_profit_pct"] == 8.0
        assert t["max_hold_minutes"] == 1440  # unchanged

    def test_isolated_per_symbol(self):
        svc = PositionAlertService()
        svc.set_position_thresholds("SPY", stop_loss_pct=-3.0)
        svc.set_position_thresholds("QQQ", take_profit_pct=12.0)
        assert svc.get_position_thresholds("SPY")["stop_loss_pct"] == -3.0
        assert svc.get_position_thresholds("SPY")["take_profit_pct"] == 10.0  # default
        assert svc.get_position_thresholds("QQQ")["stop_loss_pct"] == -5.0  # default
        assert svc.get_position_thresholds("QQQ")["take_profit_pct"] == 12.0

    def test_reset_fired_types(self):
        svc = PositionAlertService()
        svc._fired_types["SPY_LONG_500.0"] = {"STOP_LOSS"}
        svc._fired_types["SPY_LONG_505.0"] = {"TAKE_PROFIT"}
        svc._fired_types["QQQ_SHORT_400.0"] = {"STOP_LOSS"}
        svc.reset_fired_types("SPY")
        assert "SPY_LONG_500.0" not in svc._fired_types
        assert "SPY_LONG_505.0" not in svc._fired_types
        assert "QQQ_SHORT_400.0" in svc._fired_types


# ---------------------------------------------------------------------------
# Alert evaluation tests
# ---------------------------------------------------------------------------

class TestPositionAlertEvaluation:
    """Test threshold evaluation logic."""

    @pytest.mark.asyncio
    async def test_no_trader_no_alerts(self):
        svc = PositionAlertService()
        alerts = await svc.evaluate_positions()
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_disabled_no_alerts(self):
        svc = PositionAlertService()
        svc.config.enabled = False
        svc.set_paper_trader(make_mock_trader(positions={"key1": make_mock_position()}))
        alerts = await svc.evaluate_positions()
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_no_open_positions(self):
        svc = PositionAlertService()
        svc.set_paper_trader(make_mock_trader(positions={}))
        alerts = await svc.evaluate_positions()
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_stop_loss_triggers(self):
        svc = PositionAlertService(config=PositionAlertConfig(stop_loss_pct=-5.0, take_profit_pct=10.0))
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG_TEST": pos}))
        alerts = await svc.evaluate_positions(current_prices={"SPY": 460.0})  # -8% loss
        assert len(alerts) >= 1
        stop_loss_alerts = [a for a in alerts if a.alert_type == PositionAlertType.STOP_LOSS]
        assert len(stop_loss_alerts) == 1
        assert stop_loss_alerts[0].symbol == "SPY"
        assert stop_loss_alerts[0].severity == PositionAlertSeverity.CRITICAL
        assert stop_loss_alerts[0].unrealized_pnl_pct < 0

    @pytest.mark.asyncio
    async def test_take_profit_triggers(self):
        svc = PositionAlertService(config=PositionAlertConfig(stop_loss_pct=-5.0, take_profit_pct=10.0))
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG_TEST": pos}))
        alerts = await svc.evaluate_positions(current_prices={"SPY": 560.0})  # +12% gain
        tp_alerts = [a for a in alerts if a.alert_type == PositionAlertType.TAKE_PROFIT]
        assert len(tp_alerts) == 1
        assert tp_alerts[0].severity == PositionAlertSeverity.WARNING
        assert tp_alerts[0].unrealized_pnl_pct > 0

    @pytest.mark.asyncio
    async def test_short_position_stop_loss(self):
        svc = PositionAlertService()
        svc.config.stop_loss_pct = -5.0
        pos = make_mock_position(symbol="SPY", side="SHORT", quantity=10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_SHORT_TEST": pos}))
        # Short loss = price went up
        alerts = await svc.evaluate_positions(current_prices={"SPY": 540.0})  # -8% loss on short
        sl_alerts = [a for a in alerts if a.alert_type == PositionAlertType.STOP_LOSS]
        assert len(sl_alerts) >= 1

    @pytest.mark.asyncio
    async def test_short_position_take_profit(self):
        svc = PositionAlertService()
        svc.config.take_profit_pct = 10.0
        pos = make_mock_position(symbol="SPY", side="SHORT", quantity=10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_SHORT_TEST": pos}))
        # Short profit = price went down
        alerts = await svc.evaluate_positions(current_prices={"SPY": 430.0})  # +14% gain on short
        tp_alerts = [a for a in alerts if a.alert_type == PositionAlertType.TAKE_PROFIT]
        assert len(tp_alerts) >= 1

    @pytest.mark.asyncio
    async def test_no_alert_when_within_thresholds(self):
        svc = PositionAlertService()
        svc.config.stop_loss_pct = -5.0
        svc.config.take_profit_pct = 10.0
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG_TEST": pos}))
        alerts = await svc.evaluate_positions(current_prices={"SPY": 510.0})  # +2% within range
        sl_alerts = [a for a in alerts if a.alert_type == PositionAlertType.STOP_LOSS]
        tp_alerts = [a for a in alerts if a.alert_type == PositionAlertType.TAKE_PROFIT]
        assert len(sl_alerts) == 0
        assert len(tp_alerts) == 0

    @pytest.mark.asyncio
    async def test_portfolio_drawdown_triggers(self):
        svc = PositionAlertService()
        svc.config.max_drawdown_pct = -10.0
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=100, entry_price=500.0)
        # Position is 100 shares @ $500 = $50k entry cost, cash starts at $100k
        # Total initial value would be $100k (cash) + 0 unrealized (at entry)
        # After price drops to $400: unrealized = -$10k, value = $90k
        svc.set_paper_trader(make_mock_trader(
            cash=50_000.0,  # after spending $50k on 100 shares @ $500
            initial_capital=100_000.0,
            positions={"SPY_LONG_TEST": pos},
        ))
        svc._peak_portfolio_value = 100_000.0
        alerts = await svc.evaluate_positions(current_prices={"SPY": 400.0})
        dd_alerts = [a for a in alerts if a.alert_type == PositionAlertType.DRAW_DOWN]
        assert len(dd_alerts) >= 1

    @pytest.mark.asyncio
    async def test_max_hold_time_triggers(self):
        svc = PositionAlertService()
        svc.config.max_hold_minutes = 1  # 1 minute
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        pos = make_mock_position(
            symbol="SPY", side="LONG", quantity=10,
            entry_price=500.0, entry_time=old_time,
        )
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG_TEST": pos}))
        alerts = await svc.evaluate_positions(current_prices={"SPY": 505.0})
        hold_alerts = [a for a in alerts if a.alert_type == PositionAlertType.MAX_HOLD_TIME]
        assert len(hold_alerts) >= 1


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplication:
    """Test alert deduplication logic."""

    @pytest.mark.asyncio
    async def test_stop_loss_fires_once_per_position(self):
        svc = PositionAlertService()
        svc.config.stop_loss_pct = -5.0
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG_TEST": pos}))

        # First evaluation — should fire
        alerts1 = await svc.evaluate_positions(current_prices={"SPY": 460.0})
        sl1 = [a for a in alerts1 if a.alert_type == PositionAlertType.STOP_LOSS]
        assert len(sl1) == 1

        # Second evaluation with same price — should NOT fire again (deduped)
        alerts2 = await svc.evaluate_positions(current_prices={"SPY": 460.0})
        sl2 = [a for a in alerts2 if a.alert_type == PositionAlertType.STOP_LOSS]
        assert len(sl2) == 0

    @pytest.mark.asyncio
    async def test_different_positions_separate_dedup(self):
        svc = PositionAlertService()
        svc.config.stop_loss_pct = -5.0
        spy = make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=500.0)
        qqq = make_mock_position(symbol="QQQ", side="SHORT", quantity=5, entry_price=400.0)
        svc.set_paper_trader(make_mock_trader(positions={
            "SPY_LONG_1": spy,
            "QQQ_SHORT_1": qqq,
        }))
        alerts = await svc.evaluate_positions(current_prices={"SPY": 460.0, "QQQ": 430.0})
        sl = [a for a in alerts if a.alert_type == PositionAlertType.STOP_LOSS]
        tp = [a for a in alerts if a.alert_type == PositionAlertType.TAKE_PROFIT]
        # SPY loss triggers stop-loss, QQQ loss also triggers stop-loss (price went up for short)
        assert len(sl) == 2

    @pytest.mark.asyncio
    async def test_drawdown_also_deduped(self):
        svc = PositionAlertService()
        svc.config.max_drawdown_pct = -5.0
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=100, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(
            cash=50_000.0, initial_capital=100_000.0,
            positions={"SPY_LONG_TEST": pos},
        ))
        svc._peak_portfolio_value = 100_000.0
        alerts1 = await svc.evaluate_positions(current_prices={"SPY": 450.0})
        dd1 = [a for a in alerts1 if a.alert_type == PositionAlertType.DRAW_DOWN]
        assert len(dd1) >= 1

        alerts2 = await svc.evaluate_positions(current_prices={"SPY": 450.0})
        dd2 = [a for a in alerts2 if a.alert_type == PositionAlertType.DRAW_DOWN]
        assert len(dd2) == 0


# ---------------------------------------------------------------------------
# WebSocket broadcast tests
# ---------------------------------------------------------------------------

class TestWebSocketBroadcast:
    """Test WebSocket client registration and alert broadcasting."""

    def test_register_ws_client(self):
        svc = PositionAlertService()
        ws = MockWS()
        svc.register_ws_client(ws)
        assert ws in svc._ws_clients

    def test_register_ws_client_dedup(self):
        svc = PositionAlertService()
        ws = MockWS()
        svc.register_ws_client(ws)
        svc.register_ws_client(ws)
        assert len(svc._ws_clients) == 1

    def test_unregister_ws_client(self):
        svc = PositionAlertService()
        ws = MockWS()
        svc.register_ws_client(ws)
        svc.unregister_ws_client(ws)
        assert ws not in svc._ws_clients

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_clients(self):
        svc = PositionAlertService()
        ws = MockWS()
        svc.register_ws_client(ws)
        event = PositionAlertEvent(
            alert_id="TEST_001",
            alert_type=PositionAlertType.STOP_LOSS,
            severity=PositionAlertSeverity.CRITICAL,
            symbol="SPY", side="LONG", quantity=10,
            entry_price=500.0, current_price=460.0,
            unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
            message="STOP LOSS triggered",
        )
        svc._record_and_broadcast(event)
        await asyncio.sleep(0.05)  # Let the broadcast task run
        assert len(ws.sent) == 1
        payload = ws.sent[0]
        assert payload["type"] == "position_alert"
        assert payload["data"]["alert_id"] == "TEST_001"

    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected_client(self):
        svc = PositionAlertService()
        bad_ws = MagicMock()
        bad_ws.send_json = AsyncMock(side_effect=Exception("disconnected"))
        svc.register_ws_client(bad_ws)
        event = PositionAlertEvent(
            alert_id="TEST_002",
            alert_type=PositionAlertType.TAKE_PROFIT,
            severity=PositionAlertSeverity.WARNING,
            symbol="SPY", side="LONG", quantity=10,
            entry_price=500.0, current_price=560.0,
            unrealized_pnl=600.0, unrealized_pnl_pct=0.12,
            message="TAKE PROFIT triggered",
        )
        svc._record_and_broadcast(event)
        await asyncio.sleep(0.05)
        assert bad_ws not in svc._ws_clients  # Should have been removed


# ---------------------------------------------------------------------------
# Alert history & acknowledgement tests
# ---------------------------------------------------------------------------

class TestAlertHistory:
    """Test alert history querying and acknowledgement."""

    def test_get_alert_history_empty(self):
        svc = PositionAlertService()
        history = svc.get_alert_history()
        assert len(history) == 0

    def test_get_alert_history_with_events(self):
        svc = PositionAlertService()
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="SL_001", alert_type=PositionAlertType.STOP_LOSS,
                severity=PositionAlertSeverity.CRITICAL,
                symbol="SPY", side="LONG", quantity=10,
                entry_price=500.0, current_price=460.0,
                unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
                message="STOP LOSS",
            )
        )
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="TP_001", alert_type=PositionAlertType.TAKE_PROFIT,
                severity=PositionAlertSeverity.WARNING,
                symbol="QQQ", side="SHORT", quantity=5,
                entry_price=400.0, current_price=360.0,
                unrealized_pnl=200.0, unrealized_pnl_pct=0.10,
                message="TAKE PROFIT",
            )
        )
        history = svc.get_alert_history()
        assert len(history) == 2

    def test_filter_by_type(self):
        svc = PositionAlertService()
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="SL_001", alert_type=PositionAlertType.STOP_LOSS,
                severity=PositionAlertSeverity.CRITICAL,
                symbol="SPY", side="LONG", quantity=10,
                entry_price=500.0, current_price=460.0,
                unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
                message="STOP LOSS",
            )
        )
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="TP_001", alert_type=PositionAlertType.TAKE_PROFIT,
                severity=PositionAlertSeverity.WARNING,
                symbol="QQQ", side="SHORT", quantity=5,
                entry_price=400.0, current_price=360.0,
                unrealized_pnl=200.0, unrealized_pnl_pct=0.10,
                message="TAKE PROFIT",
            )
        )
        sl_only = svc.get_alert_history(alert_type="STOP_LOSS")
        assert len(sl_only) == 1
        assert sl_only[0]["alert_type"] == "STOP_LOSS"

    def test_filter_by_symbol(self):
        svc = PositionAlertService()
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="SL_001", alert_type=PositionAlertType.STOP_LOSS,
                severity=PositionAlertSeverity.CRITICAL,
                symbol="SPY", side="LONG", quantity=10,
                entry_price=500.0, current_price=460.0,
                unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
                message="STOP LOSS",
            )
        )
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="TP_001", alert_type=PositionAlertType.TAKE_PROFIT,
                severity=PositionAlertSeverity.WARNING,
                symbol="QQQ", side="SHORT", quantity=5,
                entry_price=400.0, current_price=360.0,
                unrealized_pnl=200.0, unrealized_pnl_pct=0.10,
                message="TAKE PROFIT",
            )
        )
        spy_only = svc.get_alert_history(symbol="SPY")
        assert len(spy_only) == 1
        assert spy_only[0]["symbol"] == "SPY"

    def test_filter_by_severity(self):
        svc = PositionAlertService()
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="SL_001", alert_type=PositionAlertType.STOP_LOSS,
                severity=PositionAlertSeverity.CRITICAL,
                symbol="SPY", side="LONG", quantity=10,
                entry_price=500.0, current_price=460.0,
                unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
                message="STOP LOSS",
            )
        )
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="TP_001", alert_type=PositionAlertType.TAKE_PROFIT,
                severity=PositionAlertSeverity.WARNING,
                symbol="QQQ", side="SHORT", quantity=5,
                entry_price=400.0, current_price=360.0,
                unrealized_pnl=200.0, unrealized_pnl_pct=0.10,
                message="TAKE PROFIT",
            )
        )
        critical_only = svc.get_alert_history(severity="CRITICAL")
        assert len(critical_only) == 1
        assert critical_only[0]["severity"] == "CRITICAL"

    def test_filter_unacknowledged(self):
        svc = PositionAlertService()
        ev = PositionAlertEvent(
            alert_id="SL_001", alert_type=PositionAlertType.STOP_LOSS,
            severity=PositionAlertSeverity.CRITICAL,
            symbol="SPY", side="LONG", quantity=10,
            entry_price=500.0, current_price=460.0,
            unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
            message="STOP LOSS",
        )
        ev.acknowledged = True
        svc._alert_history.append(ev)
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="TP_001", alert_type=PositionAlertType.TAKE_PROFIT,
                severity=PositionAlertSeverity.WARNING,
                symbol="QQQ", side="SHORT", quantity=5,
                entry_price=400.0, current_price=360.0,
                unrealized_pnl=200.0, unrealized_pnl_pct=0.10,
                message="TAKE PROFIT",
            )
        )
        unacked = svc.get_alert_history(unacknowledged_only=True)
        assert len(unacked) == 1
        assert unacked[0]["alert_id"] == "TP_001"

    def test_history_truncated(self):
        svc = PositionAlertService()
        for i in range(1100):
            svc._alert_history.append(
                PositionAlertEvent(
                    alert_id=f"A{i:04d}", alert_type=PositionAlertType.POSITION_OPEN,
                    severity=PositionAlertSeverity.INFO,
                    symbol="SPY", side="LONG", quantity=10,
                    entry_price=500.0, current_price=500.0,
                    unrealized_pnl=0.0, unrealized_pnl_pct=0.0,
                    message=f"Event {i}",
                )
            )
        # Truncation happens on get_alert_history access
        history = svc.get_alert_history(limit=2000)
        assert len(history) == 1000  # truncated at query time

    def test_acknowledge_alert(self):
        svc = PositionAlertService()
        svc._alert_history.append(
            PositionAlertEvent(
                alert_id="SL_001", alert_type=PositionAlertType.STOP_LOSS,
                severity=PositionAlertSeverity.CRITICAL,
                symbol="SPY", side="LONG", quantity=10,
                entry_price=500.0, current_price=460.0,
                unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
                message="STOP LOSS",
            )
        )
        assert svc.acknowledge_alert("SL_001") is True
        assert svc._alert_history[0].acknowledged is True
        assert "SL_001" in svc._acknowledged_ids

    def test_acknowledge_nonexistent(self):
        svc = PositionAlertService()
        assert svc.acknowledge_alert("DOES_NOT_EXIST") is False

    def test_acknowledge_already_acknowledged(self):
        svc = PositionAlertService()
        ev = PositionAlertEvent(
            alert_id="SL_001", alert_type=PositionAlertType.STOP_LOSS,
            severity=PositionAlertSeverity.CRITICAL,
            symbol="SPY", side="LONG", quantity=10,
            entry_price=500.0, current_price=460.0,
            unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
            message="STOP LOSS",
        )
        ev.acknowledged = True
        svc._alert_history.append(ev)
        assert svc.acknowledge_alert("SL_001") is False


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------

class TestServiceLifecycle:
    """Test service start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        svc = PositionAlertService()
        assert svc._running is False
        assert svc._task is None
        await svc.start()
        assert svc._running is True
        assert svc._task is not None
        await svc.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        svc = PositionAlertService()
        await svc.start()
        assert svc._task is not None
        await svc.stop()
        assert svc._running is False
        assert svc._task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        svc = PositionAlertService()
        await svc.start()
        task = svc._task
        await svc.start()  # Should be no-op
        assert svc._task is task  # Same task
        await svc.stop()

    @pytest.mark.asyncio
    async def test_poll_loop_evaluates_positions(self):
        """Start the service with a trader and verify it evaluates on poll."""
        svc = PositionAlertService()
        svc.config.poll_seconds = 0.2  # Fast poll
        svc.set_paper_trader(make_mock_trader(positions={
            "SPY_LONG": make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=500.0),
        }))
        await svc.start()
        await asyncio.sleep(0.4)  # Let it poll 2 times
        await svc.stop()
        # The poll loop should have run without error — no way to check exact count
        # but we verify no exception was raised


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_zero_entry_price_does_not_crash(self):
        svc = PositionAlertService()
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=0.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG_TEST": pos}))
        alerts = await svc.evaluate_positions(current_prices={"SPY": 100.0})
        # Should not crash; P&L % may be undefined
        assert isinstance(alerts, list)

    @pytest.mark.asyncio
    async def test_negative_quantity_does_not_crash(self):
        svc = PositionAlertService()
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=-10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG_TEST": pos}))
        alerts = await svc.evaluate_positions(current_prices={"SPY": 460.0})
        assert isinstance(alerts, list)

    @pytest.mark.asyncio
    async def test_empty_position_dict(self):
        svc = PositionAlertService()
        svc.set_paper_trader(make_mock_trader(positions={}))
        alerts = await svc.evaluate_positions()
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_very_large_pnl_does_not_overflow(self):
        svc = PositionAlertService()
        svc.config.take_profit_pct = 1000.0  # 1000%
        pos = make_mock_position(symbol="BTC", side="LONG", quantity=1, entry_price=1.0)
        svc.set_paper_trader(make_mock_trader(positions={"BTC_LONG": pos}))
        alerts = await svc.evaluate_positions(current_prices={"BTC": 1000000.0})
        # Should not overflow, and should trigger take-profit
        tp = [a for a in alerts if a.alert_type == PositionAlertType.TAKE_PROFIT]
        assert len(tp) >= 1
        assert tp[0].unrealized_pnl_pct > 0

    @pytest.mark.asyncio
    async def test_position_closed_does_not_evaluate(self):
        svc = PositionAlertService()
        closed_pos = make_mock_position(
            symbol="SPY", side="LONG", quantity=10, entry_price=500.0, status="closed",
        )
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG": closed_pos}))
        alerts = await svc.evaluate_positions(current_prices={"SPY": 460.0})
        assert len(alerts) == 0

    def test_get_status_no_trader(self):
        svc = PositionAlertService()
        status = svc.get_status()
        assert status["running"] is False
        assert status["open_positions"] == 0

    def test_get_status_with_trader(self):
        svc = PositionAlertService()
        svc.set_paper_trader(make_mock_trader(positions={
            "SPY_LONG": make_mock_position(),
            "QQQ_SHORT": make_mock_position(symbol="QQQ", side="SHORT"),
        }))
        status = svc.get_status()
        assert status["open_positions"] == 2

    def test_to_dict_serializes_properly(self):
        """Ensure PositionAlertEvent.to_dict() handles all fields."""
        event = PositionAlertEvent(
            alert_id="TEST_001",
            alert_type=PositionAlertType.STOP_LOSS,
            severity=PositionAlertSeverity.CRITICAL,
            symbol="SPY", side="LONG", quantity=10,
            entry_price=500.0, current_price=460.0,
            unrealized_pnl=-400.0, unrealized_pnl_pct=-0.08,
            message="STOP LOSS triggered",
            details={"extra": "info"},
        )
        d = event.to_dict()
        assert d["alert_id"] == "TEST_001"
        assert d["alert_type"] == "STOP_LOSS"
        assert d["severity"] == "CRITICAL"
        assert d["symbol"] == "SPY"
        assert d["side"] == "LONG"
        assert d["quantity"] == 10
        assert d["unrealized_pnl"] == -400.0
        assert d["unrealized_pnl_pct"] == -0.08
        assert d["details"]["extra"] == "info"
        assert d["acknowledged"] is False


# ---------------------------------------------------------------------------
# Price provider tests
# ---------------------------------------------------------------------------

class TestPriceProvider:
    """Test price provider integration."""

    @pytest.mark.asyncio
    async def test_price_provider_called_for_missing_price(self):
        svc = PositionAlertService()
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG": pos}))

        call_count = 0

        async def fake_provider(sym: str) -> float:
            nonlocal call_count
            call_count += 1
            return 510.0

        svc.set_price_provider(fake_provider)
        await svc.evaluate_positions()  # No prices dict provided — should use provider
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_price_provider_error_caught_gracefully(self):
        svc = PositionAlertService()
        pos = make_mock_position(symbol="SPY", side="LONG", quantity=10, entry_price=500.0)
        svc.set_paper_trader(make_mock_trader(positions={"SPY_LONG": pos}))

        async def broken_provider(sym: str) -> float:
            raise ValueError("API error")

        svc.set_price_provider(broken_provider)
        # Should not raise
        alerts = await svc.evaluate_positions()
        assert isinstance(alerts, list)
