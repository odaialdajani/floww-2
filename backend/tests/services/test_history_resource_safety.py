"""Offline deadlines and cancellation ownership for shared history jobs."""
from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from routes import price_history as route
from services import public_api_adapter as adapter
from services import public_budget
from tests.offline_network import deny_external_network  # noqa: F401

BAR = {"t": "2026-10-06T14:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101, "v": 10}
DEADLINE = 0.04
WATCHDOG = 0.5
TIMEOUT_FAILURE = {"reason": "history_job_timeout", "retry_after_seconds": None}


@pytest.fixture(autouse=True)
async def isolated(monkeypatch, deny_external_network):
    """No app startup, real broker, persisted store or shared singleton state."""
    monkeypatch.setattr(route, "_bar_reads", {})
    # raising=False lets the old implementation run and fail on behavior in RED.
    monkeypatch.setattr(route, "_HISTORY_JOB_TIMEOUT_SECONDS", DEADLINE, raising=False)
    monkeypatch.setattr(adapter, "BROKER", None)
    monkeypatch.setattr(adapter, "_BROKER_LOCK", asyncio.Lock())
    monkeypatch.setattr(adapter, "PublicBroker", Mock(side_effect=AssertionError("Real broker forbidden")))
    monkeypatch.setenv("PUBLIC_API_KEY", "offline-test-only")
    budget = public_budget.PublicBudget(max_inflight=1)
    budget.release = Mock(wraps=budget.release)
    monkeypatch.setattr(public_budget, "budget", budget)
    monkeypatch.setitem(sys.modules, "services.duckdb_engine", SimpleNamespace(db=object()))
    monkeypatch.setattr(route, "recording_summary", lambda *a: {"status": "available", "durable": False})
    try:
        yield budget
    finally:
        jobs = list(route._bar_reads.values())
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        await asyncio.sleep(0)


async def history(ticker="SPY"):
    return await route._history_bars(ticker, "DAY", "ONE_MINUTE", "regular")


async def settle(task):
    """A watchdog fails broken code quickly without cancelling its shared job."""
    return await asyncio.wait_for(asyncio.shield(task), WATCHDOG)


@pytest.mark.asyncio
async def test_active_waiter_gets_explicit_timeout_then_distinct_key_is_admitted(isolated, monkeypatch):
    cancelled = asyncio.Event()

    async def bars(ticker, **kwargs):
        if ticker == "QQQ":
            return [BAR]
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(adapter, "fetch_bars_by_interval", bars)
    result = await asyncio.wait_for(route.price_history(
        "SPY", days=1, query_key=None, interval_minutes=None, include_metric_lines=False,
        contract_symbol=None, sessions="regular",
    ), WATCHDOG)
    assert result["price_status"] == "unavailable"
    assert result["price_failure"] == TIMEOUT_FAILURE
    assert result["prices_received_at"] is None
    assert result["frames"] == []
    assert cancelled.is_set()
    assert not route._bar_reads
    assert isolated._inflight == 0
    isolated.release.assert_called_once_with()
    assert (await history("QQQ"))[0] == [BAR]
    assert isolated.release.call_count == 2


@pytest.mark.asyncio
async def test_all_waiters_leave_but_job_still_times_out_releases_once_and_evicts(isolated, monkeypatch):
    entered = asyncio.Event()

    async def bars(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(adapter, "fetch_bars_by_interval", bars)
    first = asyncio.create_task(history())
    second = asyncio.create_task(history())
    await asyncio.wait_for(entered.wait(), WATCHDOG)
    job = next(iter(route._bar_reads.values()))
    for waiter in (first, second):
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
    assert not job.done()
    assert isolated._inflight == 1
    assert (await settle(job)) == ([], TIMEOUT_FAILURE, None)
    await asyncio.sleep(0)
    assert isolated._inflight == 0
    isolated.release.assert_called_once_with()
    assert not route._bar_reads
    monkeypatch.setattr(adapter, "fetch_bars_by_interval", AsyncMock(return_value=[BAR]))
    assert (await history("QQQ"))[0] == [BAR]


@pytest.mark.asyncio
async def test_total_deadline_includes_admission_wait_without_releasing_unowned_slot(isolated, monkeypatch):
    # PublicBudget waits on its lock before admitting: the job clock must start
    # before acquisition, not only around the final HTTP request.
    await isolated._guard.acquire()
    provider = AsyncMock(return_value=[BAR])
    monkeypatch.setattr(adapter, "fetch_bars_by_interval", provider)
    try:
        assert await asyncio.wait_for(history(), WATCHDOG) == ([], TIMEOUT_FAILURE, None)
        isolated.release.assert_not_called()
        provider.assert_not_awaited()
        assert isolated._inflight == 0
        assert not route._bar_reads
    finally:
        isolated._guard.release()


@pytest.mark.asyncio
async def test_cancelled_waiter_preserves_sibling_and_completed_values_are_not_cached(isolated, monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def bars(*args, **kwargs):
        entered.set()
        await finish.wait()
        return [BAR]

    provider = AsyncMock(side_effect=bars)
    monkeypatch.setattr(adapter, "fetch_bars_by_interval", provider)
    first = asyncio.create_task(history())
    second = asyncio.create_task(history())
    await asyncio.wait_for(entered.wait(), WATCHDOG)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert isolated._inflight == 1
    isolated.release.assert_not_called()
    finish.set()
    assert (await settle(second))[0] == [BAR]
    provider.assert_awaited_once()
    isolated.release.assert_called_once_with()
    assert not route._bar_reads
    assert (await history())[0] == [BAR]
    assert provider.await_count == 2
    assert isolated.release.call_count == 2


@pytest.mark.asyncio
async def test_explicit_shared_job_cancellation_releases_exactly_once(isolated, monkeypatch):
    entered = asyncio.Event()

    async def bars(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(adapter, "fetch_bars_by_interval", bars)
    waiter = asyncio.create_task(history())
    await asyncio.wait_for(entered.wait(), WATCHDOG)
    next(iter(route._bar_reads.values())).cancel()
    with pytest.raises(asyncio.CancelledError):
        await settle(waiter)
    assert isolated._inflight == 0
    isolated.release.assert_called_once_with()
    assert not route._bar_reads


def broker_stub():
    return SimpleNamespace(auth=AsyncMock(), get_accounts=AsyncMock(), close=AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["auth", "get_accounts"])
@pytest.mark.parametrize("close_fails", [False, True])
async def test_cold_init_cancellation_closes_discard_once_propagates_and_allows_retry(
    isolated, monkeypatch, stage, close_fails,
):
    entered = asyncio.Event()

    async def block():
        entered.set()
        await asyncio.Event().wait()

    discarded, recovered = broker_stub(), broker_stub()
    setattr(discarded, stage, AsyncMock(side_effect=block))
    if close_fails:
        discarded.close.side_effect = RuntimeError("offline close failure")
    factory = Mock(side_effect=[discarded, recovered])
    monkeypatch.setattr(adapter, "PublicBroker", factory)
    init = asyncio.create_task(adapter._get_broker())
    await asyncio.wait_for(entered.wait(), WATCHDOG)
    init.cancel()
    with pytest.raises(asyncio.CancelledError):
        await settle(init)
    discarded.close.assert_awaited_once()
    assert adapter.BROKER is None
    assert not adapter._BROKER_LOCK.locked()
    assert await adapter._get_broker() is recovered
    assert adapter.BROKER is recovered
    recovered.auth.assert_awaited_once()
    recovered.get_accounts.assert_awaited_once()
    recovered.close.assert_not_awaited()
    assert factory.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["auth", "get_accounts"])
async def test_history_deadline_cancels_cold_init_and_closes_before_slot_release(isolated, monkeypatch, stage):
    discarded = broker_stub()

    async def block():
        await asyncio.Event().wait()

    async def close():
        assert isolated._inflight == 1
        assert adapter._BROKER_LOCK.locked()

    setattr(discarded, stage, AsyncMock(side_effect=block))
    discarded.close.side_effect = close
    monkeypatch.setattr(adapter, "PublicBroker", Mock(return_value=discarded))
    # Exercise the real fetch_bars_by_interval -> _get_broker cold path; every
    # broker collaborator is a stub, including account initialization.
    assert await asyncio.wait_for(history(), WATCHDOG) == ([], TIMEOUT_FAILURE, None)
    discarded.close.assert_awaited_once()
    assert adapter.BROKER is None
    assert not adapter._BROKER_LOCK.locked()
    assert isolated._inflight == 0
    isolated.release.assert_called_once_with()
    assert not route._bar_reads


@pytest.mark.asyncio
async def test_history_deadline_includes_wait_for_another_broker_initializer(isolated, monkeypatch):
    await adapter._BROKER_LOCK.acquire()
    try:
        assert await asyncio.wait_for(history(), WATCHDOG) == ([], TIMEOUT_FAILURE, None)
        adapter.PublicBroker.assert_not_called()
        assert adapter.BROKER is None
        assert isolated._inflight == 0
        isolated.release.assert_called_once_with()
        assert not route._bar_reads
    finally:
        adapter._BROKER_LOCK.release()
