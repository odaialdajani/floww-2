"""R11 item 1 — missing delta vs invalid delta are distinct exclusions.

A boolean, nonfinite, or out-of-range delta is an INVALID observation, not a
missing one. Both stay unavailable (never zero), but they must be counted and
surfaced separately through canonical calculations, grids, surface coverage
and wall-local rows. Valid members keep the proven four-surface values
(raw 100000 / delta-OI 50000 / volume 10000 / volume-x-|delta| 5000).
"""
from __future__ import annotations

import asyncio as _asyncio
import math
from unittest.mock import AsyncMock, patch

import pytest

import server
import services.cvserver_client as cvmod
from domain.exposure_metrics import (
    compute_delta_weighted_oi,
    compute_session_delta_volume_gamma,
    wall_metric_breakdown,
)
from services.gex_core import (
    compute_gex_grid_delta_weighted,
    compute_gex_grid_session_delta_volume,
)
from services.solstice_metric_contract import build_surface_coverage
from tests.offline_network import deny_external_network  # noqa: F401

_LOOP = _asyncio.new_event_loop()
EXP = "2031-01-17"
TICKER = "R11DX"


def _c(strike, typ, delta):
    return {"strike": float(strike), "expiry": EXP, "T": 30 / 365.0, "type": typ,
            "oi": 100.0, "volume": 10.0, "gamma": 0.1, "delta": delta,
            "iv": 0.25, "multiplier": 100, "bid": 1.0, "ask": 1.1}


@pytest.fixture
def contracts():
    return [
        _c(100, "call", 0.5),    # valid
        _c(105, "put", None),    # missing delta
        _c(110, "call", True),   # invalid: boolean is not a reading
        _c(115, "put", 1.5),     # invalid: out of range
        _c(120, "call", float("nan")),  # invalid: nonfinite
    ]


def test_canonical_delta_weighted_splits_missing_and_invalid(contracts):
    out = compute_delta_weighted_oi(contracts, 100.0)
    assert out.usable == 1
    assert out.missing_delta == 1
    assert out.invalid_delta == 3
    assert math.isclose(out.gross, 50_000.0, rel_tol=1e-9)
    assert math.isclose(out.net, 50_000.0, rel_tol=1e-9)


def test_canonical_session_delta_volume_splits_missing_and_invalid(contracts):
    out = compute_session_delta_volume_gamma(contracts, 100.0)
    assert out.usable == 1
    assert out.missing_delta == 1
    assert out.invalid_delta == 3
    assert math.isclose(out.gross, 5_000.0, rel_tol=1e-9)


def test_delta_grid_counts_and_maps_invalid_cells_separately(contracts):
    sec = compute_gex_grid_delta_weighted(100.0, contracts)
    assert sec["usable"] == 1
    assert sec["missing_delta"] == 1
    assert sec["invalid_delta"] == 3
    assert math.isclose(sec["grid"][EXP]["100"], 50_000.0, rel_tol=1e-9)
    for strike in ("105", "110", "115", "120"):
        assert strike not in sec["grid"][EXP]
    assert sec["cell_missing_delta"][EXP] == {"105": 1}
    assert sec["cell_invalid_delta"][EXP] == {"110": 1, "115": 1, "120": 1}


def test_session_delta_volume_grid_counts_invalid_separately(contracts):
    sec = compute_gex_grid_session_delta_volume(100.0, contracts)
    assert sec["usable"] == 1
    assert sec["missing_delta"] == 1
    assert sec["invalid_delta"] == 3
    assert math.isclose(sec["grid"][EXP]["100"], 5_000.0, rel_tol=1e-9)
    assert sec["cell_missing_delta"][EXP] == {"105": 1}
    assert sec["cell_invalid_delta"][EXP] == {"110": 1, "115": 1, "120": 1}


def test_wall_row_carries_distinct_delta_exclusions(contracts):
    walls = [{"wall_id": "w", "members": [100, 105, 110, 115, 120]}]
    row = wall_metric_breakdown(walls, contracts, 100.0)["w"]
    assert row["daddex_usable"] == 1
    assert row["daddex_missing"] == 1
    assert row["daddex_invalid"] == 3
    assert row["sdv_usable"] == 1
    assert row["sdv_missing_delta"] == 1
    assert row["session_delta_volume_invalid"] == 3
    assert math.isclose(row["sdv_gross"], 5_000.0, rel_tol=1e-9)


def _build(contracts):
    payload = {"ticker": TICKER, "spot": 100.0, "expiries": [EXP],
               "contracts": [dict(c) for c in contracts], "data_source": "public_api"}

    async def fake_fetch(_ticker, max_expiries=4):
        return {**payload, "contracts": [dict(c) for c in payload["contracts"]]}

    async def _no_velocity(_ticker, _nodes):
        return {"velocity_score": 0, "rolling_floor": "stable",
                "rolling_ceiling": "stable", "history": []}

    server._BUILD_HEATMAP_CACHE.clear()
    cvmod.CVSERVER_API_KEY = ""
    with patch.object(server, "fetch_spot_and_chains_merged", new=fake_fetch), \
            patch.object(server, "save_snapshot", new=AsyncMock(return_value=None)), \
            patch.object(server, "velocity_and_rolling", new=_no_velocity):
        try:
            return _LOOP.run_until_complete(
                server._build_heatmap_impl(TICKER, max_expiries=4, with_taps=False))
        finally:
            server._BUILD_HEATMAP_CACHE.clear()


def test_builder_surfaces_and_coverage_keep_invalid_distinct(contracts):
    out = _build(contracts)
    grids = out["metrics"]["grids"]
    assert math.isclose(out["grid"]["grid"][EXP]["100"], 100_000.0, rel_tol=1e-9)
    assert math.isclose(grids["delta"]["grid"][EXP]["100"], 50_000.0, rel_tol=1e-9)
    assert math.isclose(grids["activity"]["grid"][EXP]["100"], 10_000.0, rel_tol=1e-9)
    assert math.isclose(grids["session_delta_volume"]["grid"][EXP]["100"], 5_000.0, rel_tol=1e-9)
    cov = out["metrics"]["surface_coverage"]
    assert cov["delta"]["usable"] == 1
    assert cov["delta"]["missing_delta"] == 1
    assert cov["delta"]["invalid_delta"] == 3
    assert cov["delta"]["status"] == "partial"
    assert cov["session_delta_volume"]["invalid_delta"] == 3
    assert cov["session_delta_volume"]["status"] == "partial"
    # Raw never needed delta: all five members usable there.
    assert cov["raw"]["usable"] == 5
    assert cov["raw"]["status"] == "ok"


def test_coverage_summary_counts_invalid_from_section():
    cov = build_surface_coverage(
        {"grids": {"delta": {"usable": 1, "missing_delta": 1, "invalid_delta": 3,
                             "invalid_type": 0, "quarantined": 0,
                             "exposure_basis": "OI_DELTA_WEIGHTED",
                             "formula_version": "gex.v2", "status": "ok", "reason": None}}}, {})
    assert cov["delta"]["invalid_delta"] == 3
    assert cov["delta"]["missing_delta"] == 1
    assert cov["delta"]["status"] == "partial"


def _mult_contract(strike, typ, mult):
    return {"strike": float(strike), "expiry": EXP, "T": 30 / 365.0, "type": typ,
            "oi": 100.0, "volume": 10.0, "gamma": 0.1, "delta": 0.5,
            "iv": 0.25, "multiplier": mult, "bid": 1.0, "ask": 1.1}


def test_explicit_invalid_multiplier_is_not_a_missing_delta():
    """An explicitly invalid multiplier is its own exclusion, never lumped
    into missing_delta (and never silently dropped on the sdv surface)."""
    contracts = [_c(100, "call", 0.5), _mult_contract(110, "call", 0)]
    delta = compute_gex_grid_delta_weighted(100.0, contracts)
    assert delta["usable"] == 1
    assert delta["missing_delta"] == 0
    assert delta["invalid_mult"] == 1
    sdv = compute_gex_grid_session_delta_volume(100.0, contracts)
    assert sdv["usable"] == 1
    assert sdv["missing_delta"] == 0
    assert sdv["invalid_mult"] == 1
    cov = build_surface_coverage(
        {"grids": {"delta": delta, "session_delta_volume": sdv}}, {})
    assert cov["delta"]["invalid_mult"] == 1
    assert cov["delta"]["missing_delta"] == 0
    assert cov["delta"]["status"] == "partial"
    assert cov["session_delta_volume"]["invalid_mult"] == 1


def test_wall_zero_volume_member_skips_delta_evaluation():
    """A valid reported zero volume still counts volume_usable, but the
    wall-local session-delta-volume surface must match the canonical/grid
    kernels: no volume, no delta evaluation, no missing-delta exclusion."""
    walls = [{"wall_id": "w", "members": [100, 105]}]
    zero_vol = dict(_c(105, "put", None), volume=0.0)
    row = wall_metric_breakdown(walls, [_c(100, "call", 0.5), zero_vol], 100.0)["w"]
    assert row["volume_usable"] == 2
    assert row["sdv_usable"] == 1
    assert row["sdv_missing_delta"] == 0
    assert row["session_delta_volume_missing"] == 0
