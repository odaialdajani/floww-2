"""
backend/tests/services/test_alpaca_paper.py — Alpaca paper venue pins.
Paper-hardcoded base URL, OCC normalization, option/bracket/read methods.
HTTP mocked; no network, no keys needed.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _client(**over):
    from alpaca_client import AlpacaClient
    c = AlpacaClient.__new__(AlpacaClient)
    c._api_key = "K"
    c._secret_key = "S"
    for k, v in over.items():
        setattr(c, k, v)
    return c


class TestPaperVenue:
    def test_base_url_is_paper(self):
        import alpaca_client
        assert alpaca_client.ALPACA_BASE_URL == "https://paper-api.alpaca.markets"
        assert "paper" in alpaca_client.ALPACA_BASE_URL

    def test_normalize_option_symbol(self):
        from alpaca_client import AlpacaClient
        assert AlpacaClient.normalize_option_symbol("SPY260904C00760000") == "SPY260904C00760000"
        assert AlpacaClient.normalize_option_symbol(" spy260904p00760000 ") == "SPY260904P00760000"
        assert AlpacaClient.normalize_option_symbol("SPY") == ""
        assert AlpacaClient.normalize_option_symbol("") == ""


class TestOptionOrders:
    @pytest.mark.asyncio
    async def test_option_order_posts_occ(self):
        from alpaca_client import AlpacaClient
        c = _client()
        with patch.object(AlpacaClient, "_post", new=AsyncMock(
                return_value={"id": "o1", "status": "accepted"})) as post:
            res = await c.place_option_order("SPY260904C00760000", 2, "buy", "limit", 3.5)
        assert res["status"] == "accepted"
        sent = post.call_args.args[1]
        assert sent["symbol"] == "SPY260904C00760000"
        assert sent["qty"] == "2" and sent["limit_price"] == "3.5"

    @pytest.mark.asyncio
    async def test_option_order_rejects_garbage(self):
        from alpaca_client import AlpacaClient
        c = _client()
        assert await c.place_option_order("SPY", 1, "buy") is None
        assert await c.place_option_order("SPY260904C00760000", 0, "buy") is None
        assert await c.place_option_order("SPY260904C00760000", 1, "buy", "weird") is None

    @pytest.mark.asyncio
    async def test_bracket_needs_legs(self):
        from alpaca_client import AlpacaClient
        c = _client()
        assert await c.place_bracket_order("SPY", 1, "buy") is None
        with patch.object(AlpacaClient, "_post", new=AsyncMock(
                return_value={"id": "b1", "status": "held", "legs": [{}, {}]})) as post:
            res = await c.place_bracket_order("SPY", 5, "buy", 700.0, 680.0)
        assert res["status"] == "held" and len(res["legs"]) == 2
        sent = post.call_args.args[1]
        assert sent["order_class"] == "bracket"
        assert sent["take_profit"] == {"limit_price": "700.0"}
        assert sent["stop_loss"] == {"stop_price": "680.0"}

    @pytest.mark.asyncio
    async def test_reads(self):
        from alpaca_client import AlpacaClient
        c = _client()
        with patch.object(AlpacaClient, "_get", new=AsyncMock(return_value={"equity": "1"})):
            assert (await c.get_account())["equity"] == "1"
        with patch.object(AlpacaClient, "_get", new=AsyncMock(return_value=[{"a": 1}])):
            assert await c.get_orders() == [{"a": 1}]
            assert await c.get_positions() == [{"a": 1}]
        with patch.object(AlpacaClient, "_get", new=AsyncMock(return_value={"is_open": True})):
            assert (await c.get_clock())["is_open"] is True
        with patch.object(AlpacaClient, "_get", new=AsyncMock(
                return_value={"bars": [{"c": 1}]})):
            assert await c.get_bars("SPY") == [{"c": 1}]
        with patch.object(AlpacaClient, "_get", new=AsyncMock(return_value={"nope": 1})):
            assert await c.get_bars("SPY") is None


class TestOptionRoute:
    @pytest.mark.asyncio
    async def test_route_journals_option_fill(self, monkeypatch):
        import routes.alpaca as route_mod
        from services.duckdb_engine import DuckDBEngine
        from services.journal_store import init_journal_tables, read_trades

        eng = DuckDBEngine(":memory:")
        init_journal_tables(eng)
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)

        fake_client = AsyncMock()
        fake_client.place_option_order = AsyncMock(
            return_value={"id": "oid-9", "status": "accepted"})
        monkeypatch.setattr("alpaca_client.AlpacaClient", lambda: fake_client)

        res = await route_mod.place_option_order(
            symbol="SPY260904C00760000", qty=2, side="buy",
            order_type="limit", limit_price=3.0)
        assert res["status"] == "accepted"
        trades = read_trades(eng)
        assert len(trades) == 1
        t = trades[0]
        assert t["type"] == "call" and t["strike"] == 760.0
        assert t["expiry"] == "2026-09-04" and t["source"] == "api-alpaca-option"

    def test_parse_occ(self):
        import routes.alpaca as route_mod
        assert route_mod._parse_occ("SPY260904C00760000") == {
            "type": "call", "strike": 760.0, "expiry": "2026-09-04"}
        assert route_mod._parse_occ("QQQ260904P00718000")["type"] == "put"
        assert route_mod._parse_occ("SPY") is None
