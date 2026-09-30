"""S5 time boundary + Triad exact strike identity (Spark).

R10-11: the legacy Eastern fallback preserved UTC tzinfo while subtracting
4/5h, shifting the instant. eastern_at_safe always returns an aware
datetime whose UTC timestamp equals the input. R10-08:
project_triad_from_chain collapsed 100.25/100.75 into strike 100 via int().
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.eastern_clock import (  # noqa: E402
    eastern_at_safe,
    eastern_utc_offset_hours,
)
from services.triad_projection import project_triad_from_chain  # noqa: E402


def _utc(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def test_safe_boundary_preserves_instant_and_wall_hour():
    for utc, wall in (
        (_utc(2026, 1, 15, 14, 30), "09:30"),   # EST (-5)
        (_utc(2026, 6, 15, 13, 30), "09:30"),   # EDT (-4)
        (_utc(2026, 3, 8, 6, 59), "01:59"),     # pre-transition EST edge
        (_utc(2026, 11, 1, 5, 59), "01:59"),    # pre-transition EDT edge
    ):
        got = eastern_at_safe(utc)
        assert got.tzinfo is not None
        assert got.timestamp() == utc.timestamp(), (utc, got)
        assert got.strftime("%H:%M") == wall, (utc, got)
        assert got.utcoffset().total_seconds() == eastern_utc_offset_hours(utc) * 3600


def test_safe_boundary_matches_offset_rule_across_hosts():
    # Host-independent by construction: only the input instant matters.
    utc = _utc(2026, 3, 20, 13, 0)
    assert eastern_at_safe(utc).strftime("%H:%M") == "09:00"


def test_safe_boundary_rejects_naive_input():
    import pytest

    with pytest.raises(ValueError):
        eastern_at_safe(datetime(2026, 6, 15, 13, 30))


def _payload(strikes):
    return {
        "ticker": "SPY",
        "spot": 100,
        "contracts": [
            {
                "strike": s, "expiry": "2030-01-15", "type": "call",
                "gamma": 0.01, "oi": 100, "multiplier": 100,
            }
            for s in strikes
        ],
    }


def test_decimal_strikes_stay_distinct():
    pkt = project_triad_from_chain(_payload([100.25, 100.75]))
    got = {s["strike"]: s["gex"] for s in pkt["strikes"]}
    assert set(got) == {100.25, 100.75}
    assert got[100.25] == got[100.75] == 10_000.0
    assert set(pkt["grid"]["grid"]["2030-01-15"]) == {"100.25", "100.75"}


def test_integer_strikes_keep_legacy_key_form():
    pkt = project_triad_from_chain(_payload([450, 460]))
    assert set(pkt["grid"]["grid"]["2030-01-15"]) == {"450", "460"}
    assert [s["strike"] for s in pkt["strikes"]] == [460.0, 450.0]
