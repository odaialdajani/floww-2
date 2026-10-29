"""Offline GET status contract; no provider or account calls are made."""
from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

import alpaca_client
from routes.alpaca import get_status, router


class FakeClient:
    @property
    def enabled(self):
        return bool(os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "secret", "expected"),
    [("key", "secret", (True, True, True)), ("", "secret", (False, False, True)),
     ("key", "", (False, True, False)), ("", "", (False, False, False))],
)
async def test_status_reads_current_configuration_without_provider_calls(monkeypatch, key, secret, expected):
    monkeypatch.setattr(alpaca_client, "AlpacaClient", FakeClient)
    with patch.dict(os.environ, {"ALPACA_API_KEY": key, "ALPACA_SECRET_KEY": secret}, clear=True):
        status = await get_status()
    assert (status["configured"], status["api_key_set"], status["secret_key_set"]) == expected
    assert status["base_url"] == "https://paper-api.alpaca.markets"
    assert status["mode"] == "paper trading"
    assert set(status) == {"configured", "api_key_set", "secret_key_set", "base_url", "mode"}


@pytest.mark.asyncio
async def test_status_matches_actual_client_enabled_offline():
    with patch.dict(os.environ, {"ALPACA_API_KEY": "example", "ALPACA_SECRET_KEY": "example"}, clear=True):
        expected = alpaca_client.AlpacaClient().enabled
        status = await get_status()
    assert expected is True and status["configured"] is expected


@pytest.mark.asyncio
async def test_router_get_serializes_status_without_network(monkeypatch):
    monkeypatch.setattr(alpaca_client, "AlpacaClient", FakeClient)
    app = FastAPI()
    app.include_router(router)
    with patch.dict(os.environ, {}, clear=True):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/alpaca/status")
    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "api_key_set": False,
        "secret_key_set": False,
        "base_url": "https://paper-api.alpaca.markets",
        "mode": "paper trading",
    }


@pytest.mark.asyncio
async def test_unknown_error_is_safe_and_does_not_expose_exception(monkeypatch):
    class BrokenClient:
        def __init__(self):
            raise RuntimeError("synthetic-sensitive-value")

    monkeypatch.setattr(alpaca_client, "AlpacaClient", BrokenClient)
    with patch.dict(os.environ, {}, clear=True):
        status = await get_status()
    assert status["configured"] is False
    assert isinstance(status["error"], str) and status["error"]
    assert "synthetic-sensitive-value" not in repr(status)
    assert "api_key_set" not in status and "secret_key_set" not in status
