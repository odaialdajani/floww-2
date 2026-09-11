"""
backend/tests/test_public_api_only.py

Public-API-only policy tests (2026-09-03, architect directive):
no Schwab, no Alpha Vantage — every live market-data path is Public.com.

All tests are offline (mocked broker/provider). No live key required.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import server
from server import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bars(n: int = 30, start: float = 100.0) -> list[dict]:
    """Deterministic rising OHLCV bars for technical-indicator tests."""
    return [
        {"t": i, "o": start + i, "h": start + i + 1, "l": start + i - 1,
         "c": start + i, "v": 1000}
        for i in range(n)
    ]


def _fake_broker(**kwargs) -> MagicMock:
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="TEST-ACCT")
    for key, val in kwargs.items():
        setattr(broker, key, val)
    return broker


# ---------------------------------------------------------------------------
# 1. AlphaVantageProvider is a disabled stub
# ---------------------------------------------------------------------------

class TestAlphaVantageRetired:
    def test_disabled_by_default(self):
        from data_providers import AlphaVantageProvider
        with patch.dict(os.environ, {"ALPHA_VANTAGE_KEY": "some-key"}):
            p = AlphaVantageProvider()
        assert p.enabled is False

    @pytest.mark.asyncio
    async def test_quote_returns_none(self):
        from data_providers import AlphaVantageProvider
        p = AlphaVantageProvider()
        assert await p.get_quote("SPY") is None

    @pytest.mark.asyncio
    async def test_technical_returns_none(self):
        from data_providers import AlphaVantageProvider
        p = AlphaVantageProvider()
        assert await p.get_technical_indicator("SPY", "RSI") is None

    @pytest.mark.asyncio
    async def test_forex_returns_none(self):
        from data_providers import AlphaVantageProvider
        p = AlphaVantageProvider()
        assert await p.get_forex_rate("USD", "EUR") is None

    def test_status_reports_disabled(self):
        from data_providers import DataAggregator
        status = DataAggregator().get_status()
        assert status["public_api"]["enabled"] is True
        assert status["alphavantage"]["enabled"] is False


# ---------------------------------------------------------------------------
# 2. DataAggregator tries Public API first
# ---------------------------------------------------------------------------

class TestAggregatorPublicFirst:
    @pytest.mark.asyncio
    async def test_public_api_first(self):
        from data_providers import DataAggregator
        agg = DataAggregator()
        import services.public_api_adapter as adapter
        with patch.object(adapter, "fetch_spot_from_public_api",
                          new=AsyncMock(return_value=450.0)):
            result = await agg.get_spot_price("SPY")
        assert result is not None
        assert result["source"] == "public_api"
        assert result["price"] == 450.0

    @pytest.mark.asyncio
    async def test_falls_through_when_public_unavailable(self):
        from data_providers import DataAggregator
        agg = DataAggregator()
        agg.finnhub.get_quote = AsyncMock(return_value={"price": 451.0, "source": "finnhub"})
        import services.public_api_adapter as adapter
        with patch.object(adapter, "fetch_spot_from_public_api",
                          new=AsyncMock(return_value=None)):
            result = await agg.get_spot_price("SPY")
        assert result is not None
        assert result["source"] == "finnhub"


# ---------------------------------------------------------------------------
# 3. Schwab is deleted — no routes, no client module
# ---------------------------------------------------------------------------

class TestSchwabDeleted:
    def test_auth_url_absent(self):
        r = client.get("/api/schwab/auth-url")
        assert r.status_code == 404

    def test_accounts_absent(self):
        r = client.get("/api/schwab/accounts")
        assert r.status_code == 404

    def test_positions_absent(self):
        r = client.get("/api/schwab/positions/abc123")
        assert r.status_code == 404

    def test_sweeps_absent(self):
        r = client.get("/api/schwab/sweeps/abc123")
        assert r.status_code == 404

    def test_import_absent(self):
        r = client.post("/api/schwab/import-to-portfolio/x/abc123",
                        headers={"X-API-Key": "test-secret-key"})
        assert r.status_code == 404

    def test_admin_schwab_health_absent(self):
        r = client.get("/api/admin/schwab/health",
                       headers={"X-API-Key": "test-secret-key"})
        assert r.status_code == 404

    def test_client_module_deleted(self):
        # NOTE: bare `import schwab` still resolves — as a *namespace package*
        # for backend/tests/schwab/ (streamer-harness chaos tests, kept).
        # What must be gone is the brokerage client module file itself.
        import importlib.util
        from pathlib import Path
        assert not (Path(__file__).resolve().parents[1] / "schwab.py").exists()
        assert importlib.util.find_spec("routes.schwab") is None

    def test_router_module_deleted(self):
        import importlib.util
        assert importlib.util.find_spec("routes.schwab") is None


# ---------------------------------------------------------------------------
# 4. Alpha routes: live shims on Public API, 410 elsewhere
# ---------------------------------------------------------------------------

class TestAlphaShims:
    def test_quote_from_public(self):
        with patch("services.public_api_adapter.fetch_spot_from_public_api",
                   new=AsyncMock(return_value=450.0)):
            r = client.get("/api/alpha/quote/SPY")
        assert r.status_code == 200
        d = r.json()
        assert d["price"] == 450.0
        assert d["data_source"] == "public_api"

    def test_options_from_public(self):
        fake_chain = {"spot": 450.0, "expiries": ["2026-09-04"],
                      "contracts": [{"expiry": "2026-09-04", "strike": 450}]}
        with patch("services.public_api_adapter.fetch_chain_from_public_api",
                   new=AsyncMock(return_value=fake_chain)):
            r = client.get("/api/alpha/options/SPY")
        assert r.status_code == 200
        assert r.json()["data_source"] == "public_api"

    def test_technical_from_public_bars(self):
        with patch("services.public_api_adapter.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars())):
            r = client.get("/api/alpha/technical/SPY/RSI")
        assert r.status_code == 200
        d = r.json()
        assert d["indicator"] == "RSI"
        assert d["data_source"] == "public_api"
        assert d["value"] == 100.0  # monotonically rising → RSI 100

    def test_historical_from_public(self):
        payload = {"ticker": "SPY", "interval": "daily", "bars": _bars(5),
                   "n_bars": 5, "data_source": "public_api"}
        with patch("services.public_api_adapter.fetch_history_from_public_api",
                   new=AsyncMock(return_value=payload)):
            r = client.get("/api/alpha/historical/SPY")
        assert r.status_code == 200
        assert r.json()["data_source"] == "public_api"

    def test_intraday_from_public(self):
        with patch("services.public_api_adapter.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars(5))):
            r = client.get("/api/alpha/intraday/SPY?interval=5min")
        assert r.status_code == 200
        assert r.json()["data_source"] == "public_api"

    def test_overview_gone(self):
        r = client.get("/api/alpha/overview/SPY")
        assert r.status_code == 410
        assert r.json()["error"] == "alpha_vantage_retired"

    def test_market_status_gone(self):
        r = client.get("/api/alpha/market-status")
        assert r.status_code == 410

    def test_no_alphavantage_co_calls(self):
        # The vendor request helpers are deleted; no route may reference
        # the vendor host anymore.
        import inspect

        import routes.alpha_advantage as mod
        src = inspect.getsource(mod)
        assert "alphavantage.co" not in src
        assert not hasattr(mod, "_av_request")
        assert not hasattr(mod, "_av_request_circuit")
        # The quote path is served live from Public API.
        with patch("services.public_api_adapter.fetch_spot_from_public_api",
                   new=AsyncMock(return_value=1.0)):
            r = client.get("/api/alpha/quote/SPY")
            assert r.status_code == 200
            assert r.json()["data_source"] == "public_api"


# ---------------------------------------------------------------------------
# 5. New /api/public/* endpoints (mocked broker)
# ---------------------------------------------------------------------------

class TestPublicBarsHistoryTechnical:
    def test_bars(self):
        with patch("routes.public_api.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars(5))):
            r = client.get("/api/public/bars/SPY?interval=daily")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["n_bars"] == 5
        assert d["data_source"] == "public_api"

    def test_bars_502_when_unavailable(self):
        with patch("routes.public_api.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=None)):
            r = client.get("/api/public/bars/SPY")
        assert r.status_code == 502

    def test_history(self):
        payload = {"ticker": "SPY", "interval": "daily", "bars": _bars(5),
                   "n_bars": 5, "data_source": "public_api"}
        with patch("routes.public_api.fetch_history_from_public_api",
                   new=AsyncMock(return_value=payload)):
            r = client.get("/api/public/history/SPY")
        assert r.status_code == 200
        assert r.json()["n_bars"] == 5

    def test_technical_sma(self):
        with patch("routes.public_api.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars(30))):
            r = client.get("/api/public/technical/SPY/SMA?time_period=10")
        assert r.status_code == 200
        d = r.json()
        assert d["indicator"] == "SMA"
        # closes 100..129 → SMA(10) of last 10 = mean(120..129) = 124.5
        assert d["value"] == pytest.approx(124.5)

    def test_technical_bad_indicator_400(self):
        with patch("routes.public_api.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars(30))):
            r = client.get("/api/public/technical/SPY/NOPE")
        assert r.status_code == 400

    def test_expirations(self):
        broker = _fake_broker()
        broker.get_option_expirations = AsyncMock(return_value=["2026-09-04"])
        with patch("routes.public_api._get_broker", new=AsyncMock(return_value=broker)):
            r = client.get("/api/public/expirations/SPY")
        assert r.status_code == 200
        assert r.json()["expirations"] == ["2026-09-04"]


# ---------------------------------------------------------------------------
# 6. Local technical math
# ---------------------------------------------------------------------------

class TestTechnicalMath:
    def test_rsi_rising_is_100(self):
        from services.public_api_adapter import compute_technical_from_bars
        out = compute_technical_from_bars("SPY", "RSI", _bars(30), 14)
        assert out["value"] == 100.0

    def test_rsi_flat_is_100(self):
        from services.public_api_adapter import compute_technical_from_bars
        flat = [{"t": i, "o": 100, "h": 100, "l": 100, "c": 100, "v": 1} for i in range(30)]
        out = compute_technical_from_bars("SPY", "RSI", flat, 14)
        assert out["value"] == 100.0

    def test_sma_value(self):
        from services.public_api_adapter import compute_technical_from_bars
        out = compute_technical_from_bars("SPY", "SMA", _bars(30), 10)
        assert out["value"] == pytest.approx(124.5)

    def test_macd_positive_on_rise(self):
        from services.public_api_adapter import compute_technical_from_bars
        out = compute_technical_from_bars("SPY", "MACD", _bars(60), 14)
        assert out["value"] > 0

    def test_unsupported_indicator(self):
        from services.public_api_adapter import compute_technical_from_bars
        out = compute_technical_from_bars("SPY", "NOPE", _bars(30), 14)
        assert "error" in out


# ---------------------------------------------------------------------------
# 8. Chain cache: TTL + coalescing + stale-serve (rate-limit shield)
# ---------------------------------------------------------------------------

class TestChainCache:
    @pytest.fixture(autouse=True)
    def _clean(self):
        import services.public_api_adapter as adapter
        adapter._clear_chain_cache()
        yield
        adapter._clear_chain_cache()

    def _broker(self, spot=450.0, expiries=None):
        broker = MagicMock()
        broker.get_trading_account.return_value = MagicMock(account_id="TEST-ACCT")
        broker.get_option_expirations = AsyncMock(
            return_value=expiries or ["2026-09-18", "2026-09-25"])
        q = MagicMock()
        q.mid_price = spot
        q.last = spot
        broker.get_quotes = AsyncMock(return_value=[q])
        broker.get_option_chain_parsed = AsyncMock(return_value={"calls": [], "puts": []})
        return broker

    @pytest.mark.asyncio
    async def test_second_call_served_from_cache(self):
        import services.public_api_adapter as adapter
        broker = self._broker()
        with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker)):
            # Empty chain -> None is NOT cached (falsy contracts); use expiries
            # with no parsed data is also None... so give it contracts via
            # parsed side effect below instead.
            broker.get_option_chain_parsed = AsyncMock(return_value={
                "calls": [MagicMock(symbol="X", expiration="2026-09-18", strike=450,
                                    open_interest=10, iv=0.2, delta=0.5, gamma=0.01,
                                    theta=0, vega=0.1, bid=1.0, ask=1.2, volume=5)],
                "puts": [],
            })
            r1 = await adapter.fetch_chain_from_public_api("CACHE1", max_expiries=1)
            r2 = await adapter.fetch_chain_from_public_api("CACHE1", max_expiries=1)
        assert r1 is not None and r2 is not None
        assert r1["stale"] is False and r2["stale"] is False
        assert broker.get_option_expirations.await_count == 1

    @pytest.mark.asyncio
    async def test_different_broker_refetches(self):
        import services.public_api_adapter as adapter
        with patch.object(adapter, "_get_broker",
                          new=AsyncMock(return_value=self._broker(spot=450.0))):
            await adapter.fetch_chain_from_public_api("CACHE2", max_expiries=1)
        # Different broker object, same key -> must NOT serve the other
        # broker's entry (unit-test isolation + key-rotation safety).
        b2 = self._broker(spot=451.0)
        with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=b2)):
            r = await adapter.fetch_chain_from_public_api("CACHE2", max_expiries=1)
        assert b2.get_option_expirations.await_count == 1
        assert r is None or r.get("spot") in (450.0, 451.0)

    @pytest.mark.asyncio
    async def test_stale_served_on_failure(self):
        import services.public_api_adapter as adapter
        broker = self._broker()
        broker.get_option_chain_parsed = AsyncMock(return_value={
            "calls": [MagicMock(symbol="X", expiration="2026-09-18", strike=450,
                                open_interest=10, iv=0.2, delta=0.5, gamma=0.01,
                                theta=0, vega=0.1, bid=1.0, ask=1.2, volume=5)],
            "puts": [],
        })
        with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker)):
            r1 = await adapter.fetch_chain_from_public_api("CACHE3", max_expiries=1)
            assert r1 is not None
            # Now break the upstream for the SAME broker object.
            broker.get_option_expirations = AsyncMock(side_effect=RuntimeError("down"))
            with patch.object(adapter, "_CHAIN_CACHE_TTL", 0):
                r2 = await adapter.fetch_chain_from_public_api("CACHE3", max_expiries=1)
        assert r2 is not None and r2["stale"] is True
        assert r2["contracts"] == r1["contracts"]


# ---------------------------------------------------------------------------
# 9. Health reports public_api, retired stub stays disabled
# ---------------------------------------------------------------------------

class TestHealthPublicApi:
    def test_public_api_healthy_with_key(self):
        with patch.dict(os.environ, {"PUBLIC_API_KEY": "test-key"}):
            r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["checks"]["public_api"]["status"] == "healthy"

    def test_alpha_stub_disabled_never_degrades(self):
        with patch.dict(os.environ, {"PUBLIC_API_KEY": "test-key"}):
            r = client.get("/api/health")
        body = r.json()
        assert body["checks"]["alpha_vantage"]["status"] == "disabled"
        assert body["status"] == "healthy"

    def test_data_status_reports_policy(self):
        r = client.get("/api/data/status")
        assert r.status_code == 200
        d = r.json()
        assert d["primary"] == "public_api"
        assert "alphavantage" in d["retired"]
        assert "schwab" in d["retired"]
        assert d["providers"]["alphavantage"]["enabled"] is False


# ---------------------------------------------------------------------------
# 10. Brokerage crash guards (2026-09-04 audit fixes)
# ---------------------------------------------------------------------------

def _mock_brokerage():
    """Broker with a trading account + one scalar-lastPrice position."""
    import types
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="TEST-ACCT")
    pos = types.SimpleNamespace(
        raw={},
        instrument={"symbol": "SPY", "name": "SPY", "type": "EQUITY",
                    "lastPrice": 450.0},  # scalar (was: .get().get() crash)
        cost_basis=4000.0,
        current_value=4500.0,
        symbol="SPY",
        name="SPY",
        quantity=10,
        last_price=450.0,
        current_price=450.0,
        position_daily_gain={},
    )
    portfolio = types.SimpleNamespace(
        positions=[pos],
        buying_power=10000.0,
        cash=5000.0,
        options_buying_power=8000.0,
        total_account_value=15000.0,
        orders=[],
    )
    broker.get_portfolio = AsyncMock(return_value=portfolio)
    return broker


class TestBrokerageGuards:
    def test_portfolio_scalar_lastprice_no_500(self):
        import routes.public_brokerage as mod
        with patch.object(mod, "_get_broker", new=AsyncMock(return_value=_mock_brokerage())):
            r = client.get("/api/public/portfolio")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["positions"][0]["symbol"] == "SPY"

    @pytest.mark.parametrize("bad", ["abc", None, "", -1, 0])
    def test_place_order_rejects_bad_quantity_422(self, bad):
        import routes.public_brokerage as mod
        broker = _mock_brokerage()
        broker.place_order = AsyncMock()
        with patch.object(mod, "_get_broker", new=AsyncMock(return_value=broker)):
            r = client.post("/api/public/order", headers={"X-API-Key": "test-secret-key"}, json={
                "symbol": "AAPL", "side": "BUY", "order_type": "MARKET",
                "quantity": bad, "time_in_force": "DAY",
                "instrument_type": "EQUITY",
            })
        assert r.status_code == 422, r.text
        broker.place_order.assert_not_called()

    def test_place_order_rejects_bad_prices_422(self):
        import routes.public_brokerage as mod
        broker = _mock_brokerage()
        broker.place_order = AsyncMock()
        with patch.object(mod, "_get_broker", new=AsyncMock(return_value=broker)):
            r = client.post("/api/public/order", headers={"X-API-Key": "test-secret-key"}, json={
                "symbol": "AAPL", "side": "BUY", "order_type": "LIMIT",
                "quantity": 1, "limit_price": "abc",
                "time_in_force": "DAY", "instrument_type": "EQUITY",
            })
        assert r.status_code == 422, r.text
        broker.place_order.assert_not_called()
