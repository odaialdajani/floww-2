"""GRACEFUL-SHUTDOWN follow-up: every shutdown join must be bounded.

The retired preview survived SIGTERM/SIGINT while holding journal.duckdb.
The tracked-task path already has a 5s bound, but three joins in on_stop()
had none: the scheduler-task join, research.close(), and close_broker().
A step stuck in uninterruptible work stalled shutdown forever with storage
open and no error surfaced. These tests pin bounded return (not hangs) plus
deterministic journal-lock release on an isolated store.
"""

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def isolated_shutdown(monkeypatch):
    import server
    from services import public_api_adapter

    monkeypatch.setattr(server, "_background_tasks", set())
    monkeypatch.setattr(server, "_shutdown_event", asyncio.Event())
    monkeypatch.setattr(server, "_scheduler_task", None)
    monkeypatch.setattr(server, "_BACKGROUND_SHUTDOWN_TIMEOUT_S", 0.2, raising=False)
    monkeypatch.setattr(server, "client", MagicMock())
    monkeypatch.setattr(server.app.state, "research_service", None, raising=False)
    monkeypatch.setattr(public_api_adapter, "close_broker", AsyncMock())
    return server


async def _ignores_cancellation(release):
    """Simulates a step stuck in uninterruptible work: swallows cancel.

    `release` lets the test end the task afterwards: a leaked
    cancel-ignoring task would hang the test runner's own loop teardown
    (runners cancel-and-await pending tasks), so every such task must be
    releasable. Production tasks have no such release — that is the point.
    """
    while True:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            if release.is_set():
                raise
            continue


async def _hangs_forever():
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_scheduler_join_bounded_when_scheduler_ignores_cancel(isolated_shutdown):
    server = isolated_shutdown
    release = asyncio.Event()
    stuck = asyncio.create_task(_ignores_cancellation(release))
    # Production tracks the scheduler task: mirror that registration.
    server._background_tasks.add(stuck)
    stuck.add_done_callback(server._background_tasks.discard)
    server._scheduler_task = stuck
    # Let the task suspend inside its shielded work first: cancelling a
    # never-started task kills it before its handler exists, which would
    # make this test vacuous.
    await asyncio.sleep(0)
    assert not stuck.done()
    start = time.monotonic()
    # A stuck scheduler must surface the existing unfinished-work error
    # quickly — never stall shutdown with storage open and silent.
    with pytest.raises(RuntimeError, match="Background work did not stop"):
        await asyncio.wait_for(server.on_stop(), timeout=10)
    assert time.monotonic() - start < 5, "on_stop hung on an uncancellable scheduler join"
    # Release the simulation so the runner's loop teardown is not hung by
    # our own stuck task; production tasks have no such release.
    release.set()
    stuck.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(stuck, timeout=5)
    assert stuck.done()


@pytest.mark.asyncio
async def test_research_close_bounded_when_close_hangs(isolated_shutdown):
    server = isolated_shutdown
    research = MagicMock()
    research.close = _hangs_forever
    server.app.state.research_service = research
    start = time.monotonic()
    await asyncio.wait_for(server.on_stop(), timeout=10)
    assert time.monotonic() - start < 5, "on_stop hung in research.close()"
    server.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_broker_close_bounded_when_broker_hangs(isolated_shutdown, monkeypatch):
    server = isolated_shutdown
    from services import public_api_adapter

    async def _stuck_close():
        await asyncio.Event().wait()

    monkeypatch.setattr(public_api_adapter, "close_broker", _stuck_close)
    start = time.monotonic()
    await asyncio.wait_for(server.on_stop(), timeout=10)
    assert time.monotonic() - start < 5, "on_stop hung in close_broker()"
    server.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_journal_engine_closed_releases_file_lock(isolated_shutdown, tmp_path, monkeypatch):
    server = isolated_shutdown
    from services import journal_store
    from services.duckdb_engine import DuckDBEngine

    db_path = tmp_path / "journal.duckdb"
    engine = DuckDBEngine(str(db_path))
    engine.conn.execute("CREATE TABLE t (a INTEGER)")
    engine.conn.execute("INSERT INTO t VALUES (1)")
    monkeypatch.setattr(journal_store, "_engine", engine)
    await asyncio.wait_for(server.on_stop(), timeout=10)
    assert journal_store._engine is None, "journal singleton still referenced after shutdown"
    db_path.unlink()  # raises while the file is still locked
    assert not db_path.exists()
