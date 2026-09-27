"""
backend/discord_bot.py — SOLSTICE Discord gateway bot (separate process).

Solstice = the dealer-positioning desk: gamma/vanna exposure, walls, flips,
pin magnets — rendered as chart pictures on request. (A separate Tidehunter
flow bot comes later; this process stays gamma-specialized.)

Run:  cd backend && .venv/bin/python3 discord_bot.py
Needs: DISCORD_BOT_TOKEN + Alpaca keys in env. Paper venue only.

Commands (! prefix): heatmap / vanna / walls (Solstice); buy / sell /
holdings / orders / approve / alerts / help (paper trading).
Trading commands (!buy/!sell/!approve) require DISCORD_ALLOWED_USER_IDS
membership; everything else is read-only. discord.py is imported lazily so
the FastAPI backend boots without it installed.
"""
from __future__ import annotations

import collections
import copy
import logging
import os
import sys
import time as _time

from services import discord_harness as _harness

try:
    from dotenv import load_dotenv

    load_dotenv(__import__("pathlib").Path(__file__).resolve().parent / ".env")
except Exception:
    pass

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

log = logging.getLogger("discord_bot")

# Prompt harness: per-user cooldowns on heavy commands (heatmap builds hit
# paid chains — 20s/user keeps one enthusiastic thumb inside budget) and an
# audit ring so allowlisted users can see who ran what.
_COOLDOWNS: dict[tuple[str, str], float] = _harness.new_cooldowns()
_COOLDOWN_S = dict(_harness.COOLDOWN_S)
_AUDIT: collections.deque = _harness.new_audit_ring()
_NL_READ = _harness.NL_READ


def _cool_ok(user_id, cmd: str) -> tuple[bool, float]:
    return _harness.cool_check(_COOLDOWNS, _COOLDOWN_S, user_id, cmd, _time.monotonic())


def _audit(user_id, cmd: str) -> None:
    _harness.audit_append(_AUDIT, user_id, cmd, _time.time())


def usage_counts() -> dict:
    return _harness.audit_counts(_AUDIT)


def _commands():
    from discord.ext import commands

    from services import discord_ops as ops

    intents = __import__("discord").Intents.default()
    intents.message_content = True  # enable in Developer Portal too
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    @bot.before_invoke
    async def audit_request(ctx):
        # Count parsed invocations, not successful trades or provider responses.
        args = str(getattr(getattr(ctx, "message", None), "content", "")).partition(" ")[2]
        _audit(getattr(getattr(ctx, "author", None), "id", "?"),
               f"{ctx.command.name} {args}".strip())

    def _deny(ctx) -> bool:
        return ops.is_trading_allowed(getattr(getattr(ctx, "author", None), "id", None))

    def _router():
        from services.order_router import OrderRouter

        return OrderRouter("discord-paper")

    def _engine():
        from services.duckdb_engine import db as duckdb_engine

        return duckdb_engine

    _TOPICS = {
        "solstice": ("**Solstice (gamma desk)**\n"
                     "`!heatmap <T>` GEX ladder picture · `!vanna <T>` VEX picture · "
                     "`!walls <T>` walls/flip/regime readout"),
        "trading": ("**Paper trading (Alpaca paper ONLY)**\n"
                    "`!buy <qty> <SYM> [limit <px>]` · `!sell <qty> <SYM>` · "
                    "`!bracket <buy|sell> <qty> <SYM> <tp%%> <sl%%>` (entry + TP/SL legs)\n"
                    "`!approve <alert-key> [qty]` — trade a posted alert (journaled)\n"
                    "`!close <SYM>` closes a position · allowlisted only"),
        "portfolio": ("**Portfolio**\n`!holdings` open paper positions · `!orders` recent "
                      "orders · `!pnl` day P&L · `!risk` buying power · `!journal [n]` "
                      "recent journaled trades"),
        "ops": ("**Ops**\n`!status` desk health · `!clock` market hours · `!audit [n]` command log "
                f"(allowlisted) · `!cancel <order-id>` · cooldowns: {_harness.cooldown_line(_COOLDOWN_S)} per user"),
    }

    @bot.command(name="help", aliases=["h"])
    async def help_cmd(ctx, topic: str = ""):
        t = (topic or "").lower()
        if t in _TOPICS:
            await ctx.send(_TOPICS[t])
            return
        aliases = sorted({a for c in bot.walk_commands() for a in c.aliases})
        await ctx.send(ops.HELP_TEXT + "\n`!help <solstice|trading|portfolio|ops>` for topics. "
                       "Aliases: " + " ".join(aliases) + ".")

    @bot.command(name="holdings", aliases=["pos", "positions", "p"])
    async def holdings_cmd(ctx):
        try:
            from alpaca_client import AlpacaClient

            client = AlpacaClient()
            if not client.enabled:
                await ctx.send("Alpaca paper keys not configured.")
                return

            pos = await client.get_positions()
            if pos is None:
                await ctx.send("Paper holdings unavailable — positions unknown.")
                return
            if not pos:
                await ctx.send("No open paper positions.")
                return
            lines = [f"{p.get('symbol')}: {p.get('qty')} @ {p.get('current_price', '?')}"
                     for p in pos[:20]]
            await ctx.send("**Paper holdings**\n" + "\n".join(lines))
        except Exception as e:
            await ctx.send(f"holdings failed: {e}")

    @bot.command(name="orders")
    async def orders_cmd(ctx):
        try:
            from alpaca_client import AlpacaClient

            client = AlpacaClient()
            if not client.enabled:
                await ctx.send("Alpaca paper keys not configured.")
                return
            orders = await client.get_orders(status="open", limit=10)
            closed = await client.get_orders(status="closed", limit=5)

            def order_line(o):
                return (f"`{o.get('id') or '?'}` {o.get('symbol')} {o.get('side')} "
                        f"{o.get('qty')} {o.get('status') or '?'} ({o.get('type')}) · "
                        f"filled {o.get('filled_qty') if o.get('filled_qty') is not None else '?'} "
                        f"@ {o.get('filled_avg_price') if o.get('filled_avg_price') is not None else '?'}")

            lines = (["Open orders unavailable — state unknown."] if orders is None
                     else [order_line(o) for o in orders] or ["none open."])
            if closed is None:
                lines.append("Recent closed orders unavailable — state unknown.")
            elif closed:
                lines.append("— recent closed orders —")
                lines += [order_line(o) for o in closed[:5]]
            header = "**Orders (paper)** · `!cancel <order-id>` for open orders\n"
            chunk = header
            for line in lines or ["none open."]:
                if len(chunk) + len(line) + 1 > 2000:
                    await ctx.send(chunk.rstrip())
                    chunk = header
                chunk += line + "\n"
            await ctx.send(chunk.rstrip())
        except Exception as e:
            await ctx.send(f"orders failed: {e}")

    @bot.command(name="alerts", aliases=["a"])
    async def alerts_cmd(ctx, n: int = 5):
        rows = ops.fetch_recent_alerts(_engine(), limit=n)
        if rows is None:
            await ctx.send("Recent alerts unavailable — feed state unknown.")
            return
        if not rows:
            await ctx.send("No recent alerts.")
            return
        lines = []
        for a in rows:
            lines.append(f"`{a.get('key')}` {a.get('tier')} {a.get('rule')} "
                         f"{a.get('under')} {a.get('bias') or ''} score={a.get('score')}")
        await ctx.send("**Recent alerts** (approve with `!approve <key> [qty]`)\n" + "\n".join(lines))

    async def _trade(ctx, side: str, qty: int, symbol: str, order_type="market", limit_price=0.0):
        if not _deny(ctx):
            await ctx.send("Trading commands are allowlisted (DISCORD_ALLOWED_USER_IDS).")
            return
        import time

        router = _router()
        res = await router.submit_order({
            "ticker": symbol.upper(), "side": side, "qty": qty,
            "order_type": order_type, "limit_price": limit_price,
            "signal_id": f"discord:{ctx.author.id}:{int(time.time() * 1e6)}",
            "timestamp_us": int(time.time() * 1e6),
        })
        if res.get("status") == "submitted":
            await ctx.send(f"PAPER {side.upper()} {qty} {symbol.upper()} submitted "
                           f"(`{res.get('client_order_id')}`)")
        else:
            await ctx.send(f"Trade rejected: {res.get('reason', res)}")

    @bot.command(name="buy")
    async def buy_cmd(ctx, qty: int = 0, symbol: str = "", *rest):
        if not symbol or qty <= 0:
            await ctx.send("Usage: `!buy <qty> <SYM> [limit <px>]`")
            return
        limit_px = 0.0
        otype = "market"
        if len(rest) >= 2 and rest[0].lower() == "limit":
            try:
                limit_px = float(rest[1])
                otype = "limit"
            except (TypeError, ValueError):
                await ctx.send("Usage: `!buy <qty> <SYM> [limit <px>]`")
                return
        await _trade(ctx, "buy", qty, symbol, otype, limit_px)

    @bot.command(name="sell")
    async def sell_cmd(ctx, qty: int = 0, symbol: str = "", *rest):
        if not symbol or qty <= 0:
            await ctx.send("Usage: `!sell <qty> <SYM>`")
            return
        await _trade(ctx, "sell", qty, symbol)

    @bot.command(name="pnl")
    async def pnl_cmd(ctx):
        try:
            from alpaca_client import AlpacaClient

            client = AlpacaClient()
            if not client.enabled:
                await ctx.send("Alpaca paper keys not configured.")
                return
            acct = await client.get_account() or {}
            eq = acct.get("equity", "?")
            last = acct.get("last_equity", "?")
            try:
                pnl = float(eq) - float(last)
                await ctx.send(f"**Paper P&L (day): {pnl:+.2f}** · equity {eq} · BP {acct.get('buying_power', '?')}")
            except (TypeError, ValueError):
                await ctx.send(f"equity {eq} · last {last} · BP {acct.get('buying_power', '?')}")
        except Exception as e:
            await ctx.send(f"pnl failed: {e}")

    @bot.command(name="close")
    async def close_cmd(ctx, symbol: str = ""):
        if not symbol:
            await ctx.send("Usage: `!close <SYM>`")
            return
        if not _deny(ctx):
            await ctx.send("Trading commands are allowlisted (DISCORD_ALLOWED_USER_IDS).")
            return
        try:
            from alpaca_client import AlpacaClient

            res = await AlpacaClient().close_position(symbol)
            await ctx.send(f"Close {symbol.upper()}: {res.get('message', res) if res else 'failed'}")
        except Exception as e:
            await ctx.send(f"close failed: {e}")

    @bot.command(name="bracket")
    async def bracket_cmd(ctx, side: str = "", qty: int = 0, symbol: str = "",
                          tp_pct: float = 0, sl_pct: float = 0):
        if side.lower() not in ("buy", "sell") or qty <= 0 or not symbol or tp_pct <= 0 or sl_pct <= 0:
            await ctx.send("Usage: `!bracket <buy|sell> <qty> <SYM> <tp%%> <sl%%>` — e.g. `!bracket buy 10 SPY 3 2`")
            return
        if not _deny(ctx):
            await ctx.send("Trading commands are allowlisted (DISCORD_ALLOWED_USER_IDS).")
            return
        try:
            from alpaca_client import AlpacaClient
            from services.public_api_adapter import fetch_spot_from_public_api

            spot = await fetch_spot_from_public_api(symbol)
            if not spot or spot <= 0:
                await ctx.send(f"No live quote for {symbol.upper()} — bracket needs a reference price.")
                return
            long = side.lower() == "buy"
            tp = spot * (1 + tp_pct / 100) if long else spot * (1 - tp_pct / 100)
            sl = spot * (1 - sl_pct / 100) if long else spot * (1 + sl_pct / 100)
            res = await AlpacaClient().place_bracket_order(
                symbol, qty, side, take_profit_price=round(tp, 2), stop_loss_price=round(sl, 2))
            if res:
                await ctx.send(f"PAPER bracket {side.upper()} {qty} {symbol.upper()} @~{spot:.2f} "
                               f"TP {tp:.2f} / SL {sl:.2f} (`{res.get('id', '')}`)")
            else:
                await ctx.send("Bracket rejected (check approval/funds).")
        except Exception as e:
            await ctx.send(f"bracket failed: {e}")

    @bot.command(name="risk")
    async def risk_cmd(ctx):
        try:
            from alpaca_client import AlpacaClient

            client = AlpacaClient()
            if not client.enabled:
                await ctx.send("Alpaca paper keys not configured.")
                return
            acct = await client.get_account() or {}
            await ctx.send(f"**Paper risk** · BP {acct.get('buying_power', '?')} · equity "
                           f"{acct.get('equity', '?')} · daytrades {acct.get('daytrade_count', '?')}")
        except Exception as e:
            await ctx.send(f"risk failed: {e}")

    @bot.command(name="journal", aliases=["j"])
    async def journal_cmd(ctx, n: int = 5):
        try:
            from services.journal_store import get_engine, init_journal_tables, read_trades

            eng = get_engine()
            init_journal_tables(eng)
            rows = read_trades(eng, days=30)[-max(1, min(int(n), 10)):]
            if not rows:
                await ctx.send("Journal empty (last 30d).")
                return
            lines = [f"{t.get('entry_date', '')[:10]} {t.get('action','')} {t.get('quantity','')}x "
                     f"{t.get('ticker','')} {t.get('type','')} @{t.get('strike','')} "
                     f"({t.get('source','')})" for t in rows]
            await ctx.send("**Journal (recent)**\n" + "\n".join(lines))
        except Exception as e:
            await ctx.send(f"journal failed: {e}")

    @bot.command(name="approve")
    async def approve_cmd(ctx, key: str = "", qty: int = 1):
        if not key:
            await ctx.send("Usage: `!approve <alert-key> [qty]`")
            return
        if not _deny(ctx):
            await ctx.send("Trading commands are allowlisted (DISCORD_ALLOWED_USER_IDS).")
            return
        res = await ops.execute_approve(key, qty, _engine(), _router())
        if res.get("status") == "submitted":
            await ctx.send(f"PAPER trade from `{key}` submitted.")
        else:
            await ctx.send(f"Approve failed: {res.get('reason', res)}")

    # ---------- Solstice: gamma/vanna exposure on request ----------
    @bot.command(name="heatmap", aliases=["hm"])
    async def heatmap_cmd(ctx, ticker: str = ""):
        if not ticker:
            await ctx.send("Usage: `!heatmap <TICKER>` — e.g. `!heatmap SPY`")
            return
        ok, wait = _cool_ok(getattr(getattr(ctx, "author", None), "id", "?"), "heatmap")
        if not ok:
            await ctx.send(f"Easy — `heatmap` cools down for {wait:.0f}s more (paid-chain budget).")
            return
        await ctx.send(f"Building {ticker.upper()} GEX ladder…")
        try:
            from services import heatmap_image as hi

            norm = await hi.get_heatmap_data(ticker)
            if norm is None:
                await ctx.send(f"Heatmap unavailable for {ticker.upper()} — chain state unknown.")
                return
            png = hi.render_gex_png(norm)
            if not png:
                await ctx.send(f"No exposure data for {ticker.upper()} right now.")
                return
            import discord as _dc

            net = sum(g for _, g in norm["strikes"])
            await ctx.send(
                content=(f"**{ticker.upper()}** spot {norm['spot']:.2f} · "
                         f"net {_money(net)} · regime {norm.get('regime', '?')}"),
                file=_dc.File(__import__("io").BytesIO(png), filename=f"gex-{ticker.upper()}.png"),
            )
        except Exception as e:
            await ctx.send(f"heatmap failed: {e}")

    @bot.command(name="vanna", aliases=["v"])
    async def vanna_cmd(ctx, ticker: str = ""):
        if not ticker:
            await ctx.send("Usage: `!vanna <TICKER>` — e.g. `!vanna QQQ`")
            return
        ok, wait = _cool_ok(getattr(getattr(ctx, "author", None), "id", "?"), "vanna")
        if not ok:
            await ctx.send(f"Easy — `vanna` cools down for {wait:.0f}s more (paid-chain budget).")
            return
        await ctx.send(f"Building {ticker.upper()} VEX ladder…")
        try:
            from services import heatmap_image as hi

            norm = await hi.get_vex_data(ticker)
            if norm is None:
                await ctx.send(f"Vanna unavailable for {ticker.upper()} — chain state unknown.")
                return
            png = hi.render_vex_png(norm)
            if not png:
                await ctx.send(f"No vol-exposure data for {ticker.upper()} right now "
                               f"(needs chain IVs).")
                return
            import discord as _dc

            net = sum(v for _, v in norm["strikes"])
            await ctx.send(
                content=(f"**{ticker.upper()} VEX** net {_money(net)} "
                         f"(dealer vomma exposure)"),
                file=_dc.File(__import__("io").BytesIO(png), filename=f"vex-{ticker.upper()}.png"),
            )
        except Exception as e:
            await ctx.send(f"vanna failed: {e}")

    @bot.command(name="walls", aliases=["w"])
    async def walls_cmd(ctx, ticker: str = ""):
        if not ticker:
            await ctx.send("Usage: `!walls <TICKER>` — e.g. `!walls SPY`")
            return
        ok, wait = _cool_ok(getattr(getattr(ctx, "author", None), "id", "?"), "walls")
        if not ok:
            await ctx.send(f"Easy — `walls` cools down for {wait:.0f}s more (paid-chain budget).")
            return
        try:
            from services import heatmap_image as hi

            norm = await hi.get_heatmap_data(ticker)
            if norm is None:
                await ctx.send(f"Walls unavailable for {ticker.upper()} — chain state unknown.")
                return
            await ctx.send(hi.walls_text(norm) if norm else
                           f"No wall data for {ticker.upper()} right now.")
        except Exception as e:
            await ctx.send(f"walls failed: {e}")

    @bot.command(name="cancel", aliases=["x"])
    async def cancel_cmd(ctx, order_id: str = ""):
        if not order_id:
            await ctx.send("Usage: `!cancel <order-id>` (see `!orders`)")
            return
        if not _deny(ctx):
            await ctx.send("Trading commands are allowlisted (DISCORD_ALLOWED_USER_IDS).")
            return
        try:
            from alpaca_client import AlpacaClient

            ok = await AlpacaClient().cancel_order(order_id)
            await ctx.send(f"Cancel `{order_id}`: {'confirmed' if ok else 'failed / already gone'}.")
        except Exception as e:
            await ctx.send(f"cancel failed: {e}")

    @bot.command(name="clock")
    async def clock_cmd(ctx):
        try:
            from alpaca_client import AlpacaClient

            clk = await AlpacaClient().get_clock()
            if not isinstance(clk, dict) or not isinstance(clk.get("is_open"), bool):
                await ctx.send("Market clock unavailable — session state unknown.")
                return
            state = "OPEN" if clk["is_open"] else "CLOSED"
            await ctx.send(f"Market **{state}** · next open {clk.get('next_open', '?')} · next close {clk.get('next_close', '?')}")
        except Exception as e:
            await ctx.send(f"clock failed: {e}")

    @bot.command(name="status")
    async def status_cmd(ctx):
        try:
            from services.public_budget import budget as _budget

            acct_note = "Alpaca keys missing"
            try:
                from alpaca_client import AlpacaClient

                c = AlpacaClient()
                acct_note = "Alpaca paper keys configured (connectivity unverified)" if c.enabled else "Alpaca paper keys missing"
            except Exception:
                pass
            b = _budget.status()
            await ctx.send(f"**Desk status** · {acct_note} · budget {b['available']}/{b['capacity']} · "
                           f"inflight {b['inflight']} · universe 40 · venue alpaca-paper")
        except Exception as e:
            await ctx.send(f"status failed: {e}")

    @bot.command(name="audit")
    async def audit_cmd(ctx, n: int = 10):
        if not _deny(ctx):
            await ctx.send("Audit is allowlisted.")
            return
        rows = list(_AUDIT)[-max(1, min(int(n), 25)):]
        if not rows:
            await ctx.send("Audit log empty.")
            return
        import datetime as _dt
        lines = [f"{_dt.datetime.fromtimestamp(r['t']).strftime('%H:%M:%S')} <@{r['user']}> `{r['cmd']}`" for r in rows]
        use = " ".join(f"{k}×{v}" for k, v in sorted(usage_counts().items()))
        await ctx.send("**Command audit**\n" + "\n".join(lines) + (f"\n_requests: {use}_" if use else ""))

    @bot.event
    async def on_message(message):
        author = getattr(message, "author", None)
        if (author is None or getattr(author, "bot", False)
                or getattr(message, "webhook_id", None) is not None
                or author == bot.user):
            return
        text = str(getattr(message, "content", "") or "").strip()
        parsed = _harness.parse_nl(text)
        command_text = None
        if parsed:
            cmd, ticker = parsed
            command_text = f"{cmd} {ticker}" if ticker else cmd
        if command_text:
            # Preserve the original event and use the normal parser, checks,
            # invocation hooks, callbacks, cooldowns, and error dispatch.
            message = copy.copy(message)
            message.content = f"!{command_text}"
        await bot.process_commands(message)

    @bot.event
    async def on_command_error(ctx, error):
        from discord.ext import commands as _cmds

        if isinstance(error, _cmds.CommandNotFound):
            typed = str(getattr(ctx, "invoked_with", "") or "")
            known = [c.name for c in bot.commands] + ["pos", "h", "a", "hm", "w", "v", "j", "p", "x"]
            guess = _harness.fuzzy_hint(typed, known)
            hint = f" Did you mean `!{guess}`?" if guess else ""
            await ctx.send(f"Unknown command `!{typed}`.{hint} Try `!help`.")
            return
        await ctx.send(f"Command error: {type(error).__name__}. Try `!help`.")

    return bot


def _money(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    a = abs(n)
    if a >= 1e9:
        return f"${n / 1e9:.2f}B"
    if a >= 1e6:
        return f"${n / 1e6:.1f}M"
    if a >= 1e3:
        return f"${n / 1e3:.0f}k"
    return f"${n:.0f}"


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("DISCORD_BOT_TOKEN not set — refusing to start.")
        return 2
    try:
        import discord  # noqa: F401
    except ImportError:
        print("discord.py not installed — run: .venv/bin/pip install 'discord.py>=2.3'")
        return 2
    bot = _commands()
    bot.run(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
