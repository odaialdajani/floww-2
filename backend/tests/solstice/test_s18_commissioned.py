"""S2 commissioned admission: operators, risk ledger, strict layering, route patch.

No live calls, no activation, no venue flags. Broker doubles explode on any
use inside admission paths; preflight priming happens in setup only.
"""

import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime

import pytest


@pytest.fixture(autouse=True)
def _isolate():
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    yield
    lc._reset_for_tests()


def _base_intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_s2",
        "replay_id": None,
        "ticker": "SPY",
        "contract": {
            "osi": "SPY261218C00760000",
            "expiry": "2026-12-18",
            "option_type": "CALL",
            "strike_exact": "760.00",
            "multiplier": "100",
            "multiplier_provenance": "vendor-instrument",
        },
        "side": "BUY",
        "open_close": "OPEN",
        "quantity": 1,
        "limit_price": "3.15",
        "tick": "0.05",
        "account_id": "ACCT-1",
        "venue": "PUBLIC",
        "cash_margin_choice": "CASH",
        "budget": {"preflight_total": "318.20", "fees": "3.20", "asof": "2026-10-02T15:00:00+00:00"},
        "session_policy": {"session": "regular", "freshness_s": 30, "confirmation": "quoted"},
        "risk_policy_version": "research_barriers.v1",
        "execution_owner": "FLOWW_BACKEND",
        "entry_pause_ack": False,
        "replay_authorization": None,
    }
    intent.update(kw)
    return intent


def _ctx(**kw):
    base = {
        "quotes": {"bid": "3.10", "ask": "3.20", "bid_ts": "2026-10-02T14:59:40+00:00",
                   "ask_ts": "2026-10-02T14:59:41+00:00"},
        "now": datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        "account": {"options_level": "2", "entitlement": "verified", "margin": True},
        "snapshot_id": "snap_1",
        "supported_expiries": ["2026-12-18"],
        "supported_products": ["OPTION", "EQUITY"],
    }
    base.update(kw)
    return base


def _facts(**kw):
    facts = {
        "buying_power": "10000",
        "positions": [],
        "open_orders": [],
        "fills": [],
        "account_id": "ACCT-1",
        "source": "fake-broker",
        "asof": "2026-10-02T14:59:00+00:00",
    }
    facts.update(kw)
    return facts


class _ExplodingBroker:
    def __getattr__(self, name):
        raise AssertionError(f"admission must never touch broker.{name}")


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


def test_operator_remove_revokes_future_authorization():
    import services.operator_registry as operators

    conn = _memdb()
    try:
        assert operators.register_operator(conn, "op-7", ["ACCT-1"], "root")["ok"] is True
        assert operators.authorize_operator(conn, "op-7", "ACCT-1")["ok"] is True
        assert operators.remove_operator(conn, "op-7")["ok"] is True
        assert operators.authorize_operator(conn, "op-7", "ACCT-1")["reason"] == "OPERATOR_UNKNOWN"
        assert operators.remove_operator(conn, "op-7")["reason"] == "OPERATOR_UNKNOWN"
        assert operators.remove_operator(None, "op-7")["reason"] == "STORE_UNAVAILABLE"
    finally:
        conn.close()


def test_operator_register_authorize_and_refusals():
    import services.operator_registry as operators

    conn = _memdb()
    try:
        assert operators.register_operator(conn, "op-1", ["ACCT-1"], "root")["ok"] is True
        assert operators.register_operator(
            conn, "op-1", ["ACCT-1"], "root")["reason"] == "OPERATOR_EXISTS"
        assert operators.authorize_operator(conn, "op-1", "ACCT-1")["ok"] is True
        assert operators.authorize_operator(conn, "op-1", "ACCT-9")["reason"] == "OPERATOR_UNAUTHORIZED"
        assert operators.authorize_operator(conn, "ghost", "ACCT-1")["reason"] == "OPERATOR_UNKNOWN"
        assert operators.authorize_operator(None, "op-1", "ACCT-1")["reason"] == "STORE_UNAVAILABLE"
        assert operators.list_operators(conn) == {"ok": True, "operators": ["op-1"]}
    finally:
        conn.close()


def test_ledger_fifo_realized_exposure_and_breaches():
    import services.account_risk_ledger as ledger

    ok = ledger.evaluate_account_risk(
        _facts(
            positions=[{"symbol": "SPY", "quantity": 2, "market_price": "3.30",
                        "multiplier": "100"}],
            fills=[
                {"fill_id": "f1", "symbol": "SPY", "side": "BUY", "quantity": 2,
                 "price": "3.15", "fees": "1.00", "ts": "2026-10-02T15:00:00+00:00",
                 "multiplier": "100"},
                {"fill_id": "f1", "symbol": "SPY", "side": "BUY", "quantity": 2,
                 "price": "3.15", "fees": "1.00", "ts": "2026-10-02T15:00:00+00:00",
                 "multiplier": "100"},
                {"fill_id": "f2", "symbol": "SPY", "side": "SELL", "quantity": 1,
                 "price": "3.25", "fees": "0.50", "ts": "2026-10-02T15:01:00+00:00",
                 "multiplier": "100"},
            ]),
        {"max_positions": 5, "max_notional": "1000"})
    assert ok["ok"] is True, ok
    snap = ok["snapshot"]
    assert snap["realized"] == "10.00" and snap["exposure"] == "660.00"
    assert snap["premium_paid"] == "630.00" and snap["fees_paid"] == "1.50"
    assert snap["duplicate_fills_ignored"] == 1
    breach = ledger.evaluate_account_risk(
        _facts(positions=[{"symbol": "SPY", "quantity": 2, "market_price": "3.30",
                           "multiplier": "100"}]),
        {"max_positions": 1})
    assert breach["reason"] == "RISK_MAX_POSITIONS_EXCEEDED"
    breach = ledger.evaluate_account_risk(
        _facts(positions=[{"symbol": "SPY", "quantity": 2, "market_price": "3.30",
                           "multiplier": "100"}]),
        {"max_notional": "5"})
    assert breach["reason"] == "RISK_NOTIONAL_EXCEEDED"


def test_ledger_previous_day_lots_carry_into_today():
    import services.account_risk_ledger as ledger

    out = ledger.evaluate_account_risk(
        _facts(fills=[
            {"fill_id": "yd1", "symbol": "SPY", "side": "BUY", "quantity": 2,
             "price": "3.00", "fees": "1.00", "ts": "2026-10-01T15:00:00+00:00",
             "multiplier": "100"},
            {"fill_id": "td1", "symbol": "SPY", "side": "SELL", "quantity": 2,
             "price": "2.00", "fees": "1.00", "ts": "2026-10-02T15:01:00+00:00",
             "multiplier": "100"},
            {"fill_id": "td1", "symbol": "SPY", "side": "SELL", "quantity": 2,
             "price": "2.00", "fees": "1.00", "ts": "2026-10-02T15:01:00+00:00",
             "multiplier": "100"},
        ]),
        {"max_daily_loss": "500", "today": "2026-10-02"})
    assert out["ok"] is True, out
    # Yesterday's basis carries: 2 × (2.00 − 3.00) × 100, duplicate ignored,
    # NET of the same-day sell fee (1.00): commissions count against the day.
    assert out["snapshot"]["day_realized"] == "-201.00"
    assert out["snapshot"]["day_fees"] == "1.00"
    assert out["snapshot"]["duplicate_fills_ignored"] == 1
    out = ledger.evaluate_account_risk(
        _facts(fills=[
            {"fill_id": "yd1", "symbol": "SPY", "side": "BUY", "quantity": 2,
             "price": "3.00", "fees": "1.00", "ts": "2026-10-01T15:00:00+00:00",
             "multiplier": "100"},
            {"fill_id": "td1", "symbol": "SPY", "side": "SELL", "quantity": 2,
             "price": "2.00", "fees": "1.00", "ts": "2026-10-02T15:01:00+00:00",
             "multiplier": "100"},
        ]),
        {"max_daily_loss": "100", "today": "2026-10-02"})
    assert out["reason"] == "RISK_DAILY_LOSS_EXCEEDED", out


def test_ledger_refuses_missing_unknown_and_uncovered():
    import services.account_risk_ledger as ledger

    assert ledger.evaluate_account_risk(
        _facts(buying_power=None), {})["reason"] == "RISK_FACTS_INCOMPLETE"
    assert ledger.evaluate_account_risk(
        _facts(open_orders=[{"order_id": "o1", "status": "UNKNOWN"}]),
        {})["reason"] == "UNKNOWN_ORDERS_PENDING"
    assert ledger.evaluate_account_risk(
        _facts(positions=[{"symbol": "SPY", "quantity": 1, "multiplier": "100"}]),
        {})["reason"] == "RISK_FACTS_INCOMPLETE"  # no market price
    out = ledger.evaluate_account_risk(
        _facts(fills=[{"fill_id": "f9", "symbol": "SPY", "side": "SELL",
                       "quantity": 1, "price": "3.25", "fees": "0.50",
                       "ts": "2026-10-02T15:00:00+00:00", "multiplier": "100"}]), {})
    assert out["reason"] == "RISK_FACTS_INCOMPLETE"  # uncovered sale


def test_commissioned_admit_full_stack_and_each_refusal():
    import asyncio

    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        intent, ctx = _base_intent(), _ctx()
        broker = _ExplodingBroker()
        out = adm.admit_commissioned_entry(conn, intent, ctx, broker)
        assert out["reason"] == "OPERATOR_UNKNOWN", out
        assert operators.register_operator(conn, "op-1", ["ACCT-1"], "root")["ok"] is True
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, operator_id="op-1")
        assert out["reason"] == "POLICY_UNSET", out
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "max_notional": "100000",
                             "max_positions": 10, "max_daily_loss": "10000",
                             "today": "2026-10-02", "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        from datetime import timedelta

        now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
        appr = lc.create_approval(
            lc.intent_hash(intent), intent["account_id"], "single-entry",
            now + timedelta(hours=1), "op-1", now=now)
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(), remote_native={"workflows": []})
        assert out["reason"] == "APPROVAL_NOT_STORED", out
        assert adm.store_approval_required(conn, appr, "op-1")["ok"] is True
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(), remote_native={"workflows": []})
        assert out["reason"] == "STALE_PREFLIGHT", out
        primer = _PrimerBroker()
        assert asyncio.run(lc.preflight(intent, ctx, primer))["ok"] is True
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(), remote_native={"workflows": []})
        assert out["decision"] == "ADMIT", out
        assert out["operator_id"] == "op-1"
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(),
            remote_native={"workflows": [{"strategy": "s", "status": "OPEN"}]})
        assert out["reason"] == "OVERLAP_NATIVE", out
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(),
            remote_native={"workflows": ["garbage", {"strategy": "s"}]})
        assert out["reason"] == "NATIVE_CENSUS_UNAVAILABLE", out
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts())
        assert out["reason"] == "NATIVE_CENSUS_UNAVAILABLE", out
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            remote_native={"workflows": []})
        assert out["reason"] == "RISK_FACTS_INCOMPLETE", out
        out = adm.admit_commissioned_entry(
            conn, _base_intent(account_id="ACCT-9"), ctx, broker,
            approval=appr, operator_id="op-1",
            risk_facts=_facts(), remote_native={"workflows": []})
        assert out["reason"] == "OPERATOR_UNAUTHORIZED", out
    finally:
        conn.close()


def test_commissioned_refuses_expired_and_unprotected():
    import asyncio

    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        assert operators.register_operator(conn, "op-1", ["ACCT-1"], "root")["ok"] is True
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "max_notional": "100000",
                             "max_positions": 10, "max_daily_loss": "10000",
                             "today": "2026-10-02", "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        # Expired Sep-4 contract at Oct-2 now: regression, never a pass.
        old = _base_intent()
        old["contract"] = dict(old["contract"], osi="SPY260904C00760000",
                               expiry="2026-09-04")
        ctx = _ctx(supported_expiries=["2026-09-04", "2026-12-18"])
        appr, _ = _stored_appr_for(lc, old)
        assert adm.store_approval_required(conn, appr, "op-1")["ok"] is True
        primer = _PrimerBroker()
        assert asyncio.run(lc.preflight(old, ctx, primer))["ok"] is True
        broker = _ExplodingBroker()
        out = adm.admit_commissioned_entry(
            conn, old, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(), remote_native={"workflows": []})
        assert out["reason"] in ("EXPIRY_TOO_NEAR", "EXPIRY_INVALID"), out
        # Same December intent, identical setup, minus the protection ack.
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "max_notional": "100000",
                             "max_positions": 10, "max_daily_loss": "10000",
                             "today": "2026-10-02", "min_entry_dte": 5},
            "op-1")["ok"] is True
        dec = _base_intent()
        ctx2 = _ctx()
        appr2, _ = _stored_appr_for(lc, dec)
        assert adm.store_approval_required(conn, appr2, "op-1")["ok"] is True
        assert asyncio.run(lc.preflight(dec, ctx2, primer))["ok"] is True
        out = adm.admit_commissioned_entry(
            conn, dec, ctx2, broker, approval=appr2, operator_id="op-1",
            risk_facts=_facts(), remote_native={"workflows": []})
        assert out["reason"] == "PROTECTION_UNVERIFIED", out
    finally:
        conn.close()


def test_order_approval_guards_expiry_and_protection():
    """Executable-path guards: approvals cannot be minted for expired /
    near-expiry / unacknowledged-unprotected option contracts, and a
    policy narrowing between creation and placement refuses at verify.
    Equity (non-OSI) symbols skip the option expiry gate. Zero broker
    calls anywhere (service layer never touches a broker).
    """
    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        assert operators.register_operator(
            conn, "op-1", ["ACCT-1"], "root")["ok"] is True
        full = {"max_quantity": 5, "max_notional": "100000",
                "max_positions": 10, "max_daily_loss": "10000",
                "today": "2026-10-02", "min_entry_dte": 5,
                "allow_unprotected_entry": True}
        assert adm.set_account_policy_required(conn, "ACCT-1", full, "op-1")["ok"] is True
        # Expired Sep-4 OSI (real clock is Oct 2026): creation refuses.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY260904C00760000", "BUY", 1, 3.15, "op-1")
        assert out["ok"] is False and out["reason"] in (
            "EXPIRY_INVALID", "EXPIRY_TOO_NEAR"), out
        # Far-future OSI mints fine under the acknowledging policy.
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1")
        assert created["ok"] is True, created
        verified = adm.verify_order_approval(
            conn, created["approval_id"], "ACCT-1",
            "SPY271217C00760000", "BUY", 1, 3.15, operator="op-1")
        assert verified["ok"] is True, verified
        # Policy narrows (ack removed): the live approval now refuses.
        narrowed = dict(full)
        del narrowed["allow_unprotected_entry"]
        assert adm.set_account_policy_required(conn, "ACCT-1", narrowed, "op-1")["ok"] is True
        out = adm.verify_order_approval(
            conn, created["approval_id"], "ACCT-1",
            "SPY271217C00760000", "BUY", 1, 3.15, operator="op-1")
        assert out["reason"] == "PROTECTION_UNVERIFIED", out
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1")
        assert out["reason"] == "PROTECTION_UNVERIFIED", out
        # Policy without an expiry floor: creation refuses unconfigured.
        nofloor = {"max_quantity": 5}
        assert adm.set_account_policy_required(conn, "ACCT-1", nofloor, "op-1")["ok"] is True
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1")
        assert out["reason"] == "GUARD_UNCONFIGURED", out
        # Equity ticker: no option expiry concept, still mints + verifies.
        eq = adm.create_order_approval(conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1")
        assert eq["ok"] is True, eq
        assert adm.verify_order_approval(
            conn, eq["approval_id"], "ACCT-1", "SPY", "BUY", 1, 3.15,
            operator="op-1")["ok"] is True
        # Malformed OSI (month 13): refuses instead of riding the equity path.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY261300C00760000", "BUY", 1, 3.15, "op-1")
        assert out["reason"] == "BAD_CONTRACT", out
    finally:
        conn.close()


def _stored_appr_for(lc, intent, operator="op-1"):
    from datetime import timedelta

    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    appr = lc.create_approval(
        lc.intent_hash(intent), intent["account_id"], "single-entry",
        now + timedelta(hours=1), operator, now=now)
    return appr, now


def test_commissioned_affordability_and_complete_policy():
    import services.account_risk_ledger as ledger
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        full = {"max_quantity": 5, "max_notional": "100000",
                "max_daily_loss": "10000", "today": "2026-10-02"}
        assert adm.set_account_policy_required(conn, "ACCT-1", full, "op-1")["ok"] is True
        intent = _base_intent(quantity=100)
        out = ledger.check_affordability(intent, _facts())
        assert out["reason"] == "INSUFFICIENT_BUDGET", out  # 31500 > 10000
        out = ledger.check_affordability(
            intent, _facts(buying_power="100000",
                           open_orders=[{"order_id": "r1", "status": "OPEN",
                                         "quantity": 1, "limit_price": "3.00",
                                         "multiplier": "100"}]))
        assert out["ok"] is True and out["reserved"] == "300.00", out
        out = ledger.check_affordability(
            _base_intent(), _facts(open_orders=[{"order_id": "r2", "status": "OPEN"}]))
        assert out["reason"] == "RISK_FACTS_INCOMPLETE", out  # no reservation data
        out = ledger.evaluate_account_risk(_facts(), {"max_quantity": 5},
                                           require_complete_policy=True)
        assert out["reason"] == "POLICY_INCOMPLETE", out
    finally:
        conn.close()


class _PrimerBroker:
    async def preflight_single_leg(self, **kw):
        return {"total": "318.20", "fees": "3.20", "buying_power_ok": True}


def test_commissioned_refuses_stale_foreign_unsourced_facts():
    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        assert operators.register_operator(conn, "op-1", ["ACCT-1"], "root")["ok"] is True
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "max_notional": "100000",
                             "max_positions": 10, "max_daily_loss": "10000",
                             "today": "2026-10-02", "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        intent, ctx = _base_intent(), _ctx()
        appr, _ = _stored_appr_for(lc, intent)
        assert adm.store_approval_required(conn, appr, "op-1")["ok"] is True
        primer = _PrimerBroker()
        import asyncio

        assert asyncio.run(lc.preflight(intent, ctx, primer))["ok"] is True
        broker = _ExplodingBroker()
        good_native = {"workflows": []}
        # Stale facts (previous day) refuse even though everything else passes.
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(asof="2026-10-01T15:00:00+00:00"),
            remote_native=good_native)
        assert out["reason"] == "STALE_FACTS", out
        # Foreign-account facts refuse.
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(account_id="ACCT-9"),
            remote_native=good_native)
        assert out["reason"] == "RISK_FACTS_INCOMPLETE", out
        # Missing source refuses.
        facts = _facts()
        del facts["source"]
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=facts, remote_native=good_native)
        assert out["reason"] == "RISK_FACTS_INCOMPLETE", out
    finally:
        conn.close()


def test_ledger_refuses_short_positions():
    import services.account_risk_ledger as ledger

    out = ledger.evaluate_account_risk(
        _facts(positions=[{"symbol": "SPY", "quantity": -1,
                           "market_price": "3.30", "multiplier": "100"}]), {})
    assert out["reason"] == "RISK_FACTS_INCOMPLETE", out
    assert "short" in out["detail"], out


def test_ledger_single_lot_exposure_multiplier():
    import services.account_risk_ledger as ledger

    # Quantity 1 x price 3.30 x multiplier 100 exposure, fees counted.
    out = ledger.evaluate_account_risk(
        _facts(
            positions=[{"symbol": "SPY", "quantity": 1, "market_price": "3.30",
                        "multiplier": "100"}],
            fills=[{"fill_id": "e1", "symbol": "SPY", "side": "BUY",
                     "quantity": 1, "price": "3.30", "fees": "0.65",
                     "ts": "2026-10-02T15:00:00+00:00", "multiplier": "100"}]),
        {})
    assert out["ok"] is True, out
    assert out["snapshot"]["exposure"] == "330.00"
    assert out["snapshot"]["premium_paid"] == "330.00"
    assert out["snapshot"]["fees_paid"] == "0.65"


def test_ledger_missing_fees_time_multiplier_and_status_refuse():
    import services.account_risk_ledger as ledger

    good = {"fill_id": "g1", "symbol": "SPY", "side": "BUY", "quantity": 1,
            "price": "3.15", "fees": "0.50", "ts": "2026-10-02T15:00:00+00:00",
            "multiplier": "100"}
    for drop in ("fees", "ts", "multiplier"):
        bad = dict(good)
        del bad[drop]
        out = ledger.evaluate_account_risk(_facts(fills=[bad]), {})
        assert out["reason"] == "RISK_FACTS_INCOMPLETE", (drop, out)
    assert ledger.evaluate_account_risk(
        _facts(open_orders=[{"order_id": "o1"}]), {})["reason"] == "RISK_FACTS_INCOMPLETE"
    assert ledger.evaluate_account_risk(
        _facts(open_orders=[{"order_id": "o1", "status": ""}]),
        {})["reason"] == "RISK_FACTS_INCOMPLETE"


def test_operator_corrupt_allowlist_refuses_distinctly():
    import services.operator_registry as operators

    conn = _memdb()
    try:
        assert operators.register_operator(conn, "op-9", ["ACCT-1"], "root")["ok"] is True
        conn.execute(
            "UPDATE operators_v1 SET allowed_accounts = 'broken{{{' WHERE operator_id = 'op-9'")
        out = operators.authorize_operator(conn, "op-9", "ACCT-1")
        assert out["reason"] == "OPERATOR_STORE_UNAVAILABLE", out
    finally:
        conn.close()


def test_route_patch_decision_and_risk_shapes(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import services.public_execution_lifecycle as lc
    from routes.execution_admission import router

    monkeypatch.setenv("API_SECRET_KEY", "test-secret-key")
    headers = {"X-API-Key": "test-secret-key"}
    lc._reset_for_tests()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/admission/risk/evaluate",
                    json={"facts": {"buying_power": "10", "positions": [],
                                    "open_orders": [], "fills": []},
                          "policy": {}}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    r = client.post("/admission/decision", json={"intent": _base_intent()})
    assert r.status_code == 401, r.text  # master key required even unmounted-in-test
    r = client.post("/admission/decision", json={"nope": True},
                    headers={"X-API-Key": "wrong-key"})
    assert r.status_code in (401, 503), r.text
    r = client.post("/admission/operators/never-registered/remove",
                    headers=headers)
    assert r.status_code == 404, r.text  # unknown removal refuses, never silent


def test_route_decision_never_admits_client_asserted():
    """Research decision surface is labeled non-dispatch (S9).

    Even a fully valid body returns EVIDENCE_UNVERIFIED, never ADMIT:
    client-asserted facts cannot produce executable authority.
    """
    import os

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import services.public_execution_lifecycle as lc
    from routes.execution_admission import router

    os.environ["API_SECRET_KEY"] = "test-secret-key"
    headers = {"X-API-Key": "test-secret-key"}
    lc._reset_for_tests()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    body = {
        "intent": _base_intent(), "ctx": {
            "quotes": {"bid": "3.10", "ask": "3.20",
                       "bid_ts": "2026-10-02T14:59:40+00:00",
                       "ask_ts": "2026-10-02T14:59:41+00:00"},
            "now": "2026-10-02T15:00:00+00:00",
            "account": {"entitlement": "verified"},
            "supported_expiries": ["2026-12-18"],
            "supported_products": ["OPTION", "EQUITY"]},
        "approval": {"intent_hash": "x"}, "operator_id": "op-1",
        "risk_facts": _facts(), "remote_native": {"workflows": []},
    }
    r = client.post("/admission/decision", json=body, headers=headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["decision"] == "REFUSE", out
    assert out["reason"] == "EVIDENCE_UNVERIFIED", out
    assert out["evidence_grade"] == "client-asserted", out


def test_commissioned_binds_approved_by_and_evidence():
    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        assert operators.register_operator(conn, "op-1", ["ACCT-1"], "root")["ok"] is True
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "max_notional": "100000",
                             "max_positions": 10, "max_daily_loss": "10000",
                             "today": "2026-10-02", "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        intent, ctx = _base_intent(), _ctx()
        spoofed, _ = _stored_appr_for(lc, intent, operator="mallory")
        assert adm.store_approval_required(conn, spoofed, "mallory")["ok"] is True
        primer = _PrimerBroker()
        import asyncio

        assert asyncio.run(lc.preflight(intent, ctx, primer))["ok"] is True
        broker = _ExplodingBroker()
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=spoofed, operator_id="op-1",
            risk_facts=_facts(), remote_native={"workflows": []})
        assert out["reason"] == "APPROVAL_INVALID", out
        honest, _ = _stored_appr_for(lc, intent, operator="op-1")
        assert adm.store_approval_required(conn, honest, "op-1")["ok"] is True
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=honest, operator_id="op-1",
            risk_facts=_facts(), remote_native={"workflows": []},
            evidence_grade="client-asserted")
        assert out["reason"] == "EVIDENCE_UNVERIFIED", out
    finally:
        conn.close()


def test_single_store_mismatch_refuses():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    first, second = _memdb(), _memdb()
    try:
        lc.register_store(first)
        out = adm.admit_production_entry(second, _base_intent(), _ctx(), None)
        assert out["reason"] == "STORE_MISMATCH", out
    finally:
        first.close()
        second.close()
