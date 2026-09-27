"""Circuit-breaker behaviour, provider-neutral.

These four tests were extracted from `test_api_resilience.py`, which was
deleted with the Schwab retirement. That file tested `data_fallback.py` and
`schwab_streamer.py` — both dead since 2026-09-03, with zero production
importers — and the circuit-breaker cases were collateral: they exercise
`services/circuit_breaker.py`, which is live and unrelated to any provider.

Kept here rather than dropped, because a breaker that silently fails to trip
is a real trading risk: it is the control that stops the app hammering a dead
upstream. The rest of the deleted file was genuinely Schwab-specific (source
failover ordering, per-provider retry, DataSource.SCHWAB), and is gone with it.
"""

from __future__ import annotations

import pytest

from services.circuit_breaker import BreakerThresholds, CircuitBreaker, CircuitState


@pytest.fixture
def breaker():
    """Fresh CircuitBreaker for each test."""
    return CircuitBreaker(
        "test_breaker",
        thresholds=BreakerThresholds(
            error_rate_pct=10.0,
            min_measurements=5,
            latency_p99_ms=5000.0,
        ),
    )


def test_circuit_breaker_trips_on_sustained_errors(breaker):
    """Circuit breaker should trip when error rate exceeds threshold."""
    for i in range(10):
        breaker.record_request(latency_ms=float(i), is_error=(i < 3))

    assert breaker.is_tripped, "Circuit breaker should trip on 30% error rate with 10% threshold"
    assert breaker.state == CircuitState.OPEN


def test_circuit_breaker_blocks_when_tripped(breaker):
    """When circuit breaker is tripped, trading should be blocked."""
    for i in range(10):
        breaker.record_request(latency_ms=float(i), is_error=(i < 3))

    assert breaker.is_tripped
    assert breaker.is_trading_allowed() is False


def test_circuit_breaker_half_open_after_cooldown(breaker, monkeypatch):
    """Circuit breaker should transition to HALF_OPEN after cooldown."""
    breaker.thresholds.cooldown_seconds = 0  # Instant cooldown for testing

    for i in range(10):
        breaker.record_request(latency_ms=float(i), is_error=(i < 3))

    assert breaker.is_tripped

    monkeypatch.setattr("services.circuit_breaker.time.time", lambda: breaker._last_trip_time + 1)
    allowed = breaker.is_trading_allowed()
    assert breaker.state == CircuitState.HALF_OPEN
    assert allowed is True


def test_circuit_breaker_closes_after_successes(breaker, monkeypatch):
    """Circuit breaker should close after enough successes in HALF_OPEN."""
    breaker.thresholds.cooldown_seconds = 0
    breaker.thresholds.half_open_successes_needed = 3

    for i in range(10):
        breaker.record_request(latency_ms=float(i), is_error=(i < 3))

    monkeypatch.setattr("services.circuit_breaker.time.time", lambda: breaker._last_trip_time + 1)
    assert breaker.is_trading_allowed()  # -> HALF_OPEN

    # Clear old measurements so the error rate does not immediately re-trip.
    breaker._measurements.clear()

    for _ in range(3):
        breaker.record_request(latency_ms=1.0, is_error=False)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.is_trading_allowed() is True
