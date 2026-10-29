"""B24 context. Synthetic only."""
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import duckdb
import pytest

from services.chart_context import bind_context, resolve_context, resolve_focused_chart

CURSOR = 1792510200  # 2026-10-20T15:30:00+00:00
SCOPE = "SPY|expiries=2026-10-23|gex.v2|OI"
WALL = [{"wall_id": "w-a", "mid": 431.5, "low": 431.0, "high": 432.0}]


def _row(asof, received, snap="snap-a", ticker="SPY", query_key="SPY"):
    return {"ticker": ticker, "snapshot_id": snap, "query_key": query_key,
            "expiries": json.dumps(["2026-10-23"]), "formula_version": "gex.v2",
            "exposure_basis": "OI", "asof_ts": asof, "received_at": received,
            "walls_json": json.dumps(WALL),
            "strikes_json": json.dumps([{"strike": 431.5, "gex": 1}])}


def test_bind_and_race_guards():
    assert bind_context(focus=None, query="q", scope="s", cursor=1, generation=1)["status"] == "refused"
    d = bind_context(focus="SPY", query="q", scope="front", cursor=100, generation=7)
    assert d["status"] == "bound"
    assert resolve_context(d, {"generation": 6, "scope": "front"})["status"] == "refused"
    assert resolve_context(d, {"generation": 7, "scope": "other"})["status"] == "refused"
    assert resolve_context(d, {"generation": 7, "scope": "front", "pane_removed": True})["status"] == "refused"
    assert resolve_context(d, {"generation": 7, "scope": "front"})["status"] == "admitted"


def test_focused_chart_resolves_only_recorded_availability_from_the_store():
    """Server-owned resolution: receipt/known-at eligibility, never a candle clock."""
    rows = [
        _row("2026-10-20T15:25:00+00:00", "2026-10-20T15:27:00+00:00", "snap-b"),
        _row("2026-10-20T14:28:00+00:00", "2026-10-20T14:29:00+00:00", "snap-a"),
    ]
    out = resolve_focused_chart(rows, focus="SPY", scope=SCOPE, cursor=CURSOR)
    assert out["status"] == "available"
    assert out["snapshot_id"] == "snap-b"
    assert out["nodes"][0]["level"] == 431.5
    assert out["node_known_at"] == "2026-10-20T15:27:00+00:00"  # recorded receipt clock, not the cursor
    assert out["node_age_seconds"] == 300  # cursor minus the observed as-of
    assert out["gaps"] == []


def test_focused_chart_refuses_unrecorded_or_not_yet_available_selectors():
    rows = [_row("2026-10-20T14:28:00+00:00", "2026-10-20T14:29:00+00:00", "snap-b")]
    assert resolve_focused_chart(rows, focus="QQQ", scope=SCOPE, cursor=CURSOR)["status"] == "refused"
    assert resolve_focused_chart(rows, focus="SPY", scope="OTHER", cursor=CURSOR)["status"] == "refused"
    # The row is recorded but not yet receipt-known at an earlier cursor.
    earlier = resolve_focused_chart(rows, focus="SPY", scope=SCOPE, cursor=1792502400)
    assert earlier["status"] == "unavailable"
    assert "not yet recorded" in earlier["reason"]


def test_focused_chart_refuses_stale_observations_instead_of_freshening_them():
    rows = [_row("2026-10-20T12:00:00+00:00", "2026-10-20T12:00:01+00:00", "snap-old")]
    out = resolve_focused_chart(rows, focus="SPY", scope=SCOPE, cursor=CURSOR)
    assert out["status"] == "unavailable" and "age" in out["reason"]


def test_focused_chart_unknown_ticker_window_is_honestly_empty():
    assert resolve_focused_chart([], focus="SPY", scope=SCOPE, cursor=CURSOR)["status"] == "unavailable"


def _engine_with_rows(rows):
    conn = duckdb.connect(":memory:")
    from services.heatmap_history import ensure_tables

    ensure_tables(conn)
    for row in rows:
        conn.execute(
            "INSERT INTO heatmap_snapshots_v2 (ticker, query_key, expiries, formula_version, "
            "exposure_basis, snapshot_id, asof_ts, received_at, walls_json, strikes_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["ticker"], row["query_key"], row["expiries"], row["formula_version"],
             row["exposure_basis"], row["snapshot_id"], row["asof_ts"], row["received_at"],
             row["walls_json"], row["strikes_json"]),
        )

    def store_query(sql, args):
        result = conn.execute(sql, args)
        names = [column[0] for column in result.description]
        return [dict(zip(names, r, strict=True)) for r in result.fetchall()]

    return SimpleNamespace(conn=conn, query_strict=store_query), conn


async def test_chart_context_reads_resolve_from_the_recorded_store_only():
    """The read seam touches the local recorded store, never live/provider reads."""
    from routes.price_history import read_snapshots
    from services.agent.reads import ResearchReads

    engine, conn = _engine_with_rows([
        _row("2026-10-20T15:25:00+00:00", "2026-10-20T15:27:00+00:00", "snap-b"),
        _row("2026-10-20T14:50:00+00:00", "2026-10-20T14:52:00+00:00", "snap-a"),
    ])
    assertion = AssertionError("Focused research attempted live work")

    async def forbidden(*args, **kwargs):
        raise assertion

    reads = ResearchReads(forbidden, forbidden, forbidden,
                          read_recorded_chart=lambda ticker, first, last: read_snapshots(engine, ticker, first, last))
    now = datetime.fromtimestamp(CURSOR, UTC)
    snap = await reads.snapshot(
        "SPY", "all",
        screen={"displayMode": "price-history"},
        chart_context={"status": "bound", "focus": "SPY", "query": "focused-chart",
                       "scope": SCOPE, "cursor": CURSOR, "generation": "SPY:5:30:x:1"},
        now=now,
    )
    facts = {f["metric"]: f for f in snap["facts"]}
    wall = facts["Focused chart recorded wall level"]
    assert wall["value"] == 431.5
    assert wall["event_time"] == "2026-10-20T15:25:00+00:00"   # observation clock
    assert wall["received_at"] == "2026-10-20T15:27:00+00:00"  # recorded receipt clock
    assert wall["snapshot_id"] == "snap-b"
    known = facts["Focused chart node known-at"]
    assert known["value"] == "2026-10-20T15:27:00+00:00"
    assert snap["gaps"] == []
    # No live/provider read attempted: assertion helper never raised.
    conn.close()


async def test_chart_context_without_recorded_seam_keeps_the_honest_unavailable_path():
    from services.agent.reads import ResearchReads

    async def forbidden(*args, **kwargs):
        raise AssertionError("Focused research attempted live work")

    reads = ResearchReads(forbidden, forbidden, forbidden)
    now = datetime.fromtimestamp(CURSOR, UTC)
    snap = await reads.snapshot(
        "SPY", "all",
        screen={"displayMode": "price-history"},
        chart_context={"status": "bound", "focus": "SPY", "query": "focused-chart",
                       "scope": SCOPE, "cursor": CURSOR, "generation": "SPY:5:30:x:1"},
        now=now,
    )
    assert snap["facts"] == []
    assert any("unavailable" in gap for gap in snap["gaps"])
    assert snap["anchor_kind"] != "display"


async def test_chart_context_records_at_a_future_cursor_stay_unavailable():
    """Rows recorded after the ask's cursor are not yet knowable at it."""
    from routes.price_history import read_snapshots
    from services.agent.reads import ResearchReads

    engine, conn = _engine_with_rows([
        _row("2026-10-20T15:25:00+00:00", "2026-10-20T15:27:00+00:00", "snap-b"),
    ])
    async def forbidden(*args, **kwargs):
        raise AssertionError("Focused research attempted live work")

    reads = ResearchReads(forbidden, forbidden, forbidden,
                          read_recorded_chart=lambda ticker, first, last: read_snapshots(engine, ticker, first, last))
    snap = await reads.snapshot(
        "SPY", "all",
        screen={"displayMode": "price-history"},
        chart_context={"status": "bound", "focus": "SPY", "query": "focused-chart",
                       "scope": SCOPE, "cursor": 1792456200, "generation": "SPY:5:30:x:1"},
        now=datetime.fromtimestamp(1792456200, UTC),
    )
    assert snap["facts"] == []
    assert any("not yet recorded" in gap for gap in snap["gaps"])
    conn.close()
