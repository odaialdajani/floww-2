"""Actual server shutdown ownership and refusal checks with isolated boundaries."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def isolated_server(monkeypatch):
    import server
    from services import public_api_adapter

    monkeypatch.setattr(server, "_background_tasks", set())
    monkeypatch.setattr(server, "_shutdown_event", asyncio.Event())
    monkeypatch.setattr(server, "_scheduler_task", None)
    monkeypatch.setattr(server, "_BUILD_HEATMAP_CACHE", {})
    monkeypatch.setattr(server, "_BUILD_HEATMAP_INFLIGHT", set())
    monkeypatch.setattr(server, "_BACKGROUND_SHUTDOWN_TIMEOUT_S", .03, raising=False)
    monkeypatch.setattr(server, "client", MagicMock())
    monkeypatch.setattr(server.app.state, "research_service", None, raising=False)
    monkeypatch.setattr(public_api_adapter, "close_broker", AsyncMock())
    return server


def stale_cache(server):
    key = "SPY:4:day:None:False:True:200"
    server._BUILD_HEATMAP_CACHE[key] = {
        "ts": time.time() - 120,
        "data": {"ticker": "SPY", "spot": 123.45, "strikes": [{"strike": 123}]},
    }
    return key


@pytest.mark.asyncio
async def test_actual_stale_refresh_stops_before_shared_storage_closes(isolated_server, monkeypatch):
    server = isolated_server
    key = stale_cache(server)
    entered = asyncio.Event()
    events = []
    refresh_tasks = []

    async def slow_build(*args):
        refresh_tasks.append(asyncio.current_task())
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            events.append("refresh_stopped")

    monkeypatch.setattr(server, "_build_heatmap_impl", slow_build)
    server.client.close.side_effect = lambda: events.append("storage_closed")
    try:
        answer = await server.build_heatmap("SPY")
        assert answer["spot"] == 123.45
        await asyncio.wait_for(entered.wait(), 1)
        await server.on_stop()
        assert events == ["refresh_stopped", "storage_closed"]
        assert key not in server._BUILD_HEATMAP_INFLIGHT
        assert not [task for task in server._background_tasks if not task.done()]
    finally:
        for task in refresh_tasks:
            task.cancel()
        await asyncio.gather(*refresh_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_shutdown_refuses_new_heatmap_work(isolated_server, monkeypatch):
    from fastapi import HTTPException

    server = isolated_server
    stale_cache(server)
    build = AsyncMock(return_value={"spot": 123.45})
    monkeypatch.setattr(server, "_build_heatmap_impl", build)
    server._shutdown_event.set()
    with pytest.raises(HTTPException) as caught:
        await server.build_heatmap("SPY")
    assert caught.value.status_code == 503
    await asyncio.sleep(0)
    build.assert_not_awaited()
    assert not server._BUILD_HEATMAP_INFLIGHT


@pytest.mark.asyncio
async def test_unfinished_background_work_cannot_close_storage_or_claim_success(isolated_server):
    server = isolated_server
    entered = asyncio.Event()
    release = asyncio.Event()
    research = MagicMock()
    research.close = AsyncMock()
    server.app.state.research_service = research

    async def slow_cancel():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()

    task = asyncio.create_task(slow_cancel())
    server._background_tasks.add(task)
    task.add_done_callback(server._background_tasks.discard)
    await entered.wait()
    try:
        with pytest.raises(RuntimeError, match="Background work did not stop"):
            await server.on_stop()
        server.client.close.assert_not_called()
        research.close.assert_awaited_once()
    finally:
        release.set()
        await task
    await server.on_stop()
    server.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_tracks_children_created_during_cancellation(isolated_server):
    server = isolated_server
    entered = asyncio.Event()
    children = []
    events = []

    async def child():
        try:
            await asyncio.Event().wait()
        finally:
            events.append("child_stopped")

    async def parent():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            task = asyncio.create_task(child())
            children.append(task)
            server._background_tasks.add(task)
            task.add_done_callback(server._background_tasks.discard)
            await asyncio.sleep(0)

    parent_task = asyncio.create_task(parent())
    server._background_tasks.add(parent_task)
    parent_task.add_done_callback(server._background_tasks.discard)
    server.client.close.side_effect = lambda: events.append("storage_closed")
    await entered.wait()
    try:
        await server.on_stop()
        assert events == ["child_stopped", "storage_closed"]
        assert all(task.done() for task in children)
    finally:
        for task in children:
            task.cancel()
        await asyncio.gather(*children, return_exceptions=True)
