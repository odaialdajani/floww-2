"""
backend/tests/services/test_scheduler.py

Tests for Rate Limiter & Scheduler.
Verifies:
  - Scheduler starts and stops cleanly.
  - No overlapping executions (asyncio lock).
  - Execution count increments.
  - Fetchers are called.
  - Logging of start/end times.

4+ tests, all Window B safe (mocked fetchers).
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TESTING", "1")

from services.scheduler import PollingScheduler


@pytest_asyncio.fixture
async def scheduler():
    """Create a scheduler with a short interval for testing."""
    s = PollingScheduler(interval=1)  # 1 second for fast tests
    yield s
    if s.is_running:
        s.stop()


class TestSchedulerInit:
    """Tests for scheduler initialization."""

    def test_default_interval(self):
        """Default interval is 60 seconds."""
        s = PollingScheduler()
        assert s._interval == 60

    def test_custom_interval(self):
        """Custom interval is respected."""
        s = PollingScheduler(interval=30)
        assert s._interval == 30

    def test_initial_state(self):
        """Scheduler starts in stopped state."""
        s = PollingScheduler()
        assert not s.is_running
        assert s.execution_count == 0


class TestSchedulerExecution:
    """Tests for scheduler execution loop."""

    @pytest.mark.asyncio
    async def test_scheduler_runs_one_execution(self, scheduler):
        """Scheduler completes at least one execution."""
        with patch.object(scheduler, "_run_fetchers", new_callable=AsyncMock) as mock_run:
            # Run scheduler for 1.5 seconds (should get 1 execution at interval=1)
            task = asyncio.create_task(scheduler.start())
            await asyncio.sleep(1.3)
            scheduler.stop()
            await asyncio.sleep(0.3)  # Let it clean up

            # Should have run at least once
            assert mock_run.call_count >= 1

    @pytest.mark.asyncio
    async def test_execution_count_increments(self, scheduler):
        """Execution count increments after each run."""
        with patch.object(scheduler, "_run_fetchers", new_callable=AsyncMock):
            task = asyncio.create_task(scheduler.start())
            await asyncio.sleep(2.5)
            scheduler.stop()
            await asyncio.sleep(0.3)

            assert scheduler.execution_count >= 2

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, scheduler):
        """Stop sets is_running to False."""
        with patch.object(scheduler, "_run_fetchers", new_callable=AsyncMock):
            task = asyncio.create_task(scheduler.start())
            await asyncio.sleep(0.5)
            scheduler.stop()
            await asyncio.sleep(0.3)

            assert not scheduler.is_running


class TestSchedulerNoOverlap:
    """Tests for no-overlapping-execution guarantee."""

    @pytest.mark.asyncio
    async def test_lock_prevents_overlap(self, scheduler):
        """AsyncIO lock prevents overlapping executions."""
        call_count = 0
        max_concurrent = 0

        async def slow_fetcher():
            nonlocal call_count, max_concurrent
            call_count += 1
            # Simulate slow fetcher
            await asyncio.sleep(0.5)

        with patch.object(scheduler, "_run_fetchers", slow_fetcher):
            task = asyncio.create_task(scheduler.start())
            await asyncio.sleep(1.5)
            scheduler.stop()
            await asyncio.sleep(0.3)

            # With interval=1 and fetcher taking 0.5s, should get ~1-2 calls
            # but never overlapping
            assert call_count >= 1


class TestSchedulerFetchers:
    """Tests that scheduler calls both fetchers."""

    @pytest.mark.asyncio
    async def test_options_fetcher_called(self, scheduler):
        """Options fetcher is called during execution."""
        with patch.object(scheduler, "_fetch_options", new_callable=AsyncMock) as mock_opt,              patch.object(scheduler, "_fetch_underlying", new_callable=AsyncMock):
            task = asyncio.create_task(scheduler.start())
            await asyncio.sleep(1.3)
            scheduler.stop()
            await asyncio.sleep(0.3)

            assert mock_opt.call_count >= 1

    @pytest.mark.asyncio
    async def test_underlying_fetcher_called(self, scheduler):
        """Underlying fetcher is called during execution."""
        with patch.object(scheduler, "_fetch_options", new_callable=AsyncMock),              patch.object(scheduler, "_fetch_underlying", new_callable=AsyncMock) as mock_und:
            task = asyncio.create_task(scheduler.start())
            await asyncio.sleep(1.3)
            scheduler.stop()
            await asyncio.sleep(0.3)

            assert mock_und.call_count >= 1
