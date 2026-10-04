"""S8 armed-path admission repair: policy-gated order approvals.

Disarmed behavior is pinned by test_public_brokerage_gate (untouched).
These tests cover the armed path only, with an isolated admission store
and a fake broker. No live calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routes import public_brokerage


def _isolated_store(monkeypatch):
    import duckdb

    conn = duckdb.connect(":memory:")
    monkeypatch.setattr(public_brokerage, "_admission_store_conn", lambda: conn)
    return conn


def _broker(monkeypatch):
    order = SimpleNamespace(
        order_id="ord-1", symbol="SPY", side="BUY", order_type="LIMIT",
        quantity=1, price=3.15, status="OPEN", created_at="2026-10-02T15:00:00+00:00",
        raw={"order": {"status": "OPEN"}},
    )
    broker = SimpleNamespace(
        get_trading_account=lambda: SimpleNamespace(account_id="ACCT-1"),
        place_order=AsyncMock(return_value=order),
    )
    monkeypatch.setattr(public_brokerage, "_get_broker", AsyncMock(return_value=broker))
    return broker


def _body(**kw):
    base = {"symbol": "SPY", "side": "BUY", "order_type": "LIMIT",
            "quantity": 1, "limit_price": 3.15, "time_in_force": "DAY",
            "instrument_type": "EQUITY"}
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_armed_without_policy_keeps_legacy_path(monkeypatch):
    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    conn = _isolated_store(monkeypatch)
    broker = _broker(monkeypatch)
    try:
        out = await public_brokerage.place_order(_body())
        assert out["ok"] is True and out["order_id"] == "ord-1"
        broker.place_order.assert_awaited_once()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_armed_with_policy_requires_bound_approval(monkeypatch):
    from fastapi import HTTPException

    from services import execution_admission as adm

    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    conn = _isolated_store(monkeypatch)
    broker = _broker(monkeypatch)
    try:
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(_body())
        assert error.value.status_code == 403
        assert error.value.detail["error"] == "APPROVAL_NOT_STORED"
        broker.place_order.assert_not_awaited()
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1")
        assert created["ok"] is True
        out = await public_brokerage.place_order(
            _body(approval_id=created["approval_id"]))
        assert out["ok"] is True
        broker.place_order.assert_awaited_once()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_armed_with_policy_refuses_revoked_and_tampered(monkeypatch):
    from fastapi import HTTPException

    from services import execution_admission as adm

    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    conn = _isolated_store(monkeypatch)
    broker = _broker(monkeypatch)
    try:
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1")
        assert adm.revoke_approval_required(
            conn, created["approval_id"], "op-1")["ok"] is True
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(
                _body(approval_id=created["approval_id"]))
        assert error.value.status_code == 403
        assert error.value.detail["error"] == "APPROVAL_INVALID"
        created2 = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1")
        with pytest.raises(HTTPException) as error2:
            await public_brokerage.place_order(
                _body(quantity=2, approval_id=created2["approval_id"]))
        assert error2.value.detail["error"] == "APPROVAL_INVALID"
        broker.place_order.assert_not_awaited()
    finally:
        conn.close()


def test_order_fingerprint_is_canonical():
    from services import execution_admission as adm

    assert (adm.order_fingerprint("ACCT-1", "spy", "buy", 1, 3.15)
            == adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15))
    assert (adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15)
            != adm.order_fingerprint("ACCT-1", "SPY", "BUY", 2, 3.15))
    # Stop and TIF are bound: tampering either breaks the identity.
    base = adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, 3.00, "DAY")
    assert base != adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, 2.95, "DAY")
    assert base != adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, 3.00, "GTC")
    assert base == adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, 3.00, "day")


@pytest.mark.asyncio
async def test_armed_stop_and_tif_tamper_refuse(monkeypatch):
    from fastapi import HTTPException

    from services import execution_admission as adm

    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    conn = _isolated_store(monkeypatch)
    broker = _broker(monkeypatch)
    try:
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1",
            stop_price=3.00, time_in_force="DAY")
        assert created["ok"] is True
        # Tampered stop refuses with zero placement.
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(
                _body(limit_price=3.15, stop_price=2.95,
                      approval_id=created["approval_id"]))
        assert error.value.detail["error"] == "APPROVAL_INVALID"
        # Tampered TIF refuses with zero placement.
        with pytest.raises(HTTPException) as error2:
            await public_brokerage.place_order(
                _body(limit_price=3.15, stop_price=3.00,
                      time_in_force="GTC",
                      approval_id=created["approval_id"]))
        assert error2.value.detail["error"] == "APPROVAL_INVALID"
        broker.place_order.assert_not_awaited()
        # Exact fields place exactly once.
        out = await public_brokerage.place_order(
            _body(limit_price=3.15, stop_price=3.00,
                  approval_id=created["approval_id"]))
        assert out["ok"] is True
        broker.place_order.assert_awaited_once()
    finally:
        conn.close()


def test_option_approval_requires_limit_price():
    import duckdb

    from services import execution_admission as adm

    conn = duckdb.connect(":memory:")
    try:
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, None, "op-1")
        assert out["reason"] == "BAD_CONTRACT", out
    finally:
        conn.close()
