"""G1.4: per-command usage counters in the audit surface."""
import collections
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
    monkeypatch.setattr(gateway, "_AUDIT", collections.deque(maxlen=200))
    yield bot, ctx
    await bot.close()


def test_audit_tracks_per_command_usage_counts(monkeypatch):
    monkeypatch.setattr(gateway, "_AUDIT", collections.deque(maxlen=200))
    gateway._audit(7, "heatmap")
    gateway._audit(7, "heatmap")
    gateway._audit(9, "walls")
    assert gateway.usage_counts() == {"heatmap": 2, "walls": 1}


@pytest.mark.asyncio
async def test_audit_output_carries_usage_summary(desk, monkeypatch):
    from services import discord_ops as ops
    monkeypatch.setattr(ops, "is_trading_allowed", lambda *a: True)
    bot, ctx = desk
    monkeypatch.setattr(gateway, "_AUDIT", collections.deque(maxlen=200))
    gateway._audit(42, "heatmap")
    gateway._audit(42, "walls")
    await bot.get_command("audit")(ctx)
    out = "\n".join(str(c.args[0] if c.args else "") for c in ctx.send.await_args_list)
    assert "heatmap×1" in out and "walls×1" in out


def test_usage_counts_folds_nl_variants_to_base_command(monkeypatch):
    monkeypatch.setattr(gateway, "_AUDIT", collections.deque(maxlen=200))
    gateway._audit(7, "heatmap SPY (nl)")
    gateway._audit(7, "heatmap")
    assert gateway.usage_counts() == {"heatmap": 2}
