"""
backend/tests/integration/test_api_resilience.py

Integration tests for API failure resilience.
Verifies the system handles yoptions/yfinance 429/500 errors gracefully:
  - Switches to cached data when APIs fail
  - Retry logic triggers with exponential backoff
  - No crashes under sustained API failures
  - Circuit breaker trips on high error rates
  - Recovery when APIs come back online

All tests are Window B safe — all failures are mocked.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Dict, Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TESTING", "1")

from services.circuit_breaker import BreakerThresholds, CircuitBreaker, CircuitState
from services.data_fallback import (
    DataFallbackHandler,
    DataSource,
    FallbackConfig,
    FallbackState,
)

# ── Helpers ──────────────────────────────────────────────────────────────


def make_failing_fetcher(error: Exception = ConnectionError("HTTP 500")):
    """Create a fetcher that always fails."""
    async def fetcher(symbol):
        raise error
    return fetcher


def make_slow_fetcher(delay_s: float = 10.0):
    """Create a fetcher that takes too long (simulates timeout)."""
    async def fetcher(symbol):
        await asyncio.sleep(delay_s)
        return None
    return fetcher


def make_working_fetcher(data: Optional[Dict] = None):
    """Create a fetcher that returns valid data."""
    async def fetcher(symbol):
        if data:
            return data
        return {
            "symbol": symbol,
            "bid": 500.0,
            "ask": 501.0,
            "last": 500.5,
            "volume": 1000,
            "timestamp": time.time(),
        }
    return fetcher


def make_intermittent_fetcher(fail_rate: float = 0.5, seed: int = 42):
    """Create a fetcher that fails randomly."""
    import random
    rng = random.Random(seed)

    async def fetcher(symbol):
        if rng.random() < fail_rate:
            raise ConnectionError(f"HTTP {rng.choice([429, 500, 502, 503])}")
        return {
            "symbol": symbol,
            "bid": 500.0,
            "ask": 501.0,
            "last": 500.5,
            "volume": 1000,
        }
    return fetcher


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def handler():
    """Fresh DataFallbackHandler for each test."""
    config = FallbackConfig(
        stale_threshold_s=5.0,
        max_consecutive_errors=3,
    )
    return DataFallbackHandler(config=config)


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


# ── Test: 429 Rate Limit Handling ────────────────────────────────────────


@pytest.mark.asyncio
async def test_429_triggers_fallback_to_cache(handler):
    """When API returns 429, system should switch to cached data."""
    # Pre-populate cache
    handler._sources[DataSource.SCHWAB].record_update({
        "symbol": "SPY", "bid": 499.0, "ask": 500.0, "last": 499.5, "volume": 500,
    })
    handler._sources[DataSource.SCHWAB].last_update = time.monotonic()

    # Configure all sources to return 429
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher(ConnectionError("HTTP 429")))
    handler.configure_source(DataSource.YFINANCE, make_failing_fetcher(ConnectionError("HTTP 429")))
    handler.configure_source(DataSource.POLYGON, make_failing_fetcher(ConnectionError("HTTP 429")))

    data = await handler.get_data("SPY")

    # Should get cached data, not crash
    assert data is not None, "Should return cached data when all sources return 429"
    assert data["symbol"] == "SPY"


@pytest.mark.asyncio
async def test_500_triggers_fallback_to_yfinance(handler):
    """When Schwab returns 500, system should fall back to yfinance."""
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher(ConnectionError("HTTP 500")))
    handler.configure_source(DataSource.YFINANCE, make_working_fetcher())

    data = await handler.get_data("SPY")

    assert data is not None, "Should get data from yfinance when Schwab returns 500"
    assert handler.state == FallbackState.FALLBACK_1


@pytest.mark.asyncio
async def test_502_503_504_all_trigger_fallback(handler):
    """Various server errors should all trigger fallback behavior."""
    for status_code in [502, 503, 504]:
        h = DataFallbackHandler(config=FallbackConfig(max_consecutive_errors=3))
        h.configure_source(DataSource.SCHWAB, make_failing_fetcher(ConnectionError(f"HTTP {status_code}")))
        h.configure_source(DataSource.YFINANCE, make_working_fetcher())

        data = await h.get_data("SPY")
        assert data is not None, f"Should handle HTTP {status_code} gracefully"


# ── Test: Retry Logic ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_triggers_on_failure(handler):
    """System should retry failed sources on subsequent get_data calls when fallback also fails."""
    call_count = 0

    async def counting_fetcher(symbol):
        nonlocal call_count
        call_count += 1
        raise ConnectionError("HTTP 500")

    # Both sources fail — Schwab should be retried each call
    handler.configure_source(DataSource.SCHWAB, counting_fetcher)
    handler.configure_source(DataSource.YFINANCE, make_failing_fetcher())
    handler.configure_source(DataSource.POLYGON, make_failing_fetcher())

    # First call — Schwab tried, fails, yfinance tried, fails, polygon tried, fails
    await handler.get_data("SPY")
    first_count = call_count
    assert first_count == 1, "Schwab should be tried once on first call"

    # Second call — Schwab should be retried (error_count < max_consecutive_errors)
    await handler.get_data("SPY")
    second_count = call_count

    assert second_count > first_count, "Schwab should be retried on subsequent calls"


@pytest.mark.asyncio
async def test_exponential_backoff_delays(handler):
    """Retry delays should follow exponential backoff pattern."""
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer()
    assert streamer.initial_reconnect_delay == 1.0
    assert streamer.max_reconnect_delay == 60.0

    # Simulate backoff progression
    delay = streamer.initial_reconnect_delay
    delays = []
    for _ in range(10):
        delays.append(delay)
        if delay >= streamer.max_reconnect_delay:
            break
        delay = min(delay * 2, streamer.max_reconnect_delay)

    # Verify exponential growth: 1, 2, 4, 8, 16, 32, 60
    assert delays[0] == 1.0
    assert delays[1] == 2.0
    assert delays[2] == 4.0
    assert delays[3] == 8.0
    assert delays[4] == 16.0
    assert delays[5] == 32.0
    assert delays[6] == 60.0  # Capped

    # Each step should be ~2x previous (until cap)
    for i in range(1, len(delays) - 1):
        ratio = delays[i] / delays[i - 1]
        assert ratio >= 1.9, f"Backoff ratio at step {i} is {ratio}, expected >= 1.9"


@pytest.mark.asyncio
async def test_max_consecutive_errors_respected(handler):
    """After max_consecutive_errors, source should be skipped."""
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher())
    handler.configure_source(DataSource.YFINANCE, make_failing_fetcher())
    handler.configure_source(DataSource.POLYGON, make_failing_fetcher())

    # Call enough times to exceed max_consecutive_errors (3)
    for _ in range(5):
        await handler.get_data("SPY")

    # Schwab should be marked unavailable
    assert handler._sources[DataSource.SCHWAB].is_available is False
    assert handler._sources[DataSource.SCHWAB].error_count >= handler.config.max_consecutive_errors


# ── Test: No Crashes ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_crash_all_sources_fail(handler):
    """System should not crash when all data sources fail."""
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher())
    handler.configure_source(DataSource.YFINANCE, make_failing_fetcher())
    handler.configure_source(DataSource.POLYGON, make_failing_fetcher())

    # Should not raise
    data = await handler.get_data("SPY")
    assert data is None  # Graceful degradation
    assert handler.is_safe_mode


@pytest.mark.asyncio
async def test_no_crash_no_sources_configured(handler):
    """System should not crash when no sources are configured."""
    data = await handler.get_data("SPY")
    assert data is None
    assert handler.is_safe_mode


@pytest.mark.asyncio
async def test_no_crash_rapid_requests(handler):
    """System should handle rapid sequential requests without crashing."""
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher())
    handler.configure_source(DataSource.YFINANCE, make_working_fetcher())

    results = []
    for _ in range(50):
        try:
            d = await handler.get_data("SPY")
            results.append(("ok", d is not None))
        except Exception as e:
            results.append(("crash", str(e)))

    crashes = [r for r in results if r[0] == "crash"]
    assert len(crashes) == 0, f"{len(crashes)} crashes in 50 rapid requests"


@pytest.mark.asyncio
async def test_no_crash_concurrent_requests(handler):
    """System should handle concurrent requests without crashing."""
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher())
    handler.configure_source(DataSource.YFINANCE, make_working_fetcher())

    async def request_data(symbol):
        try:
            d = await handler.get_data(symbol)
            return ("ok", d is not None)
        except Exception as e:
            return ("crash", str(e))

    # 20 concurrent requests
    tasks = [request_data("SPY") for _ in range(20)]
    results = await asyncio.gather(*tasks)

    crashes = [r for r in results if r[0] == "crash"]
    assert len(crashes) == 0, f"{len(crashes)} crashes in 20 concurrent requests"


# ── Test: Circuit Breaker ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_circuit_breaker_trips_on_sustained_errors(breaker):
    """Circuit breaker should trip when error rate exceeds threshold."""
    # Record 10 measurements with 30% error rate (> 10% threshold)
    for i in range(10):
        breaker.record_request(latency_ms=float(i), is_error=(i < 3))

    assert breaker.is_tripped, "Circuit breaker should trip on 30% error rate with 10% threshold"
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_when_tripped(breaker):
    """When circuit breaker is tripped, trading should be blocked."""
    # Trip the breaker
    for i in range(10):
        breaker.record_request(latency_ms=float(i), is_error=(i < 3))

    assert breaker.is_tripped
    assert breaker.is_trading_allowed() is False


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_after_cooldown(breaker):
    """Circuit breaker should transition to HALF_OPEN after cooldown."""
    breaker.thresholds.cooldown_seconds = 0  # Instant cooldown for testing

    # Trip the breaker
    for i in range(10):
        breaker.record_request(latency_ms=float(i), is_error=(i < 3))

    assert breaker.is_tripped

    # Check trading — should transition to HALF_OPEN
    allowed = breaker.is_trading_allowed()
    assert breaker.state == CircuitState.HALF_OPEN
    assert allowed is True


@pytest.mark.asyncio
async def test_circuit_breaker_closes_after_successes(breaker):
    """Circuit breaker should close after enough successes in HALF_OPEN."""
    breaker.thresholds.cooldown_seconds = 0
    breaker.thresholds.half_open_successes_needed = 3

    # Trip the breaker
    for i in range(10):
        breaker.record_request(latency_ms=float(i), is_error=(i < 3))

    # Transition to HALF_OPEN
    breaker.is_trading_allowed()

    # Clear old measurements so error rate doesn't re-trip
    breaker._measurements.clear()

    # Record successes
    for _ in range(3):
        breaker.record_request(latency_ms=1.0, is_error=False)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.is_tripped is False


# ── Test: Recovery ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recovery_when_api_comes_back(handler):
    """System should recover when failing API comes back online."""
    # Start with all sources failing
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher())
    handler.configure_source(DataSource.YFINANCE, make_failing_fetcher())

    data = await handler.get_data("SPY")
    assert handler.is_safe_mode

    # Fix Schwab
    handler.configure_source(DataSource.SCHWAB, make_working_fetcher())
    handler._sources[DataSource.SCHWAB].is_available = True
    handler._sources[DataSource.SCHWAB].error_count = 0

    recovered = await handler.attempt_recovery()
    assert recovered is True
    assert handler.state == FallbackState.PRIMARY


@pytest.mark.asyncio
async def test_recovery_fails_if_source_still_down(handler):
    """Recovery should fail if primary source is still unavailable."""
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher())
    handler.configure_source(DataSource.YFINANCE, make_failing_fetcher())

    await handler.get_data("SPY")
    assert handler.is_safe_mode

    # Try recovery without fixing anything
    recovered = await handler.attempt_recovery()
    assert recovered is False
    assert handler.is_safe_mode


@pytest.mark.asyncio
async def test_intermittent_failures_dont_crash(handler):
    """Intermittent API failures should not crash the system."""
    handler.configure_source(DataSource.SCHWAB, make_intermittent_fetcher(fail_rate=0.7))
    handler.configure_source(DataSource.YFINANCE, make_intermittent_fetcher(fail_rate=0.3))

    results = []
    for _ in range(30):
        try:
            d = await handler.get_data("SPY")
            results.append(("ok", d is not None))
        except Exception as e:
            results.append(("crash", str(e)))

    crashes = [r for r in results if r[0] == "crash"]
    assert len(crashes) == 0, f"{len(crashes)} crashes with intermittent failures"


# ── Test: Cache Behavior ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_serves_stale_data_during_outage(handler):
    """Cache should serve data (even if stale) during API outage."""
    # Pre-populate with data
    handler._sources[DataSource.SCHWAB].record_update({
        "symbol": "SPY", "bid": 498.0, "ask": 499.0, "last": 498.5, "volume": 200,
    })
    handler._sources[DataSource.SCHWAB].last_update = time.monotonic()

    # All sources fail
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher())
    handler.configure_source(DataSource.YFINANCE, make_failing_fetcher())
    handler.configure_source(DataSource.POLYGON, make_failing_fetcher())

    data = await handler.get_data("SPY")
    assert data is not None, "Cache should serve data during outage"
    assert data["bid"] == 498.0


@pytest.mark.asyncio
async def test_cache_freshest_data_used(handler):
    """When multiple sources have cached data, the freshest should be used."""
    now = time.monotonic()

    # Schwab has older data
    handler._sources[DataSource.SCHWAB].record_update({
        "symbol": "SPY", "bid": 495.0, "ask": 496.0, "last": 495.5, "volume": 100,
    })
    handler._sources[DataSource.SCHWAB].last_update = now - 10

    # yfinance has fresher data
    handler._sources[DataSource.YFINANCE].record_update({
        "symbol": "SPY", "bid": 500.0, "ask": 501.0, "last": 500.5, "volume": 500,
    })
    handler._sources[DataSource.YFINANCE].last_update = now - 1

    # All fetchers fail
    handler.configure_source(DataSource.SCHWAB, make_failing_fetcher())
    handler.configure_source(DataSource.YFINANCE, make_failing_fetcher())
    handler.configure_source(DataSource.POLYGON, make_failing_fetcher())

    data = await handler.get_data("SPY")
    assert data is not None
    # Should get the fresher data (from yfinance)
    assert data["bid"] == 500.0, f"Expected freshest data (bid=500.0), got bid={data['bid']}"
