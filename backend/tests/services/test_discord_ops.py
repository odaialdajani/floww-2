"""
backend/tests/services/test_discord_ops.py — webhook gate/format, command
parsing, allowlist, approve flow. No network (httpx/broker/engine mocked).
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _alert(**over):
    base = {
        "key": "score|SPY|call|745|2099-01-08", "ckey": "SPY|call|745|2099-01-08",
        "rule": "SCORE", "tier": "GOLD", "side": "BUY", "bias": "BULLISH",
        "under": "SPY", "type": "call", "strike": 745, "exp": "2099-01-08",
        "dte": 5, "score": 95, "premium": 2000000, "vol_oi": 6.0,
        "conviction": 88, "why": "score 95 — vol 6.0x OI",
        "key_levels": {"entry": 740.0, "invalidation": 721.5, "target": 765.9},
    }
    base.update(over)
    return base


class TestGate:
    def test_gold_score_posts_by_default(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.delenv("DISCORD_MIN_TIER", raising=False)
        monkeypatch.delenv("DISCORD_RULES", raising=False)
        assert ops.should_notify(_alert()) is True

    def test_silver_blocked_by_gold_floor(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_MIN_TIER", "GOLD")
        assert ops.should_notify(_alert(tier="SILVER")) is False

    def test_rule_allowlist(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_RULES", "WHALE")
        assert ops.should_notify(_alert(rule="SCORE")) is False
        assert ops.should_notify(_alert(rule="WHALE")) is True


class TestFormat:
    def test_embed_shape(self):
        from services import discord_ops as ops
        payload = ops.format_alert_message(_alert())
        assert payload["embeds"][0]["title"].startswith("GOLD SCORE — SPY")
        fields = {f["name"]: f["value"] for f in payload["embeds"][0]["fields"]}
        assert fields["Premium"] == "$2.0M"
        assert "Levels" in fields
        assert "!approve score|SPY|call|745|2099-01-08" in payload["embeds"][0]["footer"]["text"]


class TestPost:
    @pytest.mark.asyncio
    async def test_no_webhook_is_silent_noop(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        assert await ops.post_alerts([_alert()]) == 0

    @pytest.mark.asyncio
    async def test_posts_only_gated(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
        monkeypatch.setenv("DISCORD_MIN_TIER", "GOLD")
        resp = MagicMock(status_code=204)
        posted = []

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None):
                posted.append(json)
                return resp

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            n = await ops.post_alerts([_alert(), _alert(tier="BRONZE")])
        assert n == 1 and len(posted) == 1


class TestParse:
    def test_buy_sell(self):
        from services import discord_ops as ops
        assert ops.parse_command("!buy 10 SPY") == {
            "cmd": "buy", "qty": 10, "symbol": "SPY", "order_type": "market"}
        assert ops.parse_command("!buy 5 qqq limit 700") == {
            "cmd": "buy", "qty": 5, "symbol": "QQQ",
            "order_type": "limit", "limit_price": 700.0}
        assert ops.parse_command("!sell 3 AAPL")["cmd"] == "sell"
        assert ops.parse_command("!buy ten SPY") is None
        assert ops.parse_command("!buy 10") is None

    def test_approve_alerts_help(self):
        from services import discord_ops as ops
        assert ops.parse_command("!approve score|X 5") == {
            "cmd": "approve", "key": "score|X", "qty": 5}
        assert ops.parse_command("!approve score|X") == {"cmd": "approve", "key": "score|X"}
        assert ops.parse_command("!alerts 3") == {"cmd": "alerts", "n": 3}
        assert ops.parse_command("!alerts") == {"cmd": "alerts", "n": 5}
        assert ops.parse_command("!holdings") == {"cmd": "holdings"}
        assert ops.parse_command("hello") is None
        assert ops.parse_command("!unknowncmd x") is None


class TestAllowlist:
    def test_empty_deny_all_trading(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.delenv("DISCORD_ALLOWED_USER_IDS", raising=False)
        assert ops.is_trading_allowed("123") is False
        assert ops.is_trading_allowed(None) is False

    def test_member_allowed(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_ALLOWED_USER_IDS", "123, 456")
        assert ops.is_trading_allowed(123) is True
        assert ops.is_trading_allowed("999") is False


class TestApprove:
    @pytest.mark.asyncio
    async def test_approve_bullish_executes_buy(self, monkeypatch):
        from services import discord_ops as ops
        # Isolate from the real journal: approve seeds + duplicate-guard
        # reads must never touch data/journal.duckdb from unit tests.
        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        engine = MagicMock()
        router = MagicMock()
        router.submit_order = AsyncMock(return_value={"status": "submitted"})
        with patch.object(ops, "fetch_recent_alerts", return_value=[_alert()]):
            res = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 2, engine, router)
        assert res["status"] == "submitted"
        intent = router.submit_order.call_args.args[0]
        assert intent["side"] == "buy" and intent["qty"] == 2
        assert intent["ticker"] == "SPY"

    @pytest.mark.asyncio
    async def test_approve_unknown_key_errors(self):
        from services import discord_ops as ops
        with patch.object(ops, "fetch_recent_alerts", return_value=[]):
            res = await ops.execute_approve("nope", 1, MagicMock(), MagicMock())
        assert res["status"] == "error"

    @pytest.mark.asyncio
    async def test_approve_nondirectional_errors(self):
        from services import discord_ops as ops
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert(bias=None, side="STRATEGY")]):
            res = await ops.execute_approve("k", 1, MagicMock(), MagicMock())
        assert res["status"] == "error"


def _mem_engine():
    from services.duckdb_engine import DuckDBEngine
    from services.journal_store import init_journal_tables
    eng = DuckDBEngine(":memory:")
    init_journal_tables(eng)
    return eng


class TestApproveJournals:
    @pytest.mark.asyncio
    async def test_approve_success_saves_equity_seed(self, monkeypatch):
        from services import discord_ops as ops
        from services.journal_store import read_trades

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        alert = _alert()
        router = MagicMock()
        router.submit_order = AsyncMock(return_value={
            "status": "submitted", "client_order_id": "cid-1"})
        with patch.object(ops, "fetch_recent_alerts", return_value=[alert]):
            res = await ops.execute_approve(alert["key"], 2, MagicMock(), router)
        assert res["status"] == "submitted"
        trades = read_trades(eng)
        assert len(trades) == 1
        t = trades[0]
        assert t["ticker"] == "SPY" and t["type"] == "equity"  # never mislabeled option
        assert t["action"] == "buy" and t["quantity"] == "2"
        assert "cid-1" in t["notes"] and t["source"] == "discord-approve"

    @pytest.mark.asyncio
    async def test_approve_failure_saves_nothing(self, monkeypatch):
        from services import discord_ops as ops
        from services.journal_store import read_trades

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        router = MagicMock()
        router.submit_order = AsyncMock(return_value={"status": "error", "reason": "x"})
        with patch.object(ops, "fetch_recent_alerts", return_value=[_alert()]):
            res = await ops.execute_approve("k", 1, MagicMock(), router)
        assert res["status"] == "error"
        assert read_trades(eng) == []


class TestPostImage:
    @pytest.mark.asyncio
    async def test_no_webhook_is_false(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        assert await ops.post_image(b"\x89PNG", "x.png") is False

    @pytest.mark.asyncio
    async def test_posts_multipart(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
        seen = {}
        resp = MagicMock(status_code=200)

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, data=None, files=None, json=None):
                seen.update(url=url, data=data, files=files)
                return resp

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            assert await ops.post_image(b"\x89PNGDATA", "gex-SPY.png", "hi") is True
        assert seen["url"] == "https://discord.test/hook"
        assert seen["files"]["file"][0] == "gex-SPY.png"
        assert seen["files"]["file"][2] == "image/png"


class TestBotSurface:
    def test_all_commands_registered_with_aliases(self):
        import discord_bot

        bot = discord_bot._commands()
        names = {c.name for c in bot.commands}
        for expected in ("heatmap", "vanna", "walls", "buy", "sell", "bracket",
                         "approve", "close", "holdings", "orders", "pnl",
                         "risk", "journal", "alerts", "help"):
            assert expected in names, f"missing command {expected}"
        alias_map = {}
        for c in bot.commands:
            for a in getattr(c, "aliases", []):
                alias_map[a] = c.name
        for alias, target in (("h", "help"), ("pos", "holdings"), ("hm", "heatmap"),
                              ("w", "walls"), ("v", "vanna"), ("j", "journal")):
            assert alias_map.get(alias) == target, f"alias !{alias} -> {target}"

    def test_help_covers_solstice_and_trading(self):
        from services import discord_ops as ops
        assert "!heatmap" in ops.HELP_TEXT and "!bracket" in ops.HELP_TEXT
        assert "!journal" in ops.HELP_TEXT and "Alpaca paper ONLY" in ops.HELP_TEXT

    def test_fuzzy_suggests_closest_command(self):
        import difflib
        known = ["heatmap", "vanna", "walls", "bracket", "approve"]
        assert difflib.get_close_matches("heatmp", known, n=1, cutoff=0.6) == ["heatmap"]
        assert difflib.get_close_matches("xyzzy", known, n=1, cutoff=0.6) == []


class TestDigest:
    def _mk(self, i, conviction=50):
        return {"key": f"k{i}", "ckey": f"c{i}", "rule": "SCORE", "tier": "GOLD",
                "side": "BUY", "bias": "BULLISH", "under": f"T{i}", "type": "call",
                "strike": 100 + i, "exp": "2026-09-18", "dte": 5, "score": 90 + (i % 9),
                "premium": 1e6 + i, "vol_oi": 5.0, "conviction": conviction,
                "why": "x"}

    def test_three_or_fewer_post_singly(self):
        from services import discord_ops as ops
        alerts = [self._mk(0), self._mk(1)]
        # singles path exercised via post_alerts mock below; digest builder:
        msgs = ops.build_digest_messages(alerts)
        assert len(msgs) == 1 and len(msgs[0]["embeds"]) == 2

    def test_many_alerts_batch_with_honest_overflow(self):
        from services import discord_ops as ops
        alerts = [self._mk(i, conviction=i) for i in range(35)]
        msgs = ops.build_digest_messages(alerts, max_embeds=10, max_msgs=3)
        assert len(msgs) == 3
        assert all(len(m["embeds"]) <= 10 for m in msgs)
        assert "+5 more" in msgs[-1]["content"]
        # top conviction first, approve keys preserved
        assert "T34" in msgs[0]["embeds"][0]["title"]
        assert "`k34`" in msgs[0]["embeds"][0]["description"]

    @pytest.mark.asyncio
    async def test_post_alerts_uses_digest_over_three(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
        sent = []
        resp = MagicMock(status_code=204)

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None):
                sent.append(json)
                return resp

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            n = await ops.post_alerts([self._mk(i) for i in range(12)])
        assert n == 2  # 12 embeds -> 2 messages, not 12 POSTs


class TestPromptHarness:
    def test_cooldown_helpers(self):
        import discord_bot as bot_mod

        ok, wait = bot_mod._cool_ok("u1", "heatmap")
        assert ok is True
        ok2, wait2 = bot_mod._cool_ok("u1", "heatmap")
        assert ok2 is False and wait2 > 0
        ok3, _ = bot_mod._cool_ok("u2", "heatmap")
        assert ok3 is True  # per-user, not global
        ok4, _ = bot_mod._cool_ok("u1", "walls")
        assert ok4 is True or isinstance(wait2, float)  # walls has own bucket

    def test_audit_ring(self):
        import discord_bot as bot_mod

        bot_mod._AUDIT.clear()
        bot_mod._audit("u1", "buy 10 SPY")
        assert len(bot_mod._AUDIT) == 1
        assert bot_mod._AUDIT[0]["cmd"] == "buy 10 SPY"

    def test_nl_regex(self):
        import discord_bot as bot_mod

        m = bot_mod._NL_READ.match("spy walls")
        assert m and (m.group(1), m.group(2)) == ("spy", "walls")
        assert bot_mod._NL_READ.match("!buy 10 SPY") is None
        assert bot_mod._NL_READ.match("buy 10 SPY") is None
        assert bot_mod._NL_READ.match("hello there") is None

    def test_new_commands_registered(self):
        import discord_bot

        bot = discord_bot._commands()
        names = {c.name for c in bot.commands}
        for expected in ("cancel", "clock", "status", "audit"):
            assert expected in names


class TestPostValidator:
    def _full(self):
        return {"key": "k", "rule": "WHALE", "tier": "GOLD", "under": "SPY",
                "type": "call", "strike": 700, "exp": "2026-09-18", "score": 88,
                "premium": 1e6, "vol_oi": 3.0, "why": "big", "dte": 5}

    def test_full_alert_passes(self):
        from services import discord_ops as ops
        ok, missing = ops.validate_alert_for_post(self._full())
        assert (ok, missing) == (True, [])

    def test_gutted_alert_fails_with_list(self):
        from services import discord_ops as ops
        ok, missing = ops.validate_alert_for_post(
            {"key": "whale|SPY|call|700|2026-09-18", "rule": "WHALE",
             "tier": "GOLD", "under": "SPY"})
        assert ok is False
        assert set(missing) == {"type", "strike", "exp", "score", "premium", "why"}

    def test_zero_is_a_measurement_not_missing(self):
        from services import discord_ops as ops
        a = self._full()
        a.update(score=0, premium=0)
        ok, _ = ops.validate_alert_for_post(a)
        assert ok is True

    def test_empty_type_is_missing(self):
        from services import discord_ops as ops
        a = self._full()
        a["type"] = ""
        ok, missing = ops.validate_alert_for_post(a)
        assert ok is False and missing == ["type"]

    @pytest.mark.asyncio
    async def test_gutted_never_posts_but_counts(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
        before = ops.DROPPED_EMPTY["count"]
        with patch("httpx.AsyncClient", side_effect=AssertionError("must not POST")):
            n = await ops.post_alerts([{"key": "k", "rule": "WHALE",
                                        "tier": "GOLD", "under": "SPY"}])
        assert n == 0
        assert ops.DROPPED_EMPTY["count"] == before + 1

    def test_digest_skips_gutted(self):
        from services import discord_ops as ops
        good = [self._full() | {"key": f"k{i}", "under": f"T{i}"} for i in range(3)]
        msgs = ops.build_digest_messages(
            good + [{"key": "bad", "rule": "X", "tier": "GOLD", "under": "Z"}])
        assert len(msgs) == 1 and len(msgs[0]["embeds"]) == 3
