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
            "osi": "SPY260904C00760000",
            "expiry": "2026-09-04",
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
        "supported_expiries": ["2026-09-04"],
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
    }
    facts.update(kw)
    return facts


class _ExplodingBroker:
    def __getattr__(self, name):
        raise AssertionError(f"admission must never touch broker.{name}")


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


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
            positions=[{"symbol": "SPY", "quantity": 2, "market_price": "3.30"}],
            fills=[
                {"fill_id": "f1", "symbol": "SPY", "side": "BUY", "quantity": 2,
                 "price": "3.15", "fees": "1.00", "ts": "2026-10-02T15:00:00+00:00"},
                {"fill_id": "f1", "symbol": "SPY", "side": "BUY", "quantity": 2,
                 "price": "3.15", "ts": "2026-10-02T15:00:00+00:00"},
                {"fill_id": "f2", "symbol": "SPY", "side": "SELL", "quantity": 1,
                 "price": "3.25", "ts": "2026-10-02T15:01:00+00:00"},
            ]),
        {"max_positions": 5, "max_notional": "1000"})
    assert ok["ok"] is True, ok
    snap = ok["snapshot"]
    assert snap["realized"] == "0.10" and snap["exposure"] == "6.60"
    assert snap["fees_paid"] == "1.00" and snap["duplicate_fills_ignored"] == 1
    breach = ledger.evaluate_account_risk(
        _facts(positions=[{"symbol": "SPY", "quantity": 2, "market_price": "3.30"}]),
        {"max_positions": 1})
    assert breach["reason"] == "RISK_MAX_POSITIONS_EXCEEDED"
    breach = ledger.evaluate_account_risk(
        _facts(positions=[{"symbol": "SPY", "quantity": 2, "market_price": "3.30"}]),
        {"max_notional": "5"})
    assert breach["reason"] == "RISK_NOTIONAL_EXCEEDED"


def test_ledger_refuses_missing_unknown_and_uncovered():
    import services.account_risk_ledger as ledger

    assert ledger.evaluate_account_risk(
        _facts(buying_power=None), {})["reason"] == "RISK_FACTS_INCOMPLETE"
    assert ledger.evaluate_account_risk(
        _facts(open_orders=[{"order_id": "o1", "status": "UNKNOWN"}]),
        {})["reason"] == "UNKNOWN_ORDERS_PENDING"
    assert ledger.evaluate_account_risk(
        _facts(positions=[{"symbol": "SPY", "quantity": 1}]),
        {})["reason"] == "RISK_FACTS_INCOMPLETE"
    out = ledger.evaluate_account_risk(
        _facts(fills=[{"fill_id": "f9", "symbol": "SPY", "side": "SELL",
                       "quantity": 1, "price": "3.25"}]), {})
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
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
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


class _PrimerBroker:
    async def preflight_single_leg(self, **kw):
        return {"total": "318.20", "fees": "3.20", "buying_power_ok": True}


def test_ledger_daily_loss_breach_and_missing_day():
    import services.account_risk_ledger as ledger

    day_fills = [
        {"fill_id": "d1", "symbol": "SPY", "side": "BUY", "quantity": 2,
         "price": "3.00", "ts": "2026-10-02T15:00:00+00:00"},
        {"fill_id": "d2", "symbol": "SPY", "side": "SELL", "quantity": 2,
         "price": "2.00", "ts": "2026-10-02T15:01:00+00:00"},
    ]
    out = ledger.evaluate_account_risk(
        _facts(fills=day_fills), {"max_daily_loss": "1", "today": "2026-10-02"})
    assert out["reason"] == "RISK_DAILY_LOSS_EXCEEDED", out
    assert out["snapshot"]["day_realized"] == "-2.00"
    out = ledger.evaluate_account_risk(_facts(fills=day_fills), {"max_daily_loss": "1"})
    assert out["reason"] == "RISK_FACTS_INCOMPLETE", out
    out = ledger.evaluate_account_risk(
        _facts(fills=day_fills), {"max_daily_loss": "100", "today": "2026-10-02"})
    assert out["ok"] is True


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
