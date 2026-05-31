"""
backend/tests/services/test_alpha_vantage_circuit.py

Tests for the circuit breaker pattern in Alpha Vantage client.

Tests state transitions:
  CLOSED -> OPEN after N failures
  OPEN -> HALF_OPEN after timeout
  HALF_OPEN -> CLOSED on success
  HALF_OPEN -> OPEN on failure
"""

import asyncio
import os
import sys

import pytest

# Add backend to path so we can import services
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from services.alpha_vantage_client import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def always_succeeds():
    return "ok"


async def always_fails():
    raise RuntimeError("API down")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_starts_closed():
    """Circuit breaker starts in CLOSED state."""
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=0.1)
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_success_in_closed_resets_failure_count():
    """Success in CLOSED state resets failure counter."""
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=0.1)

    for _ in range(3):
        try:
            await cb.call(always_fails)
        except RuntimeError:
            pass

    assert cb.failure_count == 3

    result = await cb.call(always_succeeds)
    assert result == "ok"
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_closed_to_open_after_n_failures():
    """Circuit opens after failure_threshold consecutive failures."""
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=0.1)

    for i in range(5):
        try:
            await cb.call(always_fails)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 5


@pytest.mark.asyncio
async def test_open_circuit_raises_immediately():
    """OPEN circuit raises CircuitBreakerOpenError without calling the function."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0)

    for _ in range(2):
        try:
            await cb.call(always_fails)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(always_succeeds)


@pytest.mark.asyncio
async def test_open_to_half_open_after_timeout():
    """Circuit transitions to HALF_OPEN after recovery_timeout."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

    for _ in range(2):
        try:
            await cb.call(always_fails)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN

    await asyncio.sleep(0.2)

    result = await cb.call(always_succeeds)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_to_closed_on_success():
    """Successful call in HALF_OPEN state closes the circuit."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

    for _ in range(2):
        try:
            await cb.call(always_fails)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN

    await asyncio.sleep(0.2)

    result = await cb.call(always_succeeds)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_half_open_to_open_on_failure():
    """Failed call in HALF_OPEN state reopens the circuit."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

    for _ in range(2):
        try:
            await cb.call(always_fails)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN

    await asyncio.sleep(0.2)

    with pytest.raises(RuntimeError):
        await cb.call(always_fails)

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_recovers_after_temporary_failure():
    """Full cycle: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)

    # Phase 1: Cause 3 failures -> OPEN
    for _ in range(3):
        try:
            await cb.call(always_fails)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN

    # Phase 2: Wait for timeout -> HALF_OPEN
    await asyncio.sleep(0.2)

    # Phase 3: Success -> CLOSED
    result = await cb.call(always_succeeds)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_custom_threshold_and_timeout():
    """Custom failure_threshold and recovery_timeout work correctly."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.05)

    # 2 failures should NOT open (threshold is 3)
    for _ in range(2):
        try:
            await cb.call(always_fails)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.CLOSED

    # 3rd failure opens
    with pytest.raises(RuntimeError):
        await cb.call(always_fails)

    assert cb.state == CircuitState.OPEN

    # Quick timeout
    await asyncio.sleep(0.1)
    result = await cb.call(always_succeeds)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_success_count_tracking():
    """Circuit breaker tracks success count."""
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=0.1)

    for _ in range(5):
        await cb.call(always_succeeds)

    assert cb.success_count == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
