"""G1.4 contract: cooldown table + alias surface pinned against drift."""
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
async def live_bot():
    bot = gateway._commands()
    await bot._async_setup_hook()
    bot._connection.user = SimpleNamespace(id=999)
    yield bot
    await bot.close()


def test_cooldown_table_pinned():
    assert gateway._COOLDOWN_S == {"heatmap": 20.0, "vanna": 20.0, "walls": 5.0}


@pytest.mark.asyncio
async def test_alias_surface_pinned(live_bot):
    surface = {}
    for cmd in live_bot.walk_commands():
        surface[cmd.name] = sorted(cmd.aliases)
    assert surface["heatmap"] == ["hm"]
    assert surface["walls"] == ["w"]
    assert surface["vanna"] == ["v"]
    assert surface["holdings"] == ["p", "pos", "positions"]
    assert surface["help"] == ["h"]
    assert surface["alerts"] == ["a"]
    assert surface["journal"] == ["j"]
    assert surface["cancel"] == ["x"]


@pytest.mark.asyncio
async def test_help_ops_cooldowns_match_table(live_bot):
    help_cmd = live_bot.get_command("help")
    import io
    from contextlib import redirect_stdout
    sent = []
    class Ctx:
        async def send(self, msg):
            sent.append(msg)
    await help_cmd.callback(Ctx(), "ops")
    out = "\n".join(sent)
    for cmd, secs in gateway._COOLDOWN_S.items():
        assert cmd in out and f"{int(secs)}s" in out


@pytest.mark.asyncio
async def test_message_content_intent_required_for_nl(live_bot):
    assert live_bot.intents.message_content is True


def test_main_refuses_without_token(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert gateway.main() == 2
