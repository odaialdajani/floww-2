"""U15: execution default-deny boundary contract (OpenCode takeover slice).

Pinned at the current snapshot with a fake broker and isolated stores.
No live calls (LIVE flag never set here), no service restarts.

- Disarmed entry refuses 403 with ZERO broker placements (kill-switch
  holds even for a fully valid order body).
- Authenticated cancellation stays available while entries are disarmed.
- The privileged admission router stays UNMOUNTED in the production app
  (test-local mounts don't count; production openapi census decides).
"""
import sys

sys.path.insert(0, "backend")

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

KEY = {"X-API-Key": "test-secret-key"}


def _mounted(monkeypatch):
    import routes.public_brokerage as pb
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    monkeypatch.setenv("API_SECRET_KEY", "test-secret-key")
    monkeypatch.delenv("FLOWW_ENABLE_LIVE_PUBLIC", raising=False)
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="TEST-ACCT")
    broker.place_order = AsyncMock(return_value={"status": "PENDING", "order_id": "oid-1"})
    broker.cancel_order = AsyncMock(return_value={"status": "CANCELED"})
    monkeypatch.setattr(pb, "_get_broker", AsyncMock(return_value=broker))
    app = FastAPI()
    app.include_router(pb.router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False), broker


def _valid_order():
    return {"symbol": "AAPL", "side": "BUY", "order_type": "MARKET",
            "quantity": 1, "time_in_force": "DAY", "instrument_type": "EQUITY"}


def test_disarmed_entry_refuses_with_zero_placements(monkeypatch):
    client, broker = _mounted(monkeypatch)
    response = client.post("/api/public/order", json=_valid_order(), headers=KEY)
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["error"] == "live_trading_disabled"
    assert broker.place_order.await_count == 0


def test_disarmed_entry_refuses_before_broker_existence_matters(monkeypatch):
    import routes.public_brokerage as pb

    client, broker = _mounted(monkeypatch)
    monkeypatch.setattr(pb, "_get_broker", AsyncMock(return_value=None))
    response = client.post("/api/public/order", json=_valid_order(), headers=KEY)
    assert response.status_code == 403, response.text
    assert broker.place_order.await_count == 0


def test_cancel_stays_available_while_entries_disarmed(monkeypatch):
    client, broker = _mounted(monkeypatch)
    response = client.post("/api/public/order/oid-1/cancel", headers=KEY)
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "order_id": "oid-1",
                               "status": "CANCELED", "data_source": "public_api"}
    assert broker.cancel_order.await_count == 1
    assert broker.place_order.await_count == 0


def test_cancel_requires_application_key(monkeypatch):
    client, _ = _mounted(monkeypatch)
    response = client.post("/api/public/order/oid-1/cancel")
    assert response.status_code in (401, 403), response.text


def test_privileged_admission_router_unmounted_in_production():
    import server

    paths = sorted({route.path for route in server.app.routes
                    if getattr(route, "path", "")})
    assert not any(path == "/admission" or path.startswith("/admission/")
                   for path in paths), [p for p in paths if "admission" in p]
