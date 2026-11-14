"""CVServer per-key state remains bounded and locks are request-scoped."""
from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def cvserver(monkeypatch):
    import services.cvserver_client as module

    monkeypatch.setattr(module, "_cache", OrderedDict())
    monkeypatch.setattr(module, "_locks", {})
    monkeypatch.setattr(module, "_fails", OrderedDict())
    monkeypatch.setattr(module, "_req_log", [])
    monkeypatch.setattr(module, "_rl_until", 0.0)
    return module


@pytest.mark.asyncio
async def test_hourly_cap_does_not_retain_completed_key_locks(cvserver, monkeypatch):
    monkeypatch.setattr(cvserver, "HOURLY_CAP", 0)

    async def fetch():
        raise AssertionError("hourly-cap refusal must happen before the fetch")

    for index in range(100):
        assert await cvserver._cached_call(f"symbol-{index}", 60, fetch) is None

    assert cvserver._locks == {}


@pytest.mark.asyncio
async def test_success_cache_has_a_fixed_capacity(cvserver, monkeypatch):
    monkeypatch.setattr(cvserver, "HOURLY_CAP", 200)
    async def fetch():
        return {"value": "ok"}

    for index in range(80):
        await cvserver._cached_call(f"symbol-{index}", 60, fetch)

    assert len(cvserver._cache) <= 64
    assert "symbol-79" in cvserver._cache


@pytest.mark.asyncio
async def test_failure_backoff_history_has_a_fixed_capacity(cvserver, monkeypatch):
    monkeypatch.setattr(cvserver, "HOURLY_CAP", 200)

    async def fail():
        raise RuntimeError("synthetic upstream failure")

    for index in range(80):
        assert await cvserver._cached_call(f"symbol-{index}", 60, fail) is None

    assert len(cvserver._fails) <= 64


@pytest.mark.asyncio
async def test_same_key_waiters_still_share_fetch_and_cleanup_lock(cvserver, monkeypatch):
    import asyncio

    monkeypatch.setattr(cvserver, "HOURLY_CAP", 10)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"value": "ok"}

    owner = asyncio.create_task(cvserver._cached_call("SPY:4", 60, fetch))
    await asyncio.wait_for(started.wait(), timeout=2)
    waiter = asyncio.create_task(cvserver._cached_call("SPY:4", 60, fetch))
    await asyncio.sleep(0)
    release.set()

    results = await asyncio.gather(owner, waiter)
    assert results == [{"value": "ok"}, {"value": "ok"}]
    assert calls == 1
    assert cvserver._locks == {}
    assert cvserver._lock_users == {}
