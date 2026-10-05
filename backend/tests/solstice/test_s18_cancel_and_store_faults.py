"""S04/S12 cancellation truth + S01 store-failure authority audit.

Adversarial seam from the finish harness list: "lease loss before effect
and cancellation during async preparation." Cancellation during the broker
effect await must preserve ambiguity truthfully — the record becomes
UNKNOWN with an annotation, never a clean SUBMITTED certainty, and a
retry reconciles the ORIGINAL identity with zero new placements.
S01 clause "required store failures purge permission": an injected
durable-approval-store fault must purge memory authority (store) and
never fake a revocation (revoke). Fake transports only; no live calls.
"""

import asyncio
import sys

sys.path.insert(0, "backend")


def _base_intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_s5cancel",
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
    from datetime import UTC, datetime

    base = {
        "quotes": {"bid": "3.10", "ask": "3.20",
                   "bid_ts": "2026-10-02T14:59:40+00:00",
                   "ask_ts": "2026-10-02T14:59:41+00:00"},
        "now": datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        "account": {"options_level": "2", "entitlement": "verified",
                    "margin": True},
        "snapshot_id": "snap_1",
        "supported_expiries": ["2026-09-04"],
        "supported_products": ["OPTION", "EQUITY"],
    }
    base.update(kw)
    return base


def _base_approval():
    return {
        "approval_id": "ap-fault-1",
        "intent_hash": "b" * 64,
        "account_id": "ACCT-1",
        "scope": "order-entry",
        "valid_until": "2026-10-02T16:00:00+00:00",
        "approved_by": "op-1",
        "approved_at": "2026-10-02T15:00:00+00:00",
    }


class _RecordingBroker:
    def __init__(self):
        self.calls = []

    async def place_order(self, **kw):
        self.calls.append(dict(kw))
        oid = kw.get("order_id")
        return {"order_id": oid, "status": "OPEN", "raw": {}}


class _HangingBroker:
    """First place_order never returns: the cancellation point."""

    def __init__(self):
        self.calls = []
        self.started = asyncio.Event()

    async def place_order(self, **kw):
        self.calls.append(dict(kw))
        self.started.set()
        await asyncio.Event().wait()


class _FaultyConn:
    """Wraps a live conn; faults statements matching `pattern`."""

    def __init__(self, conn, pattern):
        self._conn = conn
        self._pattern = pattern

    def execute(self, sql, *args):
        if self._pattern in sql:
            raise RuntimeError("injected admission store fault")
        return self._conn.execute(sql, *args)


def test_cancellation_during_broker_await_preserves_unknown():
    """Cancelled effect await must leave UNKNOWN truth, zero new orders.

    The broker call was interrupted with its outcome unknowable: the record
    claiming a clean SUBMITTED would be a false certainty (S12 unknown stays
    unknown), and an unannotated record lets a later duplicate report the
    order as simply acknowledged. Retry reconciles the ORIGINAL identity.
    """
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    broker = _HangingBroker()
    intent, ctx = _base_intent(), _ctx()

    async def scenario():
        task = asyncio.create_task(lc.submit(intent, ctx, broker, armed=True))
        await broker.started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled"
        return "completed"

    assert asyncio.run(scenario()) == "cancelled"
    intent_id = f"in_{lc.intent_hash(intent)[:12]}"
    rec = lc._INTENTS.get(intent_id)
    assert rec is not None, "claimed intent must remain owned after cancel"
    assert rec.get("state") == "UNKNOWN", (
        f"cancelled effect must preserve UNKNOWN, got {rec.get('state')!r}")
    assert rec.get("error"), "cancellation must be annotated, not silent"

    # Retry cannot issue another economic order: duplicate returns the
    # ORIGINAL identity and the fresh broker is never called.
    fresh = _RecordingBroker()
    dup = asyncio.run(lc.submit(intent, ctx, fresh, armed=True))
    assert dup["ok"] is True and dup.get("duplicate") is True, dup
    assert dup["order_id"] == rec["order_id"]
    assert len(fresh.calls) == 0
    lc._reset_for_tests()


def test_store_failure_purges_memory_authority():
    """S01: required store failure purges permission, never leaves it live."""
    import duckdb

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = duckdb.connect(":memory:")
    try:
        lc.register_store(conn)
        appr = _base_approval()
        assert adm.store_approval_required(conn, dict(appr), "op-1")["ok"] is True
        assert lc._APPROVALS.get(appr["approval_id"]) is not None
        faulty = _FaultyConn(conn, "INTO approvals_v1")
        out = adm.store_approval_required(faulty, dict(appr), "op-1")
        assert out["ok"] is False and out["reason"] == "APPROVAL_STORE_UNAVAILABLE"
        assert lc._APPROVALS.get(appr["approval_id"]) is None, (
            "store failure must purge memory authority, not leave it live")
    finally:
        conn.close()
        lc._reset_for_tests()


def test_revoke_store_failure_no_phantom_revocation():
    """S01: revoke store failure reports explicitly; no phantom revocation.

    Durable truth governs: a failed revoke leaves the approval ACTIVE both
    durably and in memory — the operator sees STORE_UNAVAILABLE and can
    retry; a silent memory-only revoke would fake authority it lacks.
    """
    import duckdb

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = duckdb.connect(":memory:")
    try:
        lc.register_store(conn)
        appr = _base_approval()
        stored = adm.store_approval_required(conn, dict(appr), "op-1")
        assert stored["ok"] is True
        approval_id = stored["approval_id"]
        faulty = _FaultyConn(conn, "UPDATE approvals_v1")
        out = adm.revoke_approval_required(faulty, approval_id, "op-1")
        assert out["ok"] is False and out["reason"] == "APPROVAL_STORE_UNAVAILABLE"
        row = conn.execute(
            "SELECT revoked FROM approvals_v1 WHERE approval_id = ?",
            [approval_id]).fetchone()
        assert row is not None and bool(row[0]) is False
        mem = lc._APPROVALS.get(approval_id)
        assert mem is not None and mem.get("revoked") is not True, (
            "memory must mirror durable truth; no phantom revocation")
    finally:
        conn.close()
        lc._reset_for_tests()
