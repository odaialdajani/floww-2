"""Late storage readiness recovers local research without a server restart."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from routes.agent import router


def app_for(monkeypatch):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    app = FastAPI()
    app.include_router(router)
    app.state.research_service = None
    return app


@pytest.mark.asyncio
async def test_session_recovers_after_storage_becomes_available(monkeypatch):
    app = app_for(monkeypatch)
    repo = SimpleNamespace(session=AsyncMock(return_value=("owner", "capability")))
    async def initialize():
        app.state.research_service = SimpleNamespace(repository=repo)
    app.state.initialize_research = AsyncMock(side_effect=initialize)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1",
                                headers={"Origin": "http://127.0.0.1:3000"}) as client:
        response = await client.post("/api/agent/session")
        assert response.status_code == 200, response.text
        assert response.json() == {"status": "ready"}
        assert "floww_research=" in response.headers["set-cookie"]
        await client.post("/api/agent/session")
    app.state.initialize_research.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_sessions_initialize_only_once(monkeypatch):
    app = app_for(monkeypatch)
    repo = SimpleNamespace(session=AsyncMock(return_value=("owner", "capability")))
    async def initialize():
        await asyncio.sleep(0.01)
        app.state.research_service = SimpleNamespace(repository=repo)
    app.state.initialize_research = AsyncMock(side_effect=initialize)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1",
                                headers={"Origin": "http://127.0.0.1:3000"}) as client:
        responses = await asyncio.gather(*(client.post("/api/agent/session") for _ in range(4)))
    assert [response.status_code for response in responses] == [200] * 4
    app.state.initialize_research.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_start_can_retry_and_untrusted_origin_cannot_start_it(monkeypatch):
    app = app_for(monkeypatch)
    repo = SimpleNamespace(session=AsyncMock(return_value=("owner", "capability")))
    async def initialize():
        if app.state.initialize_research.await_count > 1:
            app.state.research_service = SimpleNamespace(repository=repo)
    app.state.initialize_research = AsyncMock(side_effect=initialize)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        blocked = await client.post("/api/agent/session", headers={"Origin": "http://untrusted.example"})
        assert blocked.status_code == 403
        app.state.initialize_research.assert_not_awaited()
        failed = await client.post("/api/agent/session", headers={"Origin": "http://127.0.0.1:3000"})
        assert failed.status_code == 503
        recovered = await client.post("/api/agent/session", headers={"Origin": "http://127.0.0.1:3000"})
        assert recovered.status_code == 200, recovered.text


@pytest.mark.asyncio
async def test_preferences_first_read_can_recover(monkeypatch):
    app = app_for(monkeypatch)
    repo = SimpleNamespace(owner=AsyncMock(return_value="owner"),
                           get_preferences=AsyncMock(return_value={"watchlist_extra": ["SPY"]}))
    async def initialize():
        app.state.research_service = SimpleNamespace(repository=repo)
    app.state.initialize_research = AsyncMock(side_effect=initialize)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1",
                                headers={"Cookie": "floww_research=test"}) as client:
        response = await client.get("/api/agent/prefs")
    assert response.status_code == 200, response.text
    assert response.json() == {"watchlist_extra": ["SPY"]}
    app.state.initialize_research.assert_awaited_once()
    repo.get_preferences.assert_awaited_once_with("owner")
