"""R6-1 red tests: canonical vendor display contract (B01/B02)."""

import sys

sys.path.insert(0, "backend")

SPOT = 500.0


def _contracts():
    return [
        {"strike": 500, "type": "call", "gamma": 0.05, "oi": 100, "volume": 400,
         "delta": 0.5, "multiplier": 100.0, "expiry": "2030-01-15",
         "oi_effective_date": "2030-01-01", "bid": 1.0, "ask": 1.2,
         "bid_timestamp": "2030-01-02T14:00:00+00:00",
         "ask_timestamp": "2030-01-02T14:00:00+00:00"},
        {"strike": 500, "type": "put", "gamma": 0.05, "oi": 100, "volume": 200,
         "delta": -0.5, "multiplier": 100.0, "expiry": "2030-01-15",
         "oi_effective_date": "2030-01-01", "bid": 1.0, "ask": 1.2,
         "bid_timestamp": "2030-01-02T14:00:00+00:00",
         "ask_timestamp": "2030-01-02T14:00:00+00:00"},
    ]


def test_vendor_volume_surfaces_use_supplied_gamma():
    from services.gex_core import (
        compute_gex_by_strike_volume_vendor,
        compute_gex_grid_volume_vendor,
    )
    rows = compute_gex_by_strike_volume_vendor(SPOT, _contracts())
    # u = .05*100*500^2*.01 = 12500; call 12500*400 = 5M, put 12500*200 = 2.5M
    by_strike = {r["strike"]: r for r in rows}
    assert by_strike[500.0]["call_gex"] == 5_000_000.0
    assert by_strike[500.0]["put_gex"] == 2_500_000.0
    assert by_strike[500.0]["oi_dates"] == ["2030-01-01"]
    grid = compute_gex_grid_volume_vendor(SPOT, _contracts())
    assert grid["exposure_basis"] == "VOLUME"
    assert grid["grid"]["2030-01-15"]["500"] == 2_500_000.0  # net: 5M - 2.5M


def test_canonical_reconciliation_same_scope():
    """Row sums = cell sums = registry totals over one normalized population."""
    from domain.exposure_metrics import compute_raw_oi
    from services.gex_core import (
        compute_gex_by_strike_vendor,
        compute_gex_grid_vendor,
    )
    contracts = _contracts()
    rows = compute_gex_by_strike_vendor(SPOT, contracts)
    grid = compute_gex_grid_vendor(SPOT, contracts)
    row_net = sum(r["gex"] for r in rows)
    cell_net = sum(v for col in grid["grid"].values() for v in col.values())
    reg = compute_raw_oi(contracts, SPOT)
    assert row_net == cell_net == reg.net
    assert sum(r["call_gex"] for r in rows) == reg.call


def test_replay_projection_keeps_axes_and_cells():
    import duckdb

    from services.gex_core import compute_gex_grid_vendor
    from services.heatmap_history import record_snapshot, replay_snapshot
    contracts = _contracts()
    contracts[1] = dict(contracts[1], oi=50)  # asymmetric: net cell is nonzero
    grid = compute_gex_grid_vendor(SPOT, contracts)
    payload = {"ticker": "SPY", "expiries_used": ["2030-01-15"], "spot": SPOT,
               "mode": "day", "dte": None, "scalp": False,
               "data_source": "public_api", "exposure_basis": "OI",
               "formula_version": "gex.v2",
               "asof": "2030-01-02T14:00:00+00:00", "contracts": contracts,
               "strikes": [], "grid": grid,
               "metrics": {"walls": [], "grids": {"vendor": grid}},
               "quality": {"state": "usable", "reasonCodes": [],
                           "setupEligible": True, "executionEligible": False,
                           "tradeSideCapability": "none"}}
    conn = duckdb.connect(":memory:")
    sid = record_snapshot(conn, payload, "q")
    rep = replay_snapshot(conn, sid)
    main = rep["grids"]["grid"]
    assert main["expiries"] == ["2030-01-15"] and main["strikes"] == [500]
    assert main["grid"]["2030-01-15"]["500"] != 0
    assert rep["grids"]["vendor"]["grid"]["2030-01-15"]["500"] != 0


def _model_only_contracts():
    # Greek-less fallback-provider shape: IV/T/volume/OI present, no gamma.
    return [
        {"strike": 500, "type": "call", "oi": 100, "volume": 400, "iv": 0.2,
         "T": 30 / 365, "multiplier": 100.0, "expiry": "2030-01-15"},
        {"strike": 500, "type": "put", "oi": 100, "volume": 200, "iv": 0.2,
         "T": 30 / 365, "multiplier": 100.0, "expiry": "2030-01-15"},
    ]


def test_declared_local_fallback_readability_without_eligibility():
    from services.gex_core import (
        compute_gex_by_strike_vendor,
        compute_gex_grid_vendor,
    )
    assert compute_gex_by_strike_vendor(SPOT, _model_only_contracts()) == []
    assert compute_gex_grid_vendor(SPOT, _model_only_contracts())["grid"] == {}
    # The declared fallback still renders structure (tested through the
    # assembly policy below), but never claims vendor provenance.
    from services.gex_core import compute_gex_by_strike, compute_gex_grid
    assert compute_gex_by_strike(SPOT, _model_only_contracts(), "") != []
    assert compute_gex_grid(SPOT, _model_only_contracts(), "")["grid"] != {}


def test_display_surfaces_policy_vendor_first_fallback_declared():
    from server import _display_surfaces
    basis, model, strikes, grid = _display_surfaces(SPOT, _contracts(), "SPY", False)
    assert (basis, model) == ("OI", "vendor-supplied-greeks") and strikes
    assert grid["grid"]
    basis2, model2, strikes2, grid2 = _display_surfaces(SPOT, _model_only_contracts(), "SPY", False)
    assert (basis2, model2) == ("OI", "local-bs-fallback") and strikes2
    assert grid2["grid"]
    basis3, model3, strikes3, __ = _display_surfaces(SPOT, [], "SPY", False)
    assert strikes3 == [] and model3 == "vendor-supplied-greeks"


def _volume_only_contracts():
    # yfinance fallback shape (observed ^SPX 2026-09-24): no OI, no supplied
    # gamma, IV + session volume present.
    return [
        {"strike": 500, "type": "call", "oi": 0, "volume": 400, "iv": 0.2,
         "T": 30 / 365, "multiplier": 100.0, "expiry": "2030-01-15"},
        {"strike": 500, "type": "put", "oi": 0, "volume": 200, "iv": 0.2,
         "T": 30 / 365, "multiplier": 100.0, "expiry": "2030-01-15"},
    ]


def test_display_surfaces_volume_fallback_without_vendor_gamma():
    from server import _display_surfaces
    basis, model, strikes, grid = _display_surfaces(
        SPOT, _volume_only_contracts(), "^SPX", False)
    assert basis == "VOLUME_FALLBACK_OI_UNKNOWN" and strikes
    assert grid["grid"]
    assert model == "local-bs-fallback"
