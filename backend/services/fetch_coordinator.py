"""
backend/services/fetch_coordinator.py

Request coalescing / deduplication for external API calls.

Uses asyncio.Lock per (ticker, expiries) key so that concurrent UI requests
for the same data trigger at most one external fetch. Subsequent requests
either wait on the lock (if no cache yet) or return stale cache immediately.

Usage:
    coordinator = FetchCoordinator()
    # From multiple concurrent callers:
    data = await coordinator.fetch("SPY", 4, live_fetcher)
    # Only one actual API call is made; the rest wait or get cache.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Lock timeout — if a fetch takes longer than this, let callers fall back
LOCK_TIMEOUT_SECONDS = 5.0


class FetchCoordinator:
    """Deduplicates concurrent external API fetches per ticker+expiries.

    Strategy:
      - First caller acquires the lock and performs the fetch.
      - Subsequent callers for the same key wait on the lock.
      - After the first fetch completes, all waiters get the same result.
      - If the lock times out, callers fall back to cache or degraded response.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._inflight: dict[str, asyncio.Task] = {}
        self._coalesced_count: dict[str, int] = {}

    async def fetch(
        self,
        ticker: str,
        expiries: int,
        fetcher: Callable,
    ) -> dict[str, Any]:
        """Fetch with deduplication.

        Args:
            ticker: Uppercase ticker symbol.
            expiries: Number of expiries.
            fetcher: Async callable (ticker, expiries) -> dict.

        Returns:
            Chain data dict.
        """
        key = ticker.upper() + ":" + str(expiries)

        # Check if there's already an in-flight fetch for this key
        existing = self._inflight.get(key)
        if existing and not existing.done():
            logger.debug("Coalescing fetch for %s (already inflight)", key)
            self._coalesced_count[key] = self._coalesced_count.get(key, 0) + 1
            try:
                return await asyncio.wait_for(asyncio.shield(existing), timeout=LOCK_TIMEOUT_SECONDS)
            except TimeoutError:
                logger.warning("Inflight fetch timed out for %s, returning degraded", key)
                return _error_response("fetch_timeout", "External API call timed out")

        # Acquire lock for this key
        lock = self._locks.setdefault(key, asyncio.Lock())
        if lock.locked():
            # Another coroutine is fetching — wait for it
            logger.debug("Waiting on lock for %s", key)
            self._coalesced_count[key] = self._coalesced_count.get(key, 0) + 1
            try:
                # asyncio.timeout() is 3.11+ only; use wait_for on lock.acquire() for compat
                await asyncio.wait_for(lock.acquire(), timeout=LOCK_TIMEOUT_SECONDS)
            except TimeoutError:
                logger.warning("Lock wait timed out for %s", key)
                return _error_response("lock_timeout", "Timed out waiting for fetch")
            try:
                # The fetch already completed while we waited
                existing = self._inflight.get(key)
                if existing and existing.done():
                    return existing.result()
            finally:
                lock.release()

        # We have the lock — perform the fetch. Budget-gated (2026-09-04):
        # refuse BEFORE creating the upstream task so bursts degrade to
        # structured payloads instead of burning the retail key. Coalesced
        # waiters above share the winner and never touch the budget; the
        # slot releases via done-callback when the upstream call settles.
        try:
            from services.public_budget import BudgetExhausted
            from services.public_budget import budget as pub_budget
            await pub_budget.acquire()
        except BudgetExhausted as exc:
            logger.warning("Budget refused fetch for %s: %s", key, exc)
            return degraded_response(
                "budget_exhausted", str(exc), retry_after=exc.retry_after
            )
        except Exception:
            pub_budget = None
        logger.info("Initiating external fetch for %s", key)
        task = asyncio.create_task(self._do_fetch(key, ticker, expiries, fetcher))
        if pub_budget is not None:
            with contextlib.suppress(Exception):
                task.add_done_callback(lambda _: pub_budget.release())
        self._inflight[key] = task
        try:
            async with lock:
                result = await task
                return result
        except Exception as e:
            logger.warning("Fetch failed for %s: %s", key, e)
            return _error_response("fetch_error", str(e))
        finally:
            # Clean up
            self._inflight.pop(key, None)
            self._locks.pop(key, None)

    async def _do_fetch(
        self, key: str, ticker: str, expiries: int, fetcher: Callable,
    ) -> dict[str, Any]:
        """Execute the actual fetch and track metrics."""
        t0 = time.monotonic()
        try:
            result = await fetcher(ticker, expiries)
            elapsed = time.monotonic() - t0
            coalesced = self._coalesced_count.get(key, 0)
            logger.info(
                "Fetch complete for %s in %.2fs (coalesced: %d)",
                key, elapsed, coalesced,
            )
            return result
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.warning("Fetch error for %s after %.2fs: %s", key, elapsed, e)
            raise

    def get_coalesced_count(self, ticker: str, expiries: int) -> int:
        """Return number of coalesced requests for a key (for observability)."""
        key = ticker.upper() + ":" + str(expiries)
        return self._coalesced_count.get(key, 0)


def _error_response(reason: str, detail: str) -> dict[str, Any]:
    """Return a minimal error response that won't crash the UI."""
    return {
        "spot": None,
        "contracts": [],
        "status": "error",
        "reason": reason,
        "detail": detail,
    }


def degraded_response(error_type: str, detail: str, retry_after: int = 15) -> dict[str, Any]:
    """Return a structured degradation payload (standalone function for routes).

    Returns a superset that satisfies both the canonical test contract
    (status/reason/stale/retry_after/asof) AND legacy callers that read
    degraded/error_type."""
    return {
        "degraded": True,
        "error_type": error_type,
        "status": "degraded",
        "reason": error_type,
        "detail": detail,
        "retry_after": retry_after,
        "stale": True,
        "asof": time.time(),
        "data": None,
        "contracts": [],
        "spot": None,
    }


class CacheRouter:
    """Cache-first router for market data. Reads from DuckDB cache first, falls back to external API."""

    def __init__(self):
        self._cache: dict[str, dict[str, Any]] = {}

    async def get_chain(
        self,
        ticker: str,
        expiries: int,
        max_age_seconds: int,
        coordinator: FetchCoordinator,
    ) -> dict[str, Any]:
        """Get option chain — cache-first with fallback."""
        from server import fetch_spot_and_chains_merged
        cache_key = f"chain:{ticker}:{expiries}"
        cached = self._cache.get(cache_key)

        if cached and (time.monotonic() - cached["ts"]) < max_age_seconds:
            return cached["data"]

        try:
            data = await coordinator.fetch(ticker, expiries, fetch_spot_and_chains_merged)
            if data and data.get("spot") and data.get("contracts"):
                self._cache[cache_key] = {"ts": time.monotonic(), "data": data}
            return data
        except Exception:
            if cached:
                return cached["data"]
            raise

    def degraded_response(self, error_type: str, detail: str) -> dict[str, Any]:
        """Return a structured degradation payload."""
        return degraded_response(error_type, detail)
