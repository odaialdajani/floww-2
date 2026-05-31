"""
backend/tests/services/test_live_trading_switch.py

Tests for the live-trading state machine with circuit breakers.
15+ tests covering all state transitions and breaker trips.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

# Set dev mode for testing
os.environ.setdefault("TRADING_TOTP_SECRET", "")
os.environ.setdefault("TRADING_EMAIL_CODE", "")

from services.live_trading_switch import (
    CircuitBreakerReason,
    LiveTradingSwitch,
    TradingState,
)


@pytest.fixture
def sw():
    """Fresh switch for each test."""
    s = LiveTradingSwitch()
    return s


class TestTradingState:
    def test_initial_state_is_off(self, sw):
        assert sw.state == TradingState.OFF

    def test_state_labels(self):
        assert TradingState.OFF.label == "Off"
        assert TradingState.PAPER_ONLY.label == "Paper Only"
        assert TradingState.LIVE_TINY.label == "Live Tiny"

    def test_max_notional(self):
        assert TradingState.OFF.max_notional_usd == 0
        assert TradingState.PAPER_ONLY.max_notional_usd == 0
        assert TradingState.LIVE_TINY.max_notional_usd == 1000
        assert TradingState.LIVE_NORMAL.max_notional_usd == 10000
        assert TradingState.LIVE_FULL.max_notional_usd is None

    def test_is_live(self, sw):
        assert not sw.is_live
        sw._state = TradingState.LIVE_TINY
        assert sw.is_live

    def test_is_paper(self, sw):
        assert not sw.is_paper
        sw._state = TradingState.PAPER_ONLY
        assert sw.is_paper


class TestStateTransitions:
    def test_off_to_paper(self, sw):
        ok, msg = sw.request_transition(TradingState.PAPER_ONLY, "123456", "test")
        assert ok, msg
        assert sw.state == TradingState.PAPER_ONLY

    def test_paper_to_live_tiny(self, sw):
        sw._state = TradingState.PAPER_ONLY
        ok, msg = sw.request_transition(TradingState.LIVE_TINY, "123456", "test")
        assert ok, msg
        assert sw.state == TradingState.LIVE_TINY

    def test_cannot_skip_states(self, sw):
        ok, msg = sw.request_transition(TradingState.LIVE_TINY, "123456", "test")
        assert not ok
        assert "one state" in msg.lower() or "skip" in msg.lower()

    def test_cannot_go_live_from_off(self, sw):
        ok, msg = sw.request_transition(TradingState.LIVE_FULL, "123456", "test")
        assert not ok

    def test_transition_log(self, sw):
        sw.request_transition(TradingState.PAPER_ONLY, "123456", "test")
        assert len(sw._transition_log) == 1
        assert sw._transition_log[0]["from_state"] == "OFF"
        assert sw._transition_log[0]["to_state"] == "PAPER_ONLY"

    def test_status_report(self, sw):
        status = sw.get_status()
        assert status["state"] == "OFF"
        assert status["is_live"] is False
        assert status["cooldown_active"] is False


class TestCircuitBreakers:
    def test_pnl_drawdown_trips(self, sw):
        sw._state = TradingState.LIVE_TINY
        result = sw.check_pnl_drawdown(-3.0, 5000.0)
        assert result is True
        assert sw.state == TradingState.PAPER_ONLY

    def test_pnl_drawdown_no_trip(self, sw):
        sw._state = TradingState.LIVE_TINY
        result = sw.check_pnl_drawdown(-1.0, 5000.0)
        assert result is False
        assert sw.state == TradingState.LIVE_TINY

    def test_rejected_fills_trips(self, sw):
        sw._state = TradingState.LIVE_NORMAL
        result = sw.check_rejected_fills(6)
        assert result is True
        assert sw.state == TradingState.LIVE_TINY

    def test_rejected_fills_no_trip(self, sw):
        sw._state = TradingState.LIVE_NORMAL
        result = sw.check_rejected_fills(3)
        assert result is False
        assert sw.state == TradingState.LIVE_NORMAL

    def test_reconciliation_trips(self, sw):
        sw._state = TradingState.LIVE_FULL
        result = sw.check_reconciliation(2)
        assert result is True
        assert sw.state == TradingState.LIVE_NORMAL

    def test_cooldown_after_trip(self, sw):
        sw._state = TradingState.LIVE_TINY
        sw.trip_circuit_breaker(CircuitBreakerReason.DAILY_PNL_DRAWDOWN, "test")
        assert sw._cooldown_until is not None
        assert sw._cooldown_until > datetime.now(timezone.utc)

    def test_no_transition_during_cooldown(self, sw):
        sw._state = TradingState.PAPER_ONLY
        sw._cooldown_until = datetime.now(timezone.utc) + timedelta(hours=24)
        ok, msg = sw.request_transition(TradingState.LIVE_TINY, "123456", "test")
        assert not ok
        assert "cooldown" in msg.lower()

    def test_circuit_breaker_log(self, sw):
        sw._state = TradingState.LIVE_TINY
        sw.trip_circuit_breaker(CircuitBreakerReason.MANUAL, "test trip")
        assert len(sw._circuit_breaker_log) == 1
        assert sw._circuit_breaker_log[0]["reason"] == CircuitBreakerReason.MANUAL

    def test_demotion_stops_at_off(self, sw):
        sw._state = TradingState.OFF
        sw.trip_circuit_breaker(CircuitBreakerReason.MANUAL, "test")
        assert sw.state == TradingState.OFF  # Can't go below OFF
