"""
backend/tests/services/test_replay_engine.py

Tests for the historical replay engine.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.duckdb_engine import DuckDBEngine
from services.replay_engine import ReplayEngine


class TestReplayEngine:
    """Test replay engine functionality."""

    @pytest.mark.asyncio
    async def test_replay_ticks_from_duckdb(self):
        """Replay should read ticks from DuckDB and push to handlers."""
        db = DuckDBEngine(":memory:")
        # Insert test data
        now = datetime.now(timezone.utc)
        for i in range(10):
            ts = (now + timedelta(seconds=i)).isoformat()
            db.conn.execute(
                """INSERT INTO ticks (timestamp, symbol, bid, ask, last, volume, oi,
                   delta_val, gamma_val, theta_val, vega_val, vanna_val, charm_val, vomma_val)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ts, "SPY", 500.0, 500.1, 500.05, 1000+i*100, 5000, 0.5, 0.01, -0.05, 0.2, 0.001, -0.02, 0.003),
            )

        collected = []
        engine = ReplayEngine(
            db=db,
            start=now - timedelta(seconds=1),
            end=now + timedelta(seconds=15),
            speed=100.0,  # fast replay
        )
        engine.on_tick(lambda t: collected.append(t))
        await engine.start()

        assert len(collected) == 10

    @pytest.mark.asyncio
    async def test_replay_respects_speed(self):
        """Replay at 1x speed should take roughly the right amount of time."""
        db = DuckDBEngine(":memory:")
        now = datetime.now(timezone.utc)
        for i in range(5):
            ts = (now + timedelta(seconds=i)).isoformat()
            db.conn.execute(
                """INSERT INTO ticks (timestamp, symbol, bid, ask, last, volume, oi,
                   delta_val, gamma_val, theta_val, vega_val, vanna_val, charm_val, vomma_val)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ts, "SPY", 500.0, 500.1, 500.05, 1000, 5000, 0.5, 0.01, -0.05, 0.2, 0.001, -0.02, 0.003),
            )

        collected = []
        engine = ReplayEngine(
            db=db,
            start=now - timedelta(seconds=1),
            end=now + timedelta(seconds=10),
            speed=10.0,
        )
        engine.on_tick(lambda t: collected.append(t))

        import time
        start_wall = time.monotonic()
        await engine.start()
        elapsed = time.monotonic() - start_wall

        # 5 ticks at 10x speed = ~0.4s of simulated time
        # Should complete in well under 2s wall clock
        assert elapsed < 2.0, f"Replay took {elapsed:.2f}s (expected <2s)"
        assert len(collected) == 5

    @pytest.mark.asyncio
    async def test_replay_no_data(self):
        """Replay with no data should complete without error."""
        db = DuckDBEngine(":memory:")
        now = datetime.now(timezone.utc)
        collected = []
        engine = ReplayEngine(
            db=db,
            start=now - timedelta(hours=1),
            end=now,
            speed=1.0,
        )
        engine.on_tick(lambda t: collected.append(t))
        await engine.start()
        assert len(collected) == 0

    @pytest.mark.asyncio
    async def test_replay_stop(self):
        """Replay should be stoppable."""
        db = DuckDBEngine(":memory:")
        now = datetime.now(timezone.utc)
        for i in range(100):
            ts = (now + timedelta(seconds=i)).isoformat()
            db.conn.execute(
                """INSERT INTO ticks (timestamp, symbol, bid, ask, last, volume, oi,
                   delta_val, gamma_val, theta_val, vega_val, vanna_val, charm_val, vomma_val)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ts, "SPY", 500.0, 500.1, 500.05, 1000, 5000, 0.5, 0.01, -0.05, 0.2, 0.001, -0.02, 0.003),
            )

        collected = []
        engine = ReplayEngine(
            db=db,
            start=now - timedelta(seconds=1),
            end=now + timedelta(seconds=200),
            speed=1.0,  # slow
        )
        engine.on_tick(lambda t: collected.append(t))

        # Start and stop quickly
        task = asyncio.create_task(engine.start())
        await asyncio.sleep(0.1)
        await engine.stop()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # Should have collected some but not all
        assert 0 < len(collected) < 100

    def test_replay_status(self):
        """Status should reflect engine state."""
        db = DuckDBEngine(":memory:")
        now = datetime.now(timezone.utc)
        engine = ReplayEngine(db=db, start=now, end=now + timedelta(hours=1), speed=10.0)
        status = engine.get_status()
        assert status["running"] is False
        assert status["speed"] == 10.0

    @pytest.mark.asyncio
    async def test_replay_chains(self):
        """Replay should also replay chain data."""
        db = DuckDBEngine(":memory:")
        now = datetime.now(timezone.utc)
        for i in range(5):
            ts = (now + timedelta(minutes=i)).isoformat()
            db.conn.execute(
                """INSERT INTO ticks (timestamp, symbol, bid, ask, last, volume, oi,
                   delta_val, gamma_val, theta_val, vega_val, vanna_val, charm_val, vomma_val)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ts, "SPY", 500.0, 500.1, 500.05, 1000, 5000, 0.5, 0.01, -0.05, 0.2, 0.001, -0.02, 0.003),
            )

        tick_collected = []
        chain_collected = []
        engine = ReplayEngine(
            db=db,
            start=now - timedelta(minutes=1),
            end=now + timedelta(minutes=10),
            speed=100.0,
        )
        engine.on_tick(lambda t: tick_collected.append(t))
        engine.on_chain(lambda c: chain_collected.append(c))
        await engine.start()

        assert len(tick_collected) == 5
        # Chain data has delta_val != 0 filter, our test data has delta_val=0.5
        assert len(chain_collected) == 5
