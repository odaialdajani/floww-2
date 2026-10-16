"""Brief read contention waits for admission, never replays an upstream call."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routes import price_history
from services import public_api_adapter as adapter
from services import public_budget as governor
from tests.offline_network import deny_external_network  # noqa: F401

BAR = {"t": "2026-10-06T14:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, deny_external_network):
    monkeypatch.setattr(price_history, "_bar_reads", {})
    monkeypatch.setattr(adapter, "_CHAIN_CACHE", {})
    monkeypatch.setattr(adapter, "_CHAIN_LOCKS", {})
    monkeypatch.setattr(adapter, "BROKER", None)


@pytest.mark.asyncio
async def test_history_recovers_brief_slot_contention_with_one_provider_read(monkeypatch):
    budget = governor.PublicBudget(capacity=10, refill_per_sec=0, max_inflight=1)
    monkeypatch.setattr(governor, "budget", budget)
    await budget.acquire("api.public.com")
    provider = AsyncMock(return_value=[BAR])
    monkeypatch.setattr(adapter, "fetch_bars_by_interval", provider)
    asyncio.get_running_loop().call_later(0.01, budget.release)
    results = await asyncio.wait_for(asyncio.gather(*(
        price_history._history_bars("SPY", "DAY", "ONE_MINUTE", "regular") for _ in range(6)
    )), 1)
    assert all(result[0] == [BAR] and result[1] is None for result in results)
    provider.assert_awaited_once()
    assert budget._inflight == 0
    assert await budget.peek_available() == 8  # original slot + one shared read
    assert not price_history._bar_reads


@pytest.mark.asyncio
async def test_chain_recovers_brief_slot_contention_without_reauth_or_extra_fanout(monkeypatch):
    budget = governor.PublicBudget(capacity=10, refill_per_sec=0, max_inflight=1)
    monkeypatch.setattr(governor, "budget", budget)
    await budget.acquire("api.public.com")
    broker = SimpleNamespace()
    monkeypatch.setattr(adapter, "BROKER", broker)
    initialize = AsyncMock(return_value=broker)
    provider = AsyncMock(return_value={"spot": 100, "contracts": [{"strike": 100}], "expiries": []})
    monkeypatch.setattr(adapter, "_get_broker", initialize)
    monkeypatch.setattr(adapter, "_fetch_chain_live", provider)
    asyncio.get_running_loop().call_later(0.01, budget.release)
    results = await asyncio.wait_for(asyncio.gather(*(
        adapter.fetch_chain_from_public_api("SPY", 1) for _ in range(6)
    )), 1)
    assert all(result and result["spot"] == 100 for result in results)
    provider.assert_awaited_once()
    initialize.assert_awaited_once()
    assert budget._inflight == 0
    assert await budget.peek_available() == 6  # original slot + one 2+N envelope


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["host_cooldown", "budget_exhausted", "missing_job_admission"])
async def test_nontransient_refusal_is_not_retried(reason):
    acquire = AsyncMock(side_effect=governor.BudgetExhausted(retry_after=7, reason=reason))
    with pytest.raises(governor.BudgetExhausted) as exc:
        await governor.wait_for_read_admission(acquire, wait_seconds=0.02)
    assert exc.value.reason == reason
    assert exc.value.retry_after == 7
    acquire.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["inflight_cap", "token_bucket"])
async def test_wait_is_bounded_and_preserves_actual_refusal(reason):
    acquire = AsyncMock(side_effect=governor.BudgetExhausted(retry_after=7, reason=reason))
    start = asyncio.get_running_loop().time()
    with pytest.raises(governor.BudgetExhausted) as exc:
        await governor.wait_for_read_admission(acquire, wait_seconds=0.02)
    assert exc.value.reason == reason
    assert exc.value.retry_after == 7
    assert acquire.await_count >= 2
    assert asyncio.get_running_loop().time() - start < 0.5


@pytest.mark.asyncio
async def test_cancelled_admission_wait_never_releases_another_job_slot(monkeypatch):
    budget = governor.PublicBudget(capacity=10, refill_per_sec=0, max_inflight=1)
    monkeypatch.setattr(governor, "budget", budget)
    await budget.acquire("api.public.com")
    provider = AsyncMock(return_value=[BAR])
    monkeypatch.setattr(adapter, "fetch_bars_by_interval", provider)
    waiter = asyncio.create_task(price_history._history_bars("SPY", "DAY", "ONE_MINUTE", "regular"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    job = next(iter(price_history._bar_reads.values()))
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    provider.assert_not_awaited()
    assert budget._inflight == 1
    assert await budget.peek_available() == 9
    budget.release()
    assert not price_history._bar_reads
