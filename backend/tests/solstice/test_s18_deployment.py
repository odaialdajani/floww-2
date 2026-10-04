"""S3/S6 deployment exclusion with REAL OS processes (spawn-isolated).

Every process runs under an explicit spawn context with matched Queue/Event
primitives from the same context, bounded joins with cleanup, and asserted
exit codes. Default-fork inheritance (threads, curl_cffi teardown) caused
hosted segfaults; spawn children import only the service module.
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


def _spawn():
    return _mp.get_context("spawn")


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


def _barrier_worker(path, owner, barrier, queue):
    from services import execution_lease as lease

    barrier.wait(timeout=30)
    # EXACTLY ONE acquire attempt: a correct lease grants one winner.
    # Retries are forbidden here — every extra ok True would be a second
    # executor inside the critical section.
    first = lease.acquire_lease(path, owner, ttl_s=10.0)
    held = False
    token = first.get("token") if first.get("ok") else None
    if token is not None:
        held = bool(lease.heartbeat_lease(path, token, ttl_s=10.0).get("ok"))
    queue.put({"owner": owner, "acquired": bool(first.get("ok")),
               "held": held, "token": token,
               "reason": first.get("reason")})


def _crash_worker(path):
    from services import execution_lease as lease

    acquired = lease.acquire_lease(path, "crasher", ttl_s=1.0)
    assert acquired.get("ok") is True
    os._exit(1)  # crash without release or heartbeat


def _thief_worker(path, entered, stolen):
    from services import execution_lease as lease

    assert entered.wait(timeout=30)
    current = lease._payload(path)
    current["expires_at"] = time.time() - 1.0
    with open(path, "w", encoding="utf-8") as fh:
        import json

        fh.write(json.dumps(current))
    assert lease.acquire_lease(path, "thief", ttl_s=10.0)["ok"] is True
    stolen.set()


def _foreign_release_worker(path, queue):
    from services import execution_lease as lease

    queue.put(lease.release_lease(path, "not-the-token"))


def _start(ctx, target, args):
    proc = ctx.Process(target=target, args=args)
    proc.start()
    return proc


def _join(proc, timeout=30):
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        raise AssertionError("worker hung and was terminated")
    assert proc.exitcode == 0, f"worker exited {proc.exitcode}"


def _tmp_path(tmp_path, name="exec-lease"):
    return str(tmp_path / name)


def test_sequential_holders_serialize(tmp_path):
    from services import execution_lease as lease

    ctx = _spawn()
    path = _tmp_path(tmp_path)
    mq = ctx.Queue()
    procs = [ctx.Process(target=_race_worker, args=(path, f"p{i}", 0.4, mq))
             for i in range(4)]
    for p in procs:
        p.start()
        time.sleep(0.05)
    for p in procs:
        _join(p)
    # Sequential acquisitions serialize: every racer eventually acquires AND
    # holds (heartbeat proves no silent takeover mid-hold).
    results = [mq.get(timeout=10) for _ in procs]
    assert all(r["acquired"] and r["held"] for r in results), results
    assert lease.read_lease(path)["present"] is False  # all released


def test_barrier_contention_exactly_one_effective_winner(tmp_path):
    from services import execution_lease as lease

    ctx = _spawn()
    path = _tmp_path(tmp_path)
    # Seed an EXPIRED lease so all contenders race the takeover at once.
    seed = lease.acquire_lease(path, "stale-holder", ttl_s=0.5)
    assert seed.get("ok") is True
    time.sleep(0.7)
    barrier = ctx.Barrier(4, timeout=30)
    mq = ctx.Queue()
    procs = [ctx.Process(target=_barrier_worker, args=(path, f"c{i}", barrier, mq))
             for i in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        _join(p, timeout=40)
    # Contender results are INSPECTED (not just the winner): exactly one
    # single acquire attempt succeeds — the losers observe the live owner
    # and refuse LEASE_HELD. No contender receives a success it then loses.
    results = [mq.get(timeout=10) for _ in procs]
    final = lease.read_lease(path)
    assert final["present"] is True
    winners = [r for r in results if r["acquired"]]
    assert len(winners) == 1, results
    assert winners[0]["held"] is True
    assert winners[0]["token"] is not None
    losers = [r for r in results if not r["acquired"]]
    assert len(losers) == 3, results
    assert all(r["reason"] == "LEASE_HELD" for r in losers), results
    for r in losers:
        assert r["token"] is None, r
    assert lease.release_lease(path, winners[0]["token"])["ok"] is True


def test_simultaneous_race_single_winner(tmp_path):
    from services import execution_lease as lease

    ctx = _spawn()
    path = _tmp_path(tmp_path)
    mq = ctx.Queue()
    first = lease.acquire_lease(path, "holder", ttl_s=10.0)
    assert first.get("ok") is True
    procs = [ctx.Process(target=_race_worker, args=(path, f"late{i}", 0.0, mq, 1))
             for i in range(3)]
    for p in procs:
        p.start()
    for p in procs:
        _join(p)
    # While held, contenders cannot acquire; contender results show refusal.
    late = [mq.get(timeout=10) for _ in procs]
    assert all(r["acquired"] is False for r in late), late
    assert lease.heartbeat_lease(path, first["token"], ttl_s=10.0)["ok"] is True
    assert lease.release_lease(path, first["token"])["ok"] is True


def test_crash_recovers_via_expiry_steal(tmp_path):
    from services import execution_lease as lease

    ctx = _spawn()
    path = _tmp_path(tmp_path)
    proc = ctx.Process(target=_crash_worker, args=(path,))
    proc.start()
    proc.join(30)
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        raise AssertionError("crasher hung")
    assert proc.exitcode == 1  # crashed, never released
    assert lease.acquire_lease(path, "next", ttl_s=10.0)["reason"] == "LEASE_HELD"
    time.sleep(1.2)  # past the 1s TTL with no heartbeat
    stolen = lease.acquire_lease(path, "next", ttl_s=10.0)
    assert stolen.get("ok") is True and stolen.get("stole_expired") is True
    assert lease.heartbeat_lease(path, stolen["token"], ttl_s=10.0)["ok"] is True
    assert lease.release_lease(path, stolen["token"])["ok"] is True


def test_foreign_release_and_heartbeat_refused(tmp_path):
    from services import execution_lease as lease

    ctx = _spawn()
    path = _tmp_path(tmp_path)
    first = lease.acquire_lease(path, "owner", ttl_s=10.0)
    assert first.get("ok") is True
    mq = ctx.Queue()
    proc = ctx.Process(target=_foreign_release_worker, args=(path, mq))
    proc.start()
    _join(proc)
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


def test_fenced_action_proves_ownership_around_work(tmp_path):
    from services import execution_lease as lease

    path = _tmp_path(tmp_path)
    assert lease.fenced_action(path, "a", 10.0, lambda: 42) == {"ok": True, "result": 42}

    def boom():
        raise RuntimeError("work failed")

    out = lease.fenced_action(path, "a", 10.0, boom)
    assert out["reason"] == "FENCED_ACTION_FAILED"
    assert lease.read_lease(path)["present"] is False  # released despite failure


def test_fenced_action_detects_mid_section_takeover(tmp_path):
    from services import execution_lease as lease

    ctx = _spawn()
    path = _tmp_path(tmp_path)
    entered = ctx.Event()
    stolen = ctx.Event()

    def work():
        entered.set()
        assert stolen.wait(timeout=30)
        return "side-effects-untrusted"

    proc = ctx.Process(target=_thief_worker, args=(path, entered, stolen))
    proc.start()
    out = lease.fenced_action(path, "victim", ttl_s=10.0, fn=work)
    _join(proc)
    assert out["reason"] == "FENCED_OUT", out
    assert lease.read_lease(path)["owner"] == "thief"


def test_stale_token_cannot_clobber_new_owner(tmp_path):
    from services import execution_lease as lease

    path = _tmp_path(tmp_path)
    first = lease.acquire_lease(path, "owner-a", ttl_s=10.0)
    assert first.get("ok") is True
    # Force-expiry behind the lease's back (crash/no-heartbeat equivalent).
    current = lease._payload(path)
    current["expires_at"] = time.time() - 1.0
    with open(path, "w", encoding="utf-8") as fh:
        import json

        fh.write(json.dumps(current))
    second = lease.acquire_lease(path, "owner-b", ttl_s=10.0)
    assert second.get("ok") is True and second.get("stole_expired") is True
    # The stale token now refuses everywhere AND leaves B's payload intact.
    assert lease.heartbeat_lease(path, first["token"])["reason"] == "LEASE_NOT_OWNER"
    assert lease.release_lease(path, first["token"])["reason"] == "LEASE_NOT_OWNER"
    live = lease._payload(path)
    assert live["owner"] == "owner-b"
    assert lease.heartbeat_lease(path, second["token"])["ok"] is True
    assert lease.release_lease(path, second["token"])["ok"] is True


def test_fence_generation_survives_release(tmp_path):
    from services import execution_lease as lease

    path = _tmp_path(tmp_path)
    first = lease.acquire_lease(path, "a", ttl_s=10.0)
    assert first.get("ok") is True
    fence_a = lease.read_lease(path)["fence"]
    assert lease.release_lease(path, first["token"])["ok"] is True
    second = lease.acquire_lease(path, "b", ttl_s=10.0)
    assert second.get("ok") is True
    assert lease.read_lease(path)["fence"] > fence_a
    assert lease.release_lease(path, second["token"])["ok"] is True


def test_deployment_scope_is_single_host_volume():
    from services import execution_lease as lease

    scope = lease.deployment_scope()
    assert scope["scope"] == "single host with one shared filesystem volume"
    assert "multi-host" in scope["not_scope"]
    # Ship/CI hosts are POSIX (flock); the flag is reported, not assumed.
    assert scope["multiprocess_safe"] == lease.MULTIPROCESS_SAFE


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


def test_expiry_guard_uses_et_calendar_days():
    import services.execution_protection as prot

    # 00:30 UTC Oct 3 is still Oct 2 in New York: DTE to an Oct-3 expiry
    # is 1 ET day, not 0 UTC days (UTC math would undercount → fail-open).
    overnight = datetime(2026, 10, 3, 0, 30, tzinfo=UTC)
    out = prot.entry_expiry_guard("2026-10-03", overnight, {"min_entry_dte": 1})
    assert out == {"ok": True, "dte": 1, "version": "execution-protection.v1"}


def test_expiry_guard_refuses_malformed_cutoff():
    import services.execution_protection as prot

    # Same-day expiry at 10:00 ET with a garbage cutoff must refuse, not
    # string-compare its way to an admission.
    morning = datetime(2026, 10, 2, 14, 0, tzinfo=UTC)  # 10:00 ET
    out = prot.entry_expiry_guard(
        "2026-10-02", morning,
        {"min_entry_dte": 0, "same_day_cutoff_et": "1pm"})
    assert out["reason"] == "GUARD_UNCONFIGURED", out
    out = prot.entry_expiry_guard(
        "2026-10-02", morning,
        {"min_entry_dte": 0, "same_day_cutoff_et": "13:00"})
    assert out["ok"] is True, out


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
