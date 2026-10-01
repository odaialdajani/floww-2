"""Hermes independent acceptance: four-surface fixture derived separately.

Spot S = 200, multiplier m = 100, gamma G = 0.05  ->  u = G*m*S^2*0.01 = 2000
  call @200:  OI 50, V 20, d +0.4  -> raw 100000, dOI 40000, vol 40000, sdv 16000
  put  @210:  OI 50, V 20, d -0.6  -> raw -100000, dOI +60000, vol -40000, sdv -24000
  call @190:  OI 0 (measured zero), V 5, d 0.5 -> raw skips zero-OI; vol/sdv count it
  put  @220:  OI 30, V 0, d None   -> raw -60000; volume-gated surfaces skip V=0
  call @230:  OI 40, V 10, d True  -> delta-INVALID everywhere (never missing)
  put  @240:  OI 40, V 10, d -0.3, mult 0 -> multiplier-invalid (generic invalid)
  call @250:  OI 100, V 50, d 0.5, adjusted -> quarantined from grids

Same contract identity/population/scope across raw, delta, activity and
session-delta-volume; never equality across different metrics.
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
    compute_raw_oi,
    compute_session_delta_volume_gamma,
    compute_volume_gamma,
    wall_metric_breakdown,
)
from services.gex_core import (
    compute_gex_grid_delta_weighted,
    compute_gex_grid_session_delta_volume,
    compute_gex_grid_vendor,
    compute_gex_grid_volume_vendor,
)
from tests.offline_network import deny_external_network  # noqa: F401

_LOOP = _asyncio.new_event_loop()
EXP = "2031-06-18"
TICKER = "HERMES"


def _c(strike, typ, oi, vol, delta, **extra):
    return {"strike": float(strike), "expiry": EXP, "T": 45 / 365.0, "type": typ,
            "oi": float(oi), "volume": float(vol), "gamma": 0.05, "delta": delta,
            "iv": 0.3, "multiplier": 100, "bid": 2.0, "ask": 2.2, **extra}


@pytest.fixture
def contracts():
    return [
        _c(200, "call", 50, 20, 0.4),
        _c(210, "put", 50, 20, -0.6),
        _c(190, "call", 0, 5, 0.5),
        _c(220, "put", 30, 0, None),
        _c(230, "call", 40, 10, True),
        _c(240, "put", 40, 10, -0.3, multiplier=0),
        _c(250, "call", 100, 50, 0.5, adjusted=True),
    ]


def test_raw_keeps_signs_and_skips_measured_zero(contracts):
    out = compute_raw_oi(contracts, 200.0)
    # 200/210/220/230 usable; 190 zero-OI skipped (not invalid); the canonical
    # fn resolves the multiplier through the shared provenance helper, so the
    # explicit-zero multiplier @240 and the adjusted @250 are generic invalid.
    assert out.usable == 4
    assert out.invalid == 2
    assert math.isclose(out.gross, 100_000 + 100_000 + 60_000 + 80_000, rel_tol=1e-9)
    assert math.isclose(out.net, 100_000 - 100_000 - 60_000 + 80_000, rel_tol=1e-9)


def test_delta_weighted_splits_invalid_from_missing(contracts):
    out = compute_delta_weighted_oi(contracts, 200.0)
    assert out.usable == 2  # 200, 210
    assert out.missing_delta == 1  # only the None delta @220
    assert out.invalid_delta == 1  # only the boolean delta @230
    assert out.invalid == 2  # explicit-zero multiplier @240 + adjusted @250
    assert math.isclose(out.gross, 40_000 + 60_000, rel_tol=1e-9)
    assert math.isclose(out.net, 40_000 - 60_000, rel_tol=1e-9)


def test_volume_legacy_has_no_delta_and_sdv_weights_it(contracts):
    vol = compute_volume_gamma(contracts, 200.0)
    assert vol.usable == 4  # 200, 210, 190(zero-OI is fine here), 230
    assert vol.invalid == 2  # bad multiplier + adjusted
    assert math.isclose(vol.gross, 40_000 + 40_000 + 10_000 + 20_000, rel_tol=1e-9)
    sdv = compute_session_delta_volume_gamma(contracts, 200.0)
    assert sdv.usable == 3  # 200, 210, 190
    assert sdv.missing_delta == 0  # @220 never reaches delta: V=0 skips first
    assert sdv.invalid_delta == 1  # @230 boolean
    assert sdv.invalid == 2
    assert math.isclose(sdv.gross, 16_000 + 24_000 + 5_000, rel_tol=1e-9)


def test_grids_quarantine_adjusted_and_map_invalid_cells(contracts):
    raw = compute_gex_grid_vendor(200.0, contracts)
    # The raw vendor kernel skips adjusted without a quarantine count
    # (retained); exclusion is proven by the absent cell, never a zero.
    assert "quarantined" not in raw
    assert math.isclose(raw["grid"][EXP]["200"], 100_000.0, rel_tol=1e-9)
    assert math.isclose(raw["grid"][EXP]["210"], -100_000.0, rel_tol=1e-9)
    assert "250" not in raw["grid"][EXP]

    delta = compute_gex_grid_delta_weighted(200.0, contracts)
    assert delta["quarantined"] == 1
    assert delta["usable"] == 2  # 200, 210
    assert delta["missing_delta"] == 1  # only @220 None
    assert delta["invalid_delta"] == 1  # @230 boolean
    assert delta["invalid_mult"] == 1  # @240 explicit-zero multiplier
    assert delta["cell_missing_delta"][EXP] == {"220": 1}
    assert delta["cell_invalid_delta"][EXP] == {"230": 1}
    assert math.isclose(delta["grid"][EXP]["200"], 40_000.0, rel_tol=1e-9)
    assert math.isclose(delta["grid"][EXP]["210"], -60_000.0, rel_tol=1e-9)
    for strike in ("220", "230", "240"):
        assert strike not in delta["grid"][EXP]

    sdv = compute_gex_grid_session_delta_volume(200.0, contracts)
    assert sdv["usable"] == 3  # 200, 210, 190 (zero OI is irrelevant here; V=5 counts)
    assert sdv["missing_delta"] == 0
    assert sdv["invalid_delta"] == 1
    assert sdv["cell_invalid_delta"][EXP] == {"230": 1}
    assert math.isclose(sdv["grid"][EXP]["200"], 16_000.0, rel_tol=1e-9)

    activity = compute_gex_grid_volume_vendor(200.0, contracts)
    assert math.isclose(activity["grid"][EXP]["200"], 40_000.0, rel_tol=1e-9)


def test_wall_row_keeps_each_family_distinct(contracts):
    walls = [{"wall_id": "h", "members": [190, 200, 210, 220, 230, 240]}]
    row = wall_metric_breakdown(walls, contracts, 200.0)["h"]
    assert row["daddex_usable"] == 2
    assert row["daddex_missing"] == 1
    assert row["daddex_invalid"] == 1
    assert row["sdv_usable"] == 3
    # Zero-volume @220 with unknown delta weights nothing and is skipped
    # silently (canonical/grid parity); it still counts volume_usable.
    assert row["sdv_missing_delta"] == 0
    assert row["session_delta_volume_missing"] == 0
    assert row["session_delta_volume_invalid"] == 2  # boolean delta + bad-mult u
    assert row["volume_usable"] == 5
    assert math.isclose(row["sdv_gross"], 16_000 + 24_000 + 5_000, rel_tol=1e-9)


def _build(contracts):
    payload = {"ticker": TICKER, "spot": 200.0, "expiries": [EXP],
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


def test_builder_grid_profile_and_inspector_agree_on_scope(contracts):
    out = _build(contracts)
    grids = out["metrics"]["grids"]
    assert out["expiries_used"] == [EXP]
    assert math.isclose(out["grid"]["grid"][EXP]["200"], 100_000.0, rel_tol=1e-9)
    assert math.isclose(grids["delta"]["grid"][EXP]["210"], -60_000.0, rel_tol=1e-9)
    assert math.isclose(grids["activity"]["grid"][EXP]["200"], 40_000.0, rel_tol=1e-9)
    assert math.isclose(grids["session_delta_volume"]["grid"][EXP]["200"], 16_000.0, rel_tol=1e-9)
    cov = out["metrics"]["surface_coverage"]
    # @220 None -> missing; @230 boolean -> invalid; @240 bad multiplier ->
    # its own invalid_mult bucket (folded into coverage invalid).
    assert cov["delta"]["missing_delta"] == 1
    assert cov["delta"]["invalid_delta"] == 1
    assert cov["delta"]["invalid_mult"] == 1
    assert cov["delta"]["status"] == "partial"
    # Raw has two genuinely excluded members (bad multiplier, adjusted), so
    # partial is correct; the measured-zero @190 is skipped silently by the
    # canonical fn (retained: zero OI is neither usable nor an exclusion).
    assert cov["raw"]["status"] == "partial"
    assert cov["raw"]["usable"] == 4
    # Same raw wall resolves on the same snapshot for the inspector.
    walls = out["metrics"]["walls"]
    assert walls, "fixture must produce at least one wall"
    rows = out["metrics"]["wall_metrics"]
    assert any(r.get("daddex_usable", 0) > 0 for r in rows.values())
