"""G6 bar-distributed volume profile: explicit approximation variant.

Real bar OHLC+volume only — never exact tape precision. Golden oracle below
is hand-computed, not implementation echo. Zero-range bars pin to one
tick-aligned row; sparse rows stop expansion with attained fraction.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from services.chart_volume_profile import volume_profile  # noqa: E402


def test_golden_oracle_two_bars_three_rows():
    bars = [
        {"open": 100.0, "high": 102.0, "low": 100.0, "close": 101.0,
         "volume": 100.0},
        {"open": 101.0, "high": 103.0, "low": 101.0, "close": 102.0,
         "volume": 300.0},
    ]
    out = volume_profile(bars, rows=3, value_area_pct=0.70)
    # Overlap-fraction pro-rata: bar1 [100,102] splits 50/50 over rows 0-1;
    # bar2 [101,103] splits 150/150 over rows 1-2. Rows: 50/200/150 = 400.
    # VA target 280 from POC row1 (200): expand up (150>=50) -> 350/400.
    assert out["status"] == "ok"
    assert out["total_volume"] == 400.0
    assert out["poc"] == {"price": 101.5, "volume": 200.0}
    assert out["value_area"] == {"low": 101.0, "high": 103.0, "attained": 0.875}
    assert out["approximation"] == "bar-range"


def test_zero_range_pins_single_row_and_sparse_stops():
    bars = [{"open": 50.0, "high": 50.0, "low": 50.0, "close": 50.0,
             "volume": 10.0}]
    out = volume_profile(bars, rows=5, value_area_pct=0.70)
    assert out["status"] == "ok"
    assert out["rows"] == [{"price": 50.0, "volume": 10.0}]
    assert out["poc"] == {"price": 50.0, "volume": 10.0}


def test_missing_volume_is_unavailable_not_zero():
    bars = [{"open": 1.0, "high": 2.0, "low": 1.0, "close": 1.5}]
    out = volume_profile(bars, rows=3)
    assert out["status"] == "unavailable"
    assert volume_profile([], rows=3)["status"] == "unavailable"
