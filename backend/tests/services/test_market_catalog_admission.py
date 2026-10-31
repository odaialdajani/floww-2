"""Catalogue admission must precede every cold auth/provider effect.

The stock directory is provider-backed. A refused admission must not initialize
the broker (which authenticates and reads accounts) or call the provider. The
last good directory is retained with an explicit stale flag; an empty receipt
is not a complete directory.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from services import market_catalog as catalog
from services import public_api_adapter as adapter
from services import public_budget as governor
from tests.offline_network import deny_external_network  # noqa: F401

INSTRUMENTS = [
    {
        "instrument": {"symbol": "SPY", "type": "EQUITY"},
        "optionTrading": "BUY_AND_SELL",
        "exchangeName": "NYSE",
        "sector": "Index",
    },
    {
        "instrument": {"symbol": "AMD", "type": "EQUITY"},
        "optionTrading": "BUY_AND_SELL",
        "exchangeName": "NASDAQ",
        "sector": "Technology",
    },
    {
        "instrument": {"symbol": "BOND", "type": "EQUITY"},
        "optionTrading": "LIQUIDATION_ONLY",
        "exchangeName": "NYSE",
        "sector": "Fixed Income",
    },
    {
        "instrument": {"symbol": "NOPT", "type": "EQUITY"},
        "optionTrading": "SELL_ONLY",
        "exchangeName": "NYSE",
        "sector": None,
    },
]

OLD = [
    {
        "symbol": "OLD",
        "options": True,
        "options_status": "BUY_AND_SELL",
        "exchange": "NYSE",
        "sector": "Index",
    },
]
OLD_ASOF = "2026-10-30T12:00:00+00:00"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, deny_external_network):
    budget = governor.PublicBudget(capacity=60, refill_per_sec=0, max_inflight=1)
    monkeypatch.setattr(governor, "budget", budget)
    monkeypatch.setattr(adapter, "BROKER", None)
    monkeypatch.setattr(catalog, "_cache", None)
    monkeypatch.setattr(catalog, "_loaded_at", 0.0)
    monkeypatch.setattr(catalog, "_retry_at", 0.0)
    monkeypatch.setattr(catalog, "_lock", asyncio.Lock())
    return budget


class RecordingBroker:
    def __init__(self, instruments=None, error=None):
        self.instruments = INSTRUMENTS if instruments is None else instruments
        self.error = error
        self.calls = []

    async def get_all_instruments(self, type_filter=None):
        self.calls.append(type_filter)
        if self.error is not None:
            raise self.error
        return list(self.instruments)


@pytest.mark.asyncio
async def test_cold_admission_refusal_precedes_broker_auth_and_provider(monkeypatch, isolated):
    budget = isolated
    await budget.acquire("api.public.com")  # occupy the only in-flight slot
    effects = []

    async def exploding_broker():
        effects.append("broker")
        raise AssertionError("cold broker auth must not run after admission refusal")

    monkeypatch.setattr(adapter, "_get_broker", exploding_broker)

    result = await catalog.get_catalog()

    assert effects == []
    assert result["instruments"] == []
    assert result["stale"] is True
    assert result["complete_provider_catalog"] is False
    assert result["complete_exchange_catalog"] is False
    assert result["total"] == 0
    assert result["optionable_total"] == 0
    assert budget._inflight == 1  # only the test's pre-held slot remains
    assert await budget.peek_available() == budget._capacity - 1


@pytest.mark.asyncio
async def test_cold_success_acquires_before_auth_and_releases_slot(monkeypatch, isolated):
    budget = isolated
    broker = RecordingBroker()
    observed = []

    async def get_broker():
        observed.append(("auth", budget._inflight))
        return broker

    monkeypatch.setattr(adapter, "_get_broker", get_broker)

    result = await catalog.get_catalog()

    assert observed == [("auth", 1)]
    assert broker.calls == [["EQUITY"]]
    assert result["instruments"] == catalog.parse_instruments(INSTRUMENTS)
    assert result["complete_provider_catalog"] is True
    assert result["complete_exchange_catalog"] is False
    assert result["stale"] is False
    assert result["total"] == 4
    assert result["optionable_total"] == 3
    assert budget._inflight == 0
    assert await budget.peek_available() == budget._capacity - 1


@pytest.mark.asyncio
async def test_cold_broker_unavailable_after_admission_releases_slot(monkeypatch, isolated):
    budget = isolated

    async def no_broker():
        return None

    monkeypatch.setattr(adapter, "_get_broker", no_broker)

    result = await catalog.get_catalog()

    assert result["instruments"] == []
    assert result["stale"] is True
    assert result["complete_provider_catalog"] is False
    assert budget._inflight == 0
    assert await budget.peek_available() == budget._capacity - 1


@pytest.mark.asyncio
async def test_provider_failure_retains_last_good_directory_and_cools_down(monkeypatch, isolated):
    budget = isolated
    monkeypatch.setattr(catalog, "_cache", {"instruments": list(OLD), "asof": OLD_ASOF})
    monkeypatch.setattr(catalog, "_loaded_at", time.monotonic() - catalog.TTL_SECONDS - 1)
    broker = RecordingBroker(error=RuntimeError("provider down"))
    observed = []

    async def get_broker():
        observed.append(("auth", budget._inflight))
        return broker

    monkeypatch.setattr(adapter, "_get_broker", get_broker)

    result = await catalog.get_catalog()

    assert observed == [("auth", 1)]
    assert broker.calls == [["EQUITY"]]
    assert result["instruments"] == OLD
    assert result["asof"] == OLD_ASOF
    assert result["stale"] is True
    assert result["complete_provider_catalog"] is True
    assert budget._inflight == 0
    assert await budget.peek_available() == budget._capacity - 1

    # Failure cooldown: an immediate second read must not start provider work.
    result2 = await catalog.get_catalog()
    assert observed == [("auth", 1)]
    assert broker.calls == [["EQUITY"]]
    assert result2["instruments"] == OLD
    assert result2["stale"] is True
    assert budget._inflight == 0
    assert await budget.peek_available() == budget._capacity - 1


@pytest.mark.asyncio
async def test_empty_provider_receipt_does_not_replace_good_directory(monkeypatch, isolated):
    monkeypatch.setattr(catalog, "_cache", {"instruments": list(OLD), "asof": OLD_ASOF})
    monkeypatch.setattr(catalog, "_loaded_at", time.monotonic() - catalog.TTL_SECONDS - 1)
    broker = RecordingBroker(instruments=[])

    async def get_broker():
        return broker

    monkeypatch.setattr(adapter, "_get_broker", get_broker)

    result = await catalog.get_catalog()

    assert broker.calls == [["EQUITY"]]
    assert result["instruments"] == OLD
    assert result["stale"] is True
    assert result["complete_provider_catalog"] is True
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_simultaneous_cold_consumers_share_one_admission_and_fetch(
    monkeypatch, isolated
):
    budget = isolated
    broker = RecordingBroker()
    auth_calls = []

    async def get_broker():
        auth_calls.append(budget._inflight)
        await asyncio.sleep(0.01)
        return broker

    monkeypatch.setattr(adapter, "_get_broker", get_broker)

    results = await asyncio.gather(*(catalog.get_catalog() for _ in range(6)))

    assert auth_calls == [1]
    assert broker.calls == [["EQUITY"]]
    assert all(result["instruments"] == results[0]["instruments"] for result in results)
    assert all(result["stale"] is False for result in results)
    assert budget._inflight == 0
    assert await budget.peek_available() == budget._capacity - 1


@pytest.mark.asyncio
async def test_cancelled_cold_broker_init_releases_admitted_slot(monkeypatch, isolated):
    budget = isolated
    entered = asyncio.Event()
    blocked = asyncio.Event()

    async def blocked_broker():
        entered.set()
        await blocked.wait()
        return RecordingBroker()

    monkeypatch.setattr(adapter, "_get_broker", blocked_broker)

    task = asyncio.create_task(catalog.get_catalog())
    await entered.wait()
    observed_inflight = budget._inflight
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert observed_inflight == 1
    assert budget._inflight == 0
    assert await budget.peek_available() == budget._capacity - 1
    assert catalog._cache is None


@pytest.mark.asyncio
async def test_warm_catalogue_serves_without_auth_or_provider_work(monkeypatch, isolated):
    budget = isolated
    monkeypatch.setattr(catalog, "_cache", {"instruments": list(OLD), "asof": OLD_ASOF})
    monkeypatch.setattr(catalog, "_loaded_at", time.monotonic())

    async def forbidden(*args, **kwargs):
        raise AssertionError("warm catalogue must not start provider work")

    monkeypatch.setattr(adapter, "_get_broker", forbidden)
    monkeypatch.setattr(catalog, "_fetch_instruments", forbidden)

    result = await catalog.get_catalog()

    assert result["instruments"] == OLD
    assert result["stale"] is False
    assert result["complete_provider_catalog"] is True
    assert budget._inflight == 0
    assert await budget.peek_available() == budget._capacity


@pytest.mark.asyncio
async def test_warm_broker_skips_auth_but_still_admits_one_slot(monkeypatch, isolated):
    budget = isolated
    broker = RecordingBroker()
    broker._token_expires_at = time.time() + 3600
    monkeypatch.setattr(adapter, "BROKER", broker)

    result = await catalog.get_catalog()

    assert result["instruments"] == catalog.parse_instruments(INSTRUMENTS)
    assert broker.calls == [["EQUITY"]]
    assert budget._inflight == 0
    assert await budget.peek_available() == budget._capacity - 1
