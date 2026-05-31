"""
backend/tests/services/test_lob_depth.py

Tests for Level-2 order book depth: schema, mock feed generation,
and pipeline insertion.
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


class TestLobDepthSchema:
    """Verify the lob_depth table exists in DuckDB schema."""

    def test_lob_depth_table_exists(self):
        db = DuckDBEngine(":memory:")
        tables = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "lob_depth" in table_names, f"lob_depth not in {table_names}"

    def test_lob_depth_schema(self):
        db = DuckDBEngine(":memory:")
        cols = db._conn.execute("DESCRIBE lob_depth").fetchall()
        col_names = [c[0] for c in cols]
        expected = [
            "timestamp", "symbol", "expiry", "strike", "option_type",
            "level", "bid_size", "bid_price", "ask_size", "ask_price"
        ]
        for col in expected:
            assert col in col_names, f"Missing column: {col}"


class TestMockFeedLobDepth:
    """Verify mock feed generates valid lob_depth messages."""

    @pytest.mark.asyncio
    async def test_feed_generates_lob_depth(self):
        collected = []
        feed = MockSchwabFeed(rate=100.0, symbols=["SPY"], seed=42)
        feed.on_lob_depth(lambda d: collected.append(d))
        await feed._generate_lob_depth()
        # 5 levels per symbol
        assert len(collected) == 5

    @pytest.mark.asyncio
    async def test_lob_depth_has_required_fields(self):
        collected = []
        feed = MockSchwabFeed(rate=100.0, symbols=["SPY"], seed=42)
        feed.on_lob_depth(lambda d: collected.append(d))
        await feed._generate_lob_depth()
        required = [
            "timestamp", "symbol", "level", "bid_size", "bid_price",
            "ask_size", "ask_price"
        ]
        for field in required:
            assert field in collected[0], f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_lob_depth_levels_sequential(self):
        collected = []
        feed = MockSchwabFeed(rate=100.0, symbols=["SPY"], seed=42)
        feed.on_lob_depth(lambda d: collected.append(d))
        await feed._generate_lob_depth()
        levels = [d["level"] for d in collected]
        assert levels == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_lob_depth_bid_less_than_ask(self):
        collected = []
        feed = MockSchwabFeed(rate=100.0, symbols=["SPY"], seed=42)
        feed.on_lob_depth(lambda d: collected.append(d))
        await feed._generate_lob_depth()
        for d in collected:
            assert d["bid_price"] < d["ask_price"], (
                f"bid {d['bid_price']} >= ask {d['ask_price']}"
            )

    @pytest.mark.asyncio
    async def test_lob_depth_sizes_positive(self):
        collected = []
        feed = MockSchwabFeed(rate=100.0, symbols=["SPY"], seed=42)
        feed.on_lob_depth(lambda d: collected.append(d))
        await feed._generate_lob_depth()
        for d in collected:
            assert d["bid_size"] > 0
            assert d["ask_size"] > 0

    @pytest.mark.asyncio
    async def test_lob_depth_deeper_levels_smaller(self):
        """Deeper levels should have smaller sizes (liquidity thins)."""
        collected = []
        feed = MockSchwabFeed(rate=100.0, symbols=["SPY"], seed=42)
        feed.on_lob_depth(lambda d: collected.append(d))
        await feed._generate_lob_depth()
        # Level 0 should have larger sizes on average than level 4
        level_0_sizes = [d["bid_size"] for d in collected if d["level"] == 0]
        level_4_sizes = [d["bid_size"] for d in collected if d["level"] == 4]
        assert sum(level_0_sizes) >= sum(level_4_sizes)


class TestPipelineLobDepth:
    """Test pipeline insertion of lob_depth data."""

    @pytest.mark.asyncio
    async def test_lob_depth_lands_in_duckdb(self):
        db = DuckDBEngine(":memory:")
        pipeline = IngestionPipeline(db=db, max_queue_size=1000, flush_interval_ms=50)
        await pipeline.start()

        for i in range(50):
            pipeline.enqueue_lob_depth({
                "timestamp": "2026-05-19T20:00:00",
                "symbol": "SPY",
                "expiry": "2026-05-23",
                "strike": 500.0,
                "option_type": "C",
                "level": i % 5,
                "bid_size": 100 + i,
                "bid_price": 499.0 - i * 0.1,
                "ask_size": 100 + i,
                "ask_price": 501.0 + i * 0.1,
            })

        await asyncio.sleep(0.2)
        await pipeline.stop()

        result = db.query("SELECT COUNT(*) as cnt FROM lob_depth")
        assert result[0]["cnt"] == 50

    @pytest.mark.asyncio
    async def test_lob_depth_schema_validation(self):
        db = DuckDBEngine(":memory:")
        pipeline = IngestionPipeline(db=db, max_queue_size=1000, flush_interval_ms=50)
        await pipeline.start()

        for i in range(10):
            pipeline.enqueue_lob_depth({
                "timestamp": "2026-05-19T20:00:00",
                "symbol": "SPY",
                "expiry": "2026-05-23",
                "strike": 500.0,
                "option_type": "C",
                "level": 0,
                "bid_size": 100,
                "bid_price": 499.5,
                "ask_size": 100,
                "ask_price": 500.5,
            })

        await asyncio.sleep(0.2)
        await pipeline.stop()

        rows = db.query("SELECT * FROM lob_depth LIMIT 3")
        for row in rows:
            assert row["symbol"] == "SPY"
            assert row["level"] == 0
            assert row["bid_price"] < row["ask_price"]
