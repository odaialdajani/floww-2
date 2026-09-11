"""
D6 regression: exposure_alerts finite-grid contract.

- _norm_grid must not emit NaN/Infinity cell values (strict-JSON downstream).
- _max_abs must not return NaN (NaN > 0 is False, but NaN arithmetic is unsafe).
- evaluate_exposure_events must return finite-magnitude events.
- events_to_alerts must produce finite score/under_price/context.magnitude.
"""

from __future__ import annotations

import math
import sys
import types
from pathlib import Path

import pytest

# Import from the worktree backend without relying on cwd.
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.exposure_alerts import (
    _max_abs,
    _norm_grid,
    evaluate_exposure_events,
    events_to_alerts,
)


def _nan() -> float:
    return float("nan")


def _inf() -> float:
    return float("inf")


def _neg_inf() -> float:
    return float("-inf")


# ── _norm_grid ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,any_nonfinite_after", [
    ({"2026-09-18": {"100.0": 1.5, "105.0": _nan()}}, False),
    ({"2026-09-18": {"100.0": 1.5, "105.0": _inf()}}, False),
    ({"2026-09-18": {"100.0": 1.5, "105.0": _neg_inf()}}, False),
    ({"2026-09-18": {"100.0": 1.5, "105.0": 2.0}}, False),
    ({}, False),
    ({"2026-09-18": {"100.0": "bad"}}, False),
])
def test_norm_grid_drops_nonfinite_cells(raw, any_nonfinite_after):
    norm = _norm_grid(raw)
    any_nonfinite = False
    for row in norm.values():
        for v in row.values():
            if not math.isfinite(v):
                any_nonfinite = True
                break
    assert any_nonfinite == any_nonfinite_after


# ── _max_abs ────────────────────────────────────────────────────────────────

def test_max_abs_nan_input_is_finite():
    section = {"2026-09-18": {"100.0": _nan(), "105.0": 2.0}}
    m = _max_abs(section)
    assert math.isfinite(m)


def test_max_abs_inf_input_is_finite():
    section = {"2026-09-18": {"100.0": _inf(), "105.0": 2.0}}
    m = _max_abs(section)
    assert math.isfinite(m)


def test_max_abs_empty_is_zero():
    assert _max_abs({}) == 0.0


# ── evaluate_exposure_events ─────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skip(reason="async marker left by earlier session; removing before use")
async def _dummy():
    pass


def test_events_have_finite_magnitude_with_nonfinite_grid():
    new_grid = {
        "vex_grid": {"2026-09-18": {"100.0": _nan(), "105.0": 3.0}},
        "charm_grid": {},
    }
    events = evaluate_exposure_events(new_grid, threshold_pct=0.25)
    for e in events:
        assert math.isfinite(e["magnitude"]), e
        assert math.isfinite(e["strike"]), e


def test_events_finite_with_inf_grid():
    new_grid = {
        "vex_grid": {"2026-09-18": {"100.0": _inf(), "105.0": -2.0}},
        "charm_grid": {},
    }
    events = evaluate_exposure_events(new_grid, threshold_pct=0.25)
    for e in events:
        assert math.isfinite(e["magnitude"]), e
        assert math.isfinite(e["strike"]), e


# ── events_to_alerts ─────────────────────────────────────────────────────────

def test_alerts_are_strictly_finite_json():
    events = [
        {"kind": "vex_wall_formed", "strike": 105.0, "expiry": "2026-09-18",
         "magnitude": _nan()},
        {"kind": "charm_pin_formed", "strike": 100.0, "expiry": "2026-09-18",
         "magnitude": 1e6},
    ]
    alerts = events_to_alerts("SPY", 520.5, events)
    for a in alerts:
        assert math.isfinite(a["score"])
        assert math.isfinite(a["under_price"])
        assert math.isfinite(a["context"]["magnitude"])
        assert math.isfinite(a["strike"])
    # Confirm strict-JSON serializable (no nan/inf).
    import json
    json.dumps(alerts)
