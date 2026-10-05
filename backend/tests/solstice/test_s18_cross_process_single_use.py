"""S05 cross-process single-use: durable claim atomicity audit.

The documented residual (lifecycle line ~120 and MUSE_STATE): the in-process
_SUBMIT_LOCK excludes same-process races only; the durable seam must make a
second writer's ownership write REFUSE, never silently replace the original
broker identity (pre-fix `INSERT OR REPLACE` clobbered it), and the first
durable write must be an atomic claim (plain INSERT; a committed rival row
fails the write instead of double-claiming). Approval single-use is enforced
by intent-hash binding (verify_approval) plus this one-economic-order intent
claim; a revoked approval refuses at the strict stored seam.

Fake brokers only; a real spawned child process places via a file-backed
DuckDB store (spawn-isolated, like the S14 deployment suite). No live calls,
no activation, no venue flags.
"""

import asyncio
import sys

sys.path.insert(0, "backend")

import multiprocessing as _mp

import pytest


@pytest.fixture(autouse=True)
def _isolate():
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    yield
    lc._reset_for_tests()


def _spawn():
    return _mp.get_context("spawn")


def _start(ctx, target, args):
    proc = ctx.Process(target=target, args=args)
    proc.start()
    return proc


def _join(proc, timeout=60):
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        raise AssertionError("worker hung and was terminated")
    assert proc.exitcode == 0, f"worker exited {proc.exitcode}"


def _base_intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_s5x",
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
    base = {
        "quotes": {"bid": "3.10", "ask": "3.20",
                   "bid_ts": "2026-10-02T14:59:40+00:00",
                   "ask_ts": "2026-10-02T14:59:41+00:00"},
        "now": __import__("datetime").datetime(
            2026, 10, 2, 15, 0, tzinfo=__import__("datetime").UTC),
        "account": {"options_level": "2", "entitlement": "verified",
                    "margin": True},
        "snapshot_id": "snap_1",
        "supported_expiries": ["2026-09-04"],
        "supported_products": ["OPTION", "EQUITY"],
    }
    base.update(kw)
    return base


class _RecordingBroker:
    def __init__(self):
        self.calls = []

    async def place_order(self, **kw):
        self.calls.append(dict(kw))
        oid = kw.get("order_id")
        return {"order_id": oid, "status": "OPEN", "raw": {}}


def _claim_row(conn, intent_id):
    return conn.execute(
        "SELECT order_id FROM execution_intents_v1 WHERE intent_id = ?",
        [intent_id]).fetchone()


def test_durable_claim_refuses_foreign_order_id(tmp_path):
    """Racing writer's persist step must not replace the original identity.

    Reproduces the documented cross-process interleaving deterministically:
    writer A claimed + persisted order A; writer B's advisory load happened
    before A's commit, so B's critical section holds its own record with
    order B and reaches _persist afterwards. That write must REFUSE and
    leave A's durable identity intact — pre-fix INSERT OR REPLACE clobbers.
    """
    import duckdb

    import services.public_execution_lifecycle as lc

    conn = duckdb.connect()
    assert lc.register_store(conn) is True
    broker = _RecordingBroker()
    intent = _base_intent()
    res = asyncio.run(lc.submit(intent, _ctx(), broker, armed=True))
    assert res["ok"] is True, res
    intent_id = res["intent_id"]
    assert _claim_row(conn, intent_id)[0] == res["order_id"]

    # Writer B's in-memory record for the same intent (its own order id),
    # exactly as its critical section built it before its persist step.
    lc._INTENTS[intent_id] = {
        "intent": dict(intent), "intent_hash": lc.intent_hash(intent),
        "order_id": "ord_foreign_b", "payload": {}, "state": "SUBMITTED",
    }
    persisted = lc._persist(intent_id)
    row = _claim_row(conn, intent_id)
    assert persisted is False, "foreign order_id write must refuse"
    assert row is not None and row[0] == res["order_id"], (
        "durable claim must keep the original broker identity")


def test_first_claim_wins_and_second_writer_refuses(tmp_path):
    """Fresh-intent race: exactly one atomic claim; the loser's write fails.

    Neither writer has a durable row yet (the true race window). The first
    persist is the claim; the rival's later persist with a different order_id
    must refuse instead of replacing the winner. Pre-fix both writes succeed
    and the durable registry keeps only the last writer — the exact silent
    double-ownership the S05 contract forbids.
    """
    import duckdb

    import services.public_execution_lifecycle as lc

    conn = duckdb.connect()
    assert lc.register_store(conn) is True
    intent = _base_intent(observation_id="obs_s5x_race")
    intent_id = f"in_{lc.intent_hash(intent)[:12]}"

    lc._INTENTS[intent_id] = {
        "intent": dict(intent), "intent_hash": lc.intent_hash(intent),
        "order_id": "ord_first_b", "payload": {}, "state": "SUBMITTED",
    }
    first = lc._persist(intent_id)
    assert first is True
    assert _claim_row(conn, intent_id)[0] == "ord_first_b"

    # The rival writer's identical critical-section state, different order.
    lc._INTENTS[intent_id]["order_id"] = "ord_late_a"
    late = lc._persist(intent_id)
    row = _claim_row(conn, intent_id)
    assert late is False, "second writer must not claim an owned intent"
    assert row is not None and row[0] == "ord_first_b", (
        "winner's durable claim must survive the late writer")


def _placement_child(db_path, queue):
    import asyncio

    import duckdb

    from services import public_execution_lifecycle as lc
    from tests.solstice.test_s18_cross_process_single_use import _base_intent, _ctx, _RecordingBroker

    class _ChildBroker(_RecordingBroker):
        pass

    conn = duckdb.connect(db_path)
    assert lc.register_store(conn) is True
    broker = _ChildBroker()
    res = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    conn.close()
    queue.put({"ok": res["ok"], "order_id": res.get("order_id"),
               "status": res.get("status"), "calls": len(broker.calls)})


def test_cross_pid_restart_duplicate_zero_new_placements(tmp_path):
    """Real spawned child places once; a second PID never places again.

    Child: file-backed DuckDB store, armed submit, one placement, exit
    (releasing the file lock). Parent: reconnects the same durable store —
    the cross-process guard resolves the same intent as a duplicate bound
    to the child's ORIGINAL order id (the durable row is the ownership
    truth even before recover_open rehydrates it), with zero placements in
    this process, before and after explicit recovery. No new economic order.
    """
    import duckdb

    import services.public_execution_lifecycle as lc

    db = str(tmp_path / "s05-cross-pid.db")
    ctx = _spawn()
    q = ctx.Queue()
    proc = _start(ctx, _placement_child, (db, q))
    _join(proc)
    child = q.get(timeout=10)
    assert child["ok"] is True and child["calls"] == 1, child
    original = child["order_id"]

    conn = duckdb.connect(db)
    assert lc.register_store(conn) is True
    broker = _RecordingBroker()

    # Without recovery: the durable row itself must resolve the duplicate —
    # a second economic order for the same intent is refused by identity.
    fresh = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    assert fresh["ok"] is True and fresh.get("duplicate") is True, fresh
    assert fresh["order_id"] == original
    assert len(broker.calls) == 0

    lc.recover_open()
    dup = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    assert dup["ok"] is True and dup.get("duplicate") is True, dup
    assert dup["order_id"] == original
    assert len(broker.calls) == 0  # zero new economic orders in this PID


def test_injected_write_fault_denies_before_effect(tmp_path):
    """A store that cannot write the intent claim refuses with zero placements.

    Persistence precedes effect (S05/S11): an injected INSERT failure on the
    intents table must deny entry (STORE_UNAVAILABLE) before the broker is
    touched, and the in-memory claim is rolled back, never left lying.
    """
    import duckdb

    import services.public_execution_lifecycle as lc

    class _FaultyStore:
        def __init__(self, conn):
            self._conn = conn
            self.fault = False

        def execute(self, sql, *args):
            if self.fault and "INTO execution_intents_v1" in sql:
                raise RuntimeError("injected write fault")
            return self._conn.execute(sql, *args)

    conn = _FaultyStore(duckdb.connect())
    assert lc.register_store(conn) is True
    conn.fault = True
    broker = _RecordingBroker()
    intent = _base_intent(observation_id="obs_s5x_fault")
    res = asyncio.run(lc.submit(intent, _ctx(), broker, armed=True))
    assert res["ok"] is False and res["reason"] == "STORE_UNAVAILABLE", res
    assert len(broker.calls) == 0
    intent_id = res["intent_id"]
    assert intent_id not in lc._INTENTS, "unpersisted claim must be rolled back"
