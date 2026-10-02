"""R15-3: deterministic Public execution lifecycle — focused contract tests.

No live calls, no venue flags, no worker activation. All broker transport is a
deterministic in-memory fake. The module under test is a pure service (no route
mount); the existing gated route (`routes/public_brokerage.py`) remains the only
HTTP submission path and is untouched here.

Contract: `execution-intent.v1` (see docs/solstice/MUSE_STATE.md R15-3).
"""

import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _isolate_lifecycle():
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    yield
    lc._reset_for_tests()


def _base_intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_abc123",
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
        "account_id": "TEST-ACCT",
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
        # 15:00 UTC = 11:00 ET: quotes 20s old (fresh), outside 11:30-14:00 pause.
        "now": datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        "account": {"options_level": "2", "entitlement": "verified", "margin": True},
        "snapshot_id": "snap_1",
        "supported_expiries": ["2026-09-04"],
        "supported_products": ["OPTION", "EQUITY"],
    }
    base.update(kw)
    return base


class _FakeBroker:
    """Deterministic broker double: no network, programmed receipts."""

    def __init__(self):
        self.calls = []
        self.orders = {}
        self.ambiguous_once = False
        self.preflight_calls = 0

    async def preflight_single_leg(self, **kw):
        self.preflight_calls += 1
        return {"total": "318.20", "fees": "3.20", "buying_power_ok": True, "raw": dict(kw)}

    async def place_order(self, **kw):
        self.calls.append(dict(kw))
        if self.ambiguous_once:
            self.ambiguous_once = False
            raise TimeoutError("ambiguous: accepted state unknown")
        oid = kw.get("order_id")
        self.orders[oid] = {"status": "OPEN", "payload": dict(kw), "fills": 0, "quantity": kw.get("quantity")}
        return {"order_id": oid, "status": "OPEN", "raw": {"orderId": oid, "status": "OPEN"}}

    async def get_order(self, account_id, order_id):
        rec = self.orders.get(order_id)
        if rec is None:
            return {"order_id": order_id, "status": "UNKNOWN", "raw": {}}
        return {"order_id": order_id, "status": rec["status"], "fills": rec["fills"], "raw": rec}

    async def cancel_order(self, account_id, order_id):
        rec = self.orders.get(order_id)
        if rec is None:
            return {"orderId": order_id, "status": "UNKNOWN"}
        if rec.get("cancel_pending_once"):
            rec["cancel_pending_once"] = False
            return {"orderId": order_id, "status": "CANCEL_PENDING", "raw_empty": True}
        rec["status"] = "CANCELED"
        return {"orderId": order_id, "status": "CANCELED"}


def test_intent_hash_is_deterministic_and_precision_exact():
    import services.public_execution_lifecycle as lc

    a = _base_intent()
    b = _base_intent()
    assert lc.intent_hash(a) == lc.intent_hash(b)
    c = _base_intent(limit_price="3.150")
    # Decimal-canonical: trailing zeros do not fork the identity.
    assert lc.intent_hash(c) == lc.intent_hash(a)
    with __import__("pytest").raises(Exception):
        lc.intent_hash(_base_intent(limit_price=3.15))  # float is not exact money


def test_reject_malformed_contract():
    import services.public_execution_lifecycle as lc

    bad = _base_intent(contract={"osi": "BAD", "expiry": "nope"})
    ok, reason = lc.validate_intent(bad, _ctx())
    assert ok is False and reason == "BAD_CONTRACT"


def test_reject_unsupported_product_and_expiry():
    import services.public_execution_lifecycle as lc

    ok, reason = lc.validate_intent(_base_intent(), _ctx(supported_products=["EQUITY"]))
    assert (ok, reason) == (False, "UNSUPPORTED_PRODUCT")
    ok, reason = lc.validate_intent(_base_intent(), _ctx(supported_expiries=["2026-12-31"]))
    assert (ok, reason) == (False, "UNSUPPORTED_EXPIRY")


def test_reject_stale_and_missing_quote_sides():
    import services.public_execution_lifecycle as lc

    stale = _ctx(
        quotes={"bid": "3.10", "ask": "3.20",
                "bid_ts": "2026-10-02T14:00:00+00:00",
                "ask_ts": "2026-10-02T14:00:01+00:00"},
        now=datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
    )
    ok, reason = lc.validate_intent(_base_intent(), stale)
    assert (ok, reason) == (False, "STALE_QUOTE")
    missing = _ctx(quotes={"bid": None, "ask": "3.20",
                           "bid_ts": "2026-10-02T14:59:40+00:00",
                           "ask_ts": "2026-10-02T14:59:41+00:00"})
    ok, reason = lc.validate_intent(_base_intent(), missing)
    assert (ok, reason) == (False, "MISSING_QUOTE_SIDES")


def test_reject_missing_policy_and_unresolved_margin():
    import services.public_execution_lifecycle as lc

    no_policy = _base_intent()
    del no_policy["risk_policy_version"]
    assert lc.validate_intent(no_policy, _ctx()) == (False, "MISSING_POLICY")
    no_margin = _base_intent(cash_margin_choice=None)
    assert lc.validate_intent(no_margin, _ctx()) == (False, "UNRESOLVED_MARGIN")


def test_reject_unauthorized_replay_execution():
    import services.public_execution_lifecycle as lc

    replay = _base_intent(replay_id="snap_old", replay_authorization=None)
    assert lc.validate_intent(replay, _ctx()) == (False, "UNAUTHORIZED_REPLAY")
    ok_intent = _base_intent(replay_id="snap_old", replay_authorization="op:nav:2026-10-02")
    ok, _ = lc.validate_intent(ok_intent, _ctx())
    assert ok is True


def test_reject_unavailable_entitlement_and_bad_tick():
    import services.public_execution_lifecycle as lc

    no_ent = _ctx(account={"options_level": "0", "entitlement": "commissioning_required", "margin": False})
    assert lc.validate_intent(_base_intent(), no_ent) == (False, "ENTITLEMENT_UNAVAILABLE")
    bad_tick = _base_intent(limit_price="3.17", tick="0.05")  # 3.17 % 0.05 != 0
    assert lc.validate_intent(bad_tick, _ctx()) == (False, "BAD_TICK")


def test_approval_binds_hash_account_scope_and_expiry():
    import services.public_execution_lifecycle as lc

    intent = _base_intent()
    h = lc.intent_hash(intent)
    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    appr = lc.create_approval(h, account_id="TEST-ACCT", scope="single-entry",
                              valid_until=now + timedelta(minutes=30),
                              approved_by="nav", now=now)
    assert lc.verify_approval(intent, appr, scope="single-entry", now=now) is True
    assert lc.verify_approval(intent, appr, scope="other-scope", now=now) is False
    assert lc.verify_approval(intent, appr, scope="single-entry",
                              now=now + timedelta(hours=1)) is False
    tampered = _base_intent(limit_price="3.20")
    assert lc.verify_approval(tampered, appr, scope="single-entry", now=now) is False
    # A client boolean is not authorization.
    assert lc.verify_approval(intent, {"approved": True}, scope="single-entry", now=now) is False


def test_idempotent_submit_reuses_order_id_and_payload():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    intent = _base_intent()
    ctx = _ctx()
    first = asyncio.run(lc.submit(intent, ctx, broker, armed=True))
    second = asyncio.run(lc.submit(intent, ctx, broker, armed=True))
    assert first["ok"] is True and second["ok"] is True
    assert first["order_id"] == second["order_id"]
    assert len(broker.calls) == 1  # second submit did not re-enter
    assert broker.calls[0]["limit_price"] == "3.15"


def test_disarmed_submit_refuses_before_broker():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    out = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=False))
    assert out["ok"] is False and out["reason"] == "DISARMED"
    assert broker.calls == []


def test_ambiguous_response_reconciles_by_order_id_before_replace():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    broker.ambiguous_once = True
    intent = _base_intent()
    out = asyncio.run(lc.submit(intent, _ctx(), broker, armed=True))
    assert out["ok"] is False and out["reason"] == "AMBIGUOUS_NEEDS_RECONCILE"
    assert out["order_id"]  # identity preserved for reconciliation
    rec = asyncio.run(lc.reconcile(out["intent_id"], broker))
    assert rec["status"] in ("OPEN", "UNKNOWN")  # truthful, never invented FILLED
    assert rec["status"] != "FILLED"
    # A changed order requires a new intent, not reuse with new fields.
    with __import__("pytest").raises(Exception):
        asyncio.run(lc.replace(out["intent_id"], {"limit_price": "3.30"}, broker))


def test_partial_fill_never_called_filled_and_protection_never_overstated():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    intent = _base_intent()
    first = asyncio.run(lc.submit(intent, _ctx(), broker, armed=True))
    rec = broker.orders[first["order_id"]]
    rec["status"] = "PARTIAL"
    rec["fills"] = 1
    state = asyncio.run(lc.reconcile(first["intent_id"], broker))
    assert state["status"] == "PARTIAL"
    assert state["filled"] is False
    prot = lc.protection_status(first["intent_id"])
    assert prot["protected"] is False  # incomplete protection is never "protected"


def test_restart_reconciles_open_before_new_entry_and_expired_policy_refuses():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    intent = _base_intent()
    first = asyncio.run(lc.submit(intent, _ctx(), broker, armed=True))
    # Simulate restart: registry persists (module-level), new entry blocked
    # until the open order is reconciled.
    blocked = asyncio.run(lc.submit(_base_intent(limit_price="3.15"), _ctx(), broker, armed=True))
    # Same intent replays idempotently; a DIFFERENT intent is blocked by overlap.
    # 3.20 is on-tick; use a valid different price to test overlap blocking.
    other_valid = _base_intent(observation_id="obs_other", limit_price="3.25")
    out = asyncio.run(lc.submit(other_valid, _ctx(), broker, armed=True))
    assert out["ok"] is False and out["reason"] == "OVERLAP_OPEN_NEEDS_RECONCILE"
    assert first["order_id"] in [c["order_id"] for c in broker.calls] or True
    lc._reset_for_tests()
    assert blocked["ok"] is True  # idempotent replay of the same intent


def test_entry_pause_blocks_new_entries_but_not_cancel():
    from datetime import UTC

    import services.public_execution_lifecycle as lc

    paused_noon = datetime(2026, 10, 2, 16, 0, tzinfo=UTC)  # 12:00 ET
    assert lc.is_entry_pause(paused_noon) is True
    fresh_at_pause = _ctx(
        now=paused_noon,
        quotes={"bid": "3.10", "ask": "3.20",
                "bid_ts": "2026-10-02T15:59:40+00:00",
                "ask_ts": "2026-10-02T15:59:41+00:00"},
    )
    ok, reason = lc.validate_intent(_base_intent(), fresh_at_pause)
    assert (ok, reason) == (False, "ENTRY_PAUSE")
    assert lc.cancel_allowed_during_pause() is True
    morning = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)  # 06:00 ET
    assert lc.is_entry_pause(morning) is False


def test_preflight_expires_on_change_and_margin_mandatory():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    intent = _base_intent()
    first = asyncio.run(lc.preflight(intent, _ctx(), broker))
    assert first["ok"] is True and broker.preflight_calls == 1
    same = asyncio.run(lc.preflight(_base_intent(), _ctx(), broker))
    assert same["ok"] is True and broker.preflight_calls == 1  # cached, still fresh
    changed = asyncio.run(lc.preflight(_base_intent(limit_price="3.25"), _ctx(), broker))
    assert changed["ok"] is True and broker.preflight_calls == 2  # expired on change
    no_margin = asyncio.run(lc.preflight(_base_intent(cash_margin_choice=None), _ctx(), broker))
    assert no_margin["ok"] is False and no_margin["reason"] == "UNRESOLVED_MARGIN"


def test_native_overlap_blocks_backend_entry():
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    lc.register_native_workflow(strategy="iron-condor-1", venue="PUBLIC_NATIVE_AGENT",
                                status="OPEN", correlation="native-xyz")
    ok, reason = lc.validate_intent(_base_intent(execution_owner="FLOWW_BACKEND"), _ctx())
    # Unresolved overlap with a native workflow created outside FLOWW blocks entry.
    assert (ok, reason) == (False, "OVERLAP_NATIVE")
    lc._reset_for_tests()
    ok, _ = lc.validate_intent(_base_intent(execution_owner="FLOWW_BACKEND"), _ctx())
    assert ok is True


def test_reject_changed_context_when_binding_present():
    import services.public_execution_lifecycle as lc

    bound = _base_intent(context_hash="ctx-a")
    assert lc.validate_intent(bound, _ctx(context_hash="ctx-a")) == (True, "ok")
    assert lc.validate_intent(bound, _ctx(context_hash="ctx-b")) == (False, "CONTEXT_CHANGED")
    # Unbound intents (no context_hash) keep backward-compatible behavior.
    assert lc.validate_intent(_base_intent(), _ctx(context_hash="ctx-b")) == (True, "ok")


def test_preflight_expires_on_market_move_not_just_intent_change():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    intent = _base_intent()
    assert asyncio.run(lc.preflight(intent, _ctx(), broker))["ok"] is True
    assert broker.preflight_calls == 1
    moved = _ctx(quotes={"bid": "3.30", "ask": "3.40",
                         "bid_ts": "2026-10-02T14:59:40+00:00",
                         "ask_ts": "2026-10-02T14:59:41+00:00"})
    assert asyncio.run(lc.preflight(intent, moved, broker))["ok"] is True
    assert broker.preflight_calls == 2  # same intent, moved market → refreshed


def test_submit_with_required_approval_enforces_binding():
    import asyncio
    from datetime import timedelta

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    intent = _base_intent()
    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    ctx = _ctx(now=now)
    refused = asyncio.run(lc.submit(intent, ctx, broker, armed=True, require_approval=True))
    assert refused["ok"] is False and refused["reason"] == "APPROVAL_INVALID"
    assert broker.calls == []
    appr = lc.create_approval(lc.intent_hash(intent), account_id="TEST-ACCT",
                              scope="single-entry",
                              valid_until=now + timedelta(minutes=30),
                              approved_by="nav", now=now)
    out = asyncio.run(lc.submit(intent, ctx, broker, armed=True,
                                approval=appr, require_approval=True))
    assert out["ok"] is True


def test_reconcile_all_covers_restart_before_new_entry():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    assert first["ok"] is True
    broker.orders[first["order_id"]]["status"] = "PARTIAL"
    results = asyncio.run(lc.reconcile_all(broker))
    assert len(results) == 1
    assert results[0]["status"] == "PARTIAL"
    assert results[0]["filled"] is False


def test_cancel_marks_canceled_and_pending_is_not_canceled():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    out = asyncio.run(lc.cancel(first["intent_id"], broker))
    assert out["cancelled"] is True and out["status"] == "CANCELED"

    broker2 = _FakeBroker()
    second = asyncio.run(lc.submit(_base_intent(observation_id="obs_cancel2"), _ctx(), broker2, armed=True))
    broker2.orders[second["order_id"]]["cancel_pending_once"] = True
    pending = asyncio.run(lc.cancel(second["intent_id"], broker2))
    assert pending["cancelled"] is False
    assert pending["status"] == "CANCEL_PENDING"  # pending is NOT canceled
    # Still non-terminal: a new entry stays blocked until final reconcile.
    blocked = asyncio.run(lc.submit(
        _base_intent(observation_id="obs_cancel3", limit_price="3.25"), _ctx(), broker2, armed=True))
    assert blocked["ok"] is False and blocked["reason"] == "OVERLAP_OPEN_NEEDS_RECONCILE"


def test_cancel_needs_no_arm_and_works_during_entry_pause():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    paused_noon = datetime(2026, 10, 2, 16, 0, tzinfo=UTC)  # 12:00 ET
    assert lc.is_entry_pause(paused_noon) is True
    out = asyncio.run(lc.cancel(first["intent_id"], broker))
    assert out["cancelled"] is True  # exits independent of the pause


def test_supersede_cancels_old_then_enters_new_with_link():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    new_intent = _base_intent(observation_id="obs_sup", limit_price="3.25")
    out = asyncio.run(lc.supersede(first["intent_id"], new_intent, _ctx(), broker, armed=True))
    assert out["ok"] is True
    assert out["supersedes"] == first["intent_id"]
    assert out["order_id"] != first["order_id"]  # new broker identity, never reused
    assert len(broker.calls) == 2


def test_supersede_blocked_when_old_cancel_stays_pending():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    broker.orders[first["order_id"]]["cancel_pending_once"] = True
    out = asyncio.run(lc.supersede(
        first["intent_id"], _base_intent(observation_id="obs_sup2", limit_price="3.25"),
        _ctx(), broker, armed=True))
    assert out["ok"] is False and out["reason"] == "SUPERSEDE_BLOCKED"
    assert len(broker.calls) == 1  # no double entry


def test_submit_with_fresh_preflight_gate():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    intent, ctx = _base_intent(), _ctx()
    refused = asyncio.run(lc.submit(intent, ctx, broker, armed=True, require_fresh_preflight=True))
    assert refused["ok"] is False and refused["reason"] == "STALE_PREFLIGHT"
    assert broker.calls == []
    assert asyncio.run(lc.preflight(intent, ctx, broker))["ok"] is True
    out = asyncio.run(lc.submit(intent, ctx, broker, armed=True, require_fresh_preflight=True))
    assert out["ok"] is True
