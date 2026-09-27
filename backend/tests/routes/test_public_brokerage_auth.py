"""Public.com brokerage route auth tests (audit V2, Critical #2/#3).

Every /api/public/* brokerage endpoint requires the master key
(X-API-Key). New orders additionally refuse with 403 unless FLOWW_ENABLE_LIVE_PUBLIC=1;
authenticated cancellations remain available while entries are disabled.
(fail-closed kill-switch; validation still runs first so 422
contracts hold while disarmed).

All tests are offline (mocked broker). No live key required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)

KEY = {"X-API-Key": "test-secret-key"}  # matches backend/tests/conftest.py


def _broker() -> MagicMock:
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="TEST-ACCT")
    broker.place_order = AsyncMock(return_value=MagicMock(
        status="PENDING", raw={}, order_id="oid-1", symbol="AAPL",
        side="BUY", order_type="MARKET", quantity=1, price=None,
        created_at="2026-09-27T00:00:00Z",
    ))
    broker.cancel_order = AsyncMock(return_value={"status": "CANCELED"})
    return broker


def _patched_broker(broker=None):
    import routes.public_brokerage as mod
    return patch.object(
        mod, "_get_broker",
        new=AsyncMock(return_value=broker if broker is not None else _broker()),
    )


class TestBrokerageReadsRequireMasterKey:
    def test_portfolio_no_key_401(self):
        r = client.get("/api/public/portfolio")
        assert r.status_code == 401, r.text

    def test_orders_no_key_401(self):
        r = client.get("/api/public/orders")
        assert r.status_code == 401, r.text

    def test_account_no_key_401(self):
        r = client.get("/api/public/account")
        assert r.status_code == 401, r.text

    def test_portfolio_with_key_no_broker_502(self):
        import routes.public_brokerage as mod
        with patch.object(mod, "_get_broker", new=AsyncMock(return_value=None)):
            r = client.get("/api/public/portfolio", headers=KEY)
        assert r.status_code == 502, r.text


class TestOrderKillSwitch:
    def _order(self, **kw):
        body = {"symbol": "AAPL", "side": "BUY", "order_type": "MARKET",
                "quantity": 1, "time_in_force": "DAY",
                "instrument_type": "EQUITY"}
        body.update(kw)
        return body

    def test_place_order_disarmed_403(self, monkeypatch):
        monkeypatch.delenv("FLOWW_ENABLE_LIVE_PUBLIC", raising=False)
        broker = _broker()
        with _patched_broker(broker):
            r = client.post("/api/public/order", headers=KEY, json=self._order())
        assert r.status_code == 403, r.text
        # NOTE: server's global HTTPException handler stringifies dict
        # details into {"error": "..."} — assert on the marker substring.
        assert "live_trading_disabled" in r.json()["error"]
        broker.place_order.assert_not_called()

    def test_place_order_disarmed_still_validates_422(self, monkeypatch):
        monkeypatch.delenv("FLOWW_ENABLE_LIVE_PUBLIC", raising=False)
        with _patched_broker():
            r = client.post("/api/public/order", headers=KEY,
                            json=self._order(quantity=-1))
        assert r.status_code == 422, r.text

    def test_place_order_armed_proceeds(self, monkeypatch):
        monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
        broker = _broker()
        with _patched_broker(broker):
            r = client.post("/api/public/order", headers=KEY, json=self._order())
        assert r.status_code == 200, r.text
        broker.place_order.assert_called_once()

    def test_cancel_disarmed_remains_available(self, monkeypatch):
        monkeypatch.delenv("FLOWW_ENABLE_LIVE_PUBLIC", raising=False)
        broker = _broker()
        with _patched_broker(broker):
            r = client.post("/api/public/order/oid-1/cancel", headers=KEY)
        assert r.status_code == 200, r.text
        broker.cancel_order.assert_awaited_once()

    def test_cancel_armed_proceeds(self, monkeypatch):
        monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
        broker = _broker()
        with _patched_broker(broker):
            r = client.post("/api/public/order/oid-1/cancel", headers=KEY)
        assert r.status_code == 200, r.text
        broker.cancel_order.assert_called_once()
