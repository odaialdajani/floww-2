"""S18 executor P0 hardening: Zed R18 review probes at 1d340199/e529.

Covers the exact remaining executable-path gaps (all with zero broker
calls unless stated): bad-verdict preflight satisfying the freshness
gate; commissioned aggregate exposure ignoring the proposed intent;
factory/verify missing policy ceilings; raw-ingested incoherent option
approvals passing verify; unbound instrument/session; rounded-price
fingerprint collisions; same-ID approver mutation; presented-copy
approver spoofing; operator-less armed approval reuse; armed
no-store/no-policy legacy placement.

No live calls, no activation, no venue flags.
"""

import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _isolate():
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    yield
    lc._reset_for_tests()


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


def _reg(conn, *operators, account="ACCT-1"):
    """Register order-entry principals (S02 fixture; author binding still pinned)."""
    import services.operator_registry as registry

    for op in operators:
        assert registry.register_operator(
            conn, op, [account], "root")["ok"] is True


def _intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_p0",
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
        "budget": {"preflight_total": "318.20", "fees": "3.20",
                   "asof": "2026-10-02T15:00:00+00:00"},
        "session_policy": {"session": "regular", "freshness_s": 30,
                           "confirmation": "quoted"},
        "risk_policy_version": "research_barriers.v1",
        "execution_owner": "FLOWW_BACKEND",
        "entry_pause_ack": False,
        "replay_authorization": None,
    }
    intent.update(kw)
    return intent


def _ctx(**kw):
    base = {
        "quotes": {"bid": "3.10", "ask": "3.20",
                   "bid_ts": "2026-10-02T14:59:40+00:00",
                   "ask_ts": "2026-10-02T14:59:41+00:00"},
        "now": datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        "account": {"options_level": "2", "entitlement": "verified",
                    "margin": True},
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


class _VerdictBroker:
    def __init__(self, buying_power_ok):
        self._ok = buying_power_ok

    async def preflight_single_leg(self, **kw):
        return {"total": "318.20", "fees": "3.20",
                "buying_power_ok": self._ok}


def _full_stack(conn, operator="op-1", policy=None):
    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc
    lc.register_store(conn)
    assert operators.register_operator(
        conn, operator, ["ACCT-1"], "root")["ok"] is True
    full = {"max_quantity": 5, "max_notional": "100000",
            "max_positions": 10, "max_daily_loss": "10000",
            "today": "2026-10-02", "min_entry_dte": 5,
            "allow_unprotected_entry": True}
    full.update(policy or {})
    assert adm.set_account_policy_required(
        conn, "ACCT-1", full, operator)["ok"] is True
    intent = _intent()
    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    appr = lc.create_approval(
        lc.intent_hash(intent), intent["account_id"], "single-entry",
        now + timedelta(hours=1), operator, now=now)
    assert adm.store_approval_required(conn, appr, operator)["ok"] is True
    return intent, appr


def test_bad_verdict_preflight_never_satisfies_gate():
    import asyncio

    import services.public_execution_lifecycle as lc

    intent, ctx = _intent(), _ctx()
    assert lc.has_fresh_preflight(intent, ctx) is False
    assert lc.preflight_gate(intent, ctx) == "STALE_PREFLIGHT"
    bad = _VerdictBroker(False)
    assert asyncio.run(lc.preflight(intent, ctx, bad))["ok"] is True
    # A cached buying_power_ok=false estimate must NOT satisfy the gate.
    assert lc.has_fresh_preflight(intent, ctx) is False
    assert lc.preflight_gate(intent, ctx) == "PREFLIGHT_UNAFFORDABLE"
    lc._reset_for_tests()
    good = _VerdictBroker(True)
    assert asyncio.run(lc.preflight(intent, ctx, good))["ok"] is True
    assert lc.has_fresh_preflight(intent, ctx) is True
    assert lc.preflight_gate(intent, ctx) is None


def test_commissioned_refuses_bad_verdict_and_missing_preflight():
    import asyncio

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        intent, appr = _full_stack(conn)
        ctx = _ctx()
        broker = _ExplodingBroker()
        kw = {"approval": appr, "operator_id": "op-1",
              "risk_facts": _facts(),
              "remote_native": {"workflows": []}}
        out = adm.admit_commissioned_entry(conn, intent, ctx, broker, **kw)
        assert out["reason"] == "STALE_PREFLIGHT", out
        assert asyncio.run(
            lc.preflight(intent, ctx, _VerdictBroker(False)))["ok"] is True
        out = adm.admit_commissioned_entry(conn, intent, ctx, broker, **kw)
        assert out["reason"] == "PREFLIGHT_UNAFFORDABLE", out
        lc._reset_for_tests()
        assert asyncio.run(
            lc.preflight(intent, ctx, _VerdictBroker(True)))["ok"] is True
        out = adm.admit_commissioned_entry(conn, intent, ctx, broker, **kw)
        assert out["decision"] == "ADMIT", out
    finally:
        conn.close()


def test_commissioned_aggregate_notional_covers_proposed():
    import asyncio

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        # Existing 900.00 exposure (3 x 3.00 x 100) + proposed 315.00
        # (1 x 3.15 x 100) = 1215.00 exceeds the 1000 ceiling.
        pos = {"symbol": "SPY", "quantity": 3, "market_price": "3.00",
               "multiplier": "100"}
        intent, appr = _full_stack(conn, policy={"max_notional": "1000"})
        ctx = _ctx()
        assert asyncio.run(
            lc.preflight(intent, ctx, _VerdictBroker(True)))["ok"] is True
        broker = _ExplodingBroker()
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(positions=[pos]),
            remote_native={"workflows": []})
        assert out["reason"] == "RISK_NOTIONAL_EXCEEDED", out
        # Existing 600.00 + proposed 315.00 = 915.00 stays inside.
        pos2 = dict(pos, quantity=2)
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=appr, operator_id="op-1",
            risk_facts=_facts(positions=[pos2]),
            remote_native={"workflows": []})
        assert out["decision"] == "ADMIT", out
    finally:
        conn.close()


def test_factory_and_verify_enforce_policy_ceilings():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        _reg(conn, "op-1")
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 1, "max_notional": "100000"},
            "op-1")["ok"] is True
        # maxqty1 policy never mints a qty2 approval.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 2, 3.15, "op-1",
            order_type="LIMIT", instrument_type="EQUITY")
        assert out["reason"] == "RISK_QUANTITY_EXCEEDED", out
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="EQUITY")
        assert out["ok"] is True, out
        # Narrowing the policy after mint refuses at verify.
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 1, "max_notional": "1"},
            "op-1")["ok"] is True
        out = adm.verify_order_approval(
            conn, out["approval_id"], "ACCT-1", "SPY", "BUY", 1, 3.15,
            order_type="LIMIT", instrument_type="EQUITY", operator="op-1")
        assert out["reason"] == "RISK_NOTIONAL_EXCEEDED", out
    finally:
        conn.close()


def test_raw_ingested_incoherent_option_refused_at_verify():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        _reg(conn, "op-1")
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        # Factory refuses a MARKET option; raw ingestion must not revive it.
        refused = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1",
            order_type="MARKET", instrument_type="OPTION")
        assert refused["reason"] == "BAD_CONTRACT", refused
        raw_market = {
            "intent_hash": adm.order_fingerprint(
                "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, None,
                "DAY", "MARKET", "OPTION", None),
            "account_id": "ACCT-1", "scope": "order-entry",
            "symbol": "SPY271217C00760000",
            "valid_until": "2026-10-03T15:00:00+00:00",
            "approved_by": "op-1", "approved_at": "2026-10-02T15:00:00+00:00",
        }
        stored = adm.store_approval_required(conn, raw_market, "op-1")
        assert stored["ok"] is True, stored
        out = adm.verify_order_approval(
            conn, stored["approval_id"],
            "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15,
            order_type="MARKET", instrument_type="OPTION")
        assert out["reason"] == "BAD_CONTRACT", out
        # Raw no-limit LIMIT-option likewise refuses.
        raw_nolimit = dict(
            raw_market,
            intent_hash=adm.order_fingerprint(
                "ACCT-1", "SPY271217C00760000", "BUY", 1, None, None,
                "DAY", "LIMIT", "OPTION", None))
        stored = adm.store_approval_required(conn, raw_nolimit, "op-1")
        assert stored["ok"] is True, stored
        out = adm.verify_order_approval(
            conn, stored["approval_id"], "ACCT-1", "SPY271217C00760000",
            "BUY", 1, None, order_type="LIMIT", instrument_type="OPTION")
        assert out["reason"] == "BAD_CONTRACT", out
    finally:
        conn.close()


def test_instrument_and_session_are_bound():
    import services.execution_admission as adm

    assert (adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, None,
                                 "DAY", "LIMIT", "EQUITY", None)
            != adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, None,
                                     "DAY", "LIMIT", "OPTION", None))
    assert (adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, None,
                                 "DAY", "LIMIT", "EQUITY", "PRE")
            != adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, None,
                                     "DAY", "LIMIT", "EQUITY", "POST"))
    assert (adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, None,
                                 "DAY", "LIMIT", "equity", None)
            == adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15, None,
                                     "DAY", "LIMIT", "EQUITY", None))


def test_factory_constrains_instrument_coherence():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        _reg(conn, "op-1")
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5, "min_entry_dte": 5,
                             "allow_unprotected_entry": True},
            "op-1")["ok"] is True
        # An OSI option declared as EQUITY is incoherent.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="EQUITY")
        assert out["reason"] == "BAD_CONTRACT", out
        # An equity ticker declared OPTION is incoherent.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="OPTION")
        assert out["reason"] == "BAD_CONTRACT", out
        # Unknown instrument types never mint.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="FUTURE")
        assert out["reason"] == "BAD_CONTRACT", out
        # Coherent pairs mint.
        ok = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="OPTION")
        assert ok["ok"] is True, ok
    finally:
        conn.close()


def test_decimal_exact_fingerprint_no_rounding_collisions():
    import services.execution_admission as adm

    assert (adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15)
            != adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.1500001))
    assert (adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, "3.150000")
            == adm.order_fingerprint("ACCT-1", "SPY", "BUY", "1.00", 3.15))
    assert (adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1, 3.15)
            == adm.order_fingerprint("ACCT-1", "SPY", "BUY", 1.0, "3.150"))


def test_same_id_mutated_approver_or_validity_refuses():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
        appr = lc.create_approval(
            "hash-1", "ACCT-1", "single-entry", now + timedelta(hours=1),
            "op-1", now=now)
        appr = dict(appr, approval_id="fixed-id-1")
        assert adm.store_approval_required(conn, appr, "op-1")["ok"] is True
        # Same identity, rewritten approver: conflict, never overwrite.
        out = adm.store_approval_required(
            conn, dict(appr, approved_by="mallory"), "mallory")
        assert out["reason"] == "APPROVAL_CONFLICT", out
        # Same identity, stretched validity: conflict, never overwrite.
        out = adm.store_approval_required(
            conn, dict(appr, valid_until="2026-10-09T15:00:00+00:00"),
            "op-1")
        assert out["reason"] == "APPROVAL_CONFLICT", out
        # Byte-identical re-store stays accepted (idempotent).
        assert adm.store_approval_required(conn, appr, "op-1")["ok"] is True
    finally:
        conn.close()


def test_commissioned_binding_reads_stored_row_not_presented_copy():
    import asyncio

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        import services.operator_registry as operators

        intent, appr = _full_stack(conn, operator="mallory")
        # op-1 is a legitimate registered operator; the spoof is presenting
        # mallory's stored approval under op-1's name.
        assert operators.register_operator(
            conn, "op-1", ["ACCT-1"], "root")["ok"] is True
        ctx = _ctx()
        assert asyncio.run(
            lc.preflight(intent, ctx, _VerdictBroker(True)))["ok"] is True
        broker = _ExplodingBroker()
        kw = {"risk_facts": _facts(), "remote_native": {"workflows": []}}
        # Presented copy rewrites approved_by to op-1: stored row still
        # says mallory, who is not authorized for op-1's presentation.
        spoofed = dict(appr, approved_by="op-1")
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, broker, approval=spoofed,
            operator_id="op-1", **kw)
        assert out["reason"] == "APPROVAL_INVALID", out
    finally:
        conn.close()


def test_factory_refuses_non_buy_sell_side_and_bool_quantity():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        _reg(conn, "op-1")
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        for bad_side in ("HOLD", "", "BUYSELL", "BU Y"):
            out = adm.create_order_approval(
                conn, "ACCT-1", "SPY", bad_side, 1, 3.15, "op-1",
                order_type="LIMIT", instrument_type="EQUITY")
            assert out["reason"] == "BAD_CONTRACT", (bad_side, out)
        for bad_qty in (True, False):
            out = adm.create_order_approval(
                conn, "ACCT-1", "SPY", "BUY", bad_qty, 3.15, "op-1",
                order_type="LIMIT", instrument_type="EQUITY")
            assert out["reason"] == "BAD_CONTRACT", (bad_qty, out)
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "buy", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="EQUITY")
        assert out["ok"] is True, out
        presented = adm.verify_order_approval(
            conn, out["approval_id"], "ACCT-1", "SPY", "HOLD", 1, 3.15,
            order_type="LIMIT", instrument_type="EQUITY", operator="op-1")
        assert presented["reason"] == "BAD_CONTRACT", presented
    finally:
        conn.close()


def test_verify_without_operator_always_refuses():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        lc.register_store(conn)
        _reg(conn, "op-1")
        assert adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="EQUITY")
        assert created["ok"] is True, created
        # No anonymous verification: omitted/blank presenter refuses even
        # with otherwise exact fields.
        for missing in (None, "", "  "):
            out = adm.verify_order_approval(
                conn, created["approval_id"], "ACCT-1", "SPY", "BUY", 1,
                3.15, order_type="LIMIT", instrument_type="EQUITY",
                operator=missing)
            assert out["reason"] == "APPROVAL_INVALID", (missing, out)
        ok = adm.verify_order_approval(
            conn, created["approval_id"], "ACCT-1", "SPY", "BUY", 1, 3.15,
            order_type="LIMIT", instrument_type="EQUITY", operator="op-1")
        assert ok["ok"] is True, ok
    finally:
        conn.close()
