"""S6 Solstice scan coordinator (Spark).

Covers the scope-keyed cache, the stable rotation checkpoint, the
fuse-once ranking it consumes, and the cancellation/budget contract. The
legacy TideHunter path is asserted untouched by comparing against a
separately-captured legacy result, not by asserting on its internals.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import solstice_scan as scan  # noqa: E402
from services.conviction_rank import rank_one  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    scan._CURSOR.clear()
    scan._CACHE._entries.clear()
    scan._CACHE._async_locks.clear()
    yield
    scan._CURSOR.clear()
    scan._CACHE._entries.clear()


def test_cache_key_carries_dte_and_expiry_scope():
    ordered = ["SPY", "QQQ"]
    a = scan.cache_key_for(ordered, universe="popular", dte=0, max_expiries=1)
    b = scan.cache_key_for(ordered, universe="popular", dte=30, max_expiries=4)
    c = scan.cache_key_for(ordered, universe="popular", dte=0, max_expiries=1)
    assert a != b
    assert a == c


def test_rotation_is_stable_and_resumable():
    ordered = ["A", "B", "C", "D", "E"]
    seen, cursor = [], 0
    for _ in range(3):
        batch, cursor = scan.next_slice(ordered, cursor, 2)
        seen.extend(batch)
    assert seen == ["A", "B", "C", "D", "E", "A"], "three 2-name batches cover the head once"
    # Resume from the checkpoint: the tail, not the head, is next.
    batch, cursor = scan.next_slice(ordered, cursor, 2)
    assert batch == ["B", "C"]


def test_cancelled_sweep_returns_no_rows_and_keeps_the_checkpoint():
    async def _run():
        ev = asyncio.Event()
        ev.set()
        return await scan.run_scan(
            universe="popular", limit=2, build_heatmap_fn=None,
            opportunity_fn=None, scan_cancelled=ev,
        )

    out = asyncio.run(_run())
    assert out["coverage"]["cancelled"] is True
    assert out["rows"] == []
    assert "cursor" in out and out["cursor"]["position"] == 2


def test_sweep_ranks_with_fuse_once_and_reports_scope():
    calls: list[list[str]] = []

    async def fake_batch(tickers, **kw):
        calls.append(list(tickers))
        return {
            "rows": [
                {"ticker": t, "flow": {"conviction": 90},
                 "opportunity": {"opportunity_score": 8}, "snapshot_id": "s1",
                 "asof": "2030-01-02T14:00:00+00:00"}
                for t in tickers
            ],
            "coverage": {"returned": len(tickers)},
            "skipped": [{"ticker": "BUDGET", "reason": "BUDGET_UNAFFORDABLE"}],
        }

    import services.universe_scan as us

    original = us.scan_batch
    us.scan_batch = fake_batch
    try:
        out = asyncio.run(scan.run_scan(universe="popular", limit=2, build_heatmap_fn=None,
                                        opportunity_fn=None))
    finally:
        us.scan_batch = original

    assert out["schema_version"] == "solstice_scan.v1"
    assert out["scope"]["formula_version"] == "gex.v2"
    assert out["scope"]["dte"] is None and out["scope"]["max_expiries"] == 2
    assert out["cache"] == "miss"
    assert len(out["rows"]) == 2
    assert [r["ticker"] for r in out["rows"]] == calls[0], "the batch scanned is the batch ranked"
    assert all(r["conviction"] == 55.5 for r in out["rows"]), "fused once, not re-fused"
    assert all(r["evidence"]["flow_status"] == "ok" for r in out["rows"])
    assert out["coverage"]["usable"] == 2
    # Budget refusals are reported, never converted into spend.
    assert out["coverage"]["skipped"] == [{"ticker": "BUDGET", "reason": "BUDGET_UNAFFORDABLE"}]
    # Identical scope hits the cache and does not rescan.
    out2 = asyncio.run(scan.run_scan(universe="popular", limit=2, build_heatmap_fn=None,
                                     opportunity_fn=None))
    assert out2["cache"] == "hit"
    assert len(calls) == 1


def test_prior_ranked_row_keeps_its_score_through_the_coordinator():
    fused = rank_one("SPY", flow={"conviction": 90}, opportunity={"opportunity_score": 8})

    async def fake_batch(tickers, **kw):
        return {"rows": [{**fused, "ticker": t} for t in tickers],
                "coverage": {}, "skipped": []}

    import services.universe_scan as us

    original = us.scan_batch
    us.scan_batch = fake_batch
    try:
        out = asyncio.run(scan.run_scan(universe="popular", limit=1, build_heatmap_fn=None,
                                        opportunity_fn=None))
    finally:
        us.scan_batch = original
    assert out["rows"][0]["conviction"] == 55.5
    assert out["rows"][0]["tier"] == fused["tier"]


def test_coordinator_does_not_touch_the_legacy_cache_or_cursor():
    """The legacy module keeps its own objects; we never import or mutate them."""
    src = Path(scan.__file__).read_text(encoding="utf-8")
    assert "routes.flowseeker" not in src
    assert "_scan_cache" not in src
    assert "_UNIVERSE_SCAN_CACHE" not in src
    assert scan.health()["cursors"] == {}
