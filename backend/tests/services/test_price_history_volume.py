"""Atlas hardening: price-history frames must carry real provider volume.

build_history keeps only o/h/l/c today; the provider sends `v` on every bar
(_extract_bars in public_api_adapter). Atlas's Volume/CVD/Profile/TPO panes
need per-candle volume. Volume must pass through untouched — absent stays
absent, never 0-as-fabricated.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.price_node_history import build_history  # noqa: E402


def test_build_history_preserves_positive_volume():
    bars = [
        {"t": "2026-10-06T13:30:00+00:00", "o": 100.0, "h": 102.0, "l": 99.0,
         "c": 101.0, "v": 12000},
        {"t": "2026-10-06T13:31:00+00:00", "o": 101.0, "h": 103.0, "l": 100.0,
         "c": 102.0, "v": 34000},
    ]
    out = build_history("SPY", bars, [])
    assert out["frames"][0]["volume"] == 12000
    assert out["frames"][1]["volume"] == 34000


def test_build_history_absent_volume_stays_absent():
    bars = [
        {"t": "2026-10-06T13:30:00+00:00", "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0},
    ]
    out = build_history("SPY", bars, [])
    assert "volume" not in out["frames"][0]


def test_build_history_rejects_nonfinite_and_negative_volume():
    bars = [
        {"t": "2026-10-06T13:30:00+00:00", "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0, "v": -5},
        {"t": "2026-10-06T13:31:00+00:00", "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0, "v": "nan"},
        {"t": "2026-10-06T13:32:00+00:00", "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0, "v": None},
    ]
    out = build_history("SPY", bars, [])
    for frame in out["frames"]:
        assert "volume" not in frame


def test_build_history_zero_volume_is_kept_as_measured_zero():
    bars = [
        {"t": "2026-10-06T13:30:00+00:00", "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0, "v": 0},
    ]
    out = build_history("SPY", bars, [])
    assert out["frames"][0]["volume"] == 0
