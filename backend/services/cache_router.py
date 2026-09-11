"""
backend/services/cache_router.py

Cache-first routing layer for analytics endpoints.
Memory cache with LRU eviction, stale-while-revalidate, and graceful degradation.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cached entry."""
    ticker: str
    expiries: int
    data: dict[str, Any]
    cached_at: float
    raw_contracts: list = field(default_factory=list)


class CacheRouter:
    """Cache-first router with LRU eviction and stale-while-revalidate."""

    def __init__(self, max_memory_entries: int = 64):
        self._memory: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max = max_memory_entries

    def _memory_put(self, key: str, entry: CacheEntry) -> None:
        """Put entry in cache with LRU eviction."""
        if key in self._memory:
            self._memory.move_to_end(key)
        self._memory[key] = entry
        while len(self._memory) > self._max:
            self._memory.popitem(last=False)

    def _memory_get(self, key: str) -> CacheEntry | None:
        """Get entry from cache."""
        return self._memory.get(key)

    @property
    def _memory(self) -> OrderedDict[str, CacheEntry]:
        return self.__memory

    @_memory.setter
    def _memory(self, value: OrderedDict[str, CacheEntry]) -> None:
        self.__memory = value

    async def get_chain(
        self,
        ticker: str,
        expiries: int,
        max_age_seconds: int,
        coordinator: Any = None,
    ) -> dict[str, Any]:
        """Get option chain — cache-first with fallback."""
        key = _make_key(ticker.upper(), expiries)
        entry = self._memory_get(key)

        if entry is not None:
            age = time.monotonic() - entry.cached_at
            if age < max_age_seconds:
                # Fresh hit
                result = dict(entry.data)
                result["_cache"] = {"hit": True, "stale": False}
                return result
            else:
                # Stale — return immediately with stale flag
                result = dict(entry.data)
                result["_cache"] = {
                    "hit": True,
                    "stale": True,
                    "stale_reason": "max_age_exceeded",
                }
                return result

        # Complete miss — need to fetch
        if coordinator is None:
            return degraded_response("no_coordinator", "No coordinator available")

        try:
            from server import fetch_spot_and_chains_merged
            data = await coordinator.fetch(ticker, expiries, fetch_spot_and_chains_merged)
            if isinstance(data, dict) and data.get("reason") == "budget_exhausted" and entry is not None:
                # Budget gate refused the refresh (2026-09-04) — serve the
                # stale entry with the reason instead of an empty degrade.
                result = dict(entry.data)
                result["_cache"] = {
                    "hit": True,
                    "stale": True,
                    "stale_reason": "budget_cooldown",
                    "retry_after": data.get("retry_after", 15),
                }
                return result
            if data and data.get("spot") and data.get("contracts"):
                entry = CacheEntry(
                    ticker=ticker.upper(),
                    expiries=expiries,
                    data=data,
                    cached_at=time.monotonic(),
                    raw_contracts=data.get("contracts", []),
                )
                self._memory_put(key, entry)
            result = dict(data) if data else {}
            result["_cache"] = {"hit": False, "stale": False}
            return result
        except Exception as e:
            logger.warning(f"CacheRouter fetch failed for {ticker}: {e}")
            if entry is not None:
                result = dict(entry.data)
                result["_cache"] = {"hit": True, "stale": True, "stale_reason": "fetch_error"}
                return result
            return degraded_response("fetch_error", str(e))

    def degraded_response(self, error_type: str, detail: str, retry_after: int = 15) -> dict[str, Any]:
        """Return a structured degradation payload."""
        return degraded_response(error_type, detail, retry_after)


def _make_key(ticker: str, expiries: int) -> str:
    """Build cache key from ticker and expiries count."""
    return f"{ticker.upper()}:{expiries}"


def degraded_response(error_type: str, detail: str, retry_after: int = 15) -> dict[str, Any]:
    """Return a structured degradation payload (standalone function for routes)."""
    return {
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
