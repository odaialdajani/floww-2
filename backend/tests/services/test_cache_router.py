"""
Tests for CacheRouter service.

Validates:
  - Memory cache hit returns fresh data.
  - Stale cache returns immediately with stale=True.
  - Complete miss triggers fetch.
  - Degraded response structure.
  - LRU eviction.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.cache_router import CacheRouter, _make_key, degraded_response  # noqa: F401


@pytest.fixture
def router():
    return CacheRouter(max_memory_entries=3)


@pytest.fixture
def sample_data():
    return {
        "spot": 500.0,
        "contracts": [
            {"strike": 500.0, "type": "call", "gamma": 0.04, "oi": 1000},
        ],
    }


@pytest.fixture
def coordinator():
    mock = AsyncMock()
    mock.fetch = AsyncMock(return_value={
        "spot": 500.0,
        "contracts": [{"strike": 500.0, "type": "call", "gamma": 0.04, "oi": 1000}],
    })
    return mock


class TestCacheRouterFresh:
    """Fresh cache hits."""

    @pytest.mark.asyncio
    async def test_memory_cache_hit(self, router, sample_data, coordinator):
        # Pre-populate memory
        key = _make_key("SPY", 4)
        import time

        from services.cache_router import CacheEntry
        entry = CacheEntry(
            ticker="SPY", expiries=4, data=sample_data,
            cached_at=time.monotonic(), raw_contracts=sample_data["contracts"],
        )
        router._memory_put(key, entry)

        result = await router.get_chain("SPY", 4, 300, coordinator)
        assert result["spot"] == 500.0
        assert result["_cache"]["hit"] is True
        assert result["_cache"]["stale"] is False
        # Coordinator should NOT have been called
        coordinator.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_miss_fetches(self, router, sample_data, coordinator):
        result = await router.get_chain("SPY", 4, 300, coordinator)
        assert result["spot"] == 500.0
        assert result["_cache"]["hit"] is False
        assert result["_cache"]["stale"] is False
        coordinator.fetch.assert_called_once()


class TestCacheRouterStale:
    """Stale cache returns immediately with background refresh."""

    @pytest.mark.asyncio
    async def test_stale_cache_returns_with_stale_flag(self, router, coordinator):
        import time

        from services.cache_router import CacheEntry

        key = _make_key("SPY", 4)
        stale_data = {"spot": 499.0, "contracts": []}
        entry = CacheEntry(
            ticker="SPY", expiries=4, data=stale_data,
            cached_at=time.monotonic() - 600,  # 10 min ago
            raw_contracts=[],
        )
        router._memory_put(key, entry)

        result = await router.get_chain("SPY", 4, 300, coordinator)
        assert result["spot"] == 499.0
        assert result["_cache"]["stale"] is True
        assert result["_cache"]["stale_reason"] == "max_age_exceeded"


class TestCacheRouterDegraded:
    """Degraded response structure."""

    def test_degraded_response_structure(self):
        resp = degraded_response("rate_limited", "API returned 429", retry_after=15)
        assert resp["status"] == "degraded"
        assert resp["reason"] == "rate_limited"
        assert resp["detail"] == "API returned 429"
        assert resp["retry_after"] == 15
        assert resp["stale"] is True
        assert "asof" in resp

    def test_degraded_response_defaults(self):
        resp = degraded_response("error", "test")
        assert resp["retry_after"] == 15
        assert resp["data"] is None
        assert resp["contracts"] == []
        assert resp["spot"] is None


class TestCacheRouterLRU:
    """LRU eviction."""

    def test_eviction_on_overflow(self):
        router = CacheRouter(max_memory_entries=2)
        import time

        from services.cache_router import CacheEntry

        for i in range(3):
            entry = CacheEntry(
                ticker=f"T{i}", expiries=4, data={"spot": float(i)},
                cached_at=time.monotonic(), raw_contracts=[],
            )
            router._memory_put(f"T{i}:4", entry)

        assert len(router._memory) == 2
        # First entry should be evicted
        assert router._memory_get("T0:4") is None
        assert router._memory_get("T1:4") is not None
        assert router._memory_get("T2:4") is not None


class TestCacheKey:
    def test_make_key(self):
        assert _make_key("SPY", 4) == "SPY:4"
        assert _make_key("spy", 4) == "SPY:4"
