"""Commit acknowledgement and physical-write-safe shutdown; capture stays OFF."""

import asyncio
import time
from threading import Event
from unittest.mock import AsyncMock, Mock

import duckdb
import pytest

import server
from services import heatmap_history
from services.snapshot_writes import SnapshotWrites
from tests.services.test_snapshot_write_admission import recording_hook


@pytest.mark.asyncio
async def test_requested_acknowledgement_waits_for_the_physical_write(monkeypatch):
    release = Event()
    started = Event()

    def store(conn, payload, query_key, snapshot_id=None):
        started.set()
        assert release.wait(5)
        return snapshot_id

    async def complete():
        assert await asyncio.to_thread(started.wait, 2)
        release.set()

    monkeypatch.setattr(heatmap_history, "record_snapshot", store)
    with duckdb.connect(":memory:") as conn:
        record, tasks = recording_hook(monkeypatch, conn, await_recording=True)
        completion = asyncio.create_task(complete())
        try:
            reply = await record({"snapshotId": "snap_capture"})
            assert reply["recording_receipt"]["status"] == "committed"
            await completion
        finally:
            release.set()
            await completion
            await asyncio.gather(*list(tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_ack_timeout_reports_unconfirmed_not_failed_or_committed(monkeypatch):
    release = Event()

    def store(conn, payload, query_key, snapshot_id=None):
        assert release.wait(5)
        return snapshot_id

    monkeypatch.setattr(heatmap_history, "record_snapshot", store)
    with duckdb.connect(":memory:") as conn:
        record, tasks = recording_hook(monkeypatch, conn, await_recording=True)
        try:
            reply = await record({"snapshotId": "snap_slow"})
            receipt = reply["recording_receipt"]
            assert receipt["status"] == "queued"
            assert receipt.get("reason") == "acknowledgement_timeout"
            from services.snapshot_writes import snapshot_writes
            assert snapshot_writes.status()["pending"] == 1
        finally:
            release.set()
            await asyncio.gather(*list(tasks), return_exceptions=True)
            from services.snapshot_writes import snapshot_writes
            await snapshot_writes.drain()


@pytest.mark.asyncio
@pytest.mark.parametrize("await_recording", [False, True])
async def test_only_requested_capture_bypasses_the_display_cache(monkeypatch, await_recording):
    from fastapi import HTTPException

    from services.solstice_scope import cache_key, request_query

    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    query = request_query(4, "day", None, False, False, 200, "loaded", None)
    cached = {"spot": 100, "strikes": [{"strike": 100}], "data_source": "public_api", "snapshotId": "snap_cached"}
    monkeypatch.setattr(server, "_BUILD_HEATMAP_CACHE", {
        cache_key("SPY", query): {"ts": time.time(), "data": cached, "provider_policy": "public"}})
    fetch = AsyncMock(side_effect=HTTPException(418, "synthetic fresh-source boundary"))
    monkeypatch.setattr(server, "fetch_spot_and_chains_merged", fetch)
    if await_recording:
        with pytest.raises(HTTPException) as exc:
            await server._build_heatmap_impl("SPY", with_taps=False, await_recording=True)
        assert exc.value.status_code == 418
        fetch.assert_awaited_once()
    else:
        assert await server._build_heatmap_impl("SPY", with_taps=False) == cached
        fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_background_capture_requests_commit_acknowledgement(monkeypatch):
    build = AsyncMock(return_value={"recording_receipt": {"status": "committed"}})
    monkeypatch.setattr(server, "_build_heatmap_impl", build)
    monkeypatch.setattr(server, "_solstice_capture_running", False)

    async def finish_one_tick(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(server.asyncio, "sleep", finish_one_tick)
    with pytest.raises(asyncio.CancelledError):
        await server._solstice_capture_loop(["SPY"], 60, False)
    assert build.await_count == 1
    assert build.await_args.kwargs.get("await_recording") is True
    assert server._solstice_capture_running is False


@pytest.mark.asyncio
async def test_shutdown_refuses_to_close_storage_behind_a_cancelled_waiter(monkeypatch):
    import services.snapshot_writes as writes_module

    writer = SnapshotWrites(max_pending=1)
    release = Event()
    started = Event()

    def store(*args):
        started.set()
        assert release.wait(5)
        return "snap_busy"

    monkeypatch.setattr(heatmap_history, "record_snapshot", store)
    monkeypatch.setattr(writes_module, "snapshot_writes", writer)
    monkeypatch.setattr(server, "_background_tasks", set())
    monkeypatch.setattr(server, "_scheduler_task", None)
    monkeypatch.setattr(server, "_BACKGROUND_SHUTDOWN_TIMEOUT_S", 0.02)
    monkeypatch.setattr(server, "_shutdown_event", asyncio.Event())
    monkeypatch.setattr(server.app.state, "research_service", None, raising=False)
    close = Mock()
    monkeypatch.setattr(server, "client", Mock(close=close))
    try:
        job = writer.submit(object(), {}, "query", "snap_busy")
        assert await asyncio.to_thread(started.wait, 2)
        waiter = asyncio.create_task(job.wait())
        server._background_tasks.add(waiter)
        waiter.add_done_callback(server._background_tasks.discard)
        with pytest.raises(RuntimeError, match="Snapshot writes did not stop"):
            await server.on_stop()
        assert waiter.cancelled()
        close.assert_not_called()
        assert writer.status()["pending"] == 1
    finally:
        release.set()
        await writer.drain()
        writer.shutdown()
