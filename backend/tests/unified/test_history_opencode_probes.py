"""OpenCode probe slice for U08 (claim in docs/unified/U08/OPENCODE-CLAIM.md).

History node honesty on synthetic bars/snapshots. No source edits, no stores,
no provider calls.
"""
from services.price_node_history import (
    build_history,
    epoch,
    recorded_nodes,
    scope_id,
)


def test_epoch_rejects_ambiguity_and_garbage():
    from datetime import UTC, datetime
    assert epoch(1700000000) == 1700000000.0
    assert epoch(1700000000000) == 1700000000.0
    assert epoch("2026-10-07T20:00:00+00:00") == datetime(2026, 10, 7, 20, 0, tzinfo=UTC).timestamp()
    assert epoch("2026-10-07T20:00:00") is None  # naive local time
    assert epoch("not-a-clock") is None
    assert epoch(True) is None
    assert epoch(float("nan")) is None
    assert epoch(None) is None


def test_recorded_nodes_skip_malformed_and_nonpositive():
    assert recorded_nodes({"walls_json": "not-json["}) == []
    assert recorded_nodes({"walls_json": [{"mid": 0}, {"mid": -5}, {"strike": 780.0}]})
    nodes = recorded_nodes({"walls_json": [{"mid": 0}, {"mid": -5}, {"strike": 780.0}]})
    assert nodes == [{"id": "780.0", "level": 780.0, "low": 780.0, "high": 780.0}]
    assert recorded_nodes({"walls_json": [{"nope": 1}, "str", None]}) == []


def _bar(t, o=770.0, h=775.0, low=768.0, c=774.0):
    return {"t": t, "o": o, "h": h, "l": low, "c": c}


def test_future_snapshot_never_leaks_into_earlier_bars():
    bars = [_bar(1000), _bar(1060), _bar(1120)]
    snap = {"ticker": "SPY", "asof_ts": 5000, "received_at": 5001,
            "snapshot_id": "future", "walls_json": [{"mid": 770.0}],
            "query_key": "q", "formula_version": "v", "exposure_basis": "b"}
    out = build_history("SPY", bars, [snap])
    assert out["candles"] == 3
    assert out["candles_with_recorded_nodes"] == 0
    assert all(f["snapshot_id"] is None for f in out["frames"])


def test_stale_snapshot_yields_gaps_not_old_nodes():
    bars = [_bar(1000), _bar(2000)]
    snap = {"ticker": "SPY", "asof_ts": 100, "received_at": 101,
            "snapshot_id": "old", "walls_json": [{"mid": 770.0}],
            "query_key": "q", "formula_version": "v", "exposure_basis": "b"}
    out = build_history("SPY", bars, [snap])
    # 900s age bound is inclusive: the first frame (age exactly 900) is
    # usable, the second (age 1900) is a gap — old nodes never stretch.
    assert [bool(f["nodes"]) for f in out["frames"]] == [True, False]
    assert out["frames"][1]["snapshot_id"] is None


def test_scope_changes_never_mix_and_ticker_must_match():
    bars = [_bar(1000), _bar(1060)]
    a = {"ticker": "SPY", "asof_ts": 900, "received_at": 901, "snapshot_id": "a",
         "walls_json": [{"mid": 770.0}], "query_key": "qa",
         "formula_version": "v1", "exposure_basis": "b"}
    b = dict(a, snapshot_id="b", query_key="qb", formula_version="v2",
             asof_ts=950, received_at=951, walls_json=[{"mid": 771.0}])
    foreign = dict(a, snapshot_id="f", ticker="QQQ", walls_json=[{"mid": 999.0}])
    out = build_history("SPY", bars, [a, b, foreign])
    assert out["scopes"] == sorted([scope_id(a), scope_id(b)])
    assert out["query_key"] == scope_id(b)  # latest scope is the default
    assert all(f["snapshot_id"] in (None, "b") for f in out["frames"])
    assert scope_id({**a, "expiries": ["2026-10-09"]}) != scope_id(a)
