"""Vomma walls: vol-convexity concentration alerts (prop-desk edge).

Vomma (dVega/dVol) marks where dealer hedging accelerates into vol moves —
the same wall semantics as VEX, one Greek deeper. RED on main (no
vomma_grid emission, no VOMMA_WALL rule); GREEN with both.
"""
import pytest

from services.exposure_alerts import RULE_VOMMA_WALL, evaluate_exposure_events


def _grid(vomma=None, vex=None):
    return {"vex_grid": vex or {},
            "charm_grid": {},
            "vomma_grid": vomma or {}}


def test_rule_constant():
    assert RULE_VOMMA_WALL == "VOMMA_WALL"


def test_emission_present():
    from services.gex_core import compute_gex_grid
    contracts = [{"strike": 100.0, "expiry": "2026-09-18", "T": 0.25,
                  "type": "call", "oi": 100.0, "iv": 0.25, "volume": 10.0}]
    out = compute_gex_grid(100.0, contracts, "SPY")
    assert "vomma_grid" in out
    assert out["vomma_grid"]["2026-09-18"]["100"] != 0.0


def test_wall_formed():
    new = _grid(vomma={"2026-09-18": {"100": 5e6, "105": 1e5}})
    ev = evaluate_exposure_events(new, None)
    kinds = [e["kind"] for e in ev]
    assert "vomma_wall_formed" in kinds
    assert RULE_VOMMA_WALL == "VOMMA_WALL"


def test_wall_broken():
    old = _grid(vomma={"2026-09-18": {"100": 5e6}})
    new = _grid(vomma={"2026-09-18": {"100": 1e3}})
    ev = evaluate_exposure_events(new, old)
    assert [e["kind"] for e in ev] == ["vomma_wall_broken"]


def test_silent_empty_and_stable():
    assert evaluate_exposure_events(_grid(), None) == []
    g = _grid(vomma={"2026-09-18": {"100": 5e6}})
    ev = evaluate_exposure_events(g, g)
    assert "vomma_wall_formed" not in [e["kind"] for e in ev]


def test_alert_shape():
    from services.exposure_alerts import events_to_alerts
    ev = [{"kind": "vomma_wall_formed", "strike": 100.0,
           "expiry": "2026-09-18", "magnitude": 5e6}]
    out = events_to_alerts("SPY", 100.0, ev)
    assert out[0]["rule"] == "VOMMA_WALL"
    assert 50 <= out[0]["score"] <= 99
    assert "vomma" in out[0]["why"].lower()
