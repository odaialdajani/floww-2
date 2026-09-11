"""
D7 regression: exposure_adjustment_for_events wired as the single exposure gate.

- exposure_adjustment_for_events is the canonical mapper from exposure events
  to conviction adjustment; score_conviction must not maintain a separate
  hardcoded copy of the same weights/bounds.
- _exposure_kind_of must parse both event dicts (kind field) and alert dicts
  (exposure:<kind>:... key).
- Default 0 keeps existing callers byte-identical; clamp [-5, +5] is pinned
  in one place only.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.flow_alerts import (
    _EXPOSURE_ADJUST_MAX,
    _EXPOSURE_ADJUST_MIN,
    _EXPOSURE_KIND_WEIGHTS,
    _exposure_kind_of,
    exposure_adjustment_for_events,
)


def _event(*, kind: str) -> dict:
    return {"kind": kind}


def _alert(*, kind: str, ticker: str = "SPY", exp: str = "2026-09-18", strike: float = 100.0) -> dict:
    return {"key": f"exposure:{kind}:{ticker.upper()}:{exp}:{strike:g}"}


# ── _exposure_kind_of ─────────────────────────────────────────────────────

@pytest.mark.parametrize("item,expected_kind", [
    (_event(kind="vex_wall_formed"), "vex_wall_formed"),
    (_event(kind="vex_wall_broken"), "vex_wall_broken"),
    (_event(kind="charm_pin_formed"), "charm_pin_formed"),
    (_event(kind="charm_pin_shifted"), "charm_pin_shifted"),
    (_event(kind=""), ""),
    (_event(kind="unknown_thing"), "unknown_thing"),
    (_alert(kind="vex_wall_formed"), "vex_wall_formed"),
    (_alert(kind="vex_wall_broken"), "vex_wall_broken"),
    (_alert(kind="charm_pin_formed"), "charm_pin_formed"),
    (_alert(kind="charm_pin_shifted"), "charm_pin_shifted"),
    (_alert(kind=""), ""),
    ({"key": "not_an_exposure"}, ""),
])
def test_exposure_kind_of_event_and_alert(item, expected_kind):
    assert _exposure_kind_of(item) == expected_kind


# ── exposure_adjustment_for_events ─────────────────────────────────────────

@pytest.mark.parametrize("events,total_before_clamp", [
    ([], 0),
    (None, 0),
    ([_event(kind="vex_wall_formed")], -2),
    ([_event(kind="vex_wall_broken")], 3),
    ([_event(kind="charm_pin_formed")], 2),
    ([_event(kind="charm_pin_shifted")], 1),
    ([_event(kind="vex_wall_formed"), _event(kind="vex_wall_broken")], 1),
    ([_event(kind="vex_wall_formed")] * 3, -6),
    ([_event(kind="vex_wall_formed")] * 10, -20),
])
def test_exposure_adjustment_sums_and_clamps(events, total_before_clamp):
    adj = exposure_adjustment_for_events(events)
    expected = max(_EXPOSURE_ADJUST_MIN, min(_EXPOSURE_ADJUST_MAX, total_before_clamp))
    assert adj == expected


def test_exposure_adjustment_ignores_unknown_kinds():
    events = [
        _event(kind="vex_wall_formed"),
        _event(kind="made_up_event"),
        _event(kind="charm_pin_shifted"),
    ]
    assert exposure_adjustment_for_events(events) == (-2 + 0 + 1)


def test_exposure_adjustment_ignores_non_dict_items():
    adj = exposure_adjustment_for_events(["bad", None, 123, _event(kind="vex_wall_formed")])
    assert adj == -2


def test_exposure_adjustment_accepts_alert_dicts():
    adj = exposure_adjustment_for_events([_alert(kind="vex_wall_formed"), _alert(kind="vex_wall_broken")])
    assert adj == (-2 + 3)


def test_exposure_adjustment_single_source_of_truth():
    # If the weights/bounds are ever changed here, this test must reflect them.
    assert set(_EXPOSURE_KIND_WEIGHTS.keys()) == {
        "vex_wall_formed", "vex_wall_broken", "charm_pin_formed", "charm_pin_shifted"
    }
    assert _EXPOSURE_ADJUST_MIN == -5
    assert _EXPOSURE_ADJUST_MAX == 5
