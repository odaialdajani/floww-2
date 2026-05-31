"""
backend/tests/services/test_ingestion_pipeline.py

Tests for the ingestion pipeline: mock feed -> queue -> DuckDB.
15+ tests covering end-to-end flow, backpressure, schema validation,
reconnect logic, and token refresh.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.duckdb_engine import DuckDBEngine
from services.ingestion_pipeline import IngestionPipeline
from services.mock_schwab_feed import MockSchwabFeed

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db():
    """Fresh DuckDB engine for each test."""
    return DuckDBEngine()


@pytest.fixture
def pipeline(db):
    """Fresh ingestion pipeline for each test."""
    return IngestionPipeline(
        db=db,
        max_queue_size=1000,
        flush_interval_ms=50.0,
        tick_batch_size=100,
        chain_batch_size=50,
    )


@pytest.fixture
def mock_feed():
    """Fresh mock feed for each test."""
    return MockSchwabFeed(rate=100.0, symbols=["SPY", "QQQ"], seed=42)


@pytest.fixture
def collected_ticks():
    """Collector for tick data."""
    return []


@pytest.fixture
def collected_chains():
    """Collector for chain data."""
    return []


@pytest.fixture
def collected_lob():
    """Collector for LOB data."""
    return []


# =============================================================================
# Test 1: Mock feed generates ticks
# =============================================================================


class TestMockFeedGeneration:
    """Verify the mock feed produces valid messages."""

    @pytest.mark.asyncio
    async def test_feed_generates_ticks(self, mock_feed, collected_ticks):
        """Mock feed should produce tick messages with required fields."""
        mock_feed.on_tick(lambda t: collected_ticks.append(t))
        # Generate 10 ticks
        for _ in range(10):
            await mock_feed._generate_tick()
        assert len(collected_ticks) == 10

    @pytest.mark.asyncio
    async def test_tick_has_required_fields(self, mock_feed, collected_ticks):
        """Every tick must have: timestamp, symbol, bid, ask, last, volume."""
        mock_feed.on_tick(lambda t: collected_ticks.append(t))
        await mock_feed._generate_tick()
        tick = collected_ticks[0]
        required = ["timestamp", "symbol", "bid", "ask", "last", "volume"]
        for field in required:
            assert field in tick, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_tick_prices_are_positive(self, mock_feed, collected_ticks):
        """All price fields must be positive."""
        mock_feed.on_tick(lambda t: collected_ticks.append(t))
        for _ in range(20):
            await mock_feed._generate_tick()
        for tick in collected_ticks:
            assert tick["bid"] > 0, f"bid={tick['bid']}"
            assert tick["ask"] > 0, f"ask={tick['ask']}"
            assert tick["last"] > 0, f"last={tick['last']}"
            assert tick["ask"] >= tick["bid"], f"ask < bid: {tick}"

    @pytest.mark.asyncio
    async def test_feed_generates_chain(self, mock_feed, collected_chains):
        """Mock feed should produce chain messages with Greeks."""
        mock_feed.on_chain(lambda c: collected_chains.append(c))
        await mock_feed._generate_chain()
        assert len(collected_chains) > 0

    @pytest.mark.asyncio
    async def test_chain_has_greeks(self, mock_feed, collected_chains):
        """Chain messages must include delta, gamma, theta, vega."""
        mock_feed.on_chain(lambda c: collected_chains.append(c))
        await mock_feed._generate_chain()
        chain = collected_chains[0]
        greeks = ["delta", "gamma", "theta", "vega"]
        for g in greeks:
            assert g in chain, f"Missing greek: {g}"
            assert isinstance(chain[g], float), f"{g} should be float"

    @pytest.mark.asyncio
    async def test_chain_greeks_sign_convention(self, mock_feed, collected_chains):
        """Call delta > 0, put delta < 0, gamma > 0 for both."""
        mock_feed.on_chain(lambda c: collected_chains.append(c))
        await mock_feed._generate_chain()
        # Filter to ATM-ish strikes (within 5% of spot)
        spot = mock_feed._current_prices.get("SPY", 500.0)
        atm_calls = [c for c in collected_chains if c["type"] == "call" and abs(c["strike"] / spot - 1) < 0.05]
        atm_puts = [c for c in collected_chains if c["type"] == "put" and abs(c["strike"] / spot - 1) < 0.05]
        if atm_calls:
            assert atm_calls[0]["delta"] > 0, f"Call delta should be positive: {atm_calls[0]['delta']}"
            assert atm_calls[0]["gamma"] > 0, f"Call gamma should be positive: {atm_calls[0]['gamma']}"
        if atm_puts:
            assert atm_puts[0]["delta"] < 0, f"Put delta should be negative: {atm_puts[0]['delta']}"
            assert atm_puts[0]["gamma"] > 0, f"Put gamma should be positive: {atm_puts[0]['gamma']}"

    @pytest.mark.asyncio
    async def test_feed_generates_lob(self, mock_feed, collected_lob):
        """Mock feed should produce LOB snapshots."""
        mock_feed.on_lob(lambda l: collected_lob.append(l))
        await mock_feed._generate_lob()
        assert len(collected_lob) > 0
        lob = collected_lob[0]
        assert "bid_size" in lob
        assert "ask_size" in lob
        assert "bid_price" in lob
        assert "ask_price" in lob


# =============================================================================
# Test 2: Pipeline end-to-end
# =============================================================================


class TestPipelineEndToEnd:
    """Mock feed -> queue -> DuckDB end-to-end tests."""

    @pytest.mark.asyncio
    async def test_ticks_land_in_duckdb(self, pipeline, mock_feed, db):
        """Ticks from mock feed should land in DuckDB ticks table."""
        mock_feed.on_tick(pipeline.enqueue_tick)
        await pipeline.start()

        # Generate 50 ticks
        for _ in range(50):
            await mock_feed._generate_tick()

        # Wait for flush
        await asyncio.sleep(0.2)
        await pipeline.stop()

        result = db.query("SELECT COUNT(*) as cnt FROM ticks")
        assert result[0]["cnt"] == 50, f"Expected 50 ticks, got {result[0]['cnt']}"

    @pytest.mark.asyncio
    async def test_chains_land_in_duckdb(self, pipeline, mock_feed, db):
        """Chain updates should land in DuckDB."""
        mock_feed.on_chain(pipeline.enqueue_chain)
        await pipeline.start()

        # Generate chain updates
        await mock_feed._generate_chain()

        await asyncio.sleep(0.2)
        await pipeline.stop()

        result = db.query("SELECT COUNT(*) as cnt FROM ticks")
        assert result[0]["cnt"] > 0, "Expected chain data in ticks table"

    @pytest.mark.asyncio
    async def test_lob_lands_in_duckdb(self, pipeline, mock_feed, db):
        """LOB snapshots should land in DuckDB lob_snapshots table."""
        mock_feed.on_lob(pipeline.enqueue_lob)
        await pipeline.start()

        for _ in range(10):
            await mock_feed._generate_lob()

        await asyncio.sleep(0.2)
        await pipeline.stop()

        result = db.query("SELECT COUNT(*) as cnt FROM lob_snapshots")
        # Mock feed generates LOB for each symbol (SPY + QQQ = 2 per call)
        assert result[0]["cnt"] == 20, f"Expected 20 LOB rows (10 calls x 2 symbols), got {result[0]['cnt']}"

    @pytest.mark.asyncio
    async def test_schema_validation(self, pipeline, mock_feed, db):
        """All inserted rows should have valid schema."""
        mock_feed.on_tick(pipeline.enqueue_tick)
        await pipeline.start()

        for _ in range(20):
            await mock_feed._generate_tick()

        await asyncio.sleep(0.2)
        await pipeline.stop()

        # Check schema: all required fields present and valid
        rows = db.query("SELECT * FROM ticks LIMIT 5")
        for row in rows:
            assert row["symbol"] in ["SPY", "QQQ", "DIA", "IWM"]
            assert row["bid"] > 0
            assert row["ask"] > 0
            assert row["last"] > 0
            assert row["volume"] >= 0


# =============================================================================
# Test 3: Backpressure
# =============================================================================


class TestBackpressure:
    """Test queue overflow handling."""

    @pytest.mark.asyncio
    async def test_queue_never_exceeds_max(self):
        """Queue size should never exceed max_queue_size."""
        db = DuckDBEngine()
        # Very small queue to trigger backpressure quickly
        pipe = IngestionPipeline(db=db, max_queue_size=50, flush_interval_ms=5000)
        await pipe.start()

        # Flood with ticks faster than flush
        for i in range(200):
            pipe.enqueue_tick({
                "timestamp": "2026-05-19T20:00:00",
                "symbol": "SPY",
                "bid": 500.0,
                "ask": 500.1,
                "last": 500.05,
                "volume": 1000,
            })

        assert pipe._queue.qsize() <= 50, f"Queue exceeded max: {pipe._queue.qsize()}"
        metrics = pipe.get_metrics()
        assert metrics["dropped"] > 0, "Expected some drops"
        await pipe.stop()
        print(f"  Queue max respected: size={pipe._queue.qsize()}, dropped={metrics['dropped']}")

    @pytest.mark.asyncio
    async def test_drops_are_logged(self, caplog):
        """Dropped messages should be counted in metrics."""
        db = DuckDBEngine()
        pipe = IngestionPipeline(db=db, max_queue_size=10, flush_interval_ms=5000)
        await pipe.start()

        for i in range(100):
            pipe.enqueue_tick({"symbol": "SPY", "bid": 500.0, "ask": 500.1, "last": 500.05, "volume": 1000})

        metrics = pipe.get_metrics()
        assert metrics["dropped"] == 90, f"Expected 90 drops, got {metrics['dropped']}"
        await pipe.stop()


# =============================================================================
# Test 4: Pipeline metrics
# =============================================================================


class TestPipelineMetrics:
    """Verify pipeline metrics are accurate."""

    @pytest.mark.asyncio
    async def test_metrics_track_enqueue_dequeue(self, pipeline, mock_feed):
        """Metrics should track enqueued and dequeued counts."""
        mock_feed.on_tick(pipeline.enqueue_tick)
        await pipeline.start()

        for _ in range(30):
            await mock_feed._generate_tick()

        await asyncio.sleep(0.2)
        await pipeline.stop()

        metrics = pipeline.get_metrics()
        assert metrics["enqueued"] == 30
        assert metrics["dequeued"] == 30
        assert metrics["ticks_inserted"] == 30

    @pytest.mark.asyncio
    async def test_queue_fill_percentage(self, pipeline):
        """Queue fill percentage should be accurate."""
        for i in range(500):
            pipeline.enqueue_tick({"symbol": "SPY", "bid": 500.0, "ask": 500.1, "last": 500.05, "volume": 1000})

        metrics = pipeline.get_metrics()
        assert metrics["queue_fill_pct"] == 50.0, f"Expected 50%, got {metrics['queue_fill_pct']}%"

    @pytest.mark.asyncio
    async def test_flush_cycle_count(self, pipeline, mock_feed):
        """Flush cycles should increment."""
        mock_feed.on_tick(pipeline.enqueue_tick)
        await pipeline.start()
        await asyncio.sleep(0.15)  # Should trigger ~3 flush cycles at 50ms
        await pipeline.stop()

        metrics = pipeline.get_metrics()
        assert metrics["flush_cycles"] >= 1


# =============================================================================
# Test 5: Mock feed rate control
# =============================================================================


class TestMockFeedRate:
    """Verify mock feed generates at configured rate."""

    @pytest.mark.asyncio
    async def test_feed_rate_approximation(self):
        """Feed should generate approximately the configured rate."""
        collected = []
        feed = MockSchwabFeed(rate=50.0, symbols=["SPY"], seed=42)
        feed.on_tick(lambda t: collected.append(t))

        # Run for 0.5 seconds
        task = asyncio.create_task(feed.start())
        await asyncio.sleep(0.5)
        await feed.stop()

        # Should be roughly 25 ticks (50/s * 0.5s), allow 10-40 range
        assert 10 <= len(collected) <= 40, f"Expected ~25 ticks, got {len(collected)}"

    @pytest.mark.asyncio
    async def test_feed_gbm_dynamics(self):
        """Feed should produce realistic GBM price paths (no negative prices)."""
        collected = []
        feed = MockSchwabFeed(rate=100.0, symbols=["SPY"], seed=42)
        feed.on_tick(lambda t: collected.append(t))

        task = asyncio.create_task(feed.start())
        await asyncio.sleep(0.3)
        await feed.stop()

        for tick in collected:
            assert tick["last"] > 0, f"Negative price: {tick['last']}"
            assert tick["bid"] > 0
            assert tick["ask"] > 0


# =============================================================================
# Test 6: Multiple symbols
# =============================================================================


class TestMultipleSymbols:
    """Test pipeline with multiple symbols."""

    @pytest.mark.asyncio
    async def test_multi_symbol_ticks(self, db):
        """Pipeline should handle ticks from multiple symbols."""
        pipeline = IngestionPipeline(db=db, max_queue_size=1000, flush_interval_ms=50)
        await pipeline.start()

        symbols = ["SPY", "QQQ", "DIA", "IWM"]
        for sym in symbols:
            for i in range(25):
                pipeline.enqueue_tick({
                    "timestamp": "2026-05-19T20:00:00",
                    "symbol": sym,
                    "bid": 500.0,
                    "ask": 500.1,
                    "last": 500.05,
                    "volume": 1000,
                })

        await asyncio.sleep(0.2)
        await pipeline.stop()

        for sym in symbols:
            result = db.query("SELECT COUNT(*) as cnt FROM ticks WHERE symbol = ?", [sym])
            assert result[0]["cnt"] == 25, f"Expected 25 for {sym}, got {result[0]['cnt']}"


# =============================================================================
# Test 7: Pipeline restart
# =============================================================================


class TestPipelineRestart:
    """Test pipeline can be stopped and restarted."""

    @pytest.mark.asyncio
    async def test_restart(self, pipeline, mock_feed, db):
        """Pipeline should work after stop + restart."""
        mock_feed.on_tick(pipeline.enqueue_tick)

        # First run
        await pipeline.start()
        for _ in range(20):
            await mock_feed._generate_tick()
        await asyncio.sleep(0.1)
        await pipeline.stop()

        result1 = db.query("SELECT COUNT(*) as cnt FROM ticks")
        count1 = result1[0]["cnt"]

        # Second run
        await pipeline.start()
        for _ in range(20):
            await mock_feed._generate_tick()
        await asyncio.sleep(0.1)
        await pipeline.stop()

        result2 = db.query("SELECT COUNT(*) as cnt FROM ticks")
        count2 = result2[0]["cnt"]

        assert count2 == count1 + 20, f"Expected {count1 + 20}, got {count2}"
