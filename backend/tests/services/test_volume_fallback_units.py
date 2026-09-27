"""Volume-fallback unit tests (audit V2 math-heap fix).

compute_gex_grid_volume must use the SAME canonical units as the OI path
and its per-strike sibling (dollar_*_per_contract), with signed vanna/charm.
Previously it hand-rolled gamma*vol*spot*100 (missing x spot*0.01) and
abs()'d vanna/charm, destroying their natural sign.
"""
from __future__ import annotations

from bs_greeks import bs_gamma, bs_vanna
from services.gex_core import compute_gex_by_strike_volume, compute_gex_grid_volume


def _contracts():
    return [
        {"strike": 500, "type": "call", "oi": 0, "volume": 400, "iv": 0.2,
         "T": 30 / 365, "multiplier": 100.0, "expiry": "2030-01-15"},
        {"strike": 500, "type": "put", "oi": 0, "volume": 200, "iv": 0.2,
         "T": 30 / 365, "multiplier": 100.0, "expiry": "2030-01-15"},
    ]


SPOT = 500.0


def test_volume_grid_matches_per_strike_sibling_scale():
    rows = compute_gex_by_strike_volume(SPOT, _contracts(), "^SPX")
    grid = compute_gex_grid_volume(SPOT, _contracts(), "^SPX")
    row_net = sum(r["gex"] for r in rows)
    cell_net = sum(v for col in grid["grid"].values() for v in col.values())
    assert row_net != 0 and cell_net == row_net


def test_volume_grid_uses_canonical_dollar_units():
    grid = compute_gex_grid_volume(SPOT, _contracts(), "^SPX")
    call = _contracts()[0]
    # q matches DIV_YIELD["^SPX"] used by the grid code path.
    expected = (bs_gamma(SPOT, 500, 30 / 365, 0.2, q=0.013)
                * 400 * 100 * SPOT * SPOT * 0.01)
    assert grid["grid"]["2030-01-15"]["500"] != 0
    # call cell minus put cell == net; call leg equals canonical unit value
    solo = compute_gex_grid_volume(SPOT, [call], "^SPX")
    assert solo["grid"]["2030-01-15"]["500"] == expected


def test_volume_vex_keeps_vanna_sign():
    v = bs_vanna(SPOT, 500, 30 / 365, 0.2, q=0.013)
    assert v != 0  # guard: the fixture must exercise a nonzero vanna
    grid = compute_gex_grid_volume(SPOT, _contracts(), "^SPX")
    vex_cell = grid["vex_grid"]["2030-01-15"]["500"]
    assert vex_cell != 0
    solo_call = compute_gex_grid_volume(SPOT, [_contracts()[0]], "^SPX")
    expected_vex = v * 400 * 100 * SPOT * 0.01  # signed, canonical
    assert solo_call["vex_grid"]["2030-01-15"]["500"] == expected_vex
