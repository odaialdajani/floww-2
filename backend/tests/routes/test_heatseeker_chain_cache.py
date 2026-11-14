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
    fake_fetch = _fetch_with({"spot": 0, "contracts": []})
    fake_server = SimpleNamespace(fetch_spot_and_chains_merged=fake_fetch)

    with patch.dict("sys.modules", {"server": fake_server}):
        asyncio.run(heatseeker._fetch_chain("   ", 4))
        asyncio.run(heatseeker._fetch_chain("bad/ticker", 4))

    assert heatseeker._CHAIN_CACHE == {}
    assert fake_fetch.await_count == 2


def test_flip_zones_route_keeps_its_response_shape():
    heatseeker._CHAIN_CACHE.clear()
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
