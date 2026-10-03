"""R17 hardening: supersede gates, durable-aware inventory/counts, session edge, producer restart OOO.

TDD for the take-over improvement pass. All Spark-owned, no live calls, no activation.
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
        self.orders = {}

    async def preflight_single_leg(self, **kw):
        return {"total": "318.20", "fees": "3.20", "buying_power_ok": True}

    async def place_order(self, **kw):
        self.calls.append(dict(kw))
        oid = kw.get("order_id")
        self.orders[oid] = {"status": "OPEN", "payload": dict(kw)}
        return {"order_id": oid, "status": "OPEN"}

    async def get_order(self, account_id, order_id):
        rec = self.orders.get(order_id)
        if rec is None:
            return {"order_id": order_id, "status": "UNKNOWN"}
        return {"order_id": order_id, "status": rec["status"]}

    async def cancel_order(self, account_id, order_id):
        rec = self.orders.get(order_id)
        if rec is None:
            return {"orderId": order_id, "status": "UNKNOWN"}
        rec["status"] = "CANCELED"
        return {"orderId": order_id, "status": "CANCELED"}


def test_supersede_prevalidates_approval_before_cancelling():
    """Supersede must not strand a cancelled order when the new intent would refuse."""
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    assert first["ok"] is True
    new_intent = _base_intent(observation_id="obs_sup_approval", limit_price="3.25")
    out = asyncio.run(lc.supersede(
        first["intent_id"], new_intent, _ctx(), broker, armed=True,
        require_approval=True, approval=None, approval_scope="single-entry"))
    assert out["ok"] is False and out["reason"] == "APPROVAL_INVALID"
    # Old order must NOT have been cancelled by a refused transition.
    assert broker.orders[first["order_id"]]["status"] == "OPEN"
    assert len(broker.calls) == 1


def test_supersede_prevalidates_fresh_preflight_before_cancelling():
    import asyncio

    import services.public_execution_lifecycle as lc

    broker = _FakeBroker()
    first = asyncio.run(lc.submit(_base_intent(), _ctx(), broker, armed=True))
    new_intent = _base_intent(observation_id="obs_sup_pf", limit_price="3.25")
    out = asyncio.run(lc.supersede(
        first["intent_id"], new_intent, _ctx(), broker, armed=True,
        require_fresh_preflight=True))
    assert out["ok"] is False and out["reason"] == "STALE_PREFLIGHT"
    assert broker.orders[first["order_id"]]["status"] == "OPEN"
    assert len(broker.calls) == 1


def test_inventory_includes_durable_drafts():
    import duckdb

    import services.public_execution_lifecycle as lc

    conn = duckdb.connect(":memory:")
    try:
        assert lc.register_store(conn) is True
        intent = _base_intent()
        lc.record_draft(intent)
        # Simulate restart: drop memory, keep durable.
        lc._DRAFTS.clear()
        body = lc.lifecycle_inventory()
        assert body["durable"] is True
        assert body["drafts"]["n_staged"] >= 1
        assert body["drafts"]["by_stage"].get("DRAFT", 0) >= 1
    finally:
        conn.close()


def test_max_positions_counts_durable_after_restart():
    import duckdb

    import services.public_execution_lifecycle as lc

    conn = duckdb.connect(":memory:")
    try:
        assert lc.register_store(conn) is True
        conn.execute(
            "INSERT INTO execution_intents_v1 "
            "(intent_id, intent_hash, ticker, owner, state, order_id, record_json, updated_at) "
            "VALUES ('in_restart1', 'h', 'SPY', 'FLOWW_BACKEND', 'OPEN', 'ord-1', "
            "'{\"order_id\": \"ord-1\", \"intent\": {\"ticker\": \"SPY\"}}', 'now')")
        # Memory empty (fresh process, no recover yet): durable OPEN must still block.
        lc._INTENTS.clear()
        ok, reason = lc.validate_intent(
            _base_intent(), _ctx(risk_limits={"max_positions": 1}))
        assert (ok, reason) == (False, "RISK_MAX_POSITIONS_EXCEEDED")
    finally:
        conn.close()


def test_sessions_flags_et_unparseable_divergence():
    from fastapi.testclient import TestClient

    from server import app
    from services.duckdb_engine import db as eng

    conn = eng.conn
    conn.execute(
        "CREATE TABLE IF NOT EXISTS heatmap_snapshots_v2 "
        "(ticker VARCHAR, snapshot_id VARCHAR, asof_ts VARCHAR)")
    conn.execute(
        "DELETE FROM heatmap_snapshots_v2 WHERE ticker = 'ZZU'")
    conn.execute(
        "INSERT INTO heatmap_snapshots_v2 (ticker, snapshot_id, asof_ts) VALUES "
        "('ZZU', 's-zzu-good', '2030-01-08T15:00:00+00:00'), "
        "('ZZU', 's-zzu-bad', '2030-01-08T99:99:99')")
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/solstice/price-paths/sessions", params={"ticker": "ZZU"})
    assert r.status_code == 200, r.text
    by_day = {d["date"]: d for d in r.json()["days"]}
    assert by_day["2030-01-08"]["overnight"] is True
    assert by_day["2030-01-08"]["ny_date"] is None


def test_producer_flags_out_of_order_after_restart():
    import duckdb

    from services.heatmap_history import ensure_tables, record_price_path
    from services.solstice_price_producer import PricePathProducer

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    assert record_price_path(conn, "SPY", 2000.0, 500.0, "t", "2026-10-03T00:00:00+00:00") is True
    # Fresh producer (empty _last_at) sees an earlier vendor timestamp.
    prod = PricePathProducer(
        conn, ["SPY"],
        fetch_one=lambda sym: {"price": 499.0, "event_time": 1000.0,
                               "fetched_at": "2026-10-03T00:01:00+00:00", "source": "t"},
        session_gate=lambda sym, now: (True, "open"))
    receipt = prod.tick(now_epoch=3000.0)
    assert receipt["written"] == 1
    assert receipt["out_of_order"] == 1
