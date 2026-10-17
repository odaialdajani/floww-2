"""Unknown bar volume cannot fabricate a measurement or discard a candle."""
from __future__ import annotations

import json

import pytest

from services.price_node_history import build_history
from services.public_api_adapter import _extract_bars

_UNKNOWN = [None, False, True, "", " \t", "bad", -1, "-1", float("nan"),
            float("inf"), float("-inf"), "NaN", "Infinity", "-Infinity",
            [], {}, 10**400]


@pytest.fixture(autouse=True)
def _reset_event_loop_and_motor():
    """Pure parser tests need no global ASGI/Motor/policy-reset fixture."""
    yield


def _bar(**fields):
    return {"timestamp": "2026-10-06T13:30:00+00:00", "open": "100",
            "high": "102", "low": "99", "close": "101", **fields}


def _parse(bar):
    return _extract_bars({"regularMarket": {"expectedBars": 1, "bars": [bar]}})


def _assert_candle(rows):
    assert len(rows) == 1
    row = rows[0]
    assert {k: row[k] for k in ("t", "o", "h", "l", "c", "session")} == {
        "t": "2026-10-06T13:30:00+00:00", "o": 100.0, "h": 102.0,
        "l": 99.0, "c": 101.0, "session": "regular"}
    return row


def test_absent_volume_preserves_candle_and_unknown_history_frame():
    rows = _parse(_bar())
    assert _assert_candle(rows).get("v") is None
    frame = build_history("SPY", rows, [])["frames"][0]
    assert "volume" not in frame


@pytest.mark.parametrize("alias", ["v", "volume"])
@pytest.mark.parametrize("value", _UNKNOWN)
def test_invalid_volume_preserves_candle_and_unknown_history_frame(alias, value):
    rows = _parse(_bar(**{alias: value}))
    assert _assert_candle(rows).get("v") is None
    frame = build_history("SPY", rows, [])["frames"][0]
    assert "volume" not in frame
    assert frame["cvd"] is None
    json.dumps(frame, allow_nan=False)


@pytest.mark.parametrize("alias", ["v", "volume"])
@pytest.mark.parametrize(("value", "expected"), [(0, 0.0), (0.0, 0.0), ("0", 0.0),
                                               (12, 12.0), (12.5, 12.5), (" 12.5 ", 12.5)])
def test_measured_volume_survives_parser_and_history(alias, value, expected):
    rows = _parse(_bar(**{alias: value}))
    assert _assert_candle(rows)["v"] == expected
    assert build_history("SPY", rows, [])["frames"][0]["volume"] == expected


@pytest.mark.parametrize("primary", _UNKNOWN)
def test_invalid_primary_volume_is_not_replaced_by_secondary_alias(primary):
    rows = _parse(_bar(v=primary, volume=12345))
    assert _assert_candle(rows).get("v") is None
    assert "volume" not in build_history("SPY", rows, [])["frames"][0]


@pytest.mark.parametrize("primary", [0, "0", 12.5])
def test_present_primary_volume_wins_over_secondary_alias(primary):
    rows = _parse(_bar(v=primary, volume=12345))
    assert _assert_candle(rows)["v"] == float(primary)


def test_mixed_volume_candles_keep_recorded_node_and_session_boundaries():
    payload = {"regularMarket": {"bars": [
        _bar(timestamp="2026-10-06T13:30:00+00:00"),
        _bar(timestamp="2026-10-06T13:31:00+00:00", volume=0),
        _bar(timestamp="2026-10-06T13:32:00+00:00", volume=12),
        _bar(timestamp="2026-10-06T13:33:00+00:00", volume="bad"),
    ]}, "afterMarket": {"bars": [_bar(volume=None)]}}
    rows = _extract_bars(payload)
    assert len(rows) == 4
    snapshot = {"ticker": "SPY", "snapshot_id": "local-synthetic", "query_key": "scope",
                "asof_ts": "2026-10-06T13:30:00+00:00",
                "received_at": "2026-10-06T13:30:00+00:00",
                "walls_json": [{"wall_id": "wall", "mid": 100}]}
    history = build_history("SPY", rows, [snapshot], query_key="scope")
    assert history["candles"] == 4
    assert history["candles_with_recorded_nodes"] == 4
    for frame in history["frames"]:
        assert frame["snapshot_id"] == "local-synthetic"
        assert frame["nodes"] == [{"id": "wall", "level": 100.0, "low": 100.0, "high": 100.0}]
        assert frame["session"] == "regular"
        assert [frame[k] for k in ("open", "high", "low", "close")] == [100, 102, 99, 101]
    frames = history["frames"]
    assert "volume" not in frames[0]
    assert frames[1]["volume"] == 0
    assert frames[2]["volume"] == 12
    assert "volume" not in frames[3]
    assert frames[3]["cvd"] is None
    assert len(_extract_bars(payload, sessions="all")) == 5
    json.dumps(history, allow_nan=False)
