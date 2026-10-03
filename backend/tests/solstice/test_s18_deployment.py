"""S3 deployment exclusion (real processes), protection and expiry guards.

Lease exclusion is proven with independent OS processes, not threads.
No live calls, no activation, no venue flags.
"""

import sys

sys.path.insert(0, "backend")

import multiprocessing as _mp
import os
import time
from datetime import UTC, datetime

import pytest


@pytest.fixture(autouse=True)
def _isolate():
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    yield
    lc._reset_for_tests()


def _race_worker(path, owner, hold_s, queue, retries=400):
    from services import execution_lease as lease

    first = {"ok": False}
    for _ in range(max(1, retries)):
        first = lease.acquire_lease(path, owner, ttl_s=10.0)
        if first.get("ok"):
            break
        time.sleep(0.05)
    held = False
    if first.get("ok"):
        time.sleep(hold_s)
        second = lease.heartbeat_lease(path, first["token"], ttl_s=10.0)
        held = bool(second.get("ok"))
        lease.release_lease(path, first["token"])
    queue.put({"owner": owner, "acquired": bool(first.get("ok")), "held": held})


def _crash_worker(path):
    from services import execution_lease as lease

    acquired = lease.acquire_lease(path, "crasher", ttl_s=1.0)
    assert acquired.get("ok") is True
    os._exit(1)  # crash without release or heartbeat


def _foreign_release_worker(path, queue):
    from services import execution_lease as lease

    queue.put(lease.release_lease(path, "not-the-token"))


def _run_proc(target, args, timeout=30):
    ctx = _mp.get_context()
    proc = ctx.Process(target=target, args=args)
    proc.start()
    proc.join(timeout)
    assert not proc.is_alive(), "worker hung"
    return proc


def _tmp_path(tmp_path, name="exec-lease"):
    return str(tmp_path / name)


def test_sequential_holders_serialize(tmp_path):
    from services import execution_lease as lease

    path = _tmp_path(tmp_path)
    mq = _mp.Queue()
    procs = [
        _mp.get_context().Process(target=_race_worker, args=(path, f"p{i}", 0.4, mq))
        for i in range(4)
    ]
    for p in procs:
        p.start()
        time.sleep(0.05)
    for p in procs:
        p.join(30)
        assert p.exitcode == 0
    # Sequential acquisitions serialize: every racer eventually acquires AND
    # holds (heartbeat proves no silent takeover mid-hold).
    results = [mq.get(timeout=10) for _ in procs]
    assert all(r["acquired"] and r["held"] for r in results), results
    assert lease.read_lease(path)["present"] is False  # all released


def test_simultaneous_race_single_winner(tmp_path):
    from services import execution_lease as lease

    path = _tmp_path(tmp_path)
    mq = _mp.Queue()
    first = lease.acquire_lease(path, "holder", ttl_s=10.0)
    assert first.get("ok") is True
    procs = [
        _mp.get_context().Process(target=_race_worker, args=(path, f"late{i}", 0.0, mq, 1))
        for i in range(3)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
        assert p.exitcode == 0
    # While held, no contender acquires; holder heartbeat still proves ownership.
    assert lease.heartbeat_lease(path, first["token"], ttl_s=10.0)["ok"] is True
    assert lease.release_lease(path, first["token"])["ok"] is True


def test_crash_recovers_via_expiry_steal(tmp_path):
    from services import execution_lease as lease

    path = _tmp_path(tmp_path)
    proc = _run_proc(_crash_worker, (path,))
    assert proc.exitcode == 1  # crashed, never released
    assert lease.acquire_lease(path, "next", ttl_s=10.0)["reason"] == "LEASE_HELD"
    time.sleep(1.2)  # past the 1s TTL with no heartbeat
    stolen = lease.acquire_lease(path, "next", ttl_s=10.0)
    assert stolen.get("ok") is True and stolen.get("stole_expired") is True
    assert lease.heartbeat_lease(path, stolen["token"], ttl_s=10.0)["ok"] is True
    assert lease.release_lease(path, stolen["token"])["ok"] is True


def test_foreign_release_and_heartbeat_refused(tmp_path):
    from services import execution_lease as lease

    path = _tmp_path(tmp_path)
    first = lease.acquire_lease(path, "owner", ttl_s=10.0)
    assert first.get("ok") is True
    mq = _mp.Queue()
    _run_proc(_foreign_release_worker, (path, mq))
    assert mq.get(timeout=10)["reason"] == "LEASE_NOT_OWNER"
    assert lease.heartbeat_lease(path, first["token"], ttl_s=10.0)["ok"] is True
    assert lease.release_lease(path, "wrong")["reason"] == "LEASE_NOT_OWNER"
    assert lease.release_lease(path, first["token"])["ok"] is True
    assert lease.heartbeat_lease(path, first["token"])["reason"] in (
        "LEASE_ABSENT", "LEASE_NOT_OWNER")


def test_expired_lease_cannot_heartbeat_back(tmp_path):
    from services import execution_lease as lease

    path = _tmp_path(tmp_path)
    first = lease.acquire_lease(path, "owner", ttl_s=1.0)
    assert first.get("ok") is True
    time.sleep(1.2)
    assert lease.heartbeat_lease(path, first["token"])["reason"] == "LEASE_EXPIRED"


def test_protection_refuses_unverified_everywhere():
    import services.execution_protection as prot

    for product, order in (("OPTION", "SINGLE_LEG_LIMIT"), ("OPTION", "SPREAD_LIMIT"),
                           ("EQUITY", "LIMIT"), ("NOPE", "NOPE")):
        out = prot.protection_admission(product, order, 3)
        assert out["covered"] is False
        assert out["reason"] == "PROTECTION_UNVERIFIED"
        assert out["covered_quantity"] == 0
        assert out["version"] == "execution-protection.v1", (product, order)
    assert prot.protection_admission("OPTION", "SINGLE_LEG_LIMIT", 0)["reason"] == "BAD_CONTRACT"


def test_entry_expiry_guard_policy_driven():
    import services.execution_protection as prot

    friday = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    assert prot.entry_expiry_guard("not-a-date", friday, {"min_entry_dte": 1})["reason"] == "EXPIRY_INVALID"
    assert prot.entry_expiry_guard("2026-10-09", friday, {})["reason"] == "GUARD_UNCONFIGURED"
    assert prot.entry_expiry_guard("2026-10-09", friday, None)["reason"] == "GUARD_UNCONFIGURED"
    near = prot.entry_expiry_guard("2026-10-03", friday, {"min_entry_dte": 5})
    assert near["reason"] == "EXPIRY_TOO_NEAR" and "assignment" in near["detail"]
    late = datetime(2026, 10, 2, 17, 30, tzinfo=UTC)  # 13:30 ET Friday
    assert prot.entry_expiry_guard(
        "2026-10-02", late, {"min_entry_dte": 0})["reason"] == "EXPIRY_TOO_NEAR"
    ok = prot.entry_expiry_guard("2026-10-09", friday, {"min_entry_dte": 5})
    assert ok == {"ok": True, "dte": 7, "version": "execution-protection.v1"}


def test_cancel_and_reconcile_stay_available_during_entry_pause():
    import asyncio

    import services.public_execution_lifecycle as lc

    noon = datetime(2026, 10, 2, 16, 0, tzinfo=UTC)  # 12:00 ET: entry pause
    assert lc.is_entry_pause(noon) is True
    assert lc.cancel_allowed_during_pause() is True

    class _Broker:
        def __init__(self):
            self.orders = {}

        async def place_order(self, **kw):
            self.orders[kw["order_id"]] = {"status": "OPEN"}
            return {"order_id": kw["order_id"], "status": "OPEN"}

        async def get_order(self, account_id, order_id):
            return {"order_id": order_id, "status": self.orders[order_id]["status"]}

        async def cancel_order(self, account_id, order_id):
            self.orders[order_id]["status"] = "CANCELED"
            return {"orderId": order_id, "status": "CANCELED"}

    intent = {
        "intent_version": "execution-intent.v1", "ticker": "SPY",
        "contract": {"osi": "SPY260904C00760000", "expiry": "2026-09-04",
                     "option_type": "CALL", "strike_exact": "760.00",
                     "multiplier": "100", "multiplier_provenance": "v"},
        "side": "BUY", "open_close": "OPEN", "quantity": 1,
        "limit_price": "3.15", "tick": "0.05", "account_id": "A",
        "venue": "PUBLIC", "cash_margin_choice": "CASH",
        "risk_policy_version": "research_barriers.v1",
        "execution_owner": "FLOWW_BACKEND",
    }
    ctx = {"quotes": {"bid": "3.10", "ask": "3.20",
                      "bid_ts": "2026-10-02T14:59:40+00:00",
                      "ask_ts": "2026-10-02T14:59:41+00:00"},
           "now": datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
           "account": {"entitlement": "verified"},
           "supported_expiries": ["2026-09-04"],
           "supported_products": ["OPTION", "EQUITY"]}
    broker = _Broker()
    first = asyncio.run(lc.submit(intent, ctx, broker, armed=True))
    assert first["ok"] is True
    cancelled = asyncio.run(lc.cancel(first["intent_id"], broker))
    assert cancelled["cancelled"] is True  # exits ignore the entry pause
    seen = asyncio.run(lc.reconcile(first["intent_id"], broker))
    assert seen["status"] == "CANCELED"
