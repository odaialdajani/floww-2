"""S12 lifecycle truth and exit availability: behavior audit.

ACK/open/partial/fill/reject/cancel/unknown stay distinct through
reconcile; authenticated cancel remains available while disarmed and
during the entry pause; terminal cancel makes zero broker calls.
"""
import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime


def _intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_s12", "replay_id": None, "ticker": "SPY",
        "contract": {"osi": "SPY260904C00760000", "expiry": "2026-09-04",
                      "option_type": "CALL", "strike_exact": "760.00",
                      "multiplier": "100",
                      "multiplier_provenance": "vendor-instrument"},
        "side": "BUY", "open_close": "OPEN", "quantity": 1,
        "limit_price": "3.15", "tick": "0.05", "account_id": "ACCT-1",
        "venue": "PUBLIC", "cash_margin_choice": "CASH",
        "budget": {"preflight_total": "318.20", "fees": "3.20",
                   "asof": "2026-10-02T15:00:00+00:00"},
        "session_policy": {"session": "regular", "freshness_s": 30,
                           "confirmation": "quoted"},
        "risk_policy_version": "research_barriers.v1",
        "execution_owner": "FLOWW_BACKEND", "entry_pause_ack": False,
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
        self.cancels = []
        self.orders = {}

    async def place_order(self, **kw):
        self.calls.append(dict(kw))
        oid = kw.get("order_id")
        self.orders[oid] = {"status": "OPEN"}
        return {"order_id": oid, "status": "OPEN", "raw": {}}

    async def get_order(self, account_id, order_id):
        rec = self.orders.get(order_id)
        if rec is None:
            return {"order_id": order_id, "status": "UNKNOWN", "raw": {}}
        return {"order_id": order_id, "status": rec["status"], "raw": rec}

    async def cancel_order(self, account_id, order_id):
        self.cancels.append(order_id)
        rec = self.orders.get(order_id)
        if rec is None:
            return {"orderId": order_id, "status": "UNKNOWN"}
        rec["status"] = "CANCELED"
        return {"orderId": order_id, "status": "CANCELED"}


def test_reconcile_keeps_states_distinct():
    import asyncio

    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_intent(), _ctx(), broker, armed=True))
    seen = set()
    for broker_status in ("OPEN", "PARTIAL", "FILLED", "REJECTED",
                          "CANCELED"):
        broker.orders[first["order_id"]]["status"] = broker_status
        rec = asyncio.run(lc.reconcile(first["intent_id"], broker))
        assert rec["status"] == broker_status, (broker_status, rec)
        seen.add(rec["status"])
    assert seen == {"OPEN", "PARTIAL", "FILLED", "REJECTED", "CANCELED"}
    # Unknown broker identity stays unknown, never invented.
    rec = asyncio.run(lc.reconcile("in_deadbeefcafe", broker))
    assert rec["status"] == "UNKNOWN"
    lc._reset_for_tests()


def test_cancel_available_while_disarmed_and_terminal_is_zero_call():
    import asyncio
    import inspect

    import services.public_execution_lifecycle as lc

    # Exits take no arming requirement by design: cancel() has no armed
    # parameter and performs no entry-pause check.
    assert "armed" not in inspect.signature(lc.cancel).parameters
    assert lc.cancel_allowed_during_pause() is True
    lc._reset_for_tests()
    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_intent(), _ctx(), broker, armed=True))
    out = asyncio.run(lc.cancel(first["intent_id"], broker))
    assert out["cancelled"] is True, out
    assert broker.orders[first["order_id"]]["status"] == "CANCELED"
    # Terminal cancel makes zero broker calls.
    calls_before = len(broker.calls) + len(broker.cancels)
    out = asyncio.run(lc.cancel(first["intent_id"], broker))
    assert out["cancelled"] is False, out
    assert out["reason"] == "already-terminal", out
    assert len(broker.calls) + len(broker.cancels) == calls_before
    lc._reset_for_tests()
