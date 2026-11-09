"""B15 replay algebra. Synthetic only."""
from datetime import UTC, datetime, timedelta


def test_known_at_and_age_and_partial():
    from services.chart_replay import age_ok, partial_bar, visible_snapshot
    snaps = [{"id": "a", "known_at": 100}, {"id": "b", "known_at": 90}]
    assert visible_snapshot(snaps, 95)["id"] == "b"
    assert visible_snapshot(snaps, 50) is None
    assert age_ok(0, 900) is True
    assert age_ok(0, 901) is False
    ev = [{"event_time": 10, "available_at": 10, "open": 1, "close": 2},
          {"event_time": 20, "available_at": 30, "open": 2, "close": 3}]
    out = partial_bar(ev, 25)
    assert out["close"] == 2 and out["complete"] is False
    assert partial_bar(ev, 5) == {
        "open": None, "close": None, "complete": False, "count": 0,
        "pending": 2, "lastAvailableAt": None, "bucketStart": 0,
        "bucketEnd": 900,
    }


def test_partial_bar_uses_only_cursor_owning_bucket_and_keeps_pending():
    from services.chart_replay import partial_bar

    events = [
        {"event_time": 0, "available_at": 900, "open": 100, "close": 110},
        {"event_time": 900, "available_at": 1800, "open": 200, "close": 210},
        {"event_time": 1500, "available_at": 1800, "open": 205, "close": 215},
        {"event_time": 1800, "available_at": 1800, "open": 300, "close": 310},
    ]
    assert partial_bar(events, 1500) == {
        "open": None, "close": None, "complete": False, "count": 0,
        "pending": 2, "lastAvailableAt": None, "bucketStart": 900,
        "bucketEnd": 1800,
    }
    assert partial_bar(events, 500) == {
        "open": None, "close": None, "complete": False, "count": 0,
        "pending": 1, "lastAvailableAt": None, "bucketStart": 0,
        "bucketEnd": 900,
    }
    assert partial_bar(events, 1500, bar_seconds=300) == {
        "open": None, "close": None, "complete": False, "count": 0,
        "pending": 1, "lastAvailableAt": None, "bucketStart": 1500,
        "bucketEnd": 1800,
    }
    assert partial_bar(events, 4000) is None


def test_partial_bar_refuses_unknown_or_malformed_event_and_availability_times():
    from services.chart_replay import partial_bar

    events = [
        {"event_time": 10, "available_at": None, "open": 1, "close": 2},
        {"event_time": 15, "open": 3, "close": 4},
        {"event_time": "bad", "available_at": 20, "open": 5, "close": 6},
        {"event_time": float("nan"), "available_at": 20, "open": 7, "close": 8},
        {"event_time": 30, "available_at": "bad", "open": 9, "close": 10},
    ]
    assert partial_bar(events, 50) == {
        "open": None, "close": None, "complete": False, "count": 0,
        "pending": 3, "lastAvailableAt": None, "bucketStart": 0,
        "bucketEnd": 900,
    }


def test_partial_bar_rejects_invalid_cursor_or_duration():
    from services.chart_replay import partial_bar

    events = [{"event_time": 10, "available_at": 10, "open": 1, "close": 2}]
    for cursor in (None, "bad", float("nan"), float("inf")):
        assert partial_bar(events, cursor) is None
    for duration in (None, 0, -1, "bad", float("nan"), float("inf")):
        assert partial_bar(events, 10, duration) is None


def test_partial_bar_preserves_exact_default_and_custom_boundaries():
    from services.chart_replay import partial_bar

    events = [
        {"event_time": 899.999, "available_at": 900, "open": 1, "close": 2},
        {"event_time": 900, "available_at": 900, "open": 3, "close": 4},
        {"event_time": 1799.999, "available_at": 1800, "open": 5, "close": 6},
        {"event_time": 1800, "available_at": 1800, "open": 7, "close": 8},
        {"event_time": 30, "available_at": 60, "open": 9, "close": 10},
    ]
    assert partial_bar(events, 900)["bucketStart"] == 900
    assert partial_bar(events, 900)["bucketEnd"] == 1800
    custom = partial_bar(events, 30, bar_seconds=30)
    assert custom["bucketStart"] == 30 and custom["bucketEnd"] == 60
    assert custom["pending"] == 1 and custom["count"] == 0


def _bar(at: str, o: float, h: float, low: float, c: float):
    return {"t": at, "o": o, "h": h, "l": low, "c": c, "v": 1000}


def _row(asof: str, received: str, utc: list, strikes: list, query_key: str, snap: str):
    import json
    return {"ticker": "SPY", "snapshot_id": snap, "query_key": query_key,
            "expiries": json.dumps(["2026-10-23"]), "formula_version": "gex.v2",
            "exposure_basis": "OI", "asof_ts": asof, "received_at": received,
            "walls_json": json.dumps(utc), "strikes_json": json.dumps(strikes)}


# Route-shaped fixture: three 30-minute bars; each row joins at its own
# recorded availability. A late revision and an out-of-age row stay distinct,
# and nothing is ever known-at the candle timestamp by construction.
TINGER = "2026-10-20"


def test_recorded_availability_join_never_equates_candle_time():
    from services.price_node_history import build_history
    bars = [
        _bar(f"{TINGER}T14:00:00+00:00", 430, 432, 429, 431),
        _bar(f"{TINGER}T14:30:00+00:00", 431, 434, 430, 433),
        _bar(f"{TINGER}T15:00:00+00:00", 433, 436, 432, 435),
    ]
    probe_scope = "SPY|expiries=2026-10-23|gex.v2|OI"
    first_wall = [{"wall_id": "w-a", "mid": 431.5, "low": 431.0, "high": 432.0}]
    revised_wall = [{"wall_id": "w-b", "mid": 433.5, "low": 432.5, "high": 434.0}]
    events = [
        # observed before the first bar; receipt clock is before the bar clock
        _row(f"{TINGER}T13:58:00+00:00", f"{TINGER}T13:58:30+00:00",
             first_wall, [{"strike": 431, "gex": 1}], "SPY", "snap-a"),
        # genuine late revision: observe, then receipt before the 14:30 bar
        _row(f"{TINGER}T14:28:00+00:00", f"{TINGER}T14:29:00+00:00",
             revised_wall, [{"strike": 434, "gex": -2}], "SPY", "snap-b"),
        # observation long out of recorded age at the 15:00 bar
        _row(f"{TINGER}T12:00:00+00:00", f"{TINGER}T12:00:01+00:00",
             first_wall, [{"strike": 400, "gex": 0}], "SPY", "snap-old"),
    ]
    result = build_history("SPY", bars, events, query_key=probe_scope)
    frames = {f["time"]: f for f in result["frames"]}
    first = frames[f"{TINGER}T14:00:00+00:00"]
    assert first["nodes"] and first["nodes"][0]["level"] == 431.5
    assert first["nodes_known_at"] == f"{TINGER}T13:58:30+00:00"  # recorded clock, not 14:00
    assert first["node_age_seconds"] == 120
    second = frames[f"{TINGER}T14:30:00+00:00"]
    assert second["nodes"][0]["level"] == 433.5  # the owning revision's wall
    assert second["snapshot_id"] == "snap-b"
    assert second["nodes_known_at"] == f"{TINGER}T14:29:00+00:00"
    third = frames[f"{TINGER}T15:00:00+00:00"]
    assert third["nodes"] == [] and third["nodes_known_at"] is None
    gaps = result["node_coverage"]["gap_counts"]
    assert gaps["observation_too_old"] == 1
    # Availability is refused, never invented: missing receipt removes the row.
    late_missing_receipt = _row(f"{TINGER}T15:29:00+00:00", f"{TINGER}T15:35:00+00:00",
                                revised_wall, [{"strike": 436, "gex": 1}], "SPY", "snap-late")
    late_missing_receipt.pop("asof_ts")
    result_missing = build_history("SPY", bars, events + [late_missing_receipt], query_key=probe_scope)
    last = {f["time"]: f for f in result_missing["frames"]}[f"{TINGER}T15:00:00+00:00"]
    assert last["nodes"] == [] and last["nodes_known_at"] is None
    assert last["snapshot_id"] is None


def test_bar_end_time_is_the_actual_window_boundary():
    from services.price_node_history import build_history
    bars = [
        _bar(f"{TINGER}T14:00:00+00:00", 430, 432, 429, 431),
        _bar(f"{TINGER}T14:30:00+00:00", 431, 434, 430, 433),
        _bar(f"{TINGER}T15:00:00+00:00", 433, 436, 432, 435),
    ]
    result = build_history("SPY", bars, [], bar_seconds=1800)
    ends = {f["time"]: f.get("end_time") for f in result["frames"]}
    assert ends[f"{TINGER}T14:00:00+00:00"] == f"{TINGER}T14:30:00+00:00"
    assert ends[f"{TINGER}T14:30:00+00:00"] == f"{TINGER}T15:00:00+00:00"
    assert ends[f"{TINGER}T15:00:00+00:00"] == f"{TINGER}T15:30:00+00:00"
    # Without a supplied duration the boundary stays honestly absent.
    assert all(f.get("end_time") is None for f in build_history("SPY", bars, [])["frames"])
