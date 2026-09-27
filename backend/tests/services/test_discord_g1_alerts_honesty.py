"""G1: !alerts must say UNAVAILABLE (not empty) when the feed errors."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

commands = pytest.importorskip("discord.ext.commands")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import discord_bot as gateway  # noqa: E402
from services import discord_ops as ops  # noqa: E402


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


def test_feed_failure_returns_none_not_empty():
    with patch("services.flow_alerts.read_alert_feed", side_effect=RuntimeError("down")):
        assert ops.fetch_recent_alerts(object(), limit=5) is None


@pytest.mark.asyncio
async def test_alerts_cmd_none_is_unavailable_not_empty(desk, monkeypatch):
    bot, ctx = desk
    monkeypatch.setattr(ops, "fetch_recent_alerts", lambda *a, **k: None)
    await bot.get_command("alerts")(ctx, 5)
    out = replies(ctx)
    assert "unavailable" in out and "No recent alerts" not in out


@pytest.mark.asyncio
async def test_approve_outage_remains_unavailable(monkeypatch):
    monkeypatch.setattr(ops, "fetch_recent_alerts", lambda *a, **k: None)
    res = await ops.execute_approve("NOPE", 1, object(), AsyncMock())
    assert res["status"] == "error" and "unavailable" in res["reason"]


def test_real_feed_read_error_is_not_reported_as_empty():
    class BrokenStore:
        def query(self, *args, **kwargs):
            raise RuntimeError("storage unavailable")

    assert ops.fetch_recent_alerts(BrokenStore(), limit=5) is None
