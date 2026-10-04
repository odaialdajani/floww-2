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
async def test_armed_without_policy_or_store_refuses(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    conn = _isolated_store(monkeypatch)
    broker = _broker(monkeypatch)
    try:
        # Armed + store + no required policy: no legacy placement.
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(_body())
        assert error.value.status_code == 403
        assert error.value.detail["error"] == "POLICY_UNSET"
        broker.place_order.assert_not_awaited()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_armed_without_store_refuses(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    monkeypatch.setattr(public_brokerage, "_admission_store_conn",
                        lambda: None)
    broker = _broker(monkeypatch)
    with pytest.raises(HTTPException) as error:
        await public_brokerage.place_order(_body())
    assert error.value.status_code == 403
    assert error.value.detail["error"] == "POLICY_STORE_UNAVAILABLE"
    broker.place_order.assert_not_awaited()


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
            _body(approval_id=created["approval_id"], operator="op-1"))
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
                _body(limit_price=3.15, stop_price=2.95, operator="op-1",
                      approval_id=created["approval_id"]))
        assert error.value.detail["error"] == "APPROVAL_INVALID"
        # Tampered TIF refuses with zero placement.
        with pytest.raises(HTTPException) as error2:
            await public_brokerage.place_order(
                _body(limit_price=3.15, stop_price=3.00,
                      time_in_force="GTC", operator="op-1",
                      approval_id=created["approval_id"]))
        assert error2.value.detail["error"] == "APPROVAL_INVALID"
        broker.place_order.assert_not_awaited()
        # Exact fields place exactly once.
        out = await public_brokerage.place_order(
            _body(limit_price=3.15, stop_price=3.00, operator="op-1",
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


def test_order_type_is_bound_in_fingerprint():
    from services import execution_admission as adm

    base = adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15,
                                 None, "DAY", "LIMIT")
    assert base != adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15,
                                         None, "DAY", "MARKET")
    assert base == adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15,
                                         None, "DAY", "limit")
    assert base == adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15)


def test_create_order_approval_binds_and_constrains_order_type():
    import duckdb

    from services import execution_admission as adm

    conn = duckdb.connect(":memory:")
    try:
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        # Unknown order types never mint.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1", order_type="FOO")
        assert out["reason"] == "BAD_CONTRACT", out
        # Market options have unbounded slippage: never mintable.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1",
            order_type="MARKET")
        assert out["reason"] == "BAD_CONTRACT", out
        # STOP_LIMIT without a stop is incoherent.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1",
            order_type="STOP_LIMIT")
        assert out["reason"] == "BAD_CONTRACT", out
        # LIMIT-bound approval verifies only as LIMIT.
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT")
        assert created["ok"] is True, created
        assert adm.verify_order_approval(
            conn, created["approval_id"], "ACCT-1", "SPY", "BUY", 1, 3.15,
            order_type="LIMIT")["ok"] is True
        out = adm.verify_order_approval(
            conn, created["approval_id"], "ACCT-1", "SPY", "BUY", 1, 3.15,
            order_type="MARKET")
        assert out["reason"] == "APPROVAL_INVALID", out
    finally:
        conn.close()


def test_create_order_approval_refuses_nonfinite_and_nonpositive_quantity():
    import duckdb

    from services import execution_admission as adm

    conn = duckdb.connect(":memory:")
    try:
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        for bad_qty in ("nan", "inf", "-inf", 0, -1, "0", "abc"):
            out = adm.create_order_approval(
                conn, "ACCT-1", "SPY", "BUY", bad_qty, 3.15, "op-1")
            assert out["reason"] == "BAD_CONTRACT", (bad_qty, out)
        for bad_price in ("nan", "inf"):
            out = adm.create_order_approval(
                conn, "ACCT-1", "SPY", "BUY", 1, bad_price, "op-1")
            assert out["reason"] == "BAD_CONTRACT", (bad_price, out)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_armed_order_type_tamper_refuses(monkeypatch):
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
            order_type="LIMIT")
        assert created["ok"] is True
        # A price-capped LIMIT approval replayed as MARKET refuses.
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(
                _body(order_type="MARKET", operator="op-1",
                      approval_id=created["approval_id"]))
        assert error.value.status_code == 403
        assert error.value.detail["error"] == "APPROVAL_INVALID"
        broker.place_order.assert_not_awaited()
        # The exact bound type places exactly once.
        out = await public_brokerage.place_order(
            _body(order_type="LIMIT", operator="op-1",
                  approval_id=created["approval_id"]))
        assert out["ok"] is True
        broker.place_order.assert_awaited_once()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_nonfinite_quantity_and_prices_refuse_before_any_gate(monkeypatch):
    from fastapi import HTTPException

    broker = _broker(monkeypatch)
    try:
        # Disarmed on purpose: validation precedes the kill-switch, so a
        # 422 here also pins that ordering.
        for bad in ("nan", "inf", "-inf"):
            with pytest.raises(HTTPException) as error:
                await public_brokerage.place_order(_body(quantity=bad))
            assert error.value.status_code == 422
            assert error.value.detail["error"] == "bad_quantity"
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(_body(limit_price="nan"))
        assert error.value.status_code == 422
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(
                _body(order_type="STOP", stop_price="inf"))
        assert error.value.status_code == 422
        broker.place_order.assert_not_awaited()
    finally:
        pass


@pytest.mark.asyncio
async def test_armed_approval_presenter_must_be_author(monkeypatch):
    from fastapi import HTTPException

    from services import execution_admission as adm

    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    conn = _isolated_store(monkeypatch)
    broker = _broker(monkeypatch)
    try:
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "mallory")
        assert created["ok"] is True
        # Mallory's approval presented as op-1 refuses.
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(
                _body(operator="op-1",
                      approval_id=created["approval_id"]))
        assert error.value.status_code == 403
        assert error.value.detail["error"] == "APPROVAL_INVALID"
        broker.place_order.assert_not_awaited()
        # The author presenting it places exactly once.
        out = await public_brokerage.place_order(
            _body(operator="mallory",
                  approval_id=created["approval_id"]))
        assert out["ok"] is True
        broker.place_order.assert_awaited_once()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_armed_option_requires_declared_option_instrument(monkeypatch):
    from fastapi import HTTPException

    from services import execution_admission as adm

    monkeypatch.setenv("FLOWW_ENABLE_LIVE_PUBLIC", "1")
    conn = _isolated_store(monkeypatch)
    broker = _broker(monkeypatch)
    try:
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="OPTION")
        assert created["ok"] is True
        # Route default instrument (EQUITY) is incoherent for the bound
        # OPTION approval: coherence refuses before any placement.
        with pytest.raises(HTTPException) as error:
            await public_brokerage.place_order(
                {"symbol": "SPY271217C00760000", "side": "BUY",
                 "order_type": "LIMIT", "quantity": 1, "limit_price": 3.15,
                 "time_in_force": "DAY", "instrument_type": "EQUITY",
                 "operator": "op-1",
                 "approval_id": created["approval_id"]})
        assert error.value.detail["error"] == "BAD_CONTRACT"
        broker.place_order.assert_not_awaited()
    finally:
        conn.close()
