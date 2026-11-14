"""Bounded-cache behavior for Heatseeker's short-lived option chains."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.heatseeker as heatseeker


def _fetch_with(raw):
    return AsyncMock(return_value=raw)


def test_expired_entry_is_removed_and_refetched(monkeypatch):
    heatseeker._CHAIN_CACHE.clear()
    heatseeker._CHAIN_FETCH_GENERATIONS.clear()
    monkeypatch.setattr(heatseeker, "_CHAIN_CACHE_TTL", 30)
    heatseeker._CHAIN_CACHE["SPY:4"] = (100.0, {"spot": 1})
    raw = {"spot": 500.0, "contracts": []}
    fake_server = SimpleNamespace(fetch_spot_and_chains_merged=_fetch_with(raw))

    with patch.dict("sys.modules", {"server": fake_server}), patch(
        "routes.heatseeker.time.time", return_value=131.0, create=True
    ):
        result = asyncio.run(heatseeker._fetch_chain("SPY", 4))

    assert result == raw
    assert fake_server.fetch_spot_and_chains_merged.await_count == 1
    assert heatseeker._CHAIN_CACHE["SPY:4"][1] == raw


def test_cache_is_bounded_and_hot_entries_survive_lru_eviction(monkeypatch):
    heatseeker._CHAIN_CACHE.clear()
    heatseeker._CHAIN_FETCH_GENERATIONS.clear()
    monkeypatch.setattr(heatseeker, "_CHAIN_CACHE_MAX", 2, raising=False)
    now = 10_000.0
    heatseeker._CHAIN_CACHE.update(
        {
            "A:4": (now, {"spot": 1}),
            "B:4": (now, {"spot": 2}),
        }
    )
    raw_a = {"spot": 1}
    unused_fetch = _fetch_with({"spot": 3})
    fake_server = SimpleNamespace(fetch_spot_and_chains_merged=unused_fetch)

    with patch.dict("sys.modules", {"server": fake_server}), patch(
        "routes.heatseeker.time.time", return_value=now + 1, create=True
    ):
        hot = asyncio.run(heatseeker._fetch_chain("A", 4))
        inserted = asyncio.run(heatseeker._fetch_chain("C", 4))

    assert hot == raw_a
    assert inserted == {"spot": 3}
    assert list(heatseeker._CHAIN_CACHE) == ["A:4", "C:4"]
    assert len(heatseeker._CHAIN_CACHE) <= 2
    assert unused_fetch.await_count == 1


def test_empty_or_malformed_ticker_is_not_cached():
    heatseeker._CHAIN_CACHE.clear()
    heatseeker._CHAIN_FETCH_GENERATIONS.clear()
    fake_fetch = _fetch_with({"spot": 0, "contracts": []})
    fake_server = SimpleNamespace(fetch_spot_and_chains_merged=fake_fetch)

    with patch.dict("sys.modules", {"server": fake_server}):
        asyncio.run(heatseeker._fetch_chain("   ", 4))
        asyncio.run(heatseeker._fetch_chain("bad/ticker", 4))

    assert heatseeker._CHAIN_CACHE == {}
    assert fake_fetch.await_count == 2


def test_flip_zones_route_keeps_its_response_shape():
    heatseeker._CHAIN_CACHE.clear()
    heatseeker._CHAIN_FETCH_GENERATIONS.clear()
    raw = {
        "spot": 500.0,
        "contracts": [
            {
                "strike": 500.0,
                "type": "call",
                "T": 0.1,
                "oi": 10,
                "gamma": 0.04,
                "iv": 0.2,
            }
        ],
    }

    async def fetch_chain(ticker, expiries):
        return raw

    fake_server = SimpleNamespace(
        fetch_spot_and_chains_merged=fetch_chain,
        _sanitize=lambda payload: payload,
    )
    app = FastAPI()
    app.include_router(heatseeker.router)

    with patch.dict("sys.modules", {"server": fake_server}):
        response = TestClient(app).get("/api/heatseeker/flip-zones?ticker=SPY")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "SPY"
    assert body["spot"] == 500.0
    assert isinstance(body["flip_zones"], list)
    assert body["count"] == len(body["flip_zones"])


def test_ttl_starts_after_slow_fetch_and_enrichment(monkeypatch):
    heatseeker._CHAIN_CACHE.clear()
    heatseeker._CHAIN_FETCH_GENERATIONS.clear()
    clock = [100.0]
    fetch_calls = [0]
    raw = {"spot": 500.0, "contracts": []}

    async def fetch(*_args):
        fetch_calls[0] += 1
        return await _advance_and_return(clock, raw)

    def enrich(payload):
        clock[0] += 5.0
        return payload

    monkeypatch.setattr(heatseeker, "_ensure_gamma", enrich)
    fake_server = SimpleNamespace(fetch_spot_and_chains_merged=fetch)

    with patch.dict("sys.modules", {"server": fake_server}), patch(
        "routes.heatseeker.time.time", side_effect=lambda: clock[0]
    ):
        result = asyncio.run(heatseeker._fetch_chain("SPY", 4))
        assert result is raw
        assert heatseeker._CHAIN_CACHE["SPY:4"][0] == 150.0

        clock[0] = 179.0
        assert asyncio.run(heatseeker._fetch_chain("SPY", 4)) is raw
        assert fetch_calls[0] == 1

        clock[0] = 181.0
        asyncio.run(heatseeker._fetch_chain("SPY", 4))
        assert fetch_calls[0] == 2


async def _advance_and_return(clock, raw):
    clock[0] += 45.0
    return raw


def test_older_inflight_fetch_cannot_overwrite_newer_cache_result():
    heatseeker._CHAIN_CACHE.clear()
    heatseeker._CHAIN_FETCH_GENERATIONS.clear()
    call_count = 0
    older_raw = {"spot": 111.0, "contracts": []}
    newer_raw = {"spot": 222.0, "contracts": []}

    async def fetch_chain(*_args):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await release_older.wait()
            return older_raw
        return newer_raw

    async def run_overlapping_fetches():
        nonlocal release_older
        release_older = asyncio.Event()
        older_started = asyncio.Event()

        async def mark_older_started(*args):
            older_started.set()
            return await fetch_chain(*args)

        fake_server.fetch_spot_and_chains_merged = mark_older_started
        older_task = asyncio.create_task(heatseeker._fetch_chain("SPY", 4))
        await asyncio.wait_for(older_started.wait(), timeout=1)
        newer_result = await asyncio.wait_for(heatseeker._fetch_chain("SPY", 4), timeout=1)
        release_older.set()
        older_result = await asyncio.wait_for(older_task, timeout=1)
        return older_result, newer_result

    release_older = None
    fake_server = SimpleNamespace(fetch_spot_and_chains_merged=fetch_chain)
    with patch.dict("sys.modules", {"server": fake_server}):
        older_result, newer_result = asyncio.run(run_overlapping_fetches())

    assert older_result is older_raw
    assert newer_result is newer_raw
    assert heatseeker._CHAIN_CACHE["SPY:4"][1] is newer_raw
    assert heatseeker._CHAIN_FETCH_GENERATIONS == {}
