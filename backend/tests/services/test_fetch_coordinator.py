"""
Tests for FetchCoordinator service.

Validates:
  - Concurrent requests for same key trigger only one fetch.
  - Different keys fetch independently.
  - Coalesced count is tracked.
  - Error response structure.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture(autouse=True)
def _isolated_public_budget_singleton():
    # D1: the adapter debits the shared budget singleton per C8, so each
    # test starts from a full bucket; otherwise module order decides
    # who exhausts whom.
    from services.public_budget import budget

    budget.reset()
    yield
    budget.reset()

from services.fetch_coordinator import FetchCoordinator


@pytest.fixture
def coordinator():
    return FetchCoordinator()


async def _mock_fetcher(ticker, expiries):
    await asyncio.sleep(0.05)  # simulate network delay
    return {"spot": 500.0, "ticker": ticker, "expiries": expiries, "contracts": []}


class TestFetchDeduplication:
    """Concurrent fetches for the same key are deduplicated."""

    @pytest.mark.asyncio
    async def test_concurrent_same_key_single_fetch(self, coordinator):
        """5 concurrent requests for SPY:4 should trigger only 1 fetch."""
        results = await asyncio.gather(*[
            coordinator.fetch("SPY", 4, _mock_fetcher)
            for _ in range(5)
        ])
        # All should return the same data
        for r in results:
            assert r["spot"] == 500.0
            assert r["ticker"] == "SPY"

        # Coalesced count should be 4 (first one doesn't count)
        assert coordinator.get_coalesced_count("SPY", 4) == 4

    @pytest.mark.asyncio
    async def test_different_keys_fetch_independently(self, coordinator):
        """Different ticker keys should each trigger a fetch."""
        results = await asyncio.gather(
            coordinator.fetch("SPY", 4, _mock_fetcher),
            coordinator.fetch("QQQ", 4, _mock_fetcher),
        )
        assert results[0]["ticker"] == "SPY"
        assert results[1]["ticker"] == "QQQ"

    @pytest.mark.asyncio
    async def test_sequential_same_key_reuses_inflight(self, coordinator):
        """Second request after first completes should still work."""
        r1 = await coordinator.fetch("SPY", 4, _mock_fetcher)
        assert r1["spot"] == 500.0

        # After first completes, a new fetch is allowed
        r2 = await coordinator.fetch("SPY", 4, _mock_fetcher)
        assert r2["spot"] == 500.0


class TestFetchCoordinatorErrors:
    """Error handling."""

    @pytest.mark.asyncio
    async def test_fetch_error_returns_error_response(self, coordinator):
        async def failing_fetcher(t, e):
            raise ConnectionError("API down")

        result = await coordinator.fetch("SPY", 4, failing_fetcher)
        assert result["status"] == "error"
        assert result["spot"] is None
        assert result["contracts"] == []

    @pytest.mark.asyncio
    async def test_unreachable_budget_governor_fails_closed(self, coordinator, monkeypatch):
        """An error from the budget acquire must NOT fall through to fetching.

        `BudgetExhausted` was handled and returned a degraded response, but any
        OTHER exception -- a governor that is down, unreachable, or throwing --
        was logged and then execution continued into the fetch. So an outage in
        the thing that exists to cap spend removed the cap.
        """
        # `fetch` re-imports the budget inside the function body, so the patch
        # has to land on services.public_budget, not on the coordinator module.
        import services.public_budget as pb

        class UnreachableGovernor:
            async def acquire(self):
                raise RuntimeError("governor unreachable")

            def release(self):
                pass

        monkeypatch.setattr(pb, "budget", UnreachableGovernor())

        fetched = []

        async def fetcher(t, e):
            fetched.append(t)
            return {"status": "ok", "spot": 1.0, "contracts": []}

        result = await coordinator.fetch("SPY", 4, fetcher)
        await asyncio.sleep(0.05)

        assert not fetched, "external fetch ran with an unusable budget governor"
        assert result["status"] != "ok", result
        assert result.get("contracts") == [], result

    @pytest.mark.asyncio
    async def test_budget_unavailable_is_distinct_from_exhaustion(self, coordinator, monkeypatch):
        """'Could not ask' and 'the answer was no' must not collapse together."""
        import services.public_budget as pb
        from services.public_budget import BudgetExhausted

        class Unreachable:
            async def acquire(self):
                raise RuntimeError("down")

            def release(self):
                pass

        class Exhausted:
            async def acquire(self):
                # Signature is (retry_after, reason) -- a positional message
                # here would bind to retry_after and collide with the keyword.
                raise BudgetExhausted(retry_after=30, reason="spent")

            def release(self):
                pass

        async def fetcher(t, e):
            raise AssertionError("must not fetch in either degraded case")

        # Distinct keys: the coordinator coalesces in-flight work per key, so
        # reusing one key would just replay the first result.
        monkeypatch.setattr(pb, "budget", Unreachable())
        unavailable = await coordinator.fetch("SPY", 4, fetcher)

        monkeypatch.setattr(pb, "budget", Exhausted())
        exhausted = await coordinator.fetch("QQQ", 4, fetcher)

        assert unavailable["status"] != "ok", unavailable
        assert exhausted["status"] != "ok", exhausted
        # The distinction has to survive to the caller, or an outage is
        # indistinguishable from ordinary throttling.
        assert unavailable["error_type"] == "budget_unavailable", unavailable
        assert exhausted["error_type"] == "budget_exhausted", exhausted

    def test_coalesced_count_zero_initially(self, coordinator):
        assert coordinator.get_coalesced_count("SPY", 4) == 0
