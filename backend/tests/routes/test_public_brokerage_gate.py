from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from routes import public_brokerage


@pytest.mark.asyncio
@pytest.mark.parametrize("setting", [None, "", "0", "true", "yes", "2"])
async def test_live_submission_refuses_before_any_broker_access(monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv("FLOWW_ENABLE_LIVE_PUBLIC", raising=False)
    else:
        monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", setting)
    broker_read = AsyncMock(side_effect=AssertionError("Broker must not be accessed"))
    monkeypatch.setattr(public_brokerage, "_get_broker", broker_read)
    with pytest.raises(HTTPException) as error:
        await public_brokerage.place_order({"symbol": "SPY", "quantity": 1})
    assert error.value.status_code == 403
    broker_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_mounted_actions_require_key_and_entry_off_preserves_authorized_cancel(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "fixture-key")
    monkeypatch.delenv("FLOWW_ENABLE_LIVE_PUBLIC", raising=False)
    broker = SimpleNamespace(
        get_trading_account=lambda: SimpleNamespace(account_id="fixture-account"),
        cancel_order=AsyncMock(return_value={"status": "PENDING_CANCEL"}),
    )
    read = AsyncMock(return_value=broker)
    monkeypatch.setattr(public_brokerage, "_get_broker", read)
    app = FastAPI()
    app.include_router(public_brokerage.router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        for path in ("/api/public/order", "/api/public/order/fixture-id/cancel"):
            for headers in ({}, {"X-API-Key": "wrong"}):
                assert (await client.post(path, json={}, headers=headers)).status_code == 401
        read.assert_not_awaited()
        headers = {"X-API-Key": "fixture-key"}
        assert (await client.post("/api/public/order", json={}, headers=headers)).status_code == 403
        read.assert_not_awaited()
        response = await client.post("/api/public/order/fixture-id/cancel", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "PENDING_CANCEL"
        broker.cancel_order.assert_awaited_once_with("fixture-account", "fixture-id")
