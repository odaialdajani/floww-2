"""I04 mounted test-local full-stack: admission surfaces + money entry.

One throwaway FastAPI app mounts BOTH the production-mounted public
brokerage router and the still-unmounted admission router — the reviewed
topology proven test-locally WITHOUT touching server.py (privileged
production admission stays unmounted; no live flags survive the test).

Full operator workflow over real HTTP: register operator → install
account policy → create server-stamped bound approval → armed order
places EXACTLY ONCE through the fake broker. Denied matrix at the same
mounted entry: kill-switch, missing key, missing store, missing policy,
missing/misbound/foreign-operator/revoked approvals and malformed input
each refuse with ZERO broker placements. Authenticated exits stay
available while the entry kill-switch is OFF (an entry pause never
becomes an exit pause). Entry surfaces #2–#6 of the enumeration are
paper/simulated/unregistered by construction with their own gate tests;
#7 (lifecycle submit) refuses DISARMED by default.
"""

import sys

sys.path.insert(0, "backend")

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

KEY = {"X-API-Key": "test-secret-key"}


@pytest.fixture()
def mounted(monkeypatch):
    import duckdb

    import routes.execution_admission as ea
    import routes.public_brokerage as pb
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    monkeypatch.setenv("API_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    conn = duckdb.connect(":memory:")
    monkeypatch.setattr(pb, "_admission_store_conn", lambda: conn)
    monkeypatch.setattr(ea, "_store_conn", lambda: conn)

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="TEST-ACCT")
    broker.place_order = AsyncMock(return_value=MagicMock(
        status="PENDING", raw={}, order_id="oid-mounted-1", symbol="AAPL",
        side="BUY", order_type="MARKET", quantity=1, price=None,
        created_at="2026-10-05T00:00:00Z"))
    broker.cancel_order = AsyncMock(return_value={"status": "CANCELED"})
    monkeypatch.setattr(pb, "_get_broker", AsyncMock(return_value=broker))

    app = FastAPI()
    app.include_router(pb.router, prefix="/api")
    app.include_router(ea.router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)
    yield client, broker, monkeypatch, conn
    conn.close()
    lc._reset_for_tests()


def _order(**kw):
    body = {"symbol": "AAPL", "side": "BUY", "order_type": "MARKET",
            "quantity": 1, "time_in_force": "DAY",
            "instrument_type": "EQUITY"}
    body.update(kw)
    return body


def _refusal_marker(response):
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return str(detail.get("error"))
    return str(detail)


def _install_policy(client, account_id="TEST-ACCT", policy=None, operator="op-1"):
    r = client.post("/api/admission/policies", headers=KEY, json={
        "account_id": account_id, "policy": policy or {"max_quantity": 5},
        "operator": operator})
    assert r.status_code == 200, r.text
    return r.json()


def _create_approval(client, **kw):
    body = {"account_id": "TEST-ACCT", "symbol": "AAPL", "side": "BUY",
            "quantity": 1, "operator": "op-1", "order_type": "MARKET",
            "instrument_type": "EQUITY"}
    body.update(kw)
    r = client.post("/api/admission/order-approvals", headers=KEY, json=body)
    assert r.status_code == 200, r.text
    return r.json()["approval_id"]


def test_mounted_full_operator_workflow_places_once(mounted):
    client, broker, _, _conn = mounted
    r = client.post("/api/admission/operators", headers=KEY, json={
        "operator_id": "op-1", "allowed_accounts": ["TEST-ACCT"],
        "created_by": "root"})
    assert r.status_code == 200, r.text
    _install_policy(client)
    approval_id = _create_approval(client)
    r = client.post("/api/public/order", headers=KEY,
                    json=_order(approval_id=approval_id, operator="op-1"))
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    broker.place_order.assert_called_once()
    broker.cancel_order.assert_not_called()


def test_mounted_denied_matrix_zero_placements(mounted):
    client, broker, monkeypatch, conn = mounted

    # 1. Kill-switch off: armed-only admission never runs; zero placements.
    monkeypatch.delenv("FLOWW_ENABLE_LIVE_PUBLIC", raising=False)
    r = client.post("/api/public/order", headers=KEY, json=_order())
    assert r.status_code == 403 and "live_trading_disabled" in _refusal_marker(r)
    broker.place_order.assert_not_called()
    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")

    # 2. Missing API key: 401 before any admission/broker access.
    r = client.post("/api/public/order", json=_order())
    assert r.status_code == 401, r.text
    broker.place_order.assert_not_called()

    # 3. Malformed input: validation 422 precedes every gate.
    r = client.post("/api/public/order", headers=KEY, json=_order(quantity=True))
    assert r.status_code == 422, r.text
    broker.place_order.assert_not_called()

    # 4. No admission store: fail closed, zero placements.
    import routes.public_brokerage as pb

    monkeypatch.setattr(pb, "_admission_store_conn", lambda: None)
    r = client.post("/api/public/order", headers=KEY, json=_order())
    assert r.status_code == 403
    assert _refusal_marker(r) == "POLICY_STORE_UNAVAILABLE", r.text
    broker.place_order.assert_not_called()
    monkeypatch.setattr(pb, "_admission_store_conn", lambda: conn)

    # 5. Store present, no required policy: POLICY_UNSET refuses.
    r = client.post("/api/public/order", headers=KEY, json=_order())
    assert r.status_code == 403 and _refusal_marker(r) == "POLICY_UNSET", r.text
    broker.place_order.assert_not_called()

    r = client.post("/api/admission/operators", headers=KEY, json={
        "operator_id": "op-1", "allowed_accounts": ["TEST-ACCT"],
        "created_by": "root"})
    assert r.status_code == 200, r.text
    _install_policy(client)

    # 6. Policy installed, no approval presented: refuses with zero effects.
    r = client.post("/api/public/order", headers=KEY, json=_order(operator="op-1"))
    assert r.status_code == 403, r.text
    assert "APPROVAL" in _refusal_marker(r), r.text
    broker.place_order.assert_not_called()

    # 7. Approval bound to different symbol: fingerprint mismatch refuses.
    approval_id = _create_approval(client, symbol="SPY")
    r = client.post("/api/public/order", headers=KEY,
                    json=_order(approval_id=approval_id, operator="op-1"))
    assert r.status_code == 403, r.text
    assert "APPROVAL" in _refusal_marker(r), r.text
    broker.place_order.assert_not_called()

    # 8. Foreign operator presenting another author's approval: refuses.
    approval_id = _create_approval(client)
    r = client.post("/api/public/order", headers=KEY,
                    json=_order(approval_id=approval_id, operator="impostor-op"))
    assert r.status_code == 403, r.text
    assert "APPROVAL" in _refusal_marker(r), r.text
    broker.place_order.assert_not_called()

    # 9. Revoked approval never authorizes: revoke via the mounted surface.
    r = client.post(f"/api/admission/approvals/{approval_id}/revoke",
                    headers=KEY, json={"operator": "op-1"})
    assert r.status_code == 200, r.text
    r = client.post("/api/public/order", headers=KEY,
                    json=_order(approval_id=approval_id, operator="op-1"))
    assert r.status_code == 403, r.text
    assert "APPROVAL" in _refusal_marker(r), r.text
    broker.place_order.assert_not_called()

    # Whole matrix: the fake broker was never handed an order.
    broker.place_order.assert_not_called()
    broker.cancel_order.assert_not_called()


def test_mounted_exit_available_while_entry_disabled(mounted):
    client, broker, monkeypatch, conn = mounted
    monkeypatch.delenv("FLOWW_ENABLE_LIVE_PUBLIC", raising=False)
    r = client.post("/api/public/order", headers=KEY, json=_order())
    assert r.status_code == 403, r.text
    broker.place_order.assert_not_called()
    # Authenticated risk exits remain available while entries are disabled.
    r = client.post("/api/public/order/oid-mounted-1/cancel", headers=KEY)
    assert r.status_code == 200, r.text
    broker.cancel_order.assert_awaited_once()


def test_unmounted_lifecycle_submit_refuses_disarmed():
    """Entry surface #7: default-disarmed lifecycle never reaches a broker."""
    import asyncio

    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    calls = []

    class _Broker:
        async def place_order(self, **kw):
            calls.append(dict(kw))
            return {"order_id": kw.get("order_id"), "status": "OPEN", "raw": {}}

    intent = {
        "intent_version": "execution-intent.v1", "observation_id": "obs-mounted",
        "ticker": "SPY", "contract": {"osi": "SPY260904C00760000",
                                      "expiry": "2026-09-04", "option_type": "CALL",
                                      "strike_exact": "760.00", "multiplier": "100",
                                      "multiplier_provenance": "vendor-instrument"},
        "side": "BUY", "open_close": "OPEN", "quantity": 1, "limit_price": "3.15",
        "tick": "0.05", "account_id": "ACCT-1", "venue": "PUBLIC",
        "cash_margin_choice": "CASH",
        "budget": {"preflight_total": "318.20", "fees": "3.20",
                   "asof": "2026-10-02T15:00:00+00:00"},
        "session_policy": {"session": "regular", "freshness_s": 30,
                           "confirmation": "quoted"},
        "risk_policy_version": "research_barriers.v1", "execution_owner": "FLOWW_BACKEND",
        "entry_pause_ack": False, "replay_authorization": None,
    }
    from datetime import UTC, datetime

    ctx = {"quotes": {"bid": "3.10", "ask": "3.20",
                      "bid_ts": "2026-10-02T14:59:40+00:00",
                      "ask_ts": "2026-10-02T14:59:41+00:00"},
           "now": datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
           "account": {"options_level": "2", "entitlement": "verified", "margin": True},
           "snapshot_id": "snap_1", "supported_expiries": ["2026-09-04"],
           "supported_products": ["OPTION", "EQUITY"]}
    out = asyncio.run(lc.submit(intent, ctx, _Broker(), armed=False))
    assert out["ok"] is False and out["reason"] == "DISARMED", out
    assert calls == []
    lc._reset_for_tests()
