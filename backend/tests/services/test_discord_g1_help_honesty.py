"""G1: default !help must name every topic and every registered alias."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

commands = pytest.importorskip("discord.ext.commands")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import discord_bot as gateway  # noqa: E402


@pytest_asyncio.fixture
async def desk(monkeypatch):
    monkeypatch.setattr(gateway, "_COOLDOWNS", {})
    bot = gateway._commands()
    await bot._async_setup_hook()
    bot._connection.user = SimpleNamespace(id=999)
    ctx = SimpleNamespace(author=SimpleNamespace(id=42, bot=False), send=AsyncMock())
    monkeypatch.setattr(commands.Context, "send", ctx.send)
    yield bot, ctx
    await bot.close()


def replies(ctx):
    return "\n".join(str(c.args[0] if c.args else c.kwargs.get("content", ""))
                     for c in ctx.send.await_args_list)


@pytest.mark.asyncio
async def test_default_help_names_every_topic(desk):
    from services import discord_ops as ops

    bot, ctx = desk
    await bot.get_command("help")(ctx, "")
    out = replies(ctx)
    for topic in ("solstice", "trading", "portfolio", "ops"):
        assert topic in out, f"topic {topic!r} missing from default !help"
        assert topic in ops.HELP_TEXT, f"topic {topic!r} missing from HELP_TEXT"


@pytest.mark.asyncio
async def test_default_help_names_every_registered_alias(desk):
    bot, ctx = desk
    await bot.get_command("help")(ctx, "")
    out = replies(ctx)
    missing = [a for c in bot.walk_commands() for a in c.aliases if a not in out]
    assert missing == [], f"aliases missing from default !help: {missing}"
