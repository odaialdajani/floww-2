"""G1: chain-backed reads must say UNAVAILABLE (not empty) when fetch fails."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

commands = pytest.importorskip("discord.ext.commands")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import discord_bot as gateway  # noqa: E402


@pytest_asyncio.fixture
async def desk(monkeypatch):
    from services import heatmap_image as hi

    monkeypatch.setattr(gateway, "_COOLDOWNS", {})
    monkeypatch.setattr(gateway._time, "monotonic", lambda: 1000.0)
    bot = gateway._commands()
    await bot._async_setup_hook()
    bot._connection.user = SimpleNamespace(id=999)
    ctx = SimpleNamespace(author=SimpleNamespace(id=42, bot=False), send=AsyncMock())
    monkeypatch.setattr(commands.Context, "send", ctx.send)
    yield bot, ctx, hi
    await bot.close()


def replies(ctx):
    return "\n".join(str(c.args[0] if c.args else c.kwargs.get("content", ""))
                     for c in ctx.send.await_args_list)


@pytest.mark.asyncio
async def test_heatmap_none_is_unavailable_not_empty(desk, monkeypatch):
    from services import heatmap_image as hi

    bot, ctx, _ = desk
    monkeypatch.setattr(hi, "get_heatmap_data", AsyncMock(return_value=None))
    await bot.get_command("heatmap")(ctx, "SPY")
    out = replies(ctx)
    assert "unavailable" in out and "No exposure data" not in out


@pytest.mark.asyncio
async def test_vanna_none_is_unavailable_not_empty(desk, monkeypatch):
    from services import heatmap_image as hi

    bot, ctx, _ = desk
    monkeypatch.setattr(hi, "get_vex_data", AsyncMock(return_value=None))
    await bot.get_command("vanna")(ctx, "QQQ")
    out = replies(ctx)
    assert "unavailable" in out and "No vol-exposure data" not in out


@pytest.mark.asyncio
async def test_walls_none_is_unavailable_not_empty(desk, monkeypatch):
    from services import heatmap_image as hi

    bot, ctx, _ = desk
    monkeypatch.setattr(hi, "get_heatmap_data", AsyncMock(return_value=None))
    monkeypatch.setattr(hi, "walls_text", MagicMock(return_value="SPY walls / flip"))
    await bot.get_command("walls")(ctx, "SPY")
    out = replies(ctx)
    assert "unavailable" in out and "No wall data" not in out
