"""Offline command-surface regressions using registered discord.py commands."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from discord.ext import commands

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
    bot.process_commands = AsyncMock(wraps=bot.process_commands)
    bot.dispatch = MagicMock()
    norm = {"spot": 500.0, "strikes": [(500, 1000)], "regime": "positive"}
    monkeypatch.setattr(hi, "get_heatmap_data", AsyncMock(return_value=norm))
    monkeypatch.setattr(hi, "get_vex_data", AsyncMock(return_value=norm))
    monkeypatch.setattr(hi, "render_gex_png", MagicMock(return_value=b"png"))
    monkeypatch.setattr(hi, "render_vex_png", MagicMock(return_value=b"png"))
    monkeypatch.setattr(hi, "walls_text", MagicMock(return_value="SPY walls / flip"))
    yield bot, ctx, hi
    await bot.close()


def message(ctx, text, **overrides):
    return SimpleNamespace(content=text, author=ctx.author, _state=None,
                           attachments=[], guild=None,
                           channel=SimpleNamespace(send=ctx.send), webhook_id=None,
                           **overrides)


def replies(ctx):
    return "\n".join(str(c.args[0] if c.args else c.kwargs.get("content", ""))
                     for c in ctx.send.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("word,cmd", [("gex", "heatmap"), ("hm", "heatmap"),
                                      ("v", "vanna"), ("vanna", "vanna"),
                                      ("w", "walls"), ("walls", "walls"),
                                      ("flip", "walls")])
@pytest.mark.parametrize("nl_first", [True, False])
async def test_nl_and_prefix_share_cooldown(desk, word, cmd, nl_first):
    bot, ctx, hi = desk
    read = hi.get_vex_data if cmd == "vanna" else hi.get_heatmap_data
    if nl_first:
        await bot.on_message(message(ctx, f"spy {word}"))
        await bot.get_command(cmd)(ctx, "SPY")
    else:
        await bot.get_command(cmd)(ctx, "SPY")
        await bot.on_message(message(ctx, f"spy {word}"))
    read.assert_awaited_once_with("SPY")
    assert "cools down" in replies(ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("cmd,word", [("heatmap", "gex"), ("vanna", "v"), ("walls", "w")])
@pytest.mark.parametrize("outcome", ["success", "empty", "error"])
async def test_nl_uses_registered_rendering_and_errors(desk, cmd, word, outcome):
    bot, ctx, hi = desk
    read = hi.get_vex_data if cmd == "vanna" else hi.get_heatmap_data
    if outcome == "error":
        read.side_effect = RuntimeError("provider unavailable")
    elif outcome == "empty":
        hi.render_gex_png.return_value = None
        hi.render_vex_png.return_value = None
        read.return_value = None
    await bot.get_command(cmd)(ctx, "SPY")
    expected = replies(ctx)
    expected_files = [c.kwargs["file"].filename for c in ctx.send.await_args_list if "file" in c.kwargs]
    gateway._COOLDOWNS.clear()
    ctx.send.reset_mock()
    await bot.on_message(message(ctx, f"spy {word}"))
    assert replies(ctx) == expected
    assert [c.kwargs["file"].filename for c in ctx.send.await_args_list if "file" in c.kwargs] == expected_files


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["spy gex", "!heatmap SPY", "clock"])
@pytest.mark.parametrize("kind", ["bot", "webhook"])
async def test_ignores_automated_authors(desk, text, kind):
    bot, ctx, hi = desk
    msg = message(ctx, text)
    if kind == "bot":
        msg.author = SimpleNamespace(id=99, bot=True)
    else:
        msg.webhook_id = 123
    await bot.on_message(msg)
    ctx.send.assert_not_awaited()
    bot.process_commands.assert_not_awaited()
    hi.get_heatmap_data.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("word", ["status", "CLOCK"])
async def test_prefixless_ops_use_registered_callback(desk, word):
    bot, ctx, _ = desk
    callback = AsyncMock()

    async def tracked(context):
        await callback(context)

    bot.get_command(word.lower()).callback = tracked
    await bot.on_message(message(ctx, f"  {word}  "))
    callback.assert_awaited_once()
    assert callback.await_args.args[0].author is ctx.author


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["buy 1 SPY", "sell 1 SPY", "bracket buy 1 SPY 3 2",
                                  "approve alert-key", "close SPY", "cancel order-id"])
async def test_trading_stays_prefix_only(desk, text):
    bot, ctx, _ = desk
    callback = AsyncMock()

    async def tracked(context, *args):
        await callback(context, *args)

    bot.get_command(text.split()[0]).callback = tracked
    await bot.on_message(message(ctx, text))
    callback.assert_not_awaited()
    ctx.send.assert_not_awaited()


@pytest.fixture
def alpaca(monkeypatch):
    import alpaca_client

    client = SimpleNamespace(enabled=True, get_clock=AsyncMock(), get_orders=AsyncMock(),
                             get_account=AsyncMock())
    monkeypatch.setattr(alpaca_client, "AlpacaClient", lambda: client)
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("clock", [None, {}, {"next_open": "tomorrow"}, {"is_open": None}])
async def test_missing_clock_is_unknown_not_closed(desk, alpaca, clock):
    bot, ctx, _ = desk
    alpaca.get_clock.return_value = clock
    await bot.get_command("clock")(ctx)
    assert "unavailable" in replies(ctx).lower()
    assert "CLOSED" not in replies(ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("is_open,state", [(True, "OPEN"), (False, "CLOSED")])
async def test_known_clock_state(desk, alpaca, is_open, state):
    bot, ctx, _ = desk
    alpaca.get_clock.return_value = {"is_open": is_open}
    await bot.get_command("clock")(ctx)
    assert f"**{state}**" in replies(ctx)


@pytest.mark.asyncio
async def test_status_configuration_is_not_connectivity(desk, alpaca):
    bot, ctx, _ = desk
    await bot.get_command("status")(ctx)
    assert "configured" in replies(ctx)
    assert "connected" not in replies(ctx)
    alpaca.get_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_orders_show_real_status_fills_and_cancel_ids(desk, alpaca):
    bot, ctx, _ = desk
    rows = [{"id": f"broker-{status}", "client_order_id": f"client-{status}",
             "symbol": "SPY", "side": "buy", "qty": "10", "status": status,
             "type": "limit", "filled_qty": qty, "filled_avg_price": price}
            for status, qty, price in [("partially_filled", "2", "500.25"),
                                       ("canceled", "0", None), ("rejected", "0", None),
                                       ("expired", "0", None), ("filled", "10", "501.00")]]
    alpaca.get_orders.side_effect = [rows[:1], rows[1:]]
    await bot.get_command("orders")(ctx)
    text = replies(ctx)
    assert "recent fills" not in text
    assert "recent closed orders" in text
    for row in rows:
        line = next(line for line in text.splitlines() if row["id"] in line)
        assert row["status"] in line
        assert f"filled {row['filled_qty']} @ {row['filled_avg_price'] or '?'}" in line
        assert f"`{row['id']}`" in line
        assert row["client_order_id"] not in line
    assert "!cancel <order-id>" in text


@pytest.mark.asyncio
async def test_nl_obeys_global_checks_and_no_replay(desk):
    bot, ctx, hi = desk

    async def deny(context):
        return False

    bot.add_check(deny)
    original = message(ctx, "spy gex")
    await bot.on_message(original)
    hi.get_heatmap_data.assert_not_awaited()
    assert original.content == "spy gex"
    bot.process_commands.assert_awaited_once()
    assert any(c.args[0] == "command_error" for c in bot.dispatch.call_args_list)


@pytest.mark.asyncio
async def test_nl_runs_invoke_hooks(desk):
    bot, ctx, _ = desk
    hook = AsyncMock()

    async def before(context):
        await hook(context.command.name)

    bot.before_invoke(before)
    await bot.on_message(message(ctx, "spy gex"))
    hook.assert_awaited_once_with("heatmap")


@pytest.mark.asyncio
async def test_orders_chunk_without_losing_cancel_ids(desk, alpaca):
    bot, ctx, _ = desk
    rows = [{"id": f"12345678-1234-1234-1234-{i:012d}",
             "symbol": "SPY260918C00500000", "side": "buy", "qty": "10000.123456789",
             "status": "partially_filled", "type": "limit", "filled_qty": "5000.123456789",
             "filled_avg_price": "12345.6789"} for i in range(15)]
    alpaca.get_orders.side_effect = [rows[:10], rows[10:]]
    await bot.get_command("orders")(ctx)
    assert ctx.send.await_count > 1
    assert all(len(c.args[0]) <= 2000 for c in ctx.send.await_args_list)
    for row in rows:
        assert replies(ctx).count(f"`{row['id']}`") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("open_rows,closed_rows", [(None, []), ([], None), (None, None)])
async def test_unavailable_orders_are_not_empty(desk, alpaca, open_rows, closed_rows):
    bot, ctx, _ = desk
    alpaca.get_orders.side_effect = [open_rows, closed_rows]
    await bot.get_command("orders")(ctx)
    text = replies(ctx).lower()
    if open_rows is None:
        assert "open orders unavailable" in text
        assert "none open" not in text
    else:
        assert "none open" in text
    if closed_rows is None:
        assert "closed orders unavailable" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("positions", [None, []])
async def test_holdings_unavailable_vs_empty(desk, alpaca, positions):
    bot, ctx, _ = desk
    alpaca.get_positions = AsyncMock(return_value=positions)
    await bot.get_command("holdings")(ctx)
    if positions is None:
        assert "holdings unavailable" in replies(ctx).lower()
        assert "No open" not in replies(ctx)
    else:
        assert "No open paper positions" in replies(ctx)
