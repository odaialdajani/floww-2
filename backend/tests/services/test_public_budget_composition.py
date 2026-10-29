"""Public chain admission belongs to the actual adapter, once per cold read.

The real cache router/coordinator and complete adapter function bodies run with
an in-memory broker/provider. No server import, credentials or network startup.
"""
import ast
import asyncio
import contextlib
import logging
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from services import public_budget
from services.fetch_coordinator import CacheRouter, FetchCoordinator


@pytest.fixture
def composition(monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    governor = public_budget.PublicBudget(capacity=100, refill_per_sec=0, max_inflight=4)
    monkeypatch.setattr(public_budget, "budget", governor)
    env = dict(asyncio=asyncio, contextlib=contextlib, time=time,
        log=logging.getLogger(__name__), _public_budget=public_budget,
        BROKER=None, _CHAIN_CACHE={}, _CHAIN_LOCKS={}, _CHAIN_CACHE_TTL=60,
        _CHAIN_CACHE_MAX=128, _cached_copy=lambda data, stale: dict(data, stale=stale))
    source = ast.parse((BACKEND / "services/public_api_adapter.py").read_text())
    names = {"_chain_lock", "fetch_chain_from_public_api"}
    nodes = [node for node in source.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in names]
    module = ast.Module([ast.ImportFrom("__future__", [ast.alias("annotations")], 0), *nodes], [])
    exec(compile(ast.fix_missing_locations(module), str(BACKEND / "services/public_api_adapter.py"), "exec"), env)
    calls = []
    broker = object()

    async def get_broker():
        calls.append("broker")
        env["BROKER"] = broker
        return broker

    async def read_provider(pb, ticker, count):
        calls.append(ticker)
        await asyncio.sleep(0)
        return {"ticker": ticker, "spot": 100.0, "contracts": [{"strike": 100}]}

    env.update(_get_broker=get_broker, _fetch_chain_live=read_provider)
    server = ModuleType("server")
    server.fetch_spot_and_chains_merged = env["fetch_chain_from_public_api"]
    monkeypatch.setitem(sys.modules, "server", server)
    return CacheRouter(), FetchCoordinator(), env, governor, calls


@pytest.mark.asyncio
async def test_four_cold_keys_dispatch_once_each_without_nested_reservations(composition):
    router, coordinator, _, governor, calls = composition
    results = await asyncio.gather(*[
        router.get_chain(ticker, 4, 60, coordinator)
        for ticker in ("SPY", "QQQ", "IWM", "DIA")
    ])
    assert [result and result["ticker"] for result in results] == ["SPY", "QQQ", "IWM", "DIA"]
    assert sorted(call for call in calls if call != "broker") == ["DIA", "IWM", "QQQ", "SPY"]
    assert governor.status()["available"] == 76  # four envelopes, each 2 + 4
    assert governor.status()["inflight"] == 0


@pytest.mark.asyncio
async def test_warm_adapter_read_spends_nothing_even_after_router_entry_expires(composition):
    router, coordinator, _, governor, calls = composition
    first = await router.get_chain("SPY", 4, 60, coordinator)
    assert first["ticker"] == "SPY"
    before = governor.status()["available"]
    second = await router.get_chain("SPY", 4, 0, coordinator)
    assert second["ticker"] == "SPY"
    assert governor.status()["available"] == before
    assert calls == ["broker", "SPY"]


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", [False, True])
async def test_inner_refusal_prevents_broker_initialization(composition, monkeypatch, unavailable):
    router, coordinator, _, _, calls = composition

    class RefusingGovernor:
        async def acquire(self):
            return await self.acquire_n(1)

        async def acquire_n(self, *args):
            if unavailable:
                raise RuntimeError("governor unavailable")
            raise public_budget.BudgetExhausted()

        def release(self):
            raise AssertionError("unacquired slot released")

    monkeypatch.setattr(public_budget, "budget", RefusingGovernor())
    await router.get_chain("SPY", 4, 60, coordinator)
    assert calls == []


@pytest.mark.asyncio
async def test_cancelled_read_releases_adapter_slot(composition):
    router, coordinator, env, governor, _ = composition
    entered = asyncio.Event()

    async def slow_provider(*args):
        entered.set()
        await asyncio.Event().wait()

    env["_fetch_chain_live"] = slow_provider
    task = asyncio.create_task(router.get_chain("SPY", 4, 60, coordinator))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    assert governor.status()["inflight"] == 0
