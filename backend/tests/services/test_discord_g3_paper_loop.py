"""G3 paper-loop pins (GATE-2 OFFLINE half).

Proves the Discord approve path works through the REAL OrderRouter +
a broker stub — today's code sends market orders the router rejects by
default (ALLOW_MARKET_ORDERS=False), so the whole paper loop is dead
before any network or Discord transport is involved.

Paper-only: broker is an in-memory stub; asserts paper venue constant.
No POST/DELETE, no keys, no Discord connection.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _alert(key="score|SPY|call|745|2099-01-08"):
    return {
        "key": key, "rule": "SCORE", "tier": "GOLD", "under": "SPY",
        "type": "call", "strike": 745, "exp": "2099-01-08", "score": 90,
        "premium": 120.0, "bias": "BULLISH", "side": "BUY",
        "under_price": 750.0, "why": "test flow",
        "key_levels": {"entry": 1.2, "invalidation": 0.8, "target": 2.0},
    }


def _accepting_broker():
    broker = MagicMock()
    broker.place_stock_order = AsyncMock(
        return_value={"id": "alpaca-1", "status": "accepted"})
    broker.get_order_by_client_order_id = AsyncMock(return_value=None)
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_order = AsyncMock(
        return_value={"id": "alpaca-1", "status": "filled",
                      "filled_avg_price": "751.0", "filled_qty": "1"})
    return broker


def _mem_engine():
    from services.duckdb_engine import DuckDBEngine
    from services.journal_store import init_journal_tables
    eng = DuckDBEngine(":memory:")
    init_journal_tables(eng)
    return eng


class TestApproveThroughRealRouter:
    @pytest.mark.asyncio
    async def test_approve_market_submits_paper(self, monkeypatch):
        """Approve must submit through the real router (market opt-in)."""
        from services import discord_ops as ops
        from services.order_router import OrderRouter

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        router = OrderRouter("paper", broker=_accepting_broker())
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert()]):
            res = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
        assert res["status"] == "submitted", res
        assert res["order"]["venue"] == "alpaca-paper"

    @pytest.mark.asyncio
    async def test_duplicate_approve_suppressed(self, monkeypatch):
        """Second identical approve must not place a second broker order."""
        from services import discord_ops as ops
        from services.order_router import OrderRouter

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        broker = _accepting_broker()
        router = OrderRouter("paper", broker=broker)
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert()]):
            first = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
            second = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
        assert first["status"] == "submitted"
        assert second["status"] == "duplicate", second
        assert broker.place_stock_order.call_count == 1

    @pytest.mark.asyncio
    async def test_journal_marks_submission_not_fill(self, monkeypatch):
        """Journal seed must not read as a confirmed fill."""
        from services import discord_ops as ops
        from services.journal_store import read_trades
        from services.order_router import OrderRouter

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        router = OrderRouter("paper", broker=_accepting_broker())
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert()]):
            await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
        notes = read_trades(eng)[0]["notes"]
        assert "not a confirmed fill" in notes


class TestPaperTransportPins:
    def test_paper_venue_hardcoded(self):
        import alpaca_client
        assert alpaca_client.ALPACA_BASE_URL == \
            "https://paper-api.alpaca.markets"

    @pytest.mark.asyncio
    async def test_get_order_read_path(self):
        from alpaca_client import AlpacaClient
        c = AlpacaClient.__new__(AlpacaClient)
        c._api_key = "K"
        c._secret_key = "S"
        with patch.object(AlpacaClient, "_get",
                          new=AsyncMock(return_value={"id": "a1"})) as g:
            assert (await c.get_order("a1"))["id"] == "a1"
        assert "a1" in g.call_args.args[0]

    @pytest.mark.asyncio
    async def test_stock_order_transmits_client_order_id(self):
        """The venue, not only the router cache, receives the retry key."""
        from alpaca_client import AlpacaClient
        c = _client_like()
        with patch.object(AlpacaClient, "_post", new=AsyncMock(
                return_value={"id": "a1", "status": "accepted"})) as post:
            await c.place_stock_order(
                "SPY", 1, client_order_id="floww-logical-order-1")
        assert post.call_args.args[1]["client_order_id"] == \
            "floww-logical-order-1"

    @pytest.mark.asyncio
    async def test_get_order_by_client_id_read_path(self):
        from alpaca_client import AlpacaClient
        c = _client_like()
        with patch.object(AlpacaClient, "_get", new=AsyncMock(
                return_value={"id": "a1"})) as get:
            assert (await c.get_order_by_client_order_id("floww-1"))["id"] == "a1"
        assert get.call_args.args[0].endswith("/v2/orders:by_client_order_id")
        assert get.call_args.kwargs["params"] == {
            "client_order_id": "floww-1"}


def _client_like():
    from alpaca_client import AlpacaClient
    c = AlpacaClient.__new__(AlpacaClient)
    c._api_key = "K"
    c._secret_key = "S"
    return c


class TestHonestFailures:
    """G3.3: every failure mode gets a test + an honest message."""

    def test_classify_403_names_approval(self):
        from alpaca_client import classify_alpaca_http
        v = classify_alpaca_http(403, "options trading not approved")
        assert v["ok"] is False
        assert "approval" in v["reason"].lower()

    def test_classify_401_names_keys(self):
        from alpaca_client import classify_alpaca_http
        assert classify_alpaca_http(401)["ok"] is False
        assert "key" in classify_alpaca_http(401)["reason"].lower()

    def test_classify_422_echoes_body(self):
        from alpaca_client import classify_alpaca_http
        v = classify_alpaca_http(422, "qty must be positive")
        assert v["ok"] is False and "qty must be positive" in v["reason"]

    def test_classify_429_names_backoff(self):
        from alpaca_client import classify_alpaca_http
        v = classify_alpaca_http(429, "")
        assert v["ok"] is False and "back" in v["reason"].lower()

    def test_classify_207_partial_ok(self):
        from alpaca_client import classify_alpaca_http
        v = classify_alpaca_http(207, "")
        assert v["ok"] is True and v["partial"] is True

    def test_classify_200_ok(self):
        from alpaca_client import classify_alpaca_http
        v = classify_alpaca_http(200, "")
        assert v["ok"] is True and v["partial"] is False

    @pytest.mark.asyncio
    async def test_router_timeout_is_named_error(self):
        from services.order_router import OrderRouter
        broker = MagicMock()
        broker.place_stock_order = AsyncMock(side_effect=TimeoutError())
        router = OrderRouter("paper", broker=broker)
        res = await router.submit_order({
            "ticker": "SPY", "side": "buy", "qty": 1,
            "order_type": "limit", "limit_price": 700.0,
            "signal_id": "sig-timeout", "timestamp_us": 3000000})
        assert res["status"] == "error"
        assert "TimeoutError" in res["reason"], res

    @pytest.mark.asyncio
    async def test_router_207_partial_preserved(self):
        from services.order_router import OrderRouter
        broker = MagicMock()
        broker.place_stock_order = AsyncMock(
            return_value={"id": "p1", "status": "partially_filled"})
        router = OrderRouter("paper", broker=broker)
        res = await router.submit_order({
            "ticker": "SPY", "side": "buy", "qty": 2,
            "order_type": "limit", "limit_price": 700.0,
            "signal_id": "sig-207", "timestamp_us": 4000000})
        assert res["status"] == "submitted"
        assert res["broker"]["status"] == "partially_filled"


class TestBracketLegs:
    @pytest.mark.asyncio
    async def test_legs_live_verified(self):
        from alpaca_client import AlpacaClient
        c = AlpacaClient.__new__(AlpacaClient)
        c._api_key = "K"
        c._secret_key = "S"
        order = {"id": "b1", "status": "held",
                 "legs": [{"id": "l1", "status": "accepted", "side": "sell", "qty": "5"},
                          {"id": "l2", "status": "accepted", "side": "sell", "qty": "5"}]}
        with patch.object(AlpacaClient, "_get", new=AsyncMock(return_value=order)):
            v = await c.verify_bracket_legs("b1")
        assert v["verified"] is True and len(v["legs"]) == 2

    @pytest.mark.asyncio
    async def test_missing_leg_fails_honest(self):
        from alpaca_client import AlpacaClient
        c = AlpacaClient.__new__(AlpacaClient)
        c._api_key = "K"
        c._secret_key = "S"
        order = {"id": "b2", "status": "held",
                 "legs": [{"id": "l1", "status": "rejected", "side": "sell", "qty": "5"}]}
        with patch.object(AlpacaClient, "_get", new=AsyncMock(return_value=order)):
            v = await c.verify_bracket_legs("b2")
        assert v["verified"] is False
        assert "rejected" in v["reason"].lower()

    @pytest.mark.asyncio
    async def test_no_order_found(self):
        from alpaca_client import AlpacaClient
        c = AlpacaClient.__new__(AlpacaClient)
        c._api_key = "K"
        c._secret_key = "S"
        with patch.object(AlpacaClient, "_get", new=AsyncMock(return_value=None)):
            v = await c.verify_bracket_legs("nope")
        assert v["verified"] is False


class TestU3OptionReadiness:
    @pytest.mark.asyncio
    async def test_option_payload_shape_paper(self):
        """U3 dry run: a valid 1-contract OCC builds the right paper payload.

        No POST to the venue here (mocked). Symbol is the live Fri weekly
        as of 2026-09-06 (SPY 760C, venue-verified active); the assertion
        is shape-only so it never rots when the week rolls — resolve the
        live contract via the paper contracts API before any witnessed
        attempt (the old Sep-04 week is already expired).
        """
        from alpaca_client import AlpacaClient
        c = _client_like()
        with patch.object(AlpacaClient, "_post", new=AsyncMock(
                return_value={"id": "o1", "status": "accepted"})) as post:
            res = await c.place_option_order("SPY260911C00760000", 1, "buy", "limit", 11.4)
        assert res and res["status"] == "accepted"
        sent = post.call_args.args[1]
        assert sent["symbol"] == "SPY260911C00760000"
        assert sent["qty"] == "1" and sent["limit_price"] == "11.4"

    @pytest.mark.asyncio
    async def test_bad_occ_never_reaches_venue(self):
        from alpaca_client import AlpacaClient
        c = _client_like()
        with patch.object(AlpacaClient, "_post", new=AsyncMock(
                side_effect=AssertionError("must not POST"))) as post:
            assert await c.place_option_order("SPY", 1, "buy") is None
        assert post.call_count == 0


class TestReconcile:
    @pytest.mark.asyncio
    async def test_filled_reconcile_attached(self, monkeypatch):
        from services import discord_ops as ops
        from services.journal_store import read_trades
        from services.order_router import OrderRouter

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        router = OrderRouter("paper", broker=_accepting_broker())
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert()]):
            res = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
        assert res["status"] == "submitted"
        assert res["reconciliation"]["venue_status"] == "filled"
        notes = read_trades(eng)[0]["notes"]
        assert "not a confirmed fill" in notes
        assert "venue reports filled" in notes

    @pytest.mark.asyncio
    async def test_reconcile_unknown_without_broker_read(self, monkeypatch):
        import types

        from services import discord_ops as ops
        from services.order_router import OrderRouter

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        broker = types.SimpleNamespace(
            place_stock_order=AsyncMock(
                return_value={"id": "x1", "status": "accepted"}),
            get_positions=AsyncMock(return_value=[]))
        router = OrderRouter("paper", broker=broker)
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert()]):
            res = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
        assert res["status"] == "submitted"
        assert res["reconciliation"]["venue_status"] == "unknown"


class TestCloseRouteJournal:
    @pytest.mark.asyncio
    async def test_close_stamps_open_exit(self, monkeypatch):
        import routes.alpaca as route_mod
        from services.duckdb_engine import DuckDBEngine
        from services.journal_store import init_journal_tables, read_trades, save_seeds

        eng = DuckDBEngine(":memory:")
        init_journal_tables(eng)
        save_seeds(eng, [{
            "ticker": "SPY", "type": "equity", "action": "buy",
            "strike": 750.0, "expiry": "", "quantity": "1",
            "entry_price": 749.0, "exit_price": "",
            "entry_date": "2026-09-06T10:00:00", "exit_date": "",
            "notes": "seed", "source": "discord-approve"}])
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)

        fake_client = AsyncMock()
        fake_client.close_position = AsyncMock(return_value={
            "id": "close-1", "status": "filled", "filled_qty": "1",
            "symbol": "SPY", "side": "sell", "qty": "1",
            "filled_avg_price": "751.5",
            "message": "Position SPY close submitted", "source": "alpaca"})
        monkeypatch.setattr("alpaca_client.AlpacaClient", lambda: fake_client)

        res = await route_mod.close_position(symbol="SPY")
        assert res["message"] == "Position SPY close submitted"
        assert res.get("journal_closed") == 1
        assert res.get("journal_status") == "confirmed_fill"
        open_rows = [t for t in read_trades(eng) if not t.get("exit_date")]
        assert open_rows == []

    @pytest.mark.asyncio
    async def test_close_without_price_still_closes(self, monkeypatch):
        import routes.alpaca as route_mod
        from services.duckdb_engine import DuckDBEngine
        from services.journal_store import init_journal_tables

        eng = DuckDBEngine(":memory:")
        init_journal_tables(eng)
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)

        fake_client = AsyncMock()
        fake_client.close_position = AsyncMock(
            return_value={"message": "Position SPY closed", "source": "alpaca"})
        fake_client.get_bars = AsyncMock(return_value=None)
        monkeypatch.setattr("alpaca_client.AlpacaClient", lambda: fake_client)

        res = await route_mod.close_position(symbol="SPY")
        assert res["message"] == "Position SPY closed"
        assert "journal_closed" not in res

    @pytest.mark.asyncio
    async def test_close_does_not_stamp_daily_bar_as_execution(self, monkeypatch):
        """An accepted-but-unfilled close must leave journal P&L open."""
        import routes.alpaca as route_mod
        from services.duckdb_engine import DuckDBEngine
        from services.journal_store import init_journal_tables, read_trades, save_seeds

        eng = DuckDBEngine(":memory:")
        init_journal_tables(eng)
        save_seeds(eng, [{
            "ticker": "SPY", "type": "equity", "action": "buy",
            "strike": 750.0, "expiry": "", "quantity": "1",
            "entry_price": 749.0, "exit_price": "",
            "entry_date": "2026-09-06T10:00:00", "exit_date": "",
            "notes": "seed", "source": "discord-approve"}])
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)

        fake_client = AsyncMock()
        fake_client.close_position = AsyncMock(return_value={
            "id": "close-1", "status": "accepted",
            "symbol": "SPY", "side": "sell", "qty": "1",
            "message": "Position SPY close submitted", "source": "alpaca"})
        fake_client.get_order = AsyncMock(return_value={
            "id": "close-1", "status": "accepted",
            "filled_avg_price": None, "filled_qty": "0"})
        fake_client.get_bars = AsyncMock(return_value=[{"c": 751.5}])
        monkeypatch.setattr("alpaca_client.AlpacaClient", lambda: fake_client)

        res = await route_mod.close_position(symbol="SPY")
        assert res.get("journal_closed") is None
        assert res.get("journal_status") == "pending_fill"
        assert [t for t in read_trades(eng) if not t.get("exit_date")]


class TestFeedUnavailable:
    @pytest.mark.asyncio
    async def test_none_feed_says_unavailable(self, monkeypatch):
        from services import discord_ops as ops

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        router = MagicMock()
        router.submit_order = AsyncMock()
        with patch.object(ops, "fetch_recent_alerts", return_value=None):
            res = await ops.execute_approve("any-key", 1, MagicMock(), router)
        assert res["status"] == "error"
        assert "unavailable" in res["reason"].lower()
        assert res["alert"] == "any-key"
        router.submit_order.assert_not_called()
