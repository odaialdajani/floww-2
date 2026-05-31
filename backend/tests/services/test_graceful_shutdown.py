"""Tests for the comprehensive on_stop() shutdown handler."""
import asyncio
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_on_stop_cancels_tracked_background_tasks():
    """on_stop() must cancel every task in _background_tasks."""
    # Import inside the test so the module-level infra is fresh
    import server as server_mod
    from server import _background_tasks, on_stop

    # Spawn a never-ending task and register it
    async def _never_ends():
        await asyncio.sleep(3600)

    task = asyncio.create_task(_never_ends())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Replace client with a mock — Motor's close is a property with no setter
    original_client = server_mod.client
    mock_client = MagicMock()
    mock_client.close = MagicMock()
    server_mod.client = mock_client
    try:
        await on_stop()
    finally:
        server_mod.client = original_client

    assert task.cancelled() or task.done(), "background task was not cancelled"


@pytest.mark.asyncio
async def test_on_stop_sets_shutdown_event():
    """on_stop() must set the global _shutdown_event so loops can break out."""
    import server as server_mod
    from server import _shutdown_event, on_stop

    _shutdown_event.clear()
    original_client = server_mod.client
    mock_client = MagicMock()
    mock_client.close = MagicMock()
    server_mod.client = mock_client
    try:
        await on_stop()
    finally:
        server_mod.client = original_client

    assert _shutdown_event.is_set(), "_shutdown_event was not set"
