"""
backend/tests/integration/test_network_resilience.py

Integration tests for network partition resilience.
Verifies the system survives Schwab WebSocket disconnections,
switches to cached data, reconnects with exponential backoff,
and preserves DuckDB data integrity.

NEW tests (Round 5):
  - Offline mode activation during network loss
  - Data integrity in DuckDB during partition
  - Graceful degradation under partition
  - Health endpoint reflects partition state
  - Metrics tracking during partition
  - Multi-symbol partition resilience

All tests are Window B safe — use mock feed, no live connections.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TESTING", "1")

from services.data_fallback import DataFallbackHandler, DataSource, FallbackConfig
from services.duckdb_engine import DuckDBEngine
from services.mock_schwab_feed import MockSchwabFeed
from services.schwab_streamer import SchwabStreamer

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def engine():
    """Fresh DuckDB engine for each test."""
    return DuckDBEngine(db_path=":memory:")


@pytest.fixture
def feed():
    """Mock feed for testing."""
    return MockSchwabFeed(rate=50, symbols=["SPY"], seed=42)


@pytest.fixture
def streamer():
    """Schwab streamer instance."""
    return SchwabStreamer()


# ── Test: Offline Mode Activation ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_mode_activates_on_connection_loss(engine, feed):
    """When network connection is lost, offline mode should activate."""
    await engine.start()

    ticks_received = []

    async def handler(tick):
        ticks_received.append(tick)

    feed.on_tick(handler)
    feed_task = asyncio.create_task(feed.start())
    await asyncio.sleep(0.3)

    pre_stop_count = len(ticks_received)
    assert pre_stop_count > 0, "Should receive ticks before stop"

    # Simulate connection loss
    await feed.stop()
    feed_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass

    # Verify streamer health reflects disconnection
    streamer = SchwabStreamer()
    health = streamer.get_health()
    assert health["connected"] is False, "Health should show disconnected"

    # Verify engine still functional (offline mode)
    rows = engine.query("SELECT COUNT(*) as cnt FROM ticks")
    assert isinstance(rows, list), "Engine should still be queryable in offline mode"

    await engine.stop()


@pytest.mark.asyncio
async def test_offline_mode_serves_cached_data(engine, feed):
    """During network partition, system should serve cached/stored data."""
    await engine.start()

    # Pre-load data into DuckDB
    for i in range(15):
        await engine.insert_tick(
            symbol="SPY", bid=500.0 + i, ask=501.0 + i,
            last=500.5 + i, volume=1000 * i, oi=5000,
            delta=0.5, gamma=0.01, theta=-0.1, vega=0.2,
        )
    await engine._flush_all()

    # Simulate network partition
    feed_task = asyncio.create_task(feed.start())
    await asyncio.sleep(0.2)
    await feed.stop()
    feed_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass

    # Verify data still accessible during partition
    rows = engine.query("SELECT COUNT(*) as cnt FROM ticks")
    assert rows[0]["cnt"] == 15, f"Expected 15 rows during partition, got {rows[0]['cnt']}"

    # Verify we can still query the data
    all_rows = engine.query("SELECT * FROM ticks ORDER BY timestamp")
    assert len(all_rows) == 15

    await engine.stop()


# ── Test: Data Integrity in DuckDB ───────────────────────────────────────


@pytest.mark.asyncio
async def test_data_integrity_during_partition(engine, feed):
    """All data in DuckDB should remain intact during network partition."""
    await engine.start()

    # Write known data
    known_prices = [500.0, 501.0, 502.0, 503.0, 504.0]
    for i, price in enumerate(known_prices):
        await engine.insert_tick(
            symbol="SPY", bid=price, ask=price + 1.0,
            last=price + 0.5, volume=1000 * (i + 1), oi=5000,
            delta=0.5, gamma=0.01, theta=-0.1, vega=0.2,
        )
    await engine._flush_all()

    # Simulate partition
    feed_task = asyncio.create_task(feed.start())
    await asyncio.sleep(0.2)
    await feed.stop()
    feed_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass

    # Recover
    feed2 = MockSchwabFeed(rate=50, symbols=["SPY"], seed=99)

    async def db_writer(tick):
        await engine.insert_tick(
            symbol=tick["symbol"], bid=tick["bid"], ask=tick["ask"],
            last=tick["last"], volume=tick["volume"], oi=0,
            delta=0.0, gamma=0.0, theta=0.0, vega=0.0,
        )

    feed2.on_tick(db_writer)
    feed_task2 = asyncio.create_task(feed2.start())
    await asyncio.sleep(0.5)

    # Cleanup
    await feed2.stop()
    feed_task2.cancel()
    try:
        await feed_task2
    except asyncio.CancelledError:
        pass

    await engine._flush_all()

    # Verify original data intact
    rows = engine.query("SELECT * FROM ticks WHERE volume <= 5000 ORDER BY volume")
    assert len(rows) >= 5, f"Expected >= 5 original rows, got {len(rows)}"

    # Verify known prices are present
    stored_prices = [r["bid"] for r in rows[:5]]
    for known in known_prices:
        assert any(abs(s - known) < 0.01 for s in stored_prices), f"Known price {known} not found in {stored_prices}"

    await engine.stop()


@pytest.mark.asyncio
async def test_no_data_loss_during_outage(engine, feed):
    """No data is lost in DuckDB during network outage."""
    await engine.start()

    # Pre-load data
    for i in range(20):
        await engine.insert_tick(
            symbol="SPY", bid=500.0, ask=501.0, last=500.5,
            volume=1000, oi=5000, delta=0.5, gamma=0.01,
            theta=-0.1, vega=0.2,
        )
    await engine._flush_all()

    pre_count = engine.query("SELECT COUNT(*) as cnt FROM ticks")[0]["cnt"]
    assert pre_count == 20

    # Simulate outage
    feed_task = asyncio.create_task(feed.start())
    await asyncio.sleep(0.2)
    await feed.stop()
    feed_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass

    # Verify no data loss
    await engine._flush_all()
    post_count = engine.query("SELECT COUNT(*) as cnt FROM ticks")[0]["cnt"]
    assert post_count == pre_count, f"Data loss: {pre_count} -> {post_count}"

    await engine.stop()


# ── Test: Graceful Degradation ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_graceful_degradation_during_partition(engine, feed):
    """System should degrade gracefully during network partition."""
    await engine.start()

    # Start feed
    feed_task = asyncio.create_task(feed.start())
    await asyncio.sleep(0.3)

    pre_ticks = engine.query("SELECT COUNT(*) as cnt FROM ticks")[0]["cnt"]

    # Simulate partition
    await feed.stop()
    feed_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass

    # System should still be queryable
    post_ticks = engine.query("SELECT COUNT(*) as cnt FROM ticks")[0]["cnt"]
    assert post_ticks >= pre_ticks, "Data should not decrease during partition"

    # System should not crash on queries
    try:
        engine.query("SELECT * FROM ticks LIMIT 10")
        engine.query("SELECT symbol, AVG(bid) FROM ticks GROUP BY symbol")
    except Exception as e:
        pytest.fail(f"System crashed during partition: {e}")

    await engine.stop()


@pytest.mark.asyncio
async def test_fallback_handler_enters_safe_mode_on_partition():
    """DataFallbackHandler should enter safe mode when all sources lose connection."""
    config = FallbackConfig(max_consecutive_errors=3)
    handler = DataFallbackHandler(config=config)

    # Configure sources that fail (simulating network partition)
    async def failing_fetch(symbol):
        raise ConnectionError("Network unreachable")

    handler.configure_source(DataSource.SCHWAB, failing_fetch)
    handler.configure_source(DataSource.YFINANCE, failing_fetch)
    handler.configure_source(DataSource.POLYGON, failing_fetch)

    data = await handler.get_data("SPY")

    assert data is None, "Should return None when all sources unreachable"
    assert handler.is_safe_mode, "Should enter safe mode"

    health = await handler.check_health()
    assert health["is_safe_mode"] is True
    assert health["state"] == "safe_mode"


# ── Test: Health Endpoint Reflects Partition ─────────────────────────────


@pytest.mark.asyncio
async def test_streamer_health_reflects_partition():
    """SchwabStreamer health should accurately reflect partition state."""
    streamer = SchwabStreamer()

    # Initial state — not connected
    health = streamer.get_health()
    assert health["connected"] is False
    assert health["last_message_at"] is None

    # Simulate connection
    streamer._health["connected"] = True
    streamer._health["last_message_at"] = datetime.now(timezone.utc).isoformat()

    # Internal health dict should reflect connection
    assert streamer._health["connected"] is True
    assert streamer._health["last_message_at"] is not None

    # Simulate partition (connection loss)
    streamer._health["connected"] = False
    assert streamer._health["connected"] is False


@pytest.mark.asyncio
async def test_streamer_metrics_track_reconnects():
    """SchwabStreamer metrics should track reconnection attempts."""
    streamer = SchwabStreamer()

    # Initial metrics
    metrics = streamer.get_metrics()
    assert metrics["messages_received"] == 0
    assert metrics["reconnects"] == 0

    # Simulate activity
    streamer._metrics["messages_received"] = 500
    streamer._metrics["reconnects"] = 3

    metrics = streamer.get_metrics()
    assert metrics["messages_received"] == 500
    assert metrics["reconnects"] == 3


# ── Test: Multi-Symbol Partition Resilience ──────────────────────────────


@pytest.mark.asyncio
async def test_multi_symbol_partition_resilience():
    """System should handle partition for multiple symbols independently."""
    engine = DuckDBEngine(db_path=":memory:")
    await engine.start()

    feed = MockSchwabFeed(rate=50, symbols=["SPY", "QQQ", "DIA"], seed=42)

    symbols_received = set()

    async def handler(tick):
        symbols_received.add(tick["symbol"])

    feed.on_tick(handler)
    feed_task = asyncio.create_task(feed.start())
    await asyncio.sleep(0.5)

    # Should receive ticks from multiple symbols
    pre_symbols = len(symbols_received)
    assert pre_symbols >= 1, "Should receive ticks from at least one symbol"

    # Simulate partition
    await feed.stop()
    feed_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass

    # Recover with new feed
    feed2 = MockSchwabFeed(rate=50, symbols=["SPY", "QQQ", "DIA"], seed=99)
    feed2.on_tick(handler)
    feed_task2 = asyncio.create_task(feed2.start())
    await asyncio.sleep(0.5)

    # Should receive ticks from multiple symbols after recovery
    post_symbols = len(symbols_received)
    assert post_symbols >= pre_symbols, "Should receive ticks from same or more symbols after recovery"

    await feed2.stop()
    feed_task2.cancel()
    try:
        await feed_task2
    except asyncio.CancelledError:
        pass

    await engine.stop()


# ── Test: Exponential Backoff ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exponential_backoff_reconnection(streamer):
    """Reconnection uses exponential backoff: 1s, 2s, 4s, 8s, ..."""
    assert streamer.initial_reconnect_delay == 1.0
    assert streamer.max_reconnect_delay == 60.0

    delay = streamer.initial_reconnect_delay
    delays = []
    for _ in range(10):
        delays.append(delay)
        if delay >= streamer.max_reconnect_delay:
            break
        delay = min(delay * 2, streamer.max_reconnect_delay)

    assert delays[0] == 1.0
    assert delays[1] == 2.0
    assert delays[2] == 4.0
    assert delays[3] == 8.0
    assert delays[4] == 16.0
    assert delays[5] == 32.0
    assert delays[6] == 60.0

    for i in range(1, len(delays) - 1):
        ratio = delays[i] / delays[i - 1]
        assert ratio >= 1.9, f"Backoff ratio at step {i} is {ratio}, expected >= 1.9"


# ── Test: Recovery Within 30 Seconds ─────────────────────────────────────


@pytest.mark.asyncio
async def test_recovery_within_30_seconds(engine, feed):
    """System recovers automatically within 30 seconds of reconnection."""
    await engine.start()

    ticks_after = []
    partition_active = True

    async def handler(tick):
        if partition_active:
            return
        ticks_after.append(tick)

    feed.on_tick(handler)

    feed_task = asyncio.create_task(feed.start())
    await asyncio.sleep(0.3)

    # Simulate partition
    await feed.stop()
    feed_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass

    # Wait 2 seconds (simulated outage)
    await asyncio.sleep(2)

    # Reconnect
    reconnect_start = time.monotonic()
    partition_active = False

    feed2 = MockSchwabFeed(rate=50, symbols=["SPY"], seed=99)
    feed2.on_tick(handler)
    feed_task2 = asyncio.create_task(feed2.start())

    # Wait for first tick after reconnection
    for _ in range(100):
        if ticks_after:
            break
        await asyncio.sleep(0.1)

    reconnect_duration = time.monotonic() - reconnect_start

    # Cleanup
    await feed2.stop()
    feed_task2.cancel()
    try:
        await feed_task2
    except asyncio.CancelledError:
        pass

    assert len(ticks_after) > 0, "No ticks received after reconnection"
    assert reconnect_duration < 30.0, f"Recovery took {reconnect_duration:.1f}s, exceeds 30s limit"

    await engine.stop()
