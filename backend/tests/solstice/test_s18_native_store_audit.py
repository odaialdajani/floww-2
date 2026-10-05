"""S10/S11 native census + authoritative store: behavior audit.

Malformed native rows refuse (never read as empty); a mismatched store
handle refuses STORE_MISMATCH; storeless admission refuses. Fake only.
"""
import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime, timedelta


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


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
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_ns", "replay_id": None, "ticker": "SPY",
        "contract": {"osi": "SPY261218C00760000", "expiry": "2026-12-18",
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
    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    appr = lc.create_approval(
        lc.intent_hash(intent), intent["account_id"], "single-entry",
        now + timedelta(hours=1), operator, now=now)
    assert adm.store_approval_required(conn, appr, operator)["ok"] is True
    ctx = {
        "quotes": {"bid": "3.10", "ask": "3.20",
                   "bid_ts": "2026-10-02T14:59:40+00:00",
                   "ask_ts": "2026-10-02T14:59:41+00:00"},
        "now": now,
        "account": {"options_level": "2", "entitlement": "verified",
                    "margin": True},
        "snapshot_id": "snap_1",
        "supported_expiries": ["2026-12-18"],
        "supported_products": ["OPTION", "EQUITY"],
    }
    return intent, appr, ctx


def _facts():
    return {"buying_power": "10000", "positions": [], "open_orders": [],
            "fills": [], "account_id": "ACCT-1", "source": "fake-broker",
            "asof": "2026-10-02T14:59:00+00:00"}


class _ExplodingBroker:
    def __getattr__(self, name):
        raise AssertionError(f"admission must never touch broker.{name}")


def test_malformed_native_rows_refuse():
    import asyncio

    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    conn = _memdb()
    try:
        intent, appr, ctx = _full_stack(conn)

        class _GoodPreflight:
            async def preflight_single_leg(self, **kw):
                return {"total": "318.20", "fees": "3.20",
                        "buying_power_ok": True}

        assert asyncio.run(
            lc.preflight(intent, ctx, _GoodPreflight()))["ok"] is True
        kw = {"approval": appr, "operator_id": "op-1",
              "risk_facts": _facts()}
        # Row without status is unverifiable: never read as empty.
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, _ExplodingBroker(),
            remote_native={"workflows": [{"strategy": "X"}]}, **kw)
        assert out["reason"] == "NATIVE_CENSUS_UNAVAILABLE", out
        # Non-dict row likewise refuses.
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, _ExplodingBroker(),
            remote_native={"workflows": ["OPEN"]}, **kw)
        assert out["reason"] == "NATIVE_CENSUS_UNAVAILABLE", out
        # Missing census refuses.
        out = adm.admit_commissioned_entry(
            conn, intent, ctx, _ExplodingBroker(),
            remote_native=None, **kw)
        assert out["reason"] == "NATIVE_CENSUS_UNAVAILABLE", out
    finally:
        conn.close()


def test_mismatched_and_missing_store_refuse():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    first, second = _memdb(), _memdb()
    try:
        lc.register_store(first)
        out = adm.admit_production_entry(
            second, {"account_id": "ACCT-1"}, {}, _ExplodingBroker())
        assert out["reason"] == "STORE_MISMATCH", out
        lc._reset_for_tests()
        out = adm.admit_production_entry(
            None, {"account_id": "ACCT-1"}, {}, _ExplodingBroker())
        assert out["reason"] == "STORE_UNAVAILABLE", out
    finally:
        first.close()
        second.close()
        lc._reset_for_tests()
