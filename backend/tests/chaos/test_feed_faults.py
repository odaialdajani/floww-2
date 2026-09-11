"""
backend/tests/chaos/test_feed_faults.py — Agent D (D4 chaos matrix,
feed level). Fault-injection against B-owned seams (read-only):
PublicBudget 429/cooldown math, chain-fetch degrade paths, partial
payloads, crossed quotes, broken-engines. Every fault must degrade
(stale/None/empty) — never raise, never silent-empty.

Named fault hooks shared with B (MASTER_PLAN §13): the mock points are
`fetch_chain_from_public_api`'s `_get_broker` seam and
`pub_budget.acquire`/`record_429`. The `assert_serves_stale` helper is
offered for shared use (graduates to a common module at Sync-1).
"""
from __future__ import annotations

import sys
import time
from unittest.mock import patch


def _ensure_imports():
    if "services.public_budget" not in sys.modules:
        sys.path.insert(0, "/Users/nav/Documents/GitHub/floww/backend")


_ensure_imports()

TICKER = "ZZD4"  # never a real universe ticker; cache-identity safe


def assert_serves_stale(payload, ticker=TICKER):
    """Shared stale-with-age assertion (D4/B6): stale, never silent-empty."""
    assert payload is not None, f"{ticker}: silent empty (None with no stale flag)"
    assert payload.get("stale") is True, f"{ticker}: failure served as fresh"
    assert payload.get("contracts") is not None, f"{ticker}: contracts missing"
    return payload


def _warm_payload():
    return {"ticker": TICKER, "spot": 100.0, "expiries": ["2026-12-18"],
            "contracts": [{"k": 1}], "data_source": "public_api", "stale": False}


def test_budget_429_storm_blocks_then_recovers():
    from services.public_budget import BudgetExhausted, PublicBudget

    b = PublicBudget(capacity=10, refill_per_sec=1.0)
    b.record_429("public", now=1000.0, retry_after=30)
    b.record_429("public", now=1000.0, retry_after=30)
    assert b.total_429 == 2
    try:
        import asyncio
        asyncio.get_event_loop().run_until_complete(b.acquire("public", now=1001.0))
        raised = False
    except BudgetExhausted as e:
        raised = True
        assert e.retry_after > 0
    assert raised, "429 storm must block acquire with a retry hint"
    import asyncio
    asyncio.get_event_loop().run_until_complete(b.acquire("public", now=2000.0))
    b.record_ok("public")
    assert b.status(now=2001.0)["cooldowns"].get("public", 0) == 0


def test_clock_skew_keeps_budget_sane():
    from services.public_budget import PublicBudget

    b = PublicBudget(capacity=5, refill_per_sec=1.0)
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(b.acquire("public", now=1000.0))
    # clock jumps +1h: refill must cap at capacity, never overflow
    st = b.status(now=4600.0)
    assert st["available"] <= st["capacity"]
    # clock jumps backwards: no crash, no negative tokens
    st = b.status(now=500.0)
    assert st["available"] >= 0


def _run(coro):
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


def test_chain_fetch_cold_failure_returns_none_not_raise():
    from services import public_api_adapter as pa

    async def no_broker():
        return None

    pa._CHAIN_CACHE.pop((TICKER, 4), None)
    with patch.object(pa, "_get_broker", no_broker):
        assert _run(pa.fetch_chain_from_public_api(TICKER)) is None


def test_chain_fetch_warm_failure_serves_stale():
    from services import public_api_adapter as pa

    class DeadBroker:
        def get_trading_account(self):
            return None  # no account -> _fetch_chain_live returns None, no raise

    broker = DeadBroker()

    async def dead():
        return broker

    old = pa._CHAIN_CACHE.pop((TICKER, 4), None)
    pa._CHAIN_CACHE[(TICKER, 4)] = (time.monotonic() - 120.0, broker, _warm_payload())
    try:
        with patch.object(pa, "_get_broker", dead):
            got = _run(pa.fetch_chain_from_public_api(TICKER))
        assert_serves_stale(got)
    finally:
        if old is None:
            pa._CHAIN_CACHE.pop((TICKER, 4), None)
        else:
            pa._CHAIN_CACHE[(TICKER, 4)] = old


def test_partial_chain_quarantines_bad_contracts():
    from services.contract_validators import Quarantine, validate_batch, validate_chain_row

    good = ["SPY", "O:SPY261218C00760000", "call", 760.0, "2026-12-18",
            200000, 2000, 0.5, 0.3, 758.0]
    rows = [good, ["SPY", "BAD", "call", -1.0, "nope", -5, -1, 0.5, 0.3, 758.0], good]
    q = Quarantine()
    valid, n = validate_batch("public_chain", rows, validate_chain_row, q)
    assert len(valid) == 2 and n == 1
    assert q.counts()["public_chain"] == 1


def test_crossed_quote_flagged_not_fired():
    from services.contract_validators import validate_quote

    ok, reason = validate_quote({"bid": 1.5, "ask": 1.4, "last": 1.45})
    assert ok is False and "crossed" in (reason or "")


def test_broken_engine_reads_fail_open():
    from services.flow_alerts import get_move_path, horizon_moves

    class Broken:
        def query(self, *a, **k):
            raise RuntimeError("duckdb locked")

    assert get_move_path(Broken(), "2026-09-05", "k") == []
    assert horizon_moves(Broken(), "2026-09-05", "k") == {1: None, 5: None, 20: None}
