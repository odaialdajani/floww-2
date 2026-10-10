"""E1 chain: every registered research shutdown callback must be bounded.

Failing-first regression for the second callback gap:
on_stop is bounded via _shutdown_join, but shutdown_research directly
awaits research.close(). With a hanging close, the full ASGI chain must
still exit within a bound and release isolated stores.
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def chain_shutdown(monkeypatch):
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


async def _hangs_forever():
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_full_registered_research_chain_bounded(chain_shutdown):
    server = chain_shutdown
    research = MagicMock()
    research.close = _hangs_forever
    server.app.state.research_service = research
    start = time.monotonic()
    # Full ASGI order: on_stop first, then later registered callback.
    await asyncio.wait_for(server.on_stop(), timeout=5)
    first_elapsed = time.monotonic() - start
    assert first_elapsed < 4, "on_stop hung"
    start2 = time.monotonic()
    # Before fix this raises TimeoutError (hangs); after fix returns <0.5s.
    await asyncio.wait_for(server.shutdown_research(), timeout=1.5)
    second_elapsed = time.monotonic() - start2
    assert second_elapsed < 1.4, (
        f"second registered callback hung: {second_elapsed:.2f}s"
    )
    server.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_research_service_close_idempotent_bounded():
    import contextlib

    from services.agent.research import ResearchService

    svc = ResearchService(repository=MagicMock(), reads=MagicMock(), model=None)

    release = asyncio.Event()

    async def _ignore_cancel_until_release():
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                if release.is_set():
                    raise
                continue

    stuck = asyncio.create_task(_ignore_cancel_until_release())
    await asyncio.sleep(0)
    svc.tasks["t1"] = stuck
    closer = asyncio.create_task(svc.close())
    try:
        start = time.monotonic()
        # wait-not-await: always returns after bound even if close ignores cancel.
        done, _ = await asyncio.wait({closer}, timeout=6.0)
        elapsed = time.monotonic() - start
        assert closer in done, f"ResearchService.close hung: {elapsed:.2f}s"
        assert elapsed < 6.0, f"ResearchService.close too slow: {elapsed:.2f}s"
        # Second close must be immediate idempotent, never hang.
        start2 = time.monotonic()
        closer2 = asyncio.create_task(svc.close())
        try:
            done2, _ = await asyncio.wait({closer2}, timeout=1.5)
            assert closer2 in done2, "second close hung"
            assert time.monotonic() - start2 < 1.5, "second close too slow"
        finally:
            if not closer2.done():
                closer2.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(closer2, return_exceptions=True)
    finally:
        # Always release the simulation so teardown never hangs,
        # even on RED (assert before release).
        release.set()
        # Wake the simulation; then the pending closer can finish gather.
        if not stuck.done():
            stuck.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait({stuck}, timeout=5)
        if not closer.done():
            closer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(closer, return_exceptions=True)
        assert stuck.done()
