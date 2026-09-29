"""_reset_state() must clear the shared public_budget, not just the local cache.

`public_budget.budget` is a module-level singleton, so its state outlives any
individual test. `market_bars._reset_state()` cleared the bar cache, the
quarantine counter and the last-error field -- but not the budget.

When a cooldown from an earlier test was still active on api.public.com,
`_get` returned early at the budget check and never called the broker:

    RESULT bars: None
    RESULT awaited: 0

Any test asserting the upstream seam is exercised then failed with

    AssertionError: Expected mock to have been awaited once. Awaited 0 times.

It reproduced in CI full-suite order but passed in isolation, which is what
made it look order-random.

These tests drive the real seam through a mocked broker, so they exercise the
actual budget gate rather than asserting on the reset helper.
"""

import asyncio
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _broker(with_bar=True):
    bars = [
        {
            "timestamp": "2026-09-25T00:00:00-04:00",
            "open": 101.0, "high": 102.0, "low": 100.0,
            "close": 102.0, "volume": 11,
        },
    ] if with_bar else []
    return SimpleNamespace(
        get_trading_account=lambda: SimpleNamespace(account_id="fixture"),
        get_bars=AsyncMock(return_value={"regularMarket": {"bars": bars}}),
    )


async def _fetch_through_seam(broker):
    from services import market_bars

    market_bars._reset_state()
    with patch("services.public_api_adapter._get_broker",
               new=AsyncMock(return_value=broker)):
        return await market_bars.get_daily_bars("SPY", days=10)


@pytest.fixture(autouse=True)
def _clean_budget():
    from services.public_budget import budget

    budget.reset()
    yield
    budget.reset()


@pytest.mark.asyncio
async def test_cooldown_left_by_an_earlier_test_does_not_block_the_seam():
    """The exact CI failure: leftover cooldown, _reset_state called, still blocked."""
    from services.public_budget import budget

    budget.reset()
    budget._cooldowns["api.public.com"] = time.time() + 3600

    broker = _broker()
    bars = await _fetch_through_seam(broker)

    assert broker.get_bars.await_count == 1, (
        "a leftover cooldown made the seam unreachable; "
        f"awaited {broker.get_bars.await_count} times"
    )
    assert bars is not None and len(bars) == 1


@pytest.mark.asyncio
async def test_reset_clears_cooldowns():
    from services import market_bars
    from services.public_budget import budget

    budget._cooldowns["api.public.com"] = time.time() + 3600
    market_bars._reset_state()

    assert not budget._cooldowns, (
        f"_reset_state left cooldown state behind: {budget._cooldowns}"
    )


@pytest.mark.asyncio
async def test_reset_still_clears_the_bar_cache():
    """The original contract must not regress."""
    from services import market_bars
    from services.public_budget import budget

    await _fetch_through_seam(_broker())
    assert market_bars._CACHE, "precondition: cache populated"

    market_bars._reset_state()
    budget.reset()

    assert not market_bars._CACHE
    assert market_bars._QUARANTINE["total"] == 0
    assert market_bars.last_error()["reason"] is None
