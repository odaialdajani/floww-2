"""S1 required durable admission: failure-injection tests (TDD).

Every refusal path asserts zero fake-broker placement/cancellation calls.
No live calls, no activation, no venue flags.
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
        "observation_id": "obs_s1",
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


class _FakeBroker:
    def __init__(self):
        self.calls = []
        self.cancels = []

    async def preflight_single_leg(self, **kw):
        self.calls.append(("preflight", dict(kw)))
        return {"total": "318.20", "fees": "3.20", "buying_power_ok": True}

    async def place_order(self, **kw):
        self.calls.append(("place", dict(kw)))
        raise AssertionError("admission must never place")

    async def get_order(self, account_id, order_id):
        self.calls.append(("get", order_id))
        raise AssertionError("admission must never read broker")

    async def cancel_order(self, account_id, order_id):
        self.cancels.append(order_id)
        raise AssertionError("admission must never cancel")


class _ExplodingBroker(_FakeBroker):
    def __getattr__(self, name):
        raise AssertionError(f"admission must never touch broker.{name}")


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


def _appr(lc, intent, operator="op-1"):
    from datetime import timedelta

    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    appr = lc.create_approval(
        lc.intent_hash(intent), intent["account_id"], "single-entry",
        now + timedelta(hours=1), operator, now=now)
    return appr, now


def test_policy_write_failure_purges_memory_authority():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc.set_account_policy({"max_quantity": 99}, "stale-op")
    conn = _memdb()
    lc.register_store(conn)
    conn.close()  # durable writes now fail
    out = adm.set_account_policy_required(conn, "ACCT-1", {"max_quantity": 1}, "op-1")
    assert out == {"ok": False, "reason": "POLICY_STORE_UNAVAILABLE"}
    assert lc.get_account_policy() is None  # no memory-only authority remains


def test_policy_missing_corrupt_and_wrong_account():
    import services.execution_admission as adm

    conn = _memdb()
    try:
        assert adm.get_account_policy_required(conn, "ACCT-1")["reason"] == "POLICY_UNSET"
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 2}, "op-1")["ok"] is True
        assert adm.get_account_policy_required(conn, "ACCT-2")["reason"] == "POLICY_UNSET"
        conn.execute(
            "INSERT OR REPLACE INTO account_policy_v2 "
            "(account_id, version, scope, policy_json, updated_at) "
            "VALUES ('ACCT-9', 'account-policy.v2', 's', 'not-json{{{', 'now')")
        assert adm.get_account_policy_required(conn, "ACCT-9")["reason"] == "POLICY_CORRUPT"
        assert adm.get_account_policy_required(None, "ACCT-1")["reason"] == "STORE_UNAVAILABLE"
    finally:
        conn.close()


def test_policy_shape_rejected_before_any_write():
    import services.execution_admission as adm

    conn = _memdb()
    try:
        out = adm.set_account_policy_required(conn, "ACCT-1", {"max_quantity": -5}, "op-1")
        assert out["ok"] is False and out["reason"].startswith("BAD_CONTRACT")
        assert adm.get_account_policy_required(conn, "ACCT-1")["reason"] == "POLICY_UNSET"
    finally:
        conn.close()


def test_migrate_v1_is_explicit_and_never_overwrites():
    import services.execution_admission as adm

    conn = _memdb()
    try:
        assert adm.migrate_account_policy_v1(conn, "ACCT-1", "op-1")["reason"] == "POLICY_UNSET"
        conn.execute(
            "INSERT INTO account_policy_v1 (id, version, policy_json, updated_at) "
            "VALUES ('active', 'account-policy.v1', '{\"max_quantity\": 3}', 'now')")
        assert adm.migrate_account_policy_v1(conn, "ACCT-1", "op-1")["ok"] is True
        got = adm.get_account_policy_required(conn, "ACCT-1")
        assert got["ok"] is True and got["policy"] == {"max_quantity": 3}
        assert adm.migrate_account_policy_v1(conn, "ACCT-1", "op-1")["reason"] == "POLICY_EXISTS"
    finally:
        conn.close()


def test_approval_write_failure_leaves_no_memory_authority():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    lc.register_store(conn)
    intent = _base_intent()
    appr, _ = _appr(lc, intent)
    conn.close()
    out = adm.store_approval_required(conn, appr, "op-1")
    assert out == {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    assert lc._APPROVALS == {}


def test_revoke_failure_refuses_and_rolls_back():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    lc.register_store(conn)
    assert adm.revoke_approval_required(conn, "nope", "op-1")["reason"] == "unknown-approval"
    intent = _base_intent()
    appr, _ = _appr(lc, intent)
    stored = adm.store_approval_required(conn, appr, "op-1")
    assert stored["ok"] is True
    conn.close()
    out = adm.revoke_approval_required(conn, stored["approval_id"], "op-1")
    assert out == {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    assert lc._APPROVALS[stored["approval_id"]].get("revoked") is not True


def test_census_counts_corrupt_and_unknown_never_zero():
    import services.execution_admission as adm

    conn = _memdb()
    try:
        adm.ensure_admission_tables(conn)
        conn.execute(
            "INSERT INTO execution_intents_v1 "
            "(intent_id, intent_hash, ticker, owner, state, order_id, record_json, updated_at) VALUES "
            "('in_good', 'h', 'SPY', 'FLOWW_BACKEND', 'OPEN', 'ord-1', "
            "'{\"order_id\": \"ord-1\"}', 'now'), "
            "('in_bad', 'h', 'SPY', 'FLOWW_BACKEND', 'OPEN', 'ord-2', 'not-json', 'now'), "
            "('in_unk', 'h', 'SPY', 'FLOWW_BACKEND', 'UNKNOWN', 'ord-3', "
            "'{\"order_id\": \"ord-3\"}', 'now'), "
            "('in_done', 'h', 'SPY', 'FLOWW_BACKEND', 'FILLED', 'ord-4', '{}', 'now')")
        out = adm.census_required(conn)
        assert out["ok"] is True
        assert out["nonterminal"] == 3 and out["corrupt"] == 1
        assert out["unknown_states"] == 1 and out["complete"] is False
        assert adm.census_required(None)["reason"] == "STORE_UNAVAILABLE"
    finally:
        conn.close()


def test_census_query_failure_is_unknown_not_empty():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    lc.register_store(conn)
    conn.close()
    assert adm.census_required(conn) == {"ok": False, "reason": "RECOVERY_UNKNOWN"}


def test_admit_happy_path_with_zero_broker_calls():
    import asyncio

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        intent, ctx = _base_intent(), _ctx()
        appr, _ = _appr(lc, intent)
        assert adm.store_approval_required(conn, appr, "op-1")["ok"] is True
        broker = _FakeBroker()
        assert asyncio.run(lc.preflight(intent, ctx, broker))["ok"] is True
        broker.calls.clear()
        out = adm.admit_production_entry(conn, intent, ctx, broker,
                                         approval=appr)
        assert out["decision"] == "ADMIT", out
        assert out["policy_version"] == "account-policy.v2"
        assert broker.calls == [] and broker.cancels == []
    finally:
        conn.close()


def test_admit_refuses_every_gate_without_broker():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    broker = _ExplodingBroker()
    intent, ctx = _base_intent(), _ctx()
    appr, _ = _appr(lc, intent)
    assert adm.admit_production_entry(None, intent, ctx, broker)["reason"] == "STORE_UNAVAILABLE"
    conn = _memdb()
    try:
        lc.register_store(conn)
        out = adm.admit_production_entry(conn, intent, ctx, broker, approval=appr)
        assert out["reason"] == "POLICY_UNSET", out
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        out = adm.admit_production_entry(conn, intent, ctx, broker, approval=appr)
        assert out["reason"] == "APPROVAL_NOT_STORED", out
        assert adm.store_approval_required(conn, appr, "op-1")["ok"] is True
        out = adm.admit_production_entry(conn, intent, ctx, broker, approval=appr)
        assert out["reason"] == "STALE_PREFLIGHT", out
    finally:
        conn.close()


def test_admit_refuses_corrupt_unknown_and_open_census():
    import asyncio

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        intent, ctx = _base_intent(), _ctx()
        appr, _ = _appr(lc, intent)
        assert adm.store_approval_required(conn, appr, "op-1")["ok"] is True
        broker = _FakeBroker()
        assert asyncio.run(lc.preflight(intent, ctx, broker))["ok"] is True
        broker.calls.clear()
        conn.execute(
            "INSERT INTO execution_intents_v1 "
            "(intent_id, intent_hash, ticker, owner, state, order_id, record_json, updated_at) VALUES "
            "('in_bad', 'h', 'SPY', 'FLOWW_BACKEND', 'OPEN', 'ord-9', 'broken', 'now')")
        out = adm.admit_production_entry(conn, intent, ctx, broker, approval=appr)
        assert out["reason"] == "RECOVERY_INCOMPLETE", out
        conn.execute("DELETE FROM execution_intents_v1 WHERE intent_id = 'in_bad'")
        conn.execute(
            "INSERT INTO execution_intents_v1 "
            "(intent_id, intent_hash, ticker, owner, state, order_id, record_json, updated_at) VALUES "
            "('in_unk', 'h', 'SPY', 'FLOWW_BACKEND', 'UNKNOWN', 'ord-8', "
            "'{\"order_id\": \"ord-8\"}', 'now')")
        out = adm.admit_production_entry(conn, intent, ctx, broker, approval=appr)
        assert out["reason"] == "UNKNOWN_ORDERS_PENDING", out
        conn.execute("DELETE FROM execution_intents_v1 WHERE intent_id = 'in_unk'")
        conn.execute(
            "INSERT INTO execution_intents_v1 "
            "(intent_id, intent_hash, ticker, owner, state, order_id, record_json, updated_at) VALUES "
            "('in_open', 'h', 'SPY', 'FLOWW_BACKEND', 'OPEN', 'ord-7', "
            "'{\"order_id\": \"ord-7\"}', 'now')")
        out = adm.admit_production_entry(conn, intent, ctx, broker, approval=appr)
        assert out["reason"] == "OVERLAP_OPEN_NEEDS_RECONCILE", out
        assert broker.calls == [] and broker.cancels == []
    finally:
        conn.close()
