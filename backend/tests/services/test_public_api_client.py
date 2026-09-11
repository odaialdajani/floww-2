from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _h2_isolated_public_budget(monkeypatch):
    """H2: adapter-level acquire debits the shared singleton even behind fake
    brokers. Isolate every test with a fresh high-capacity budget so file
    order can never starve a suite. Production behavior unchanged."""
    from services import public_budget as pb_mod
    monkeypatch.setattr(
        pb_mod, "budget",
        pb_mod.PublicBudget(capacity=10000, refill_per_sec=10000.0))

import services.public_api_adapter as adapter
from services.public_api import PublicBroker


@pytest.mark.asyncio
async def test_auth_mints_token_and_reuses_it_until_expiry() -> None:
    client = MagicMock()
    response = MagicMock()
    response.json.return_value = {"accessToken": "token-1"}
    client.post = AsyncMock(return_value=response)
    broker = PublicBroker("secret", client=client)

    with patch("services.public_api.time.time", side_effect=lambda: 1000.0):
        await broker._ensure_token()
        await broker._ensure_token()

    client.post.assert_awaited_once()
    assert broker._access_token == "token-1"


@pytest.mark.asyncio
async def test_expired_token_is_refreshed() -> None:
    client = MagicMock()
    first = MagicMock()
    first.json.return_value = {"accessToken": "token-1"}
    second = MagicMock()
    second.json.return_value = {"accessToken": "token-2"}
    client.post = AsyncMock(side_effect=[first, second])
    broker = PublicBroker("secret", token_validity_min=1, client=client)

    clock = MagicMock(side_effect=lambda: 1000.0)
    with patch("services.public_api.time.time", new=clock):
        await broker._ensure_token()
        broker._token_expires_at = 999.0
        await broker._ensure_token()

    assert client.post.await_count == 2
    assert broker._access_token == "token-2"


@pytest.mark.asyncio
async def test_close_closes_owned_client() -> None:
    client = MagicMock(is_closed=False)
    client.aclose = AsyncMock()
    broker = PublicBroker("secret", client=client)

    await broker.close()

    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_does_not_close_already_closed_client() -> None:
    client = MagicMock(is_closed=True)
    client.aclose = AsyncMock()
    broker = PublicBroker("secret", client=client)

    await broker.close()

    client.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_broker_closes_and_clears_singleton() -> None:
    client = MagicMock(is_closed=False)
    client.aclose = AsyncMock()
    broker = PublicBroker("secret", client=client)
    adapter.BROKER = broker

    await adapter.close_broker()

    assert adapter.BROKER is None
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_get_broker_creates_one_singleton() -> None:
    broker = MagicMock()
    broker.auth = AsyncMock()
    broker.get_accounts = AsyncMock()
    broker.close = AsyncMock()

    with patch.dict("os.environ", {"PUBLIC_API_KEY": "secret"}, clear=True), patch(
        "services.public_api_adapter.PublicBroker", return_value=broker
    ):
        adapter.BROKER = None
        results = await asyncio.gather(
            adapter._get_broker(), adapter._get_broker(), adapter._get_broker()
        )

    assert results == [broker, broker, broker]
    broker.auth.assert_awaited_once()
    broker.get_accounts.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_initialization_closes_client_and_allows_retry() -> None:
    failed = MagicMock()
    failed.auth = AsyncMock(side_effect=RuntimeError("auth failed"))
    failed.get_accounts = AsyncMock()
    failed.close = AsyncMock()

    recovered = MagicMock()
    recovered.auth = AsyncMock()
    recovered.get_accounts = AsyncMock()

    with patch.dict("os.environ", {"PUBLIC_API_KEY": "secret"}, clear=True), patch(
        "services.public_api_adapter.PublicBroker",
        side_effect=[failed, recovered],
    ):
        adapter.BROKER = None
        assert await adapter._get_broker() is None
        assert adapter.BROKER is None
        failed.close.assert_awaited_once()
        assert await adapter._get_broker() is recovered

    recovered.auth.assert_awaited_once()
    recovered.get_accounts.assert_awaited_once()
