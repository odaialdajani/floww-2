"""Test that DuckDBEngine.stop() awaits the flush loop task."""
import asyncio

import pytest


@pytest.mark.asyncio
async def test_stop_cancels_and_awaits_flush_loop():
    """After stop(), the flush_loop task must be done (not still running)."""
    from services.duckdb_engine import DuckDBEngine

    engine = DuckDBEngine()
    await engine.start()
    task = engine._flush_task

    assert task is not None, "_flush_task should be stored on start"
    assert not task.done(), "_flush_task should be running after start"

    await engine.stop()

    assert task.done(), "_flush_task should be done after stop"


@pytest.mark.asyncio
async def test_stop_is_idempotent():
    """Calling stop() twice should not raise."""
    from services.duckdb_engine import DuckDBEngine

    engine = DuckDBEngine()
    await engine.start()
    await engine.stop()
    await engine.stop()  # no exception
