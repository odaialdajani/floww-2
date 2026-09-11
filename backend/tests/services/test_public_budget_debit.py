"""D1 regression: adapter chain fetch debits the Public budget fan-out.

C8: chain fan-out debited per ticker via acquire_n(2+N). Cold fetch must
spend exactly 2+max_expiries tokens and one inflight slot (released on
settle); warm cache spends zero; refusal makes zero upstream calls.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.public_api_adapter as adapter
from services.public_budget import PublicBudget


def make_broker():
    broker = MagicMock()
    trading = MagicMock()
    trading.account_id = "acc-123"
    broker.get_trading_account.return_value = trading
    broker.get_option_expirations = AsyncMock(
        return_value=["2026-09-18", "2026-10-16"]
    )
    quote = MagicMock()
    quote.mid_price = 520.50
    quote.last = 520.50
    quote.symbol = "SPY"
    broker.get_quotes = AsyncMock(return_value=[quote])
    call = MagicMock()
    call.symbol = "SPY260918C00530000"
    call.option_type = "CALL"
    call.strike = 530.0
    call.expiration = "2026-09-18"
    call.iv = 0.15
    call.delta = 0.45
    call.open_interest = 1000
    put = MagicMock()
    put.symbol = "SPY260918P00510000"
    put.option_type = "PUT"
    put.strike = 510.0
    put.expiration = "2026-09-18"
    put.iv = 0.14
    put.delta = -0.40
    put.open_interest = 3000
    broker.get_option_chain_parsed = AsyncMock(
        return_value={"calls": [call], "puts": [put]}
    )
    return broker


@pytest.fixture
def budget():
    return PublicBudget(capacity=60, refill_per_sec=0.0, max_inflight=4)


@pytest.fixture
def cold_adapter(budget):
    adapter._CHAIN_CACHE.clear()
    broker = make_broker()
    patches = [
        patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker)),
        patch("services.public_budget.budget", budget),
    ]
    for p in patches:
        p.start()
    yield broker
    for p in patches:
        p.stop()
    adapter._CHAIN_CACHE.clear()


@pytest.mark.asyncio
async def test_cold_fetch_debits_fan_out(cold_adapter, budget):
    before = await budget.peek_available()
    result = await adapter.fetch_chain_from_public_api("SPY", max_expiries=2)
    assert result is not None
    after = await budget.peek_available()
    assert before - after == pytest.approx(2 + 2)
    assert budget._inflight == 0


@pytest.mark.asyncio
async def test_warm_fetch_spends_zero(cold_adapter, budget):
    first = await adapter.fetch_chain_from_public_api("SPY", max_expiries=2)
    assert first is not None
    before = await budget.peek_available()
    calls_before = cold_adapter.get_option_expirations.await_count
    second = await adapter.fetch_chain_from_public_api("SPY", max_expiries=2)
    assert second is not None
    after = await budget.peek_available()
    assert after == pytest.approx(before)
    assert cold_adapter.get_option_expirations.await_count == calls_before


@pytest.mark.asyncio
async def test_refusal_makes_zero_upstream_calls(cold_adapter):
    from services.public_budget import BudgetExhausted

    async def refuse(*a, **k):
        raise BudgetExhausted(reason="test")

    with patch("services.public_budget.budget") as mock_budget:
        mock_budget.acquire_n = AsyncMock(side_effect=refuse)
        result = await adapter.fetch_chain_from_public_api("SPY", max_expiries=2)
    assert result is None
    assert cold_adapter.get_option_expirations.await_count == 0
    assert cold_adapter.get_quotes.await_count == 0


@pytest.mark.asyncio
async def test_concurrent_same_key_single_fan_out(cold_adapter, budget):
    before = await budget.peek_available()
    results = await asyncio.gather(
        *(adapter.fetch_chain_from_public_api("SPY", max_expiries=2) for _ in range(4))
    )
    assert all(r is not None for r in results)
    assert cold_adapter.get_option_expirations.await_count == 1
    after = await budget.peek_available()
    assert before - after == pytest.approx(2 + 2)
