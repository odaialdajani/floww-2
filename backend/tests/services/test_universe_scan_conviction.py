"""Builds #2+#3: prefilter pure, budget take pure, fusion deterministic."""
from __future__ import annotations

import asyncio

import duckdb

from services.conviction_rank import rank_many, rank_one
from services.heatmap_history import ensure_tables
from services.universe_scan import (
    affordable_take,
    latest_leaderboard,
    prefilter_universe,
    record_leaderboard,
    scan_batch,
)


def test_dte_is_forwarded_to_the_heatmap_builder():
    """`max_expiries` is a COUNT; `dte` is a separate tenor axis.

    `build_heatmap` accepts both, and they are independent (verified live:
    `dte=0` -> only today, `dte=1` -> today excluded). `scan_batch` forwarded
    only `max_expiries`, so a scan on an expiry day silently folded 0DTE
    contracts into every row's metrics with nothing in the request to say so.
    """
    seen = {}

    async def fake_build(ticker, *, max_expiries=4, dte=None, **kw):
        seen["max_expiries"] = max_expiries
        seen["dte"] = dte
        return {"snapshotId": "s1", "spot": 1.0, "asof": "a"}

    out = asyncio.run(scan_batch(["SPY"], build_heatmap_fn=fake_build,
                                 max_expiries=3, dte=0, pace_sec=0.0))
    assert seen["max_expiries"] == 3, seen
    assert seen["dte"] == 0, seen
    assert out["rows"][0]["ticker"] == "SPY", out


def test_dte_defaults_to_none_which_means_no_tenor_filter():
    """Omitting `dte` must stay a no-filter, not silently become 0DTE-only."""
    seen = {}

    async def fake_build(ticker, *, max_expiries=4, dte=None, **kw):
        seen["dte"] = dte
        return {"snapshotId": "s1", "spot": 1.0, "asof": "a"}

    asyncio.run(scan_batch(["SPY"], build_heatmap_fn=fake_build,
                           max_expiries=2, pace_sec=0.0))
    assert "dte" in seen and seen["dte"] is None, seen


def test_non_optionable_is_not_the_same_as_entitlement_unverified():
    """`^SPX`/`^VIX` have listed options; this path simply must prove it can serve them.

    Both symbols were hardcoded NON_OPTIONABLE, which asserts they have no
    options contract at all. They do: VIX and SPX options are listed on Cboe,
    and in this very deployment `/api/heatmap/^SPX` returns 80 live strike
    rows at spot 7743.41 via yfinance (HTTP 200, 124KB). Reporting
    "non-optionable" for an instrument the service can price is a factual
    error, and it silently drops the index most traders watch.

    Both remain excluded so live behavior is unchanged, but under a distinct
    reason so an operator can tell "no options exist" from "we cannot see
    them" and act on the difference.
    """
    out = prefilter_universe(["^SPX", "^VIX", "BTC", "ETH", "SPY"], limit=10)
    reasons = {r["ticker"]: r["reason"] for r in out["excluded"]}

    assert reasons["^SPX"] == "ENTITLEMENT_UNVERIFIED", reasons
    assert reasons["^VIX"] == "ENTITLEMENT_UNVERIFIED", reasons
    assert reasons["BTC"] == "NON_OPTIONABLE", reasons
    assert reasons["ETH"] == "NON_OPTIONABLE", reasons

    # Neither category is silently dropped from the universe: the caller can
    # see what was excluded and why.
    assert "SPY" in [r["ticker"] for r in out["ordered"]]


def test_entitlement_unverified_does_not_leak_into_non_optionable():
    """The two sets must stay disjoint so a reason never contradicts itself."""
    from services.universe_scan import ENTITLEMENT_UNVERIFIED, NON_OPTIONABLE

    assert not (NON_OPTIONABLE & ENTITLEMENT_UNVERIFIED)
    assert not (ENTITLEMENT_UNVERIFIED & NON_OPTIONABLE)


def test_prefilter_orders_and_excludes():
    # BTC replaced ^VIX as the excluded exemplar. ^VIX has listed options, so
    # excluding it on "non-optionable" grounds was a factual error; it now
    # reports ENTITLEMENT_UNVERIFIED (see
    # test_non_optionable_is_not_the_same_as_entitlement_unverified). The
    # behavior this test actually pins -- an excluded symbol stays excluded --
    # is unchanged.
    out = prefilter_universe(["SPY", "BTC", "QQQ"], movers={"SPY": 5.0, "QQQ": 0.1},
        flow_alert_tickers={"QQQ"}, limit=10)
    names = [r["ticker"] for r in out["ordered"]]
    assert "BTC" not in names
    assert out["excluded"][0]["reason"] == "NON_OPTIONABLE"
    assert names[0] == "SPY"  # 5.0 beats QQQ 0.1+2.0

def test_affordable_take_pure():
    assert affordable_take(60, 4, 20) == 15
    assert affordable_take(3, 4, 20) == 0
    assert affordable_take(0, 4, 20) == 0

def test_scan_batch_yields_to_budget(monkeypatch):
    import services.public_budget as pb
    import services.universe_scan as us
    async def fake_peek():
        return 0.0
    monkeypatch.setattr(pb.budget, "peek_available", fake_peek)
    async def boom(t, max_expiries=2):
        raise AssertionError("must not build when unaffordable")
    out = asyncio.run(us.scan_batch(["SPY", "QQQ"], build_heatmap_fn=boom, pace_sec=0))
    assert out["coverage"] == {"requested": 2, "scanned": 0, "skipped": 2}
    assert all(s["reason"] == "BUDGET_UNAFFORDABLE" for s in out["skipped"])

def test_scan_batch_builds_with_injected_fns(monkeypatch):
    import services.public_budget as pb
    import services.universe_scan as us
    async def rich():
        return 1000.0
    monkeypatch.setattr(pb.budget, "peek_available", rich)
    # Signature mirrors the real build_heatmap, which takes `dte` as a
    # separate axis alongside max_expiries.
    async def fake_build(t, max_expiries=2, dte=None, **kw):
        return {"snapshotId": "snap-" + t, "spot": 500.0, "asof": "2026-01-01"}
    out = asyncio.run(us.scan_batch(["SPY"], build_heatmap_fn=fake_build,
        opportunity_fn=lambda t, h: {"ok": True}, conviction_fn=lambda t, h, o: {"ok": True}, pace_sec=0))
    assert out["coverage"]["scanned"] == 1
    assert out["rows"][0]["snapshot_id"] == "snap-SPY"

def test_rank_one_fuses_and_degrades():
    full = rank_one("SPY", flow={"conviction": 90}, opportunity={"opportunity_score": 8.0, "direction": "BULL", "trade_type": "debit_spread", "invalidation": "lose 500", "regime": "Trending"}, confluence={"total": 60.0, "direction": "bullish"}, ml={"prediction": "UP", "confidence": 0.8}, snapshot_id="s1", asof="a")
    # Tier is now MED, not HIGH. Full evidence here scores 74.25:
    #   flow 0.9, opportunity 0.8, confluence 0.6, ml 0.45
    # The old normalizers reported 85.75 for this same row by crediting a
    # signed confluence of +60 as 0.8 and a BULLISH label as 0.95, while the
    # exact bearish mirror scored 60.25. Quality must not depend on which side
    # the evidence points, so both now score 74.25 and the thresholds are
    # unchanged -- the inputs stopped being flattering.
    assert full["conviction"] == 74.25, full["conviction"]
    assert full["tier"] == "MED" and full["direction"] == "BULL"
    assert full["invalidation"] == "lose 500" and full["evidence"]["flow_status"] == "ok"
    bare = rank_one("QQQ")
    assert bare["tier"] == "LOW" and bare["direction"] == "NEUTRAL"
    assert "No invalidation" in bare["invalidation"]
    assert bare["evidence"]["flow_status"] == "missing"

    # Equal evidence, opposite side, equal quality. This was 85.75 vs 60.25
    # before the normalizers were corrected.
    bear = rank_one("SPY", flow={"conviction": 90}, opportunity={"opportunity_score": 8.0, "direction": "BEAR", "trade_type": "debit_spread", "invalidation": "lose 500", "regime": "Trending"}, confluence={"total": -60.0, "direction": "bearish"}, ml={"prediction": "DOWN", "confidence": 0.8}, snapshot_id="s1", asof="a")
    assert full["conviction"] == bear["conviction"], (full["conviction"], bear["conviction"])
    assert full["direction"] == "BULL" and bear["direction"] == "BEAR"

def test_rank_many_sorts_and_ranks():
    rows = [{"ticker": "AAA", "opportunity": {"opportunity_score": 1.0}, "snapshot_id": "s", "asof": "a"},
            {"ticker": "BBB", "opportunity": {"opportunity_score": 9.0, "direction": "BEAR", "trade_type": "x", "invalidation": "i"}, "snapshot_id": "s", "asof": "a"}]
    out = rank_many(rows)
    assert out[0]["ticker"] == "BBB" and out[0]["rank"] == 1 and out[1]["rank"] == 2

def test_leaderboard_round_trip():
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    assert latest_leaderboard(conn) == []
    record_leaderboard(conn, [{"ticker": "SPY", "rank": 1, "conviction": 88.0, "tier": "HIGH", "direction": "BULL", "trade_type": "debit_spread", "invalidation": "lose 500", "snapshot_id": "s1", "asof": "a", "evidence": {"k": 1}}])
    got = latest_leaderboard(conn)
    assert got[0]["ticker"] == "SPY" and got[0]["conviction"] == 88.0 and got[0]["evidence"] == {"k": 1}
    record_leaderboard(conn, [{"ticker": "SPY", "rank": 2, "conviction": 50.0, "tier": "WATCH", "direction": "NEUTRAL", "trade_type": "no_trade", "invalidation": "i", "snapshot_id": "s2", "asof": "a2", "evidence": {}}])
    got2 = latest_leaderboard(conn)
    assert len(got2) == 1 and got2[0]["rank"] == 2
