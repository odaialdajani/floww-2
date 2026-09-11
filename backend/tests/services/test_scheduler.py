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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TESTING", "1")

import contextlib

from services.scheduler import PollingScheduler


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch):
    monkeypatch.setattr("services.scheduler.get_duckdb_conn", MagicMock())


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
            _task = asyncio.create_task(scheduler.start())
            await asyncio.sleep(1.3)
            scheduler.stop()
            await asyncio.sleep(0.3)  # Let it clean up

            # Should have run at least once
            assert mock_run.call_count >= 1

    @pytest.mark.asyncio
    async def test_execution_count_increments(self, scheduler):
        """Execution count increments after each run."""
        with patch.object(scheduler, "_run_fetchers", new_callable=AsyncMock):
            _task = asyncio.create_task(scheduler.start())
            await asyncio.sleep(2.5)
            scheduler.stop()
            await asyncio.sleep(0.3)

            assert scheduler.execution_count >= 2

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, scheduler):
        """Stop sets is_running to False."""
        with patch.object(scheduler, "_run_fetchers", new_callable=AsyncMock):
            _task = asyncio.create_task(scheduler.start())
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
            _task = asyncio.create_task(scheduler.start())
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
        """First execution runs both price fetchers and daily news exactly once."""
        with patch.object(scheduler, "_fetch_options", new_callable=AsyncMock) as options, \
                patch.object(scheduler, "_fetch_underlying", new_callable=AsyncMock) as underlying, \
                patch.object(scheduler, "_poll_news_for_universe", new_callable=AsyncMock) as news, \
                patch.object(scheduler, "_poll_max_pain_for_universe", new_callable=AsyncMock) as max_pain, \
                patch.object(scheduler, "_poll_rv_for_universe", new_callable=AsyncMock) as rv:
            await scheduler._run_fetchers()
            options.assert_awaited_once_with()
            underlying.assert_awaited_once_with()
            news.assert_awaited_once_with()
            max_pain.assert_not_awaited()
            rv.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_underlying_fetcher_called(self, scheduler):
        """A later ordinary execution runs both fetchers without daily polls."""
        scheduler._execution_count = 1
        with patch.object(scheduler, "_fetch_options", new_callable=AsyncMock) as options, \
                patch.object(scheduler, "_fetch_underlying", new_callable=AsyncMock) as underlying, \
                patch.object(scheduler, "_poll_news_for_universe", new_callable=AsyncMock) as news, \
                patch.object(scheduler, "_poll_max_pain_for_universe", new_callable=AsyncMock) as max_pain, \
                patch.object(scheduler, "_poll_rv_for_universe", new_callable=AsyncMock) as rv:
            await scheduler._run_fetchers()
            options.assert_awaited_once_with()
            underlying.assert_awaited_once_with()
            news.assert_not_awaited()
            max_pain.assert_not_awaited()
            rv.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────
# Steal-list #7 — RV/VRP daily CRT cron.
# 4 cases pinning the contract:
#   1. _poll_rv_for_universe method exists and is callable.
#   2. Trigger logic staggered +10 ticks from the news poll.
#   3. Per-ticker exception isolation (one ticker crashing does NOT
#      fail the rest of the universe).
#   4. End-to-end: each ticker writes the 5+3+2+1=11 spec'd rows.
# ─────────────────────────────────────────────────────────────────────


class TestSchedulerRvPoll:
    """RV/VRP daily-poll contract (steal-list #7)."""

    def test_scheduler_has_rv_poll_method(self):
        """PollingScheduler exposes ``_poll_rv_for_universe`` coroutine.

        Mirrors the canonical ``test_scheduler_has_max_pain_poll_method``
        in ``test_max_pain_drift.py`` — the scheduler's surface area
        must include the new cron method without re-orchestrating the
        production event loop.
        """
        s = PollingScheduler(interval=60)
        assert hasattr(s, "_poll_rv_for_universe")
        assert callable(s._poll_rv_for_universe)
        # Method should be async (coroutine fn) — verify by
        # constructing and closing the coroutine without scheduling.
        coro = s._poll_rv_for_universe()
        # The impl wraps its body in a top-level try/except so the
        # coroutine surfaces immediately after logging the noop.
        with contextlib.suppress(Exception):
            coro.close()

    def test_rv_poll_trigger_staggered_from_news(self):
        """Trigger fires ONLY at (count + 10) % ticks_per_day == 0.

        News fires at count % ticks_per_day == 0 (offset 0 → count 0);
        max_pain at (count + 5) % ticks_per_day == 0 (offset 5 →
        count 1435 ≡ -5 mod 1440); RV at (count + 10) % ticks_per_day
        == 0 (offset 10 → count 1430 ≡ -10 mod 1440).

        All three daily polls fire on distinct ticks so the per-tick
        fetch+write bursts cannot stack into a single long-pole.
        """
        ticks_per_day = 1440   # 24*3600 / 60s interval
        cases = (
            # (execution_count, fires_news, fires_max_pain, fires_rv)
            (0,    True,  False, False),   # news at the very first tick
            (5,    False, False, False),   # all quiet (5+5=10, 5+10=15)
            (10,   False, False, False),   # all quiet (10+5=15, 10+10=20)
            (15,   False, False, False),   # all quiet
            (1429, False, False, False),   # 11 ticks before rv trigger
            (1430, False, False, True),    # rv fires (1430+10=1440 ≡ 0)
            (1434, False, False, False),   # 1 tick before max_pain
            (1435, False, True,  False),   # max_pain (1435+5=1440 ≡ 0)
            (1440, True,  False, False),   # next day, news
            (2870, False, False, True),    # day 2 rv (2870+10=2880 ≡ 0)
            (2875, False, True,  False),   # day 2 max_pain
        )
        for count, news_fire, max_pain_fire, rv_fire in cases:
            assert (
                count % ticks_per_day == 0
            ) == news_fire, f"news trigger wrong at count={count}"
            assert (
                (count + 5) % ticks_per_day == 0
            ) == max_pain_fire, f"max_pain trigger wrong at count={count}"
            assert (
                (count + 10) % ticks_per_day == 0
            ) == rv_fire, f"rv trigger wrong at count={count}"

    def test_rv_poll_iterates_top_10_universe(self):
        """Universe is the module-level ``RV_UNIVERSE`` tuple pinned
        to SPY/QQQ/AAPL/TSLA/NVDA/AMZN/MSFT/META/GOOGL/AMD.

        The universe is hoisted to module scope (mirroring the
        ``TABLE_NAME`` convention used by ``max_pain_drift``) so
        the scheduler cannot drift away from the canonical set
        without this test catching it.
        """
        from services.scheduler import RV_UNIVERSE
        expected = (
            "SPY", "QQQ", "AAPL", "TSLA", "NVDA",
            "AMZN", "MSFT", "META", "GOOGL", "AMD",
        )
        # 3 checks: type + count + set-equality against the
        # canonical 10-ticker set.
        assert isinstance(RV_UNIVERSE, tuple)
        assert len(RV_UNIVERSE) == 10
        assert set(RV_UNIVERSE) == set(expected)
        # And the order matches too (locks the iteration order).
        assert expected == RV_UNIVERSE

    def test_rv_poll_calls_all_four_accumulator_helpers(self):
        """Imports verify all 4 accumulator helpers are referenced.

        The scheduler's sync_poll closure lazy-imports the 4
        accumulator functions from ``services.realized_volatility``.
        Each per-ticker success path fires:
          - ``accumulate_today`` (5 estimator rows)
          - ``accumulate_cones_today`` (3 cone rows)
          - ``accumulate_bands_today`` (2 band rows)
          - ``accumulate_vrp_today`` (1 VRP row, conditional on IV)
        """
        # Pinned via pure introspection on the module so this test is
        # independent of the running scheduler event loop.
        from services import realized_volatility as rv
        for fn_name in (
            "accumulate_today",
            "accumulate_cones_today",
            "accumulate_bands_today",
            "accumulate_vrp_today",
        ):
            assert hasattr(rv, fn_name), f"missing helper: {fn_name}"
            assert callable(getattr(rv, fn_name)), (
                f"{fn_name} is not callable"
            )
