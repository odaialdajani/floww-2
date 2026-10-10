"""TPO maturity: bar-occupancy letters (explicit approximation), fifth-period
single-print admission, daily composite of last 20 bars. Golden oracle below
is hand-computed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from services.chart_tpo import composite, tpo_profile  # noqa: E402


def test_golden_letters_poc_and_fifth_period():
    bars = [
        {"low": 100.0, "high": 101.0},  # periods 0-3: rows {100}
        {"low": 100.0, "high": 101.0},
        {"low": 100.0, "high": 101.0},
        {"low": 100.0, "high": 101.0},
        {"low": 102.0, "high": 103.0},  # period 4: row {102} single print
        {"low": 100.0, "high": 101.0},  # period 5
    ]
    out = tpo_profile(bars, rows=3)
    # Range 100..103 rows [100,101),[101,102),[102,103]: counts 5/0/1.
    assert out["status"] == "ok"
    assert out["counts"] == [5, 0, 1]
    assert out["poc"] == {"price": 100.5, "letters": 5}
    # Single print at row 2 admitted (period 4 is the fifth period).
    assert out["single_prints"] == [{"price": 102.5, "period": 4}]


def test_single_prints_before_fifth_excluded():
    bars = [{"low": 100.0, "high": 101.0}, {"low": 105.0, "high": 106.0}]
    out = tpo_profile(bars, rows=6)
    assert out["single_prints"] == []


def test_composite_last_20_and_empty():
    bars = [{"low": float(i), "high": float(i + 1)} for i in range(30)]
    out = composite(bars)
    assert out["periods_used"] == 20
    assert tpo_profile([], rows=3)["status"] == "unavailable"
