"""S03 mandatory full admission on every entry path (test-local proof).

Drives the commissioned pipeline (policy, stored approval, operator
registry, preflight gate, census/recovery, ceilings, risk facts, native
census, evidence grade, expiry/protection) plus the lease pre-effect gate,
with an exploding fake broker: every denied case asserts zero broker
touches. The admitted positive places exactly once through the
lease-gated effect. No live calls, no mounts, no flags.
"""
import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime, timedelta


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


def _intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_full",
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
    def __init__(self, ok):
        self._ok = ok

    async def preflight_single_leg(self, **kw):
        return {"total": "318.20", "fees": "3.20",
                "buying_power_ok": self._ok}


def _full_stack(conn, operator="op-1"):
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
    assert adm.set_account_policy_required(
        conn, "ACCT-1", full, operator)["ok"] is True
    intent = _intent()
    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    appr = lc.create_approval(
        lc.intent_hash(intent), intent["account_id"], "single-entry",
        now + timedelta(hours=1), operator, now=now)
    assert adm.store_approval_required(conn, appr, operator)["ok"] is True
    return intent, appr


def _admit(conn, intent, ctx, **kw):
    import services.execution_admission as adm

    params = {"approval": kw.pop("approval", None), "operator_id": "op-1",
              "risk_facts": _facts(),
              "remote_native": {"workflows": []}}
    params.update(kw)
    return adm.admit_commissioned_entry(
        conn, intent, ctx, _ExplodingBroker(), **params)


def test_denied_matrix_zero_broker_effects():
    import asyncio

    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        intent, appr = _full_stack(conn)
        ctx = _ctx()
        # 1. No fresh preflight refuses.
        out = _admit(conn, intent, ctx, approval=appr)
        assert out["reason"] == "STALE_PREFLIGHT", out
        # Arm the preflight cache for the remaining probes.
        assert asyncio.run(
            lc.preflight(intent, ctx, _VerdictBroker(True)))["ok"] is True
        # 2. Unregistered presenter refuses.
        out = _admit(conn, intent, ctx, approval=appr, operator_id="ghost")
        assert out["reason"] in ("OPERATOR_UNKNOWN", "APPROVAL_INVALID"), out
        # 3. Missing approval refuses.
        out = _admit(conn, intent, ctx, approval=None)
        assert out["reason"] == "APPROVAL_INVALID", out
        # 4. Stale risk facts refuse.
        stale = _facts(asof="2026-10-02T14:00:00+00:00")
        out = _admit(conn, intent, ctx, approval=appr, risk_facts=stale)
        assert out["reason"] in ("STALE_FACTS", "RISK_FACTS_INCOMPLETE"), out
        # 5. Foreign-account facts refuse.
        foreign = _facts(account_id="OTHER-ACCT")
        out = _admit(conn, intent, ctx, approval=appr, risk_facts=foreign)
        assert out["reason"] in ("RISK_FACTS_INCOMPLETE", "STALE_FACTS"), out
        # 6. Open remote native workflow refuses.
        out = _admit(conn, intent, ctx, approval=appr,
                      remote_native={"workflows": [{"strategy": "X",
                                                    "status": "OPEN"}]})
        assert out["reason"] == "OVERLAP_NATIVE", out
        # 7. Client-asserted evidence grade refuses.
        out = _admit(conn, intent, ctx, approval=appr,
                      evidence_grade="client-asserted")
        assert out["reason"] == "EVIDENCE_UNVERIFIED", out
    finally:
        conn.close()


def test_admitted_positive_places_once_through_lease(tmp_path):
    import asyncio

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc
    from services import execution_lease as lease

    conn = _memdb()
    try:
        intent, appr = _full_stack(conn)
        ctx = _ctx()
        assert asyncio.run(
            lc.preflight(intent, ctx, _VerdictBroker(True)))["ok"] is True
        out = _admit(conn, intent, ctx, approval=appr)
        assert out["decision"] == "ADMIT", out
        # Lease-gated single economic effect for the admitted intent.
        path = str(tmp_path / "full-entry.lock")
        acquired = lease.acquire_lease(path, "owner-a", 60.0)
        assert acquired.get("ok") is True
        calls = []

        def effect():
            calls.append("place")
            return {"order_id": "oid-admitted-1"}

        try:
            placed = lease.effect_with_lease(
                path, acquired["token"], 60.0, effect)
            assert placed.get("ok") is True
            assert calls == ["place"]
        finally:
            lease.release_lease(path, acquired["token"])
    finally:
        conn.close()
