"""Builds #2+#3: prefilter pure, budget take pure, fusion deterministic."""
from __future__ import annotations
import asyncio, duckdb
from services.universe_scan import (affordable_take, latest_leaderboard, prefilter_universe,
    record_leaderboard, scan_batch)
from services.heatmap_history import ensure_tables
from services.conviction_rank import rank_many, rank_one

def test_prefilter_orders_and_excludes():
    out = prefilter_universe(["SPY", "^VIX", "QQQ"], movers={"SPY": 5.0, "QQQ": 0.1},
        flow_alert_tickers={"QQQ"}, limit=10)
    names = [r["ticker"] for r in out["ordered"]]
    assert "^VIX" not in names
    assert out["excluded"][0]["reason"] == "NON_OPTIONABLE"
    assert names[0] == "SPY"  # 5.0 beats QQQ 0.1+2.0

def test_affordable_take_pure():
    assert affordable_take(60, 4, 20) == 15
    assert affordable_take(3, 4, 20) == 0
    assert affordable_take(0, 4, 20) == 0

def test_scan_batch_yields_to_budget(monkeypatch):
    import services.universe_scan as us
    import services.public_budget as pb
    async def fake_peek():
        return 0.0
    monkeypatch.setattr(pb.budget, "peek_available", fake_peek)
    async def boom(t, max_expiries=2):
        raise AssertionError("must not build when unaffordable")
    out = asyncio.run(us.scan_batch(["SPY", "QQQ"], build_heatmap_fn=boom, pace_sec=0))
    assert out["coverage"] == {"requested": 2, "scanned": 0, "skipped": 2}
    assert all(s["reason"] == "BUDGET_UNAFFORDABLE" for s in out["skipped"])

def test_scan_batch_builds_with_injected_fns(monkeypatch):
    import services.universe_scan as us
    import services.public_budget as pb
    async def rich():
        return 1000.0
    monkeypatch.setattr(pb.budget, "peek_available", rich)
    async def fake_build(t, max_expiries=2):
        return {"snapshotId": "snap-" + t, "spot": 500.0, "asof": "2026-01-01"}
    out = asyncio.run(us.scan_batch(["SPY"], build_heatmap_fn=fake_build,
        opportunity_fn=lambda t, h: {"ok": True}, conviction_fn=lambda t, h, o: {"ok": True}, pace_sec=0))
    assert out["coverage"]["scanned"] == 1
    assert out["rows"][0]["snapshot_id"] == "snap-SPY"

def test_rank_one_fuses_and_degrades():
    full = rank_one("SPY", flow={"conviction": 90}, opportunity={"opportunity_score": 8.0, "direction": "BULL", "trade_type": "debit_spread", "invalidation": "lose 500", "regime": "Trending"}, confluence={"total": 60.0, "direction": "bullish"}, ml={"prediction": "UP", "confidence": 0.8}, snapshot_id="s1", asof="a")
    assert full["tier"] == "HIGH" and full["direction"] == "BULL"
    assert full["invalidation"] == "lose 500" and full["evidence"]["flow_status"] == "ok"
    bare = rank_one("QQQ")
    assert bare["tier"] == "LOW" and bare["direction"] == "NEUTRAL"
    assert "No invalidation" in bare["invalidation"]
    assert bare["evidence"]["flow_status"] == "missing"

def test_rank_many_sorts_and_ranks():
    rows = [{"ticker": "AAA", "opportunity": {"opportunity_score": 1.0}, "snapshot_id": "s", "asof": "a"},
            {"ticker": "BBB", "opportunity": {"opportunity_score": 9.0, "direction": "BEAR", "trade_type": "x", "invalidation": "i"}, "snapshot_id": "s", "asof": "a"}]
    out = rank_many(rows)
    assert out[0]["ticker"] == "BBB" and out[0]["rank"] == 1 and out[1]["rank"] == 2

def test_leaderboard_round_trip():
    conn = duckdb.connect(":memory:"); ensure_tables(conn)
    assert latest_leaderboard(conn) == []
    record_leaderboard(conn, [{"ticker": "SPY", "rank": 1, "conviction": 88.0, "tier": "HIGH", "direction": "BULL", "trade_type": "debit_spread", "invalidation": "lose 500", "snapshot_id": "s1", "asof": "a", "evidence": {"k": 1}}])
    got = latest_leaderboard(conn)
    assert got[0]["ticker"] == "SPY" and got[0]["conviction"] == 88.0 and got[0]["evidence"] == {"k": 1}
    record_leaderboard(conn, [{"ticker": "SPY", "rank": 2, "conviction": 50.0, "tier": "WATCH", "direction": "NEUTRAL", "trade_type": "no_trade", "invalidation": "i", "snapshot_id": "s2", "asof": "a2", "evidence": {}}])
    got2 = latest_leaderboard(conn)
    assert len(got2) == 1 and got2[0]["rank"] == 2
