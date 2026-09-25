"""R7-02 red tests: canonical delta/VEX contract + population parity."""

import sys

sys.path.insert(0, "backend")

SPOT = 500.0


def _contracts():
    return [
        {"strike": 500, "type": "call", "gamma": 0.05, "delta": 0.45,
         "oi": 10000, "volume": 400, "iv": 0.2, "T": 30 / 365,
         "multiplier": 100.0, "expiry": "2030-01-15"},
        {"strike": 500, "type": "put", "gamma": 0.05, "delta": -0.45,
         "oi": 10000, "volume": 200, "iv": 0.2, "T": 30 / 365,
         "multiplier": 100.0, "expiry": "2030-01-15"},
    ]


def test_delta_golden_fixtures_and_ranking():
    from services.gex_core import (
        compute_gex_by_strike_vendor,
        compute_gex_grid_vendor,
    )
    rows = compute_gex_by_strike_vendor(SPOT, _contracts())
    by = {r["strike"]: r for r in rows}
    # u = .05*100*500^2*.01 = 12500; raw net 0, gross 2*12500*10000 = 250M
    assert by[500.0]["gex"] == 0.0
    assert by[500.0]["call_gex"] == 125_000_000.0
    grid = compute_gex_grid_vendor(SPOT, _contracts())
    assert grid["grid"]["2030-01-15"]["500"] == 0.0
    # Delta-weighted: 125M * .45 = 56.25M per side, net 0.
    from domain.exposure_metrics import compute_delta_weighted_oi
    reg = compute_delta_weighted_oi(_contracts(), SPOT)
    assert reg.net == 0.0 and reg.gross == 112_500_000.0
    # Equal raw, different delta weight ranks differently.
    alt = [dict(_contracts()[0], gamma=0.01, delta=0.10, oi=50000)]
    from domain.exposure_metrics import compute_raw_oi
    assert compute_raw_oi(alt, SPOT).net == compute_raw_oi(_contracts()[:1], SPOT).net
    assert compute_delta_weighted_oi(alt, SPOT).gross == 12_500_000.0
    assert compute_delta_weighted_oi(alt, SPOT).gross < reg.gross / 2


def test_put_sign_trap_no_double_signing():
    from domain.exposure_metrics import compute_delta_weighted_oi
    both = [dict(_contracts()[0], delta=0.5), dict(_contracts()[1], delta=-0.5)]
    reg = compute_delta_weighted_oi(both, SPOT)
    assert reg.net == 0.0  # naive signed-delta double-signing gives +1M-style error
    assert reg.gross > 0.0


def test_same_coverage_invariants():
    from domain.exposure_metrics import compute_delta_weighted_oi, compute_raw_oi
    raw = compute_raw_oi(_contracts(), SPOT)
    dw = compute_delta_weighted_oi(_contracts(), SPOT)
    assert abs(raw.net) <= raw.gross
    assert abs(dw.net) <= dw.gross <= raw.gross


def test_unknown_type_rejected_everywhere_with_accounting():
    from domain.exposure_metrics import compute_raw_oi
    from services.gex_core import (
        compute_gex_by_strike_vendor,
        compute_gex_grid_vendor,
    )
    weird = _contracts() + [dict(_contracts()[0], type="mystery", strike=510)]
    rows = compute_gex_by_strike_vendor(SPOT, weird)
    assert {r["strike"] for r in rows} == {500.0}  # never a default-put row
    grid = compute_gex_grid_vendor(SPOT, weird)
    assert grid["invalid_type"] == 1
    assert grid["grid"]["2030-01-15"].get("510") is None
    reg = compute_raw_oi(weird, SPOT)
    assert reg.invalid == 1 and reg.usable == 2
    # Row sums still equal cell sums: one rule in both places.
    row_net = sum(r["gex"] for r in rows)
    cell_net = sum(v for col in grid["grid"].values() for v in col.values())
    assert row_net == cell_net


def test_vex_unit_fix_and_finite_difference_oracle():
    from domain.greek_scalers import dollar_vex_per_1pct_vol_change
    # Audit numbers: vanna .2, OI 100, mult 100, spot 100 -> 2,000, not 198,000.
    assert dollar_vex_per_1pct_vol_change(0.2, 100, 100.0) == 2000.0
    import math

    from bs_greeks import bs_delta, bs_vanna
    for S, K, T, sigma, kind in [(100.0, 100.0, 0.25, 0.2, "call"),
                                 (100.0, 110.0, 0.5, 0.3, "put"),
                                 (100.0, 90.0, 0.1, 0.15, "call")]:
        eps = 1e-4
        fd = (bs_delta(S, K, T, sigma + eps, kind=kind)
              - bs_delta(S, K, T, sigma - eps, kind=kind)) / (2 * eps)
        assert math.isclose(bs_vanna(S, K, T, sigma), fd, rel_tol=1e-4), (S, K, kind)


def test_vex_surface_shape_and_coverage():
    from services.gex_core import compute_vex_by_strike_local, compute_vex_grid_local
    rows = compute_vex_by_strike_local(SPOT, _contracts(), "SPY")
    assert rows, "IV-bearing contracts must produce a VEX surface"
    by = {r["strike"]: r for r in rows}
    # Symmetric ± vanna cancels in net but not gross (same-coverage invariant).
    assert by[500.0]["vex_gross"] > 0
    assert by[500.0]["vex_gross"] >= abs(by[500.0]["vex_net"])
    assert by[500.0]["model"] == "local-bs-vanna.v1"
    grid = compute_vex_grid_local(SPOT, _contracts(), "SPY")
    assert grid["grid"]["2030-01-15"]["500"] == by[500.0]["vex_net"]
    assert grid["exposure_basis"] == "VEX_1VOLPT"
    assert grid["missing_vanna_inputs"] == 0
    # Missing IV blocks that contract, not the whole surface.
    nodata = [dict(_contracts()[0], iv=None)]
    g2 = compute_vex_grid_local(SPOT, nodata, "SPY")
    assert g2["grid"] == {} and g2["missing_vanna_inputs"] == 1
    assert g2["status"] == "unavailable"
