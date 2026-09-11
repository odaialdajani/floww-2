"""A3 conviction-exposure wiring: exposure alerts feed score_conviction additively.

TDD contract (A34 gap: exposure alerts computed beside the heatmap in
routes/data_providers.py never fed into any conviction scorer):

  * score_conviction() gains ``exposure_adjustment`` (default 0 — no
    behavior change when no alerts).
  * exposure_adjustment_for_events() maps exposure event/alert dicts to a
    bounded adjustment in [-5, +5]. Per-kind weights:
      vex_wall_formed   -2  (vol suppression defended — fade directional prints)
      vex_wall_broken   +3  (suppression released — regime may shift, tradable)
      charm_pin_formed  +2  (hedging concentration into expiry — follow-through)
      charm_pin_shifted +1  (magnet moved — weak continuation)
    Unknown kinds contribute 0; the summed adjustment clamps to [-5, +5].
  * score_conviction() applies the adjustment additively inside the 0..100
    clamp (also defensively clamps the adjustment itself to [-5, +5]).
"""

import pytest

from services.flow_alerts import (
    exposure_adjustment_for_events,
    score_conviction,
)

_MID = {
    "vol_oi": 6,
    "vol": 10000,
    "notional": 2e6,
    "dte": 30,
    "premium": 100e3,
    "_score": 50,
}

_MAX_FACTORS = {
    "cw_confirm": True,
    "cluster": True,
    "sigma_ticker": True,
    "regime_confluent": True,
    "gex_confluent": True,
}
_MAX_ROW = {
    "vol_oi": 9,
    "vol": 50000,
    "notional": 50e6,
    "dte": 7,
    "premium": 12e6,
    "_score": 95,
    "velocity_per_min": 1500,
    "sign_method": "quote",
    "signed_side": "ASK",
}


def _ev(kind: str) -> dict:
    return {"kind": kind, "strike": 600.0, "expiry": "2026-09-18", "magnitude": 1.0}


# ── default: no behavior change ──────────────────────────────────────

def test_default_matches_zero_adjustment():
    base = score_conviction(dict(_MID))
    assert score_conviction(dict(_MID), exposure_adjustment=0) == base


def test_positive_adjustment_is_additive():
    base = score_conviction(dict(_MID))
    assert score_conviction(dict(_MID), exposure_adjustment=3) == min(100, base + 3)


def test_negative_adjustment_is_additive():
    base = score_conviction(dict(_MID))
    assert score_conviction(dict(_MID), exposure_adjustment=-2) == max(0, base - 2)


# ── 0..100 clamp survives the adjustment ─────────────────────────────

def test_upper_clamp_at_100():
    assert score_conviction(dict(_MAX_ROW), dict(_MAX_FACTORS), regime="negative") == 100
    assert (
        score_conviction(
            dict(_MAX_ROW), dict(_MAX_FACTORS),
            regime="negative", exposure_adjustment=5,
        )
        == 100
    )


def test_lower_clamp_at_0():
    assert score_conviction({}, exposure_adjustment=-5) == 0


def test_adjustment_itself_clamped_to_pm5():
    base = score_conviction(dict(_MID))
    assert score_conviction(dict(_MID), exposure_adjustment=50) == min(100, base + 5)
    assert score_conviction(dict(_MID), exposure_adjustment=-50) == max(0, base - 5)


# ── mapper: per-kind weights ─────────────────────────────────────────

@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("vex_wall_formed", -2),
        ("vex_wall_broken", 3),
        ("charm_pin_formed", 2),
        ("charm_pin_shifted", 1),
    ],
)
def test_mapper_single_kind(kind, expected):
    assert exposure_adjustment_for_events([_ev(kind)]) == expected


def test_mapper_sums_kinds():
    events = [_ev("vex_wall_broken"), _ev("charm_pin_formed")]  # 3 + 2
    assert exposure_adjustment_for_events(events) == 5


def test_mapper_opposing_kinds_net():
    events = [_ev("vex_wall_broken"), _ev("vex_wall_formed")]  # 3 - 2
    assert exposure_adjustment_for_events(events) == 1


def test_mapper_clamps_positive():
    events = [_ev("vex_wall_broken")] * 5  # 15 -> 5
    assert exposure_adjustment_for_events(events) == 5


def test_mapper_clamps_negative():
    events = [_ev("vex_wall_formed")] * 5  # -10 -> -5
    assert exposure_adjustment_for_events(events) == -5


def test_mapper_ignores_unknown_kinds_and_empties():
    assert exposure_adjustment_for_events([]) == 0
    assert exposure_adjustment_for_events(None) == 0
    assert exposure_adjustment_for_events([_ev("nope"), {"kind": ""}]) == 0


def test_mapper_accepts_alert_dicts_with_key():
    # events_to_alerts() output carries the kind inside `key`, not `kind`.
    alert = {"key": "exposure:vex_wall_broken:SPY:2026-09-18:600", "rule": "VEX_WALL"}
    assert exposure_adjustment_for_events([alert]) == 3


# ── end to end: mapper output feeds the scorer ───────────────────────

def test_end_to_end_mapper_into_scorer():
    base = score_conviction(dict(_MID))
    adj = exposure_adjustment_for_events([_ev("vex_wall_broken")])
    assert adj == 3
    assert score_conviction(dict(_MID), exposure_adjustment=adj) == min(100, base + 3)
