"""
backend/tests/services/test_circuit_breaker.py

Tests for the circuit breaker pattern.
12 tests covering all states, thresholds, and transitions.
"""

import os
import time
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("API_SECRET_KEY", "test-secret-key")

from services.circuit_breaker import (
    BreakerThresholds,
    CircuitBreaker,
    CircuitState,
)


@pytest.fixture
def breaker():
    """Fresh circuit breaker for each test."""
    return CircuitBreaker("test", thresholds=BreakerThresholds(
        error_rate_pct=10.0,
        min_measurements=5,
        latency_p99_ms=5000.0,
        daily_pnl_drawdown_pct=-2.0,
        rejected_fills_1h=5,
        window_seconds=300,
        cooldown_seconds=1,  # Short for testing
        half_open_successes_needed=3,
    ))


class TestCircuitBreakerInit:
    def test_initial_state_is_closed(self, breaker):
        assert breaker.state == CircuitState.CLOSED

    def test_trading_allowed_when_closed(self, breaker):
        assert breaker.is_trading_allowed() is True

    def test_not_tripped_initially(self, breaker):
        assert breaker.is_tripped is False

    def test_status_report(self, breaker):
        status = breaker.get_status()
        assert status["state"] == "closed"
        assert status["trading_allowed"] is True
        assert status["trip_count"] == 0
        assert status["measurements_in_window"] == 0


class TestErrorRateTrip:
    def test_high_error_rate_trips_breaker(self, breaker):
        # Record 5 measurements with 40% error rate (2/5 errors)
        for _ in range(3):
            breaker.record_request(latency_ms=100, is_error=False)
        for _ in range(2):
            breaker.record_request(latency_ms=100, is_error=True)
        # Error rate = 40% > 10% threshold -> should trip
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_tripped is True
        assert breaker.is_trading_allowed() is False

    def test_low_error_rate_no_trip(self, breaker):
        for _ in range(10):
            breaker.record_request(latency_ms=100, is_error=False)
        assert breaker.state == CircuitState.CLOSED

    def test_min_measurements_not_met(self, breaker):
        # Only 3 measurements, but min is 5
        for _ in range(3):
            breaker.record_request(latency_ms=100, is_error=True)
        assert breaker.state == CircuitState.CLOSED  # Not enough data


class TestLatencyTrip:
    def test_high_latency_trips_breaker(self, breaker):
        # Record measurements with p99 > 5000ms
        for i in range(100):
            latency = 100 if i < 98 else 10000  # p99 will be 10000ms
            breaker.record_request(latency_ms=latency, is_error=False)
        assert breaker.state == CircuitState.OPEN

    def test_normal_latency_no_trip(self, breaker):
        for _ in range(20):
            breaker.record_request(latency_ms=100, is_error=False)
        assert breaker.state == CircuitState.CLOSED


class TestPnLDrawdown:
    def test_pnl_drawdown_trips(self, breaker):
        result = breaker.check_pnl(-3.0, 5000.0)
        assert result is True
        assert breaker.state == CircuitState.OPEN

    def test_pnl_drawdown_no_trip(self, breaker):
        result = breaker.check_pnl(-1.0, 5000.0)
        assert result is False
        assert breaker.state == CircuitState.CLOSED

    def test_pnl_drawdown_at_threshold(self, breaker):
        # Exactly at threshold should NOT trip
        result = breaker.check_pnl(-2.0, 5000.0)
        assert result is False

    def test_pnl_drawdown_just_below_threshold(self, breaker):
        result = breaker.check_pnl(-2.01, 5000.0)
        assert result is True


class TestRejectedFills:
    def test_rejected_fills_trips(self, breaker):
        result = breaker.check_rejected_fills(6)
        assert result is True
        assert breaker.state == CircuitState.OPEN

    def test_rejected_fills_no_trip(self, breaker):
        result = breaker.check_rejected_fills(3)
        assert result is False

    def test_rejected_fills_at_threshold(self, breaker):
        result = breaker.check_rejected_fills(5)
        assert result is False


class TestManualOperations:
    def test_manual_trip(self, breaker):
        breaker.manual_trip(reason="test", actor="pytest")
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_tripped is True

    def test_manual_reset(self, breaker):
        breaker.manual_trip(reason="test")
        breaker.manual_reset(actor="pytest")
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_trading_allowed() is True

    def test_manual_reset_clears_measurements(self, breaker):
        for _ in range(10):
            breaker.record_request(latency_ms=100, is_error=True)
        breaker.manual_reset()
        status = breaker.get_status()
        assert status["measurements_in_window"] == 0


class TestTripLog:
    def test_trip_log_populated(self, breaker):
        breaker.check_pnl(-5.0, 5000.0)
        log = breaker.get_trip_log()
        assert len(log) == 1
        assert log[0]["reason"] == "daily_pnl_drawdown"

    def test_multiple_trips_logged(self, breaker):
        breaker.check_pnl(-5.0, 5000.0)
        breaker.manual_reset()
        breaker.check_rejected_fills(10)
        log = breaker.get_trip_log()
        assert len(log) == 2
        assert log[0]["reason"] == "daily_pnl_drawdown"
        assert log[1]["reason"] == "rejected_fills"


class TestCallback:
    def test_on_trip_callback_fires(self):
        callback = MagicMock()
        b = CircuitBreaker("cb-test", on_trip=callback)
        b.check_pnl(-5.0, 5000.0)
        callback.assert_called_once()
        args = callback.call_args[0]
        assert "daily_pnl_drawdown" in args[0]


class TestHalfOpen:
    def test_cooldown_transitions_to_half_open(self, breaker):
        breaker.check_pnl(-5.0, 5000.0)
        assert breaker.state == CircuitState.OPEN
        # Wait for cooldown (1 second in test config)
        time.sleep(1.5)
        # Now trading_allowed() should transition to HALF_OPEN
        allowed = breaker.is_trading_allowed()
        assert allowed is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_closes_after_successes(self, breaker):
        breaker.check_pnl(-5.0, 5000.0)
        time.sleep(1.5)
        # Trigger half-open
        breaker.is_trading_allowed()
        assert breaker.state == CircuitState.HALF_OPEN
        # Record enough successes
        for _ in range(3):
            breaker.record_request(latency_ms=100, is_error=False)
        assert breaker.state == CircuitState.CLOSED
