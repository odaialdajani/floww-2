"""Every extra expiry attempt requires admission before the broker is called."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services import public_api_adapter as adapter
from services.public_budget import PublicBudget
from tests.services.test_public_adapter_truth import make_contract


@pytest.mark.asyncio
@pytest.mark.parametrize("capacity", [3, 4, 6])
async def test_failed_empty_and_live_expiry_calls_never_exceed_debits(monkeypatch, capacity):
    budget = PublicBudget(capacity=capacity, refill_per_sec=0, max_inflight=4)
    monkeypatch.setattr(adapter._public_budget, "budget", budget)
    monkeypatch.setattr(adapter, "BROKER", None)
    monkeypatch.setattr(adapter, "_CHAIN_CACHE", {})
    first = datetime.now(UTC).date() + timedelta(days=10)
    expiries = [(first + timedelta(days=i)).isoformat() for i in range(4)]
    calls = []
    broker = SimpleNamespace(get_trading_account=lambda: SimpleNamespace(account_id="fixture"))
    async def listing(*args, **kwargs):
        calls.append("listing")
        return expiries
    async def quotes(*args, **kwargs):
        calls.append("quote")
        return []
    async def chain(symbol, expiry, account_id, **kwargs):
        calls.append(expiry)
        if expiry == expiries[0]:
            raise RuntimeError("isolated failed expiry")
        return {"calls": [] if expiry != expiries[-1] else [make_contract(expiration=expiry)], "puts": []}
    broker.get_option_expirations = listing
    broker.get_quotes = quotes
    broker.get_option_chain_parsed = chain
    async def spot(pb, symbol, account_id, now=None):
        await pb.get_quotes([symbol], account_id)
        return dict(price=520.5, source="fixture", event_time=None, fetched_at=datetime.now(UTC).isoformat())
    monkeypatch.setattr(adapter, "_resolve_spot_observation", spot)
    monkeypatch.setattr(adapter, "_get_broker", AsyncMock(return_value=broker))
    before = await budget.peek_available()
    result = await adapter.fetch_chain_from_public_api("SPY", max_expiries=1)
    charged = before - await budget.peek_available()
    assert len(calls) <= charged
    assert len(calls) == capacity
    assert budget._inflight == 0
    if capacity == 6:
        assert result is not None
        assert result["expiries"] == [expiries[-1]]
        assert result["budget_extra_debit"] == 3
        assert result["budget_total_debit"] == 6
        assert result["expiries_attempted"] == expiries
    else:
        assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("extra_tokens", [0, 4])
async def test_four_admitted_chains_can_debit_extra_without_fifth_job_slot(monkeypatch, extra_tokens):
    import asyncio

    budget = PublicBudget(capacity=12 + extra_tokens, refill_per_sec=0, max_inflight=4)
    monkeypatch.setattr(adapter._public_budget, "budget", budget)
    monkeypatch.setattr(adapter, "_CHAIN_CACHE", {})
    broker = SimpleNamespace(get_trading_account=lambda: SimpleNamespace(account_id="fixture"))
    monkeypatch.setattr(adapter, "BROKER", broker)
    monkeypatch.setattr(adapter, "_get_broker", AsyncMock(return_value=broker))
    start = datetime.now(UTC).date() + timedelta(days=20)
    dates = [start.isoformat(), (start + timedelta(days=7)).isoformat()]
    entered, calls = set(), []
    all_entered, allow_extra = asyncio.Event(), asyncio.Event()
    async def listing(symbol, *args, **kwargs):
        calls.append((symbol, "listing"))
        return dates
    async def quotes(symbols, *args, **kwargs):
        calls.append((symbols[0], "quote"))
        return []
    async def chain(symbol, expiry, account_id, **kwargs):
        calls.append((symbol, expiry))
        if expiry == dates[0]:
            entered.add(symbol)
            if len(entered) == 4:
                all_entered.set()
            await allow_extra.wait()
            return {"calls": [], "puts": []}
        return {"calls": [make_contract(expiration=expiry)], "puts": []}
    async def spot(pb, symbol, account_id, now=None):
        await pb.get_quotes([symbol], account_id)
        return dict(price=520.5, source="fixture", event_time=None, fetched_at=datetime.now(UTC).isoformat())
    broker.get_option_expirations, broker.get_quotes, broker.get_option_chain_parsed = listing, quotes, chain
    monkeypatch.setattr(adapter, "_resolve_spot_observation", spot)
    tasks = [asyncio.create_task(adapter.fetch_chain_from_public_api(symbol, 1)) for symbol in ["SPY", "QQQ", "IWM", "DIA"]]
    try:
        await asyncio.wait_for(all_entered.wait(), 2)
        assert budget._inflight == 4
        assert await budget.peek_available() == extra_tokens
        allow_extra.set()
        results = await asyncio.gather(*tasks)
        assert all(result is not None for result in results) if extra_tokens else all(result is None for result in results)
        assert len(calls) == 12 + extra_tokens
        assert budget._inflight == 0
        assert await budget.peek_available() == 0
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["base_call", "extra_call"])
async def test_cancellation_retains_attempt_debit_and_releases_only_owner_slot(monkeypatch, stage):
    import asyncio

    budget = PublicBudget(capacity=10, refill_per_sec=0, max_inflight=1)
    monkeypatch.setattr(adapter._public_budget, "budget", budget)
    monkeypatch.setattr(adapter, "_CHAIN_CACHE", {})
    broker = SimpleNamespace(get_trading_account=lambda: SimpleNamespace(account_id="fixture"))
    monkeypatch.setattr(adapter, "BROKER", broker)
    monkeypatch.setattr(adapter, "_get_broker", AsyncMock(return_value=broker))
    start = datetime.now(UTC).date() + timedelta(days=20)
    dates = [start.isoformat(), (start + timedelta(days=7)).isoformat()]
    started, never = asyncio.Event(), asyncio.Event()
    calls = []
    async def listing(*args, **kwargs):
        calls.append("listing")
        return dates
    async def quotes(*args, **kwargs):
        calls.append("quote")
        return []
    async def chain(symbol, expiry, account_id, **kwargs):
        calls.append(expiry)
        if stage == "extra_call" and expiry == dates[0]:
            return {"calls": [], "puts": []}
        started.set()
        await never.wait()
    async def spot(pb, symbol, account_id, now=None):
        await pb.get_quotes([symbol], account_id)
        return dict(price=520.5, source="fixture", event_time=None, fetched_at=datetime.now(UTC).isoformat())
    broker.get_option_expirations, broker.get_quotes, broker.get_option_chain_parsed = listing, quotes, chain
    monkeypatch.setattr(adapter, "_resolve_spot_observation", spot)
    task = asyncio.create_task(adapter.fetch_chain_from_public_api("SPY", 1))
    try:
        await asyncio.wait_for(started.wait(), 2)
        expected = 4 if stage == "extra_call" else 3
        assert len(calls) == expected
        assert budget._inflight == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert budget._inflight == 0
        assert await budget.peek_available() == 10 - expected
        assert adapter._CHAIN_CACHE == {}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
