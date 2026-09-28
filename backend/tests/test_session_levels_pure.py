"""Pure session exposure-weighted level checks (Command Code C1.2).

This is the portable VWAP math only: price x volume accumulation, session
boundary handling, zero/missing-volume behavior, unavailable bars, and
source timestamps. It does not call routes, server code, or the live async
bar path, and it does not create or require an event loop.

Naming boundary: this level is a session exposure-weighted reference. It
must not be labeled market VWAP unless the caller proves full-market
coverage and session scope.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.session_levels import (  # noqa: E402
    SESSION_LEVEL_VERSION,
    session_exposure_level,
)


def _bar(ts, h, low, c, v, session="regular"):
    return {
        "date": ts,
        "high": h,
        "low": low,
        "close": c,
        "volume": v,
        "session": session,
    }


def test_known_accumulation_is_exact():
    bars = [
        _bar("2030-01-02T14:00:00+00:00", 7760, 7690, 7743, 1200),
        _bar("2030-01-02T14:01:00+00:00", 7720, 7670, 7710, 900),
    ]
    out = session_exposure_level(bars, "2030-01-02")
    expected = ((7760 + 7690 + 7743) / 3 * 1200 + (7720 + 7670 + 7710) / 3 * 900) / 2100
    assert out["status"] == "ok"
    assert out["value"] == pytest.approx(expected)
    assert out["version"] == SESSION_LEVEL_VERSION


def test_only_matching_session_date_counts():
    bars = [
        _bar("2030-01-02T14:00:00+00:00", 100, 100, 100, 100),
        _bar("2030-01-02T14:01:00+00:00", 200, 200, 200, 100, session="pre"),
        _bar("2030-01-03T14:00:00+00:00", 300, 300, 300, 100),
    ]
    out = session_exposure_level(bars, "2030-01-02")
    assert out["status"] == "ok"
    assert out["value"] == pytest.approx(100.0)
    assert out["bars_used"] == 1
    assert out["bars_skipped"] == 2


def test_zero_missing_or_unavailable_volume_is_unavailable():
    assert session_exposure_level([], "2030-01-02")["reason"] == "NO_BARS"
    assert session_exposure_level(None, "2030-01-02")["reason"] == "NO_BARS"
    out = session_exposure_level([_bar("2030-01-02T14:00:00+00:00", 1, 1, 1, 0)], "2030-01-02")
    assert out["value"] is None
    assert out["reason"] == "NO_VOLUME"
    out = session_exposure_level([_bar("2030-01-02T14:00:00+00:00", 1, 1, 1, None)], "2030-01-02")
    assert out["value"] is None


def test_unusable_ohlc_and_nonfinite_inputs_are_skipped():
    bars = [
        _bar("2030-01-02T14:00:00+00:00", 700, 690, 695, 100),
        {"date": "2030-01-02T14:01:00+00:00", "volume": 50},
        {"date": "2030-01-02T14:02:00+00:00", "high": float("nan"), "low": 1, "close": 1, "volume": 5},
        None,
    ]
    out = session_exposure_level(bars, "2030-01-02")
    assert out["status"] == "ok"
    assert out["bars_used"] == 1
    assert out["bars_skipped"] == 3


def test_source_timestamps_are_preserved_not_rewritten():
    bars = [_bar("2030-01-02T14:00:00+00:00", 700, 690, 695, 100)]
    out = session_exposure_level(bars, "2030-01-02")
    assert out["source_dates"] == ["2030-01-02T14:00:00+00:00"]
