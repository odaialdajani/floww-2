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
    from services.heatmap_history import ensure_tables

    ensure_tables(conn)
    conn.execute("DELETE FROM heatmap_snapshots_v2 WHERE ticker = 'ZZU'")
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


def test_range_map_projects_complete_window():
    from datetime import timedelta
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from server import app
    from services import public_api_adapter as ada

    today = datetime.now(ZoneInfo("America/New_York")).date()
    below = (today + timedelta(days=5)).isoformat()
    inside1 = (today + timedelta(days=20)).isoformat()
    inside2 = (today + timedelta(days=45)).isoformat()
    above = (today + timedelta(days=90)).isoformat()

    async def fake_chain(ticker, max_expiries=12):
        return {"ticker": ticker, "spot": 500.0, "fetched_at": "2026-10-03T00:00:00+00:00",
                "stale": False, "expiries": [below, inside1, inside2, above]}

    with patch.object(ada, "fetch_chain_from_public_api", side_effect=fake_chain):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/solstice/price-paths/expiries",
                       params={"ticker": "SPY", "min_dte": 14, "max_dte": 60})
    assert r.status_code == 200, r.text
    body = r.json()
    rm = body["range_map"]
    assert rm["admitted_expiries"] == [inside1, inside2]
    assert rm["min_admitted_dte"] == 20 and rm["max_admitted_dte"] == 45
    assert rm["complete"] is True and rm["reason"] is None


def test_range_map_flags_capped_window():
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from server import app
    from services import public_api_adapter as ada

    async def fake_chain(ticker, max_expiries=2):
        # Capped listing with no edges observed: completeness unknown.
        return {"ticker": ticker, "spot": 500.0, "fetched_at": "2026-10-03T00:00:00+00:00",
                "stale": False, "expiries": ["2030-01-15", "2030-02-15"]}

    with patch.object(ada, "fetch_chain_from_public_api", side_effect=fake_chain):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/solstice/price-paths/expiries",
                       params={"ticker": "SPY", "min_dte": 14, "max_dte": 60,
                               "expirations": 2})
    assert r.status_code == 200, r.text
    rm = r.json()["range_map"]
    assert rm["complete"] is False
    assert rm["reason"] == "LISTING_CAPPED_WINDOW_MAY_EXTEND"


def test_account_policy_enforced_and_reported():
    import services.public_execution_lifecycle as lc

    assert lc.get_account_policy() is None
    row = lc.set_account_policy({"max_quantity": 1, "max_positions": 10}, "op-1")
    assert row["version"] == "account-policy.v1"
    ok, reason = lc.validate_intent(_base_intent(quantity=5), _ctx())
    assert (ok, reason) == (False, "RISK_QUANTITY_EXCEEDED")
    body = lc.lifecycle_inventory()
    assert body["policy"]["account_wide_limits"] != "UNSET"
    assert body["policy"]["account_wide_limits"]["version"] == "account-policy.v1"
    lc.clear_account_policy()
    assert lc.get_account_policy() is None
    assert lc.validate_intent(_base_intent(quantity=5), _ctx()) == (True, "ok")


def test_stored_approval_revocation_invalidates():
    from datetime import timedelta

    import services.public_execution_lifecycle as lc

    intent = _base_intent()
    digest = lc.intent_hash(intent)
    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    appr = lc.create_approval(digest, intent["account_id"], "single-entry",
                              now + timedelta(hours=1), "op-1", now=now)
    stored = lc.store_approval(appr, "op-1")
    assert lc.verify_approval(intent, stored, scope="single-entry", now=now) is True
    assert lc.revoke_approval(stored["approval_id"], "op-1")["ok"] is True
    assert lc.verify_approval(intent, stored, scope="single-entry", now=now) is False
    body = lc.lifecycle_inventory()
    assert body["approvals"]["n_stored"] >= 1
    assert body["approvals"]["n_revoked"] >= 1


def test_submit_refuses_new_entry_until_recovery():
    import asyncio

    import duckdb

    import services.public_execution_lifecycle as lc

    conn = duckdb.connect(":memory:")
    try:
        assert lc.register_store(conn) is True
        conn.execute(
            "INSERT INTO execution_intents_v1 "
            "(intent_id, intent_hash, ticker, owner, state, order_id, record_json, updated_at) "
            "VALUES ('in_old1', 'h', 'SPY', 'FLOWW_BACKEND', 'OPEN', 'ord-1', "
            "'{\"order_id\": \"ord-1\", \"intent\": {\"ticker\": \"SPY\"}}', 'now')")
        lc._INTENTS.clear()  # fresh process, no recover_open yet
        out = asyncio.run(lc.submit(_base_intent(), _ctx(), _FakeBroker(), armed=True))
        assert out["ok"] is False and out["reason"] == "RECOVERY_REQUIRED"
        recovered = lc.recover_open()
        assert recovered == ["in_old1"]
    finally:
        conn.close()


def test_native_protection_stays_conservative():
    import services.public_execution_lifecycle as lc

    ans = lc.native_protection_support("OPTION", "SINGLE_LEG_LIMIT")
    assert ans["supported"] is False
    assert ans["reason"] == "unverified-native-support"
    body = lc.lifecycle_inventory()
    assert body["protection"]["native_support"]["OPTION_SINGLE_LEG_LIMIT"]["supported"] is False


def test_store_approval_never_resurrects_revoked():
    from datetime import timedelta

    import services.public_execution_lifecycle as lc

    intent = _base_intent()
    digest = lc.intent_hash(intent)
    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    appr = lc.create_approval(digest, intent["account_id"], "single-entry",
                              now + timedelta(hours=1), "op-1", now=now)
    stored = lc.store_approval(appr, "op-1")
    assert lc.revoke_approval(stored["approval_id"], "op-1")["ok"] is True
    again = lc.store_approval(appr, "op-1")
    assert again["revoked"] is True
    assert lc.verify_approval(intent, again, scope="single-entry", now=now) is False


def test_stored_approval_sees_cross_process_revocation():
    from datetime import timedelta

    import duckdb

    import services.public_execution_lifecycle as lc

    conn = duckdb.connect(":memory:")
    try:
        assert lc.register_store(conn) is True
        intent = _base_intent()
        digest = lc.intent_hash(intent)
        now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
        appr = lc.create_approval(digest, intent["account_id"], "single-entry",
                                  now + timedelta(hours=1), "op-1", now=now)
        stored = lc.store_approval(appr, "op-1")
        # Another process revokes directly in the durable table; this process
        # still holds an unrevoked memory copy.
        conn.execute("UPDATE approvals_v1 SET revoked = TRUE WHERE approval_id = ?",
                     [stored["approval_id"]])
        seen = lc.stored_approval(stored["approval_id"])
        assert seen is not None and seen["revoked"] is True
        assert lc.verify_approval(intent, stored, scope="single-entry", now=now) is False
    finally:
        conn.close()


def test_account_policy_newest_durable_write_governs():
    import duckdb

    import services.public_execution_lifecycle as lc

    conn = duckdb.connect(":memory:")
    try:
        assert lc.register_store(conn) is True
        lc.set_account_policy({"max_quantity": 100}, "op-1")
        # A newer, tighter write lands durably from another process.
        conn.execute(
            "UPDATE account_policy_v1 SET policy_json = ?, updated_at = ? WHERE id = 'active'",
            ['{"max_quantity": 1}', "2099-01-01T00:00:00+00:00"])
        got = lc.get_account_policy()
        assert got is not None and got["policy"].get("max_quantity") == 1
        ok, reason = lc.validate_intent(_base_intent(quantity=5), _ctx())
        assert (ok, reason) == (False, "RISK_QUANTITY_EXCEEDED")
    finally:
        conn.close()
