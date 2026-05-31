"""
backend/services/scheduler.py

Rate Limiter & Scheduler.
Runs yoptions_fetcher and yfinance_fetcher every 60 seconds.
Ensures no overlapping executions with asyncio lock.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone
from typing import Optional

from services.yfinance_fetcher import fetch_and_store, get_duckdb_conn
from services.yoptions_fetcher import fetch_all_chains

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 60  # seconds


class PollingScheduler:
    """Async scheduler that runs fetchers at a fixed interval.

    Features:
    - No overlapping executions (asyncio lock).
    - Graceful shutdown on SIGINT/SIGTERM.
    - Logs start/end times for monitoring.
    """

    def __init__(self, interval: int = DEFAULT_INTERVAL):
        self._interval = interval
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._execution_count = 0
        self._conn = get_duckdb_conn()

    async def start(self):
        """Start the scheduler loop."""
        self._running = True
        logger.info(f"Scheduler started (interval={self._interval}s)")
        try:
            while self._running:
                start_time = datetime.now(timezone.utc)
                logger.info(
                    f"Execution #{self._execution_count + 1} started at "
                    f"{start_time.isoformat()}"
                )

                # Use lock to prevent overlapping executions
                if self._lock.locked():
                    logger.warning("Previous execution still running, skipping this cycle")
                else:
                    async with self._lock:
                        await self._run_fetchers()

                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                self._execution_count += 1
                logger.info(
                    f"Execution #{self._execution_count} completed in {duration:.2f}s"
                )

                # Sleep for remaining interval
                sleep_time = max(0, self._interval - duration)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        finally:
            logger.info(
                f"Scheduler stopped. Total executions: {self._execution_count}"
            )

    async def _run_fetchers(self):
        """Run both fetchers concurrently."""
        try:
            # Run fetchers concurrently
            options_task = asyncio.create_task(self._fetch_options())
            underlying_task = asyncio.create_task(self._fetch_underlying())

            await asyncio.gather(options_task, underlying_task, return_exceptions=True)
        except Exception as e:
            logger.error(f"Fetcher error: {e}")

    async def _fetch_options(self):
        """Fetch options chains in thread pool."""
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, fetch_all_chains)
            if not df.empty:
                logger.info(f"Options fetch: {len(df)} rows")
            else:
                logger.warning("Options fetch returned empty")
        except Exception as e:
            logger.error(f"Options fetch failed: {e}")

    async def _fetch_underlying(self):
        """Fetch underlying data in thread pool."""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, fetch_and_store, None, self._conn
            )
            total = sum(results.values())
            logger.info(f"Underlying fetch: {total} rows across {len(results)} tickers")
        except Exception as e:
            logger.error(f"Underlying fetch failed: {e}")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        logger.info("Scheduler stop requested")

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def is_running(self) -> bool:
        return self._running


async def run_scheduler(interval: int = DEFAULT_INTERVAL):
    """Convenience function to run the scheduler."""
    scheduler = PollingScheduler(interval=interval)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, scheduler.stop)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    await scheduler.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_scheduler())
