"""VEX scale-parity guard: two documented conventions disagree.

Characterization, not a fix. `bs_greeks` documents vomma exposure as
``vomma * OI * 100`` (per unit-sigma, no spot factor), while
`gex_vex_calculator.compute_vex_surface` scales like GEX
(``vomma * OI * 100 * spot^2 * 0.01``). Both docstrings claim intent, no
live caller mixes them today, and choosing the winner is an architect
decision — so this test pins the exact relationship instead of changing
either formula:

    compute_vex_surface(...) == sign * dollar_vomma_per_contract(...) * spot^2 * 0.01

Any change to either side breaks this test and forces an explicit,
reviewed reconciliation. Neither scale may be presented as observed
dealer inventory: both assume dealer positioning and sign.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs_greeks import dollar_vomma_per_contract  # noqa: E402
from services.gex_vex_calculator import compute_vex_surface  # noqa: E402


def test_vex_scale_relationship_is_explicit():
    """Pin the exact factor between the two vomma-exposure scales."""
    spot = 580.0
    strikes = np.array([575.0, 580.0])
    vommas = np.array([0.010, 0.020])
    ois = np.array([1000.0, 2000.0])
    types = np.array([0, 1])  # call, put

    got = compute_vex_surface(spot, strikes, vommas, ois, types)

    expected_scale = spot * spot * 0.01
    for i in range(2):
        sign = 1.0 if types[i] == 0 else -1.0
        canonical = sign * dollar_vomma_per_contract(float(vommas[i]),
                                                    float(ois[i]))
        assert got[i] == canonical * expected_scale

    # Name the magnitude so no one mistakes one scale for the other:
    # at SPY 580 the GEX-like scale reads ~3364x the per-unit-sigma scale.
    assert expected_scale == spot * spot * 0.01 == 3364.0


def test_scales_agree_only_at_unit_spot():
    """The two conventions coincide only at the degenerate spot=10."""
    spot = 10.0
    strikes = np.array([10.0])
    vommas = np.array([0.015])
    ois = np.array([500.0])
    types = np.array([0])

    got = compute_vex_surface(spot, strikes, vommas, ois, types)
    canonical = dollar_vomma_per_contract(0.015, 500.0)
    assert got[0] == canonical * (spot * spot * 0.01)
    assert spot * spot * 0.01 == 1.0
    assert got[0] == canonical
