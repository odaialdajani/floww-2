"""S17: single-use order-approval consumption at the mounted entry.

The r19 combined receipt recorded a verified probe: replaying the same
order-entry approval within its <=24h validity window placed a SECOND
order at the mounted armed entry. This suite pins the repair:

- verify -> consume -> place: exactly ONE placement per approval; a
  same-ID replay refuses 403 APPROVAL_ALREADY_USED with zero further
  broker placements, while a FRESH approval still places (gate intact).
- consumption happens BEFORE placement: a broker failure burns the
  approval (fail-closed doctrine; never refunded — re-approve fresh).
- consume store failures refuse 403 fail-closed with zero broker calls.
- revoked rows never consume (used_at stays NULL).
- verify stays pure: an unconsumed approval still verifies (legacy
  NULL used_at rows keep their reviewed S8 semantics).
- service-level consumption is exactly-once with a full audit trail.

No live calls: fake broker, in-memory DuckDB, throwaway FastAPI app with
the production-mounted brokerage router + the still-unmounted admission
router (same topology as test_s18_mounted_full_stack).
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
        status="PENDING", raw={}, order_id="oid-su-1", symbol="AAPL",
        side="BUY", order_type="MARKET", quantity=1, price=None,
        created_at="2026-10-06T00:00:00Z"))
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


def _refusal(response):
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return str(detail.get("error"))
    return str(detail)


def _setup(client):
    r = client.post("/api/admission/operators", headers=KEY, json={
        "operator_id": "op-1", "allowed_accounts": ["TEST-ACCT"],
        "created_by": "root"})
    assert r.status_code == 200, r.text
    r = client.post("/api/admission/policies", headers=KEY, json={
        "account_id": "TEST-ACCT", "policy": {"max_quantity": 5},
        "operator": "op-1"})
    assert r.status_code == 200, r.text


def _create_approval(client, **kw):
    body = {"account_id": "TEST-ACCT", "symbol": "AAPL", "side": "BUY",
            "quantity": 1, "operator": "op-1", "order_type": "MARKET",
            "instrument_type": "EQUITY"}
    body.update(kw)
    r = client.post("/api/admission/order-approvals", headers=KEY, json=body)
    assert r.status_code == 200, r.text
    return r.json()["approval_id"]


def test_same_approval_replay_places_exactly_once(mounted):
    client, broker, _, _conn = mounted
    _setup(client)
    approval_id = _create_approval(client)

    r1 = client.post("/api/public/order", headers=KEY,
                     json=_order(approval_id=approval_id, operator="op-1"))
    assert r1.status_code == 200, r1.text
    assert r1.json()["approval_consumed"] is True
    assert r1.json()["approval_id"] == approval_id
    assert broker.place_order.await_count == 1

    r2 = client.post("/api/public/order", headers=KEY,
                     json=_order(approval_id=approval_id, operator="op-1"))
    assert r2.status_code == 403, r2.text
    assert _refusal(r2) == "APPROVAL_ALREADY_USED"
    assert broker.place_order.await_count == 1, "replay must place nothing"

    r3 = client.post("/api/public/order", headers=KEY,
                     json=_order(approval_id=_create_approval(client),
                                 operator="op-1"))
    assert r3.status_code == 200, r3.text
    assert broker.place_order.await_count == 2, "fresh approval still places"


def test_broker_failure_burns_approval_fail_closed(mounted):
    client, broker, monkeypatch, _conn = mounted
    _setup(client)
    approval_id = _create_approval(client)

    import routes.public_brokerage as pb

    class _Boom(Exception):
        pass

    async def _fail(**_kw):
        raise _Boom("broker down")

    broker.place_order = AsyncMock(side_effect=_fail)
    monkeypatch.setattr(pb, "_get_broker", AsyncMock(return_value=broker))

    r1 = client.post("/api/public/order", headers=KEY,
                     json=_order(approval_id=approval_id, operator="op-1"))
    assert r1.status_code == 502, r1.text
    assert broker.place_order.await_count == 1, "first attempt did place-call"

    r2 = client.post("/api/public/order", headers=KEY,
                     json=_order(approval_id=approval_id, operator="op-1"))
    assert r2.status_code == 403, r2.text
    assert _refusal(r2) == "APPROVAL_ALREADY_USED"
    assert broker.place_order.await_count == 1, (
        "burned approval must never place again")


def test_consume_store_failure_refuses_with_zero_broker_calls(mounted):
    client, broker, monkeypatch, conn = mounted
    _setup(client)
    approval_id = _create_approval(client)

    import routes.public_brokerage as pb

    class _FailingUpdateConn:
        def __init__(self, inner):
            self._inner = inner

        def execute(self, sql, *args, **kwargs):
            if "SET used_at" in sql:
                raise RuntimeError("store broke mid-consume")
            return self._inner.execute(sql, *args, **kwargs)

    monkeypatch.setattr(pb, "_admission_store_conn",
                        lambda: _FailingUpdateConn(conn))

    r = client.post("/api/public/order", headers=KEY,
                    json=_order(approval_id=approval_id, operator="op-1"))
    assert r.status_code == 403, r.text
    assert _refusal(r) == "APPROVAL_STORE_UNAVAILABLE"
    assert broker.place_order.await_count == 0, (
        "a broken store must never degrade single-use into a placement")


def test_revoked_approval_never_consumes(mounted):
    client, _, _monkeypatch, conn = mounted
    _setup(client)
    approval_id = _create_approval(client)
    r = client.post(f"/api/admission/approvals/{approval_id}/revoke",
                    headers=KEY, json={"operator": "root"})
    assert r.status_code == 200, r.text

    import services.execution_admission as adm

    got = adm.consume_order_approval(conn, approval_id,
                                     fingerprint="f", operator="op-1")
    assert got == {"ok": False, "reason": "APPROVAL_INVALID",
                   "detail": "revoked"}
    used = conn.execute(
        "SELECT used_at FROM approvals_v1 WHERE approval_id = ?",
        [approval_id]).fetchone()
    assert used is not None and used[0] is None, "revoked row never consumed"


def test_consume_exactly_once_with_audit_trail(mounted):
    client, _, _monkeypatch, conn = mounted
    _setup(client)
    approval_id = _create_approval(client)

    import services.execution_admission as adm

    fingerprint = adm.order_fingerprint(
        "TEST-ACCT", "AAPL", "BUY", 1, None, stop_price=None,
        time_in_force="DAY", order_type="MARKET", instrument_type="EQUITY",
        equity_market_session=None)

    first = adm.consume_order_approval(conn, approval_id,
                                       fingerprint=fingerprint, operator="op-1")
    assert first["ok"] is True and first["used_at"]
    second = adm.consume_order_approval(conn, approval_id,
                                        fingerprint=fingerprint, operator="op-1")
    assert second["ok"] is False
    assert second["reason"] == "APPROVAL_ALREADY_USED"
    assert second["detail"]["used_at"] == first["used_at"]

    row = conn.execute(
        "SELECT used_at, used_by, used_fingerprint FROM approvals_v1 "
        "WHERE approval_id = ?", [approval_id]).fetchone()
    assert row[0] == first["used_at"]
    assert row[1] == "op-1"
    assert row[2] == fingerprint


def test_unconsumed_approval_still_verifies_pure(mounted):
    client, _, _monkeypatch, conn = mounted
    _setup(client)
    approval_id = _create_approval(client)

    import services.execution_admission as adm

    got = adm.verify_order_approval(
        conn, approval_id, "TEST-ACCT", "AAPL", "BUY", 1, None,
        stop_price=None, time_in_force="DAY", order_type="MARKET",
        instrument_type="EQUITY", equity_market_session=None, operator="op-1")
    assert got.get("ok") is True, got
    used = conn.execute(
        "SELECT used_at FROM approvals_v1 WHERE approval_id = ?",
        [approval_id]).fetchone()
    assert used is not None and used[0] is None, "verify never consumes"


def test_consume_bad_inputs_refuse_without_store(mounted):
    _client, _broker, _monkeypatch, conn = mounted
    import services.execution_admission as adm

    assert adm.consume_order_approval(None, "x") == {
        "ok": False, "reason": "STORE_UNAVAILABLE"}
    assert adm.consume_order_approval(conn, None)["reason"] == "APPROVAL_NOT_STORED"
    assert adm.consume_order_approval(conn, 123)["reason"] == "APPROVAL_NOT_STORED"
    missing = adm.consume_order_approval(conn, "no-such-id")
    assert missing["ok"] is False and missing["reason"] == "APPROVAL_NOT_STORED"
