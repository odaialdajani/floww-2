"""Run the production cache functions offline, without importing app startup."""

import ast
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


@pytest.fixture
def cache_functions(monkeypatch):
    import socket

    def refuse_network(*args, **kwargs):
        raise AssertionError("network forbidden in cache regression")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    names = {"build_heatmap", "_revalidate_heatmap", "_public_heatmap_cache_allowed"}
    tree = ast.parse((BACKEND / "server.py").read_text())
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in names]
    env = {"asyncio": asyncio, "datetime": datetime, "os": os, "time": time,
           "HTTPException": HTTPException, "log": logging.getLogger(__name__),
           "_shutdown_event": asyncio.Event(), "_BUILD_HEATMAP_CACHE": {},
           "_BUILD_HEATMAP_INFLIGHT": set(), "_BUILD_HEATMAP_PENDING": {}, "_background_tasks": set(),
           "_BUILD_HEATMAP_CACHE_TTL": 60, "_BUILD_HEATMAP_STALE_TTL": 900}
    module = ast.Module([ast.ImportFrom("__future__", [ast.alias("annotations")], 0), *functions], [])
    exec(compile(ast.fix_missing_locations(module), str(BACKEND / "server.py"), "exec"), env)
    return env


@pytest.mark.asyncio
async def test_concurrent_stale_readers_return_without_duplicate_build(cache_functions):
    env = cache_functions
    key = "SPY:4:day:None:False:True:200"
    original = {"ticker": "SPY", "spot": 100.0, "strikes": [{"strike": 100}],
                "stale_age_s": 7, "spot_event_time": None}
    env["_BUILD_HEATMAP_CACHE"][key] = {"ts": time.time() - 120, "data": original}
    entered, release = asyncio.Event(), asyncio.Event()
    builds = []

    async def slow_build(*args, **kwargs):
        builds.append(args)
        entered.set()
        await release.wait()
        return {"ticker": "SPY", "spot": 101.0, "strikes": [{"strike": 101}]}

    env["_build_heatmap_impl"] = slow_build
    first = await env["build_heatmap"]("SPY")
    await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(env["build_heatmap"]("SPY"))
    try:
        # Give a second request one event-loop turn; cached reads must not
        # wait for the deliberately blocked provider operation.
        await asyncio.sleep(0)
        assert second.done(), "a stale reader waited for a redundant provider build"
        answer = await second
        assert len(builds) == 1
        assert first["spot"] == answer["spot"] == 100.0
        assert first["stale"] is answer["stale"] is True
        assert answer["data_fallback"] is True
        assert answer["stale_age_s"] >= 127
        assert answer["spot_event_time"] is None
        assert "stale" not in original
    finally:
        release.set()
        await asyncio.gather(second, *list(env["_background_tasks"]), return_exceptions=True)
    assert key not in env["_BUILD_HEATMAP_INFLIGHT"]
    assert env["_BUILD_HEATMAP_CACHE"][key]["data"]["spot"] == 101.0


@pytest.mark.asyncio
async def test_failed_refresh_clears_owner_and_keeps_original_observation(cache_functions):
    env = cache_functions
    key = "SPY:4:day:None:False:True:200"
    original = {"ticker": "SPY", "spot": 100.0, "strikes": [{"strike": 100}]}
    env["_BUILD_HEATMAP_CACHE"][key] = {"ts": time.time() - 120, "data": original}

    async def failing_build(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    env["_build_heatmap_impl"] = failing_build
    await env["build_heatmap"]("SPY")
    outcomes = await asyncio.gather(*list(env["_background_tasks"]), return_exceptions=True)
    assert len(outcomes) == 1 and isinstance(outcomes[0], RuntimeError)
    assert key not in env["_BUILD_HEATMAP_INFLIGHT"]
    assert env["_BUILD_HEATMAP_CACHE"][key]["data"] == original


@pytest.mark.asyncio
async def test_public_policy_rejects_legacy_stale_cache(cache_functions, monkeypatch):
    env = cache_functions
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    key = "SPY:4:day:None:False:True:200"
    env["_BUILD_HEATMAP_CACHE"][key] = {"ts": time.time() - 120,
        "data": {"ticker": "SPY", "spot": 100.0, "strikes": [{"strike": 100}]}}

    async def public_build(*args, **kwargs):
        return {"ticker": "SPY", "spot": 101.0, "data_source": "public_api"}

    env["_build_heatmap_impl"] = public_build
    answer = await env["build_heatmap"]("SPY")
    assert answer["spot"] == 101.0
    assert answer["data_source"] == "public_api"
    assert not env["_background_tasks"]


@pytest.mark.asyncio
async def test_cold_readers_share_build_and_one_waiter_can_cancel(cache_functions):
    env = cache_functions
    entered, release = asyncio.Event(), asyncio.Event()
    builds = []

    async def slow_build(*args, **kwargs):
        builds.append(args)
        entered.set()
        await release.wait()
        return {"ticker": "SPY", "spot": 101.0}

    env["_build_heatmap_impl"] = slow_build
    first = asyncio.create_task(env["build_heatmap"]("SPY"))
    await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(env["build_heatmap"]("SPY"))
    try:
        await asyncio.sleep(0)
        assert len(builds) == 1, "same-scope cold readers duplicated the map build"
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not second.done()
        release.set()
        assert (await second)["spot"] == 101.0
        await asyncio.sleep(0)
        assert not env["_BUILD_HEATMAP_PENDING"]
        assert not env["_background_tasks"]
    finally:
        release.set()
        await asyncio.gather(first, second, *list(env["_background_tasks"]), return_exceptions=True)


@pytest.mark.asyncio
async def test_cold_builds_keep_different_scopes_separate_and_tracked(cache_functions):
    env = cache_functions
    release = asyncio.Event()
    entered = []

    async def slow_build(ticker, expiries, *args, **kwargs):
        entered.append(expiries)
        await release.wait()
        return {"ticker": ticker, "expiries_used": expiries}

    env["_build_heatmap_impl"] = slow_build
    reads = [asyncio.create_task(env["build_heatmap"]("SPY", max_expiries=count)) for count in (1, 4)]
    try:
        # Start the readers, then their owned builds.
        for _ in range(3):
            await asyncio.sleep(0)
        assert sorted(entered) == [1, 4]
        assert len(env["_background_tasks"]) == 2
        assert len(env["_BUILD_HEATMAP_PENDING"]) == 2
        # Model the existing shutdown owner, which cancels tracked work.
        for task in list(env["_background_tasks"]):
            task.cancel()
        results = await asyncio.gather(*reads, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        await asyncio.sleep(0)
        assert not env["_BUILD_HEATMAP_PENDING"]
        assert not env["_background_tasks"]
    finally:
        release.set()
        await asyncio.gather(*reads, *list(env["_background_tasks"]), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_cache_expiring_during_refresh_joins_existing_build(cache_functions, fails):
    env = cache_functions
    key = "SPY:4:day:None:False:True:200"
    env["_BUILD_HEATMAP_CACHE"][key] = {"ts": time.time() - 899,
        "data": {"ticker": "SPY", "spot": 100.0, "strikes": [{"strike": 100}]}}
    entered, release = asyncio.Event(), asyncio.Event()
    builds = []

    async def slow_build(*args, **kwargs):
        builds.append(args)
        entered.set()
        await release.wait()
        if fails:
            raise HTTPException(status_code=503, detail="provider admission unavailable")
        return {"ticker": "SPY", "spot": 101.0, "strikes": [{"strike": 101}]}

    env["_build_heatmap_impl"] = slow_build
    assert (await env["build_heatmap"]("SPY"))["spot"] == 100.0
    await asyncio.wait_for(entered.wait(), 1)
    env["_BUILD_HEATMAP_CACHE"][key]["ts"] -= 2
    second = asyncio.create_task(env["build_heatmap"]("SPY"))
    try:
        for _ in range(3):
            await asyncio.sleep(0)
        assert len(builds) == 1
        assert not second.done(), "expired cache must not be served while waiting"
        release.set()
        if fails:
            with pytest.raises(HTTPException) as rejected:
                await second
            assert rejected.value.status_code == 503
            assert env["_BUILD_HEATMAP_CACHE"][key]["data"]["spot"] == 100.0
        else:
            assert (await second)["spot"] == 101.0
        assert not env["_BUILD_HEATMAP_PENDING"]
    finally:
        release.set()
        await asyncio.gather(second, *list(env["_background_tasks"]), return_exceptions=True)
