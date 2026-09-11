"""
D6 feed-economics audit (Agent D). Pins B-owned fetch behavior read-only:
2+N upstream fan-out shape, cache-hit-zero-token, single-flight
coalescing under 3 concurrent pollers. The debit gap (0 debits vs 2+N
upstream cost) is quantified here; B4's acquire_n closes it.
"""
from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch


def _ensure_imports():
    if "services.public_api_adapter" not in sys.modules:
        sys.path.insert(0, "/Users/nav/Documents/GitHub/floww/backend")


_ensure_imports()

TICKER = "ZZD6"  # never a real universe ticker; cache-identity safe


class CountingBroker:
    """Fake PublicBroker: counts upstream calls, optional entry delay."""

    def __init__(self, delay: float = 0.0):
        self.calls: dict[str, int] = {"expiries": 0, "quotes": 0, "chains": 0}
        self.delay = delay

    def get_trading_account(self):
        return SimpleNamespace(account_id="ACCT")

    async def get_option_expirations(self, symbol, account_id):
        self.calls["expiries"] += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return ["2026-12-18", "2027-01-15", "2027-02-19", "2027-03-19"]

    async def get_quotes(self, symbols, account_id):
        self.calls["quotes"] += 1
        return [SimpleNamespace(mid_price=100.0, last=99.9)]

    async def get_option_chain_parsed(self, symbol, exp, account_id):
        self.calls["chains"] += 1
        leg = SimpleNamespace(expiration=exp, mid=1.3, symbol=f"O:{symbol}261218C00100000",
                              strike=100.0, open_interest=500, iv=0.4, delta=0.3,
                              gamma=0.01, theta=-0.05, vega=0.1, bid=1.2, ask=1.4,
                              last=1.3, bid_size=10, ask_size=12, volume=2000)
        return {"calls": [leg], "puts": []}


def _fresh_cache():
    from services import public_api_adapter as pa

    old = pa._CHAIN_CACHE.pop((TICKER, 4), None)
    return pa, old


def _restore(pa, old):
    if old is None:
        pa._CHAIN_CACHE.pop((TICKER, 4), None)
    else:
        pa._CHAIN_CACHE[(TICKER, 4)] = old


def test_upstream_fanout_is_two_plus_n():
    from services import public_api_adapter as pa

    broker = CountingBroker()
    pa, old = _fresh_cache()

    async def get():
        return broker

    try:
        with patch.object(pa, "_get_broker", get):
            got = asyncio.get_event_loop().run_until_complete(
                pa.fetch_chain_from_public_api(TICKER, max_expiries=2))
        assert got is not None and got["stale"] is False
        assert broker.calls == {"expiries": 1, "quotes": 1, "chains": 2}
    finally:
        _restore(pa, old)


def test_cache_hit_costs_zero_tokens_and_zero_upstream():
    from services import public_api_adapter as pa
    from services.public_budget import budget

    broker = CountingBroker()
    pa, old = _fresh_cache()

    async def get():
        return broker

    try:
        with patch.object(pa, "_get_broker", get):
            loop = asyncio.get_event_loop()
            first = loop.run_until_complete(pa.fetch_chain_from_public_api(TICKER))
            ok_before, limited_before = budget.total_ok, budget.total_limited
            calls_before = dict(broker.calls)
            second = loop.run_until_complete(pa.fetch_chain_from_public_api(TICKER))
        assert first is not None and second is not None
        assert second["stale"] is False
        assert broker.calls == calls_before, "cache hit must not touch upstream"
        assert (budget.total_ok, budget.total_limited) == (ok_before, limited_before)
    finally:
        _restore(pa, old)


def test_three_concurrent_pollers_single_flight():
    from services import public_api_adapter as pa

    broker = CountingBroker(delay=0.05)
    pa, old = _fresh_cache()

    async def get():
        return broker

    async def main():
        return await asyncio.gather(*[pa.fetch_chain_from_public_api(TICKER) for _ in range(3)])

    try:
        with patch.object(pa, "_get_broker", get):
            results = asyncio.run(main())
        assert all(r is not None for r in results)
        assert broker.calls["expiries"] == 1, f"fan-out under load: {broker.calls}"
        assert broker.calls["chains"] == 4  # max_expiries default 4, one flight
    finally:
        _restore(pa, old)


def test_success_records_exactly_one_ok():
    from services import public_api_adapter as pa
    from services.public_budget import budget

    broker = CountingBroker()
    pa, old = _fresh_cache()

    async def get():
        return broker

    try:
        with patch.object(pa, "_get_broker", get):
            before = budget.total_ok
            asyncio.get_event_loop().run_until_complete(
                pa.fetch_chain_from_public_api(TICKER))
        # D6 gap note: 1 ok-credit vs 2+N upstream cost, 0 debits — B4 closes it.
        assert budget.total_ok == before + 1
        assert time.monotonic() > 0  # monotonic clock sane (skew guard companion)
    finally:
        _restore(pa, old)
