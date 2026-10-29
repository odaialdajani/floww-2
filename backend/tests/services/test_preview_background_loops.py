"""The preview can omit automatic collectors without omitting startup storage."""
from __future__ import annotations

import ast
import asyncio
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


def startup_namespace():
    """Execute the real callback, without importing server's provider singletons."""
    source = Path(__file__).resolve().parents[2] / "server.py"
    tree = ast.parse(source.read_text())
    callback = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_start")
    callback.decorator_list = []
    cache = SimpleNamespace(ensure_index=AsyncMock())
    loops = {name: AsyncMock() for name in (
        "_scheduler_loop", "_warm_default_heatmaps", "_vpin_autofeed_loop", "_public_sweep_loop",
    )}

    async def logged_task(coroutine, _label):
        await coroutine

    namespace = {
        "asyncio": asyncio, "os": os, "log": logging.getLogger(__name__),
        "db": SimpleNamespace(snapshots=SimpleNamespace(create_index=AsyncMock())),
        "init_cache": Mock(return_value=cache),
        "_load_policy_from_mongo": AsyncMock(), "_init_alert_collection": AsyncMock(),
        "_load_rules_from_mongo": AsyncMock(), "_scheduler_started": False,
        "_scheduler_task": None, "_background_tasks": set(),
        "_logged_task": logged_task, "PREFETCH_HHMM": "08:55", **loops,
    }
    exec(compile(ast.Module(body=[callback], type_ignores=[]), str(source), "exec"), namespace)
    return namespace, cache, loops


@pytest.mark.asyncio
@pytest.mark.parametrize("setting,enabled", [(None, True), ("1", True), ("unexpected", True), ("0", False)])
async def test_background_switch_retains_initialization_and_existing_default(monkeypatch, setting, enabled):
    monkeypatch.delenv("FLOWW_AGENT_DISABLED", raising=False)
    if setting is None:
        monkeypatch.delenv("FLOWW_BACKGROUND_LOOPS", raising=False)
    else:
        monkeypatch.setenv("FLOWW_BACKGROUND_LOOPS", setting)
    namespace, cache, loops = startup_namespace()
    await namespace["on_start"]()
    tasks = list(namespace["_background_tasks"])
    if tasks:
        await asyncio.gather(*tasks)

    namespace["db"].snapshots.create_index.assert_awaited_once()
    cache.ensure_index.assert_awaited_once()
    for name in ("_load_policy_from_mongo", "_init_alert_collection", "_load_rules_from_mongo"):
        namespace[name].assert_awaited_once()
    assert len(tasks) == (4 if enabled else 0)
    assert namespace["_scheduler_started"] is enabled
    for loop in loops.values():
        assert loop.await_count == int(enabled)
    # The opt-out is separate from the existing flag that refuses manual AskFlow.
    assert "FLOWW_AGENT_DISABLED" not in os.environ


@pytest.mark.asyncio
async def test_disabled_backgrounds_stay_off_when_storage_initialization_degrades(monkeypatch):
    monkeypatch.setenv("FLOWW_BACKGROUND_LOOPS", "0")
    namespace, _, loops = startup_namespace()
    namespace["db"].snapshots.create_index.side_effect = RuntimeError("offline store")
    await namespace["on_start"]()
    tasks = list(namespace["_background_tasks"])
    if tasks:
        await asyncio.gather(*tasks)
    assert not tasks
    assert not namespace["_scheduler_started"]
    for loop in loops.values():
        loop.assert_not_called()


@pytest.mark.asyncio
async def test_enabled_preserves_existing_already_started_scheduler_guard(monkeypatch):
    monkeypatch.delenv("FLOWW_BACKGROUND_LOOPS", raising=False)
    namespace, _, loops = startup_namespace()
    namespace["_scheduler_started"] = True
    await namespace["on_start"]()
    tasks = list(namespace["_background_tasks"])
    await asyncio.gather(*tasks)
    assert len(tasks) == 2
    loops["_scheduler_loop"].assert_not_called()
    loops["_warm_default_heatmaps"].assert_not_called()
    loops["_vpin_autofeed_loop"].assert_awaited_once()
    loops["_public_sweep_loop"].assert_awaited_once()
