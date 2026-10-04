"""S05 durable single-use reservation and retry: counterexample audit.

Same-intent same-instant duplicates place once (one economic order);
ambiguous-ACK retry reuses the original broker identity without a second
placement. Fake broker only; no live calls.
"""
import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime


def _base_intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_s5",
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
        "now": datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        "account": {"options_level": "2", "entitlement": "verified",
                    "margin": True},
        "snapshot_id": "snap_1",
        "supported_expiries": ["2026-09-04"],
        "supported_products": ["OPTION", "EQUITY"],
    }
    base.update(kw)
    return base


class _FakeBroker:
    def __init__(self):
        self.calls = []
        self.orders = {}
        self.ambiguous_once = False

    async def place_order(self, **kw):
        self.calls.append(dict(kw))
        if self.ambiguous_once:
            self.ambiguous_once = False
            raise TimeoutError("ambiguous: accepted state unknown")
        oid = kw.get("order_id")
        self.orders[oid] = {"status": "OPEN", "payload": dict(kw)}
        return {"order_id": oid, "status": "OPEN", "raw": {}}

    async def get_order(self, account_id, order_id):
        rec = self.orders.get(order_id)
        if rec is None:
            return {"order_id": order_id, "status": "UNKNOWN", "raw": {}}
        return {"order_id": order_id, "status": "OPEN", "raw": rec}


def test_same_intent_same_instant_duplicates_place_once():
    import asyncio
    import threading

    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    broker = _FakeBroker()
    intent, ctx = _base_intent(), _ctx()
    barrier = threading.Barrier(5)
    results = [None] * 5

    def attempt(i):
        barrier.wait(timeout=10)
        results[i] = asyncio.run(lc.submit(intent, ctx, broker, armed=True))

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert all(not t.is_alive() for t in threads)
    assert all(r["ok"] is True for r in results), results
    assert len({r["order_id"] for r in results}) == 1
    assert len(broker.calls) == 1  # one economic order, not five
    lc._reset_for_tests()


def test_ambiguous_retry_reuses_original_identity_without_replacement():
    import asyncio

    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    broker = _FakeBroker()
    broker.ambiguous_once = True
    intent, ctx = _base_intent(), _ctx()
    first = asyncio.run(lc.submit(intent, ctx, broker, armed=True))
    assert first["ok"] is False
    assert first["reason"] == "AMBIGUOUS_NEEDS_RECONCILE"
    original_id = first["order_id"]
    # Retry after ambiguity reconciles the ORIGINAL identity: no second
    # economic order is issued.
    retry = asyncio.run(lc.submit(intent, ctx, broker, armed=True))
    assert retry["ok"] is True
    assert retry["order_id"] == original_id
    assert retry.get("duplicate") is True
    assert len(broker.calls) == 1
    rec = asyncio.run(lc.reconcile(first["intent_id"], broker))
    assert rec["order_id"] == original_id
    lc._reset_for_tests()
