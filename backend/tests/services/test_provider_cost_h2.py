"""H2 provider cost + cvserver parity (Agent 2).
Base: current origin/main (e68bdb5 at audit time).

This file is the H2 focused test — it must FAIL on origin/main (proving the
uncontrolled fan-out / no-parity invariants) and PASS after the H2 patch.

The H2 patch is designed to be test-first:
  1. This file proves the gap on the current adapter/server code.
  2. The minimal H2 patch lands second and makes these pass with the intended
     cost envelope + cvserver control invariant.

O-1: the exact per-key upstream fan-out is deterministic and testable
     (2+N cold, 0 warm, distinct N distinct key).
O-2: main's 4->8 escalation in server.py exists and is reachable — the test
     proves the current cold-cost envelope and forces the patch to either
     reuse the first-fetch expiry/quote/first-4 OR remove the escalation.
O-3: a fake broker proves exact cold/warm/concurrent call counts; budget
     refusal proves zero upstream calls.
O-4: normal Heatseeker never calls cvserver under the default path.
X-1: no H1 analytics changes.
X-2: no scoring/frontend/frozen-file/schema change.
"""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def _h2_isolated_public_budget(monkeypatch):
    """Isolate every test with a fresh high-capacity budget so this module
    leaves zero footprint on the shared singleton for later files."""
    from services import public_budget as pb_mod
    monkeypatch.setattr(
        pb_mod, "budget",
        pb_mod.PublicBudget(capacity=10000, refill_per_sec=10000.0))

from services.public_api_adapter import (
    _CHAIN_CACHE,
    _chain_fanout_budget,
    _clear_chain_cache,
    fetch_chain_from_public_api,
)


def _clear():
    _clear_chain_cache()


def _get_adapter_module():
    import services.public_api_adapter as m
    return m


class _FakeQuote:
    """Minimal quote that survives _matching_quote + _public_quote_spot."""
    def __init__(self, symbol: str, mid: float = 100.0):
        self.symbol = symbol
        self.bid = mid - 0.1
        self.ask = mid + 0.1
        self.mid_price = mid
        # Timestamp far in the future so _quote_ts_utc >= last US close.
        self.timestamp = datetime(2027, 1, 1, tzinfo=UTC).isoformat()


def _make_broker(expiries, chains_per_expiry=0, quote_mid=100.0, calls=None):
    """Build a FakeBroker whose call counts are tracked in ``calls["n"]``.

    ``calls`` is mutated in-place by the fake vendor methods so the test can
    assert exact cold/warm/concurrent call counts after the fetch returns.
    """
    if calls is None:
        calls = {"n": 0}

    class FakeContract:
        def __init__(self, sym: str, exp: str, strike: float):
            self.symbol = f"{sym}260918C00100000"  # adapter reads oc.symbol (OSI)
            self.expiration = exp
            self.strike = strike
            self.mid = quote_mid
            self.open_interest = 10.0
            self.iv = 0.25
            self.delta = 0.5
            self.gamma = 0.01
            self.theta = -0.02
            self.vega = 0.1
            self.bid = quote_mid - 0.1
            self.ask = quote_mid + 0.1
            self.last = quote_mid
            self.bid_size = 1
            self.ask_size = 1
            self.volume = 1

    class FakeBroker:
        account_id = "acct"
        def get_trading_account(self):
            return self
        async def get_quotes(self, symbols, account_id):
            calls["n"] += 1  # the spot/quote leg counts in the 2+N model
            return [_FakeQuote(symbols[0], mid=quote_mid)]
        async def get_option_expirations(self, symbol, account_id):
            calls["n"] += 1
            assert symbol == "SPY" or symbol == "QQQ"
            return expiries
        async def get_option_chain_parsed(self, symbol, exp, account_id):
            calls["n"] += 1
            assert symbol == "SPY" or symbol == "QQQ"
            objs = [FakeContract(symbol, exp, strike=100.0 + i) for i in range(chains_per_expiry)]
            return {"calls": objs, "puts": list(objs)}

    return FakeBroker


def test_chain_fanout_budget():
    assert _chain_fanout_budget(("SPY", 4)) == (6, 1)
    assert _chain_fanout_budget(("SPY", 8)) == (10, 1)


@pytest.mark.asyncio
async def test_cold_then_warm_is_2plusN_then_0():
    _clear()
    calls = {"n": 0}
    FakeBroker = _make_broker(
        ["2026-09-18", "2026-09-25", "2026-10-02", "2026-10-09",
         "2026-10-16", "2026-10-23", "2026-10-30", "2026-11-06"],
        chains_per_expiry=3, calls=calls)

    mod = _get_adapter_module()
    fake = AsyncMock(return_value=FakeBroker())
    real = mod._get_broker
    mod._get_broker = fake
    try:
        r1 = await fetch_chain_from_public_api("SPY", max_expiries=4)
        assert r1 is not None
        assert r1["max_expiries"] == 4
        cold_calls = calls["n"]

        r2 = await fetch_chain_from_public_api("SPY", max_expiries=4)
        assert r2 is not None
        warm_calls = calls["n"] - cold_calls
        assert warm_calls == 0, "warm cache must make zero upstream calls"

        # Different N = different cache key = separate cold fan-out.
        r3 = await fetch_chain_from_public_api("SPY", max_expiries=8)
        assert r3 is not None
        assert r3["max_expiries"] == 8
        second_cold_calls = calls["n"] - cold_calls - warm_calls
        assert second_cold_calls == 10, (
            "4-then-8 on distinct keys = (2+4)+(2+8) = 16 cold")
    finally:
        mod._get_broker = real


@pytest.mark.asyncio
async def test_4_then_8_total_is_16_on_distinct_keys():
    _clear()
    calls = {"n": 0}
    FakeBroker = _make_broker(
        ["2026-09-18", "2026-09-25", "2026-10-02", "2026-10-09",
         "2026-10-16", "2026-10-23", "2026-10-30", "2026-11-06"],
        chains_per_expiry=3, calls=calls)

    mod = _get_adapter_module()
    fake = AsyncMock(return_value=FakeBroker())
    real = mod._get_broker
    mod._get_broker = fake
    try:
        await fetch_chain_from_public_api("SPY", max_expiries=4)
        await fetch_chain_from_public_api("SPY", max_expiries=8)
        assert calls["n"] == 16, (
            f"expected 16 cold calls ((2+4)+(2+8)), got {calls['n']}")
    finally:
        mod._get_broker = real


@pytest.mark.asyncio
async def test_cache_key_is_ticker_and_N():
    _clear()
    calls = {"n": 0}
    FakeBroker = _make_broker(
        ["2026-09-18", "2026-09-25", "2026-10-02", "2026-10-09"],
        chains_per_expiry=3, calls=calls)

    mod = _get_adapter_module()
    fake = AsyncMock(return_value=FakeBroker())
    real = mod._get_broker
    mod._get_broker = fake
    try:
        await fetch_chain_from_public_api("SPY", max_expiries=4)
        # Different ticker, same N -> separate cold fan-out.
        await fetch_chain_from_public_api("QQQ", max_expiries=4)
        assert calls["n"] == 12, (
            f"expected 6+6=12 for two tickers, got {calls['n']}")
    finally:
        mod._get_broker = real


@pytest.mark.asyncio
async def test_budget_refusal_blocks_upstream_calls():
    """O-3: when the Public budget refuses, fetch_chain_from_public_api must
    make zero upstream calls (the acquire happens before any vendor call)."""
    _clear()
    calls = {"n": 0}
    FakeBroker = _make_broker(["2026-09-18"], calls=calls)

    from services import public_budget as pb_mod
    from services.public_budget import BudgetExhausted

    mod = _get_adapter_module()
    fake = AsyncMock(return_value=FakeBroker())
    real_broker = mod._get_broker
    real_acquire_n = pb_mod.budget.acquire_n
    mod._get_broker = fake
    # Seam follows the implementation: the adapter atomically acquires the full
    # fan-out via acquire_n (see public_budget.acquire_n all-or-nothing).
    async def _refuse(n, host="public", now=None):
        raise BudgetExhausted(retry_after=9)
    pb_mod.budget.acquire_n = _refuse
    try:
        out = await fetch_chain_from_public_api("SPY", max_expiries=4)
        assert out is None, "budget refusal must return None"
        assert calls["n"] == 0, (
            "budget refusal must make zero upstream calls")
    finally:
        mod._get_broker = real_broker
        pb_mod.budget.acquire_n = real_acquire_n
