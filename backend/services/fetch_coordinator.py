"""
backend/services/fetch_coordinator.py

Request coalescing / deduplication for external API calls.

Publishes one shared in-flight task per (ticker, expiries) key so concurrent UI
requests for the same data share one budget admission and external fetch.

Usage:
    coordinator = FetchCoordinator()
    # From multiple concurrent callers:
    data = await coordinator.fetch("SPY", 4, live_fetcher)
    # Only one actual API call is made; the rest wait or get cache.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import os
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# In-flight wait timeout — let coalesced callers fall back if a fetch stalls.
LOCK_TIMEOUT_SECONDS = 5.0
MAX_COALESCED_KEYS = 256


class FetchCoordinator:
    """Deduplicates concurrent external API fetches per ticker+expiries.

    Strategy:
      - The first caller publishes one shared task before yielding.
      - Subsequent callers for the same key await that task.
      - Different keys retain independent tasks and budget admission.
    """

    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Task] = {}
        self._inflight_coalesced_count: dict[str, int] = {}
        # Diagnostic-only per-key history. Keep a recent bounded window so
        # caller-controlled keys cannot grow this map for the process lifetime.
        self._coalesced_count: OrderedDict[str, int] = OrderedDict()

    def _record_coalesced(self, key: str) -> None:
        self._coalesced_count[key] = self._coalesced_count.get(key, 0) + 1
        self._coalesced_count.move_to_end(key)
        if len(self._coalesced_count) > MAX_COALESCED_KEYS:
            self._coalesced_count.popitem(last=False)
        self._inflight_coalesced_count[key] = self._inflight_coalesced_count.get(key, 0) + 1

    async def fetch(
        self,
        ticker: str,
        expiries: int,
        fetcher: Callable,
        *,
        source_owns_budget: bool = False,
    ) -> dict[str, Any]:
        """Fetch with deduplication.

        Args:
            ticker: Uppercase ticker symbol.
            expiries: Number of expiries.
            fetcher: Async callable (ticker, expiries) -> dict.
            source_owns_budget: Internal composition only: the hardwired
                Public adapter owns admission before any provider/auth work.

        Returns:
            Chain data dict.
        """
        key = ticker.upper() + ":" + str(expiries)

        # Check if there's already an in-flight fetch for this key
        existing = self._inflight.get(key)
        if existing and not existing.done():
            logger.debug("Coalescing fetch for %s (already inflight)", key)
            self._record_coalesced(key)
            try:
                return await asyncio.wait_for(asyncio.shield(existing), timeout=LOCK_TIMEOUT_SECONDS)
            except TimeoutError:
                logger.warning("Inflight fetch timed out for %s, returning degraded", key)
                return _error_response("fetch_timeout", "External API call timed out")

        # Publish the task before yielding to budget admission. This makes the
        # check-and-publish sequence atomic within the event loop: concurrent
        # same-key callers see this task and cannot debit budget twice.
        task = asyncio.create_task(
            self._fetch_with_budget(
                key, ticker, expiries, fetcher,
                source_owns_budget=source_owns_budget,
            )
        )
        self._inflight[key] = task
        self._inflight_coalesced_count[key] = 0
        try:
            return await task
        except Exception as e:
            logger.warning("Fetch failed for %s: %s", key, e)
            return _error_response("fetch_error", str(e))
        finally:
            # Clean up
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)
                self._inflight_coalesced_count.pop(key, None)

    async def _fetch_with_budget(
        self,
        key: str,
        ticker: str,
        expiries: int,
        fetcher: Callable,
        *,
        source_owns_budget: bool,
    ) -> dict[str, Any]:
        """Admit one shared fetch, preserving the fail-closed budget gate."""
        try:
            from services.public_budget import BudgetExhausted
            from services.public_budget import budget as public_budget
        except ImportError:
            # The budget shield is optional; a missing module retains the
            # coordinator's historical unbudgeted behavior.
            BudgetExhausted = public_budget = None

        admitted_budget = None
        if public_budget is not None and not source_owns_budget:
            try:
                await public_budget.acquire()
                admitted_budget = public_budget
            except BudgetExhausted as exc:
                logger.warning("Budget refused fetch for %s: %s", key, exc)
                return degraded_response(
                    "budget_exhausted", str(exc), retry_after=exc.retry_after
                )
            except Exception as exc:
                # Fail closed: an unavailable governor must not permit spend.
                logger.warning("Budget acquire failed for %s: %s", key, exc)
                return degraded_response("budget_unavailable", str(exc))

        try:
            logger.info("Initiating external fetch for %s", key)
            return await self._do_fetch(key, ticker, expiries, fetcher)
        except Exception as exc:
            logger.warning("Fetch failed for %s: %s", key, exc)
            return _error_response("fetch_error", str(exc))
        finally:
            if admitted_budget is not None:
                try:
                    admitted_budget.release()
                except Exception as exc:
                    logger.warning("Budget release failed for %s: %s", key, exc)

    async def _do_fetch(
        self, key: str, ticker: str, expiries: int, fetcher: Callable,
    ) -> dict[str, Any]:
        """Execute the actual fetch and track metrics."""
        t0 = time.monotonic()
        try:
            result = await fetcher(ticker, expiries)
            elapsed = time.monotonic() - t0
            coalesced = self._inflight_coalesced_count.get(key, 0)
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
        """Return the retained recent coalesced count, or zero after eviction."""
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

    def peek_chain(self, ticker: str, expiries: int = 6) -> dict[str, Any] | None:
        """Copy an existing observation without refreshing or extending its age."""
        entry = self._cache.get(f"chain:{ticker.upper()}:{expiries}")
        if entry is None:
            return None
        result = copy.deepcopy(entry["data"])
        result["cache_age_s"] = max(0.0, time.monotonic() - entry["ts"])
        return result

    def peek_available_chain(self, ticker: str, preferred: int = 6) -> dict[str, Any] | None:
        prefix = f"chain:{ticker.upper()}:"
        candidates = [(key, value) for key, value in self._cache.items() if key.startswith(prefix)]
        if not candidates:
            return None
        key, _ = max(candidates, key=lambda item: (item[0] == f"{prefix}{preferred}", item[1]["ts"]))
        count = int(key.rsplit(":", 1)[1])
        result = self.peek_chain(ticker, count)
        result["requested_expiry_count"] = count
        return result

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
            # Public-only merged reads either use the adapter's full fan-out
            # admission or refuse. Reserving another outer slot can exhaust
            # all four slots before any adapter is able to start.
            data = await coordinator.fetch(
                ticker, expiries, fetch_spot_and_chains_merged,
                source_owns_budget=os.getenv("FLOWW_MARKET_DATA_PROVIDER") == "public",
            )
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
