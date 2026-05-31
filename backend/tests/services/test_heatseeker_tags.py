"""
backend/tests/services/test_heatseeker_tags.py

Tag rendering unit tests for Heatseeker visual overlays:
  - King Nodes: local maxima detection, top-N ranking, coordinate calculation
  - Air Pockets: zero-GEX gap detection, span thresholding, coordinate output
  - Flip Zones: sign-change detection, interpolation, coordinate output

All tests verify deterministic, NaN-safe coordinate calculations (I-8 NaN guards).
Uses hand-built fixtures so expected answers are verifiable by inspection.
"""

import math
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# backend/ is two levels up from this file
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.atlas_overlays import (
    compute_air_pockets as overlay_air_pockets,
)
from services.atlas_overlays import (
    compute_king_nodes as overlay_king_nodes,
)
from services.heatseeker import (
    _gex_per_strike,
    _king_node_strike,
    calc_air_pockets,
    calc_flip_zones,
    calc_node_lifecycle,
    detect_beach_ball,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _c(strike: float, ctype: str, gamma: float, oi: float) -> Dict[str, Any]:
    return {"strike": strike, "type": ctype, "gamma": gamma, "open_interest": oi}


def _spot(val: float) -> Dict[str, Any]:
    return {"timestamp": "2026-05-18T00:00:00Z", "spot": val}


# ===========================================================================
# KING NODE TAG TESTS
# ===========================================================================

class TestKingNodeTags:
    """Tests for King Node detection, ranking, and coordinate rendering."""

    def _make_king_candidates(self, spot: float) -> List[Dict]:
        """
        Build contracts where strike=100 has the largest |GEX|, then 105, then 95.
        All calls (positive GEX) so |GEX| ranks purely by OI magnitude.
        """
        return [
            _c(95.0, "C", 0.03, 500),   # |GEX| ~ 4.5e9
            _c(100.0, "C", 0.03, 2000),  # |GEX| ~ 1.8e10 (KING)
            _c(105.0, "C", 0.03, 1200),  # |GEX| ~ 1.08e10
        ]

    def test_king_node_is_max_abs_gex(self):
        """King Node must be the strike with the largest |net GEX|."""
        spot = 100.0
        contracts = self._make_king_candidates(spot)
        gex = _gex_per_strike(spot, contracts)
        king = _king_node_strike(gex)
        assert king == pytest.approx(100.0)

    def test_king_node_overlay_returns_top3(self):
        """compute_king_nodes must return at most 3 nodes, sorted by |magnitude| desc."""
        spot = 100.0
        contracts = self._make_king_candidates(spot)
        result = overlay_king_nodes(spot, contracts)
        assert isinstance(result, list)
        assert len(result) <= 3
        magnitudes = [n["magnitude"] for n in result]
        assert magnitudes == sorted(magnitudes, reverse=True)

    def test_king_node_coordinates_are_finite(self):
        """All King Node coordinates must be finite (no NaN/Inf)."""
        spot = 100.0
        contracts = self._make_king_candidates(spot)
        result = overlay_king_nodes(spot, contracts)
        for kn in result:
            assert math.isfinite(kn["strike"]), f"Non-finite strike: {kn['strike']}"
            assert math.isfinite(kn["magnitude"]), f"Non-finite magnitude: {kn['magnitude']}"
            assert kn["strike"] > 0

    def test_king_node_label_format(self):
        """King Node label must be 'KN <strike> (<magnitude>)'."""
        spot = 100.0
        contracts = self._make_king_candidates(spot)
        result = overlay_king_nodes(spot, contracts)
        for kn in result:
            assert "KN" in kn["label"]
            assert str(int(kn["strike"])) in kn["label"]

    def test_king_node_empty_contracts(self):
        """Empty contracts → empty king node list, no crash."""
        result = overlay_king_nodes(100.0, [])
        assert result == []

    def test_king_node_zero_spot(self):
        """Zero spot → empty king node list (division by zero guard)."""
        result = overlay_king_nodes(0.0, self._make_king_candidates(100.0))
        assert result == []

    def test_king_node_negative_spot(self):
        """Negative spot → empty king node list."""
        result = overlay_king_nodes(-50.0, self._make_king_candidates(100.0))
        assert result == []

    def test_king_node_with_puts_mixed(self):
        """
        Mix of calls and puts. The king node should still be the strike with
        the largest |net GEX| after aggregation.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "P", 0.05, 3000),   # large negative GEX
            _c(100.0, "C", 0.05, 5000),  # largest |GEX| (king)
            _c(105.0, "P", 0.05, 1000),  # smaller negative GEX
        ]
        gex = _gex_per_strike(spot, contracts)
        king = _king_node_strike(gex)
        # Strike 100 has the most OI → largest |GEX|
        assert king == pytest.approx(100.0)

    def test_king_node_single_strike(self):
        """Single strike → that strike is the king node."""
        spot = 100.0
        contracts = [_c(100.0, "C", 0.05, 1000)]
        gex = _gex_per_strike(spot, contracts)
        king = _king_node_strike(gex)
        assert king == pytest.approx(100.0)

    def test_king_node_all_zero_gamma(self):
        """All zero gamma → no GEX → no king node."""
        spot = 100.0
        contracts = [_c(100.0, "C", 0.0, 1000)]
        gex = _gex_per_strike(spot, contracts)
        king = _king_node_strike(gex)
        assert king is None

    def test_king_node_nan_guard_on_coordinates(self):
        """
        I-8 NaN guard: contracts with NaN gamma must not produce NaN coordinates.
        NaN gamma contracts should be silently skipped.
        """
        spot = 100.0
        contracts = [
            _c(100.0, "C", float("nan"), 1000),
            _c(105.0, "C", 0.05, 500),
        ]
        gex = _gex_per_strike(spot, contracts)
        # NaN gamma → float(nan or 0) → 0.0 via _gamma helper → skipped
        # Only 105.0 should have GEX
        assert 100.0 not in gex or gex.get(100.0, 0) == 0.0
        king = _king_node_strike(gex)
        if king is not None:
            assert math.isfinite(king)


# ===========================================================================
# AIR POCKET TAG TESTS
# ===========================================================================

class TestAirPocketTags:
    """Tests for Air Pocket detection, span thresholding, and coordinate output."""

    def _make_pocket_chain(self, spot: float) -> List[Dict]:
        """
        Build a chain with a clear air pocket between strikes 101-103.
        Anchors at 95-100 and 104-108 have large OI; 101-103 have tiny OI.
        """
        contracts = []
        # Heavy anchors
        for s in [95, 96, 97, 98, 99, 100, 104, 105, 106, 107, 108]:
            contracts.append(_c(float(s), "C", 0.05, 2000))
        # Thin pocket
        for s in [101, 102, 103]:
            contracts.append(_c(float(s), "C", 0.0001, 1))
        return contracts

    def test_air_pocket_detected_in_gap(self):
        """Air pocket must be detected in the thin-GEX region."""
        spot = 100.0
        contracts = self._make_pocket_chain(spot)
        result = calc_air_pockets(spot, contracts)
        pockets = result["air_pockets"]
        assert len(pockets) >= 1
        # The pocket should cover 101-103
        found = any(
            p["low"] <= 101.0 and p["high"] >= 103.0 for p in pockets
        )
        assert found, f"No pocket covering 101-103. Got: {pockets}"

    def test_air_pocket_coordinates_are_finite(self):
        """All air pocket coordinates must be finite (no NaN/Inf)."""
        spot = 100.0
        contracts = self._make_pocket_chain(spot)
        result = calc_air_pockets(spot, contracts)
        for p in result["air_pockets"]:
            assert math.isfinite(p["low"]), f"Non-finite low: {p['low']}"
            assert math.isfinite(p["high"]), f"Non-finite high: {p['high']}"
            assert math.isfinite(p["span_pct"]), f"Non-finite span_pct: {p['span_pct']}"
            assert math.isfinite(p["max_abs_gex_in_run"])
            assert p["low"] < p["high"]

    def test_air_pocket_span_pct_correct(self):
        """span_pct must equal (high - low) / spot."""
        spot = 100.0
        contracts = self._make_pocket_chain(spot)
        result = calc_air_pockets(spot, contracts)
        for p in result["air_pockets"]:
            expected = round((p["high"] - p["low"]) / spot, 6)
            assert p["span_pct"] == pytest.approx(expected, abs=1e-4)

    def test_air_pocket_overlay_output_keys(self):
        """
        Overlay air pockets must use keys 'lo' and 'hi' for the Dash UI.
        This tests the contract between atlas_overlays.py and dash_ui.py.
        """
        spot = 100.0
        contracts = self._make_pocket_chain(spot)
        result = overlay_air_pockets(spot, contracts)
        for ap in result:
            assert "lo" in ap, f"Missing 'lo' key in air pocket: {ap.keys()}"
            assert "hi" in ap, f"Missing 'hi' key in air pocket: {ap.keys()}"
            assert ap["lo"] < ap["hi"]

    def test_air_pocket_empty_contracts(self):
        """Empty contracts → empty pockets, no crash."""
        result = calc_air_pockets(100.0, [])
        assert result["air_pockets"] == []

    def test_air_pocket_zero_spot(self):
        """Zero spot → empty pockets (division by zero guard)."""
        result = calc_air_pockets(0.0, self._make_pocket_chain(100.0))
        assert result["air_pockets"] == []

    def test_air_pocket_no_gap_when_all_dense(self):
        """All strikes have equal large GEX → no pockets."""
        spot = 100.0
        contracts = [_c(95.0 + i, "C", 0.05, 1000) for i in range(11)]
        result = calc_air_pockets(spot, contracts)
        assert result["air_pockets"] == []

    def test_air_pocket_short_gap_excluded(self):
        """
        A single thin strike between two anchors has span=0 → excluded
        because it doesn't meet min_gap_pct.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "C", 0.05, 1000),
            _c(100.1, "C", 0.05, 1000),
            _c(100.15, "C", 0.0001, 1),  # single thin strike
            _c(100.2, "C", 0.05, 1000),
            _c(105.0, "C", 0.05, 1000),
        ]
        result = calc_air_pockets(spot, contracts, min_gap_pct=0.005)
        for p in result["air_pockets"]:
            assert (p["high"] - p["low"]) >= 0.5  # min_span = 100 * 0.005

    def test_air_pocket_nan_guard_on_coordinates(self):
        """
        I-8 NaN guard: NaN gamma contracts must not produce NaN coordinates.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "C", 0.05, 1000),
            _c(100.0, "C", float("nan"), 1000),
            _c(101.0, "C", 0.0001, 1),
            _c(102.0, "C", 0.0001, 1),
            _c(103.0, "C", 0.0001, 1),
            _c(105.0, "C", 0.05, 1000),
        ]
        result = calc_air_pockets(spot, contracts)
        for p in result["air_pockets"]:
            assert math.isfinite(p["low"])
            assert math.isfinite(p["high"])
            assert math.isfinite(p["span_pct"])

    def test_air_pocket_multiple_pockets(self):
        """Two separate thin regions → two pockets."""
        spot = 200.0
        contracts = [
            _c(190.0, "C", 0.05, 2000),
            _c(195.0, "C", 0.05, 2000),
            # Pocket 1: 197-198
            _c(197.0, "C", 0.0001, 1),
            _c(198.0, "C", 0.0001, 1),
            _c(199.0, "C", 0.05, 2000),
            _c(200.0, "C", 0.05, 2000),
            _c(201.0, "C", 0.05, 2000),
            # Pocket 2: 202-203
            _c(202.0, "C", 0.0001, 1),
            _c(203.0, "C", 0.0001, 1),
            _c(205.0, "C", 0.05, 2000),
            _c(210.0, "C", 0.05, 2000),
        ]
        result = calc_air_pockets(spot, contracts, min_gap_pct=0.005)
        assert len(result["air_pockets"]) >= 2


# ===========================================================================
# FLIP ZONE TAG TESTS
# ===========================================================================

class TestFlipZoneTags:
    """Tests for Flip Zone detection, interpolation, and coordinate output."""

    def _make_flip_chain(self, spot: float) -> List[Dict]:
        """
        Build a chain where cumulative GEX crosses zero between strikes 102 and 105.
        GEX per strike: 95=-100k, 98=-120k, 102=+180k, 105=+140k
        Cumulative:      -100k, -220k, -40k, +100k
        Sign flip between 102 and 105.
        """
        return [
            _c(95.0, "P", 0.02, 500),
            _c(98.0, "P", 0.03, 400),
            _c(102.0, "C", 0.03, 600),
            _c(105.0, "C", 0.02, 700),
        ]

    def test_flip_zone_detected(self):
        """A single sign change must produce exactly one flip zone."""
        spot = 100.0
        contracts = self._make_flip_chain(spot)
        result = calc_flip_zones(spot, contracts, window_pct=0.10)
        assert result["count"] == 1

    def test_flip_zone_price_between_strikes(self):
        """Flip zone price must lie between the two strikes that bracket the crossing."""
        spot = 100.0
        contracts = self._make_flip_chain(spot)
        result = calc_flip_zones(spot, contracts, window_pct=0.10)
        zone = result["flip_zones"][0]
        assert 102.0 < zone["price"] < 105.0

    def test_flip_zone_sign_direction(self):
        """from_sign must be 'negative', to_sign must be 'positive'."""
        spot = 100.0
        contracts = self._make_flip_chain(spot)
        result = calc_flip_zones(spot, contracts, window_pct=0.10)
        zone = result["flip_zones"][0]
        assert zone["from_sign"] == "negative"
        assert zone["to_sign"] == "positive"

    def test_flip_zone_coordinates_are_finite(self):
        """All flip zone coordinates must be finite (no NaN/Inf)."""
        spot = 100.0
        contracts = self._make_flip_chain(spot)
        result = calc_flip_zones(spot, contracts, window_pct=0.10)
        for z in result["flip_zones"]:
            assert math.isfinite(z["price"]), f"Non-finite price: {z['price']}"
            assert math.isfinite(z["strength"]), f"Non-finite strength: {z['strength']}"
            assert z["strength"] > 0

    def test_flip_zone_window_bounds_finite(self):
        """window_low and window_high must be finite."""
        spot = 100.0
        contracts = self._make_flip_chain(spot)
        result = calc_flip_zones(spot, contracts, window_pct=0.05)
        assert math.isfinite(result["window_low"])
        assert math.isfinite(result["window_high"])

    def test_flip_zone_empty_contracts(self):
        """Empty contracts → empty zones, no crash."""
        result = calc_flip_zones(100.0, [], window_pct=0.05)
        assert result["flip_zones"] == []
        assert result["count"] == 0

    def test_flip_zone_zero_spot(self):
        """Zero spot → empty zones (division by zero guard)."""
        result = calc_flip_zones(0.0, self._make_flip_chain(100.0))
        assert result["flip_zones"] == []
        assert result["count"] == 0

    def test_flip_zone_outside_window_excluded(self):
        """Crossing outside the ±window_pct band must be excluded."""
        spot = 100.0
        contracts = [
            _c(50.0, "P", 0.05, 1000),
            _c(55.0, "C", 0.05, 2000),
        ]
        result = calc_flip_zones(spot, contracts, window_pct=0.02)
        assert result["count"] == 0

    def test_flip_zone_nan_guard_on_coordinates(self):
        """
        I-8 NaN guard: NaN gamma contracts must not produce NaN coordinates.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "P", float("nan"), 500),
            _c(98.0, "P", 0.03, 400),
            _c(102.0, "C", 0.03, 600),
            _c(105.0, "C", 0.02, 700),
        ]
        result = calc_flip_zones(spot, contracts, window_pct=0.10)
        for z in result["flip_zones"]:
            assert math.isfinite(z["price"])
            assert math.isfinite(z["strength"])

    def test_flip_zone_multiple_crossings_ordered(self):
        """Multiple flip zones must be returned in strike-ascending order."""
        spot = 100.0
        contracts = [
            _c(97.0, "P", 0.05, 200),
            _c(99.0, "C", 0.05, 500),
            _c(101.0, "P", 0.05, 600),
            _c(103.0, "C", 0.05, 800),
        ]
        result = calc_flip_zones(spot, contracts, window_pct=0.05)
        prices = [z["price"] for z in result["flip_zones"]]
        assert prices == sorted(prices)

    def test_flip_zone_strength_is_positive(self):
        """Strength must always be positive (it's the magnitude of the cumulative change)."""
        spot = 100.0
        contracts = self._make_flip_chain(spot)
        result = calc_flip_zones(spot, contracts, window_pct=0.10)
        for z in result["flip_zones"]:
            assert z["strength"] > 0


# ===========================================================================
# INTEGRATION: Tag rendering pipeline (end-to-end within the service layer)
# ===========================================================================

class TestTagRenderingPipeline:
    """
    Integration tests that verify the full tag rendering pipeline:
    contracts → GEX aggregation → tag detection → coordinate output.
    """

    def _make_realistic_chain(self, spot: float) -> List[Dict]:
        """Build a realistic options chain with known structure."""
        contracts = []
        # Dense strikes from spot-15 to spot+15
        for i in range(-15, 16):
            strike = spot + i
            if i < 0:
                # Puts below spot
                contracts.append(_c(strike, "P", 0.04, 800 + abs(i) * 50))
            elif i == 0:
                # ATM call — largest OI
                contracts.append(_c(strike, "C", 0.05, 5000))
            else:
                # Calls above spot
                contracts.append(_c(strike, "C", 0.04, 800 + i * 50))
        return contracts

    def test_all_tag_types_produce_finite_coordinates(self):
        """All tag types must produce finite coordinates for a realistic chain."""
        spot = 5000.0
        contracts = self._make_realistic_chain(spot)

        # King nodes
        king_result = overlay_king_nodes(spot, contracts)
        for kn in king_result:
            assert math.isfinite(kn["strike"])
            assert math.isfinite(kn["magnitude"])

        # Flip zones
        flip_result = calc_flip_zones(spot, contracts, window_pct=0.05)
        for z in flip_result["flip_zones"]:
            assert math.isfinite(z["price"])
            assert math.isfinite(z["strength"])

        # Air pockets
        pocket_result = calc_air_pockets(spot, contracts)
        for p in pocket_result["air_pockets"]:
            assert math.isfinite(p["low"])
            assert math.isfinite(p["high"])
            assert math.isfinite(p["span_pct"])

    def test_tag_rendering_deterministic(self):
        """Same input must produce same output (deterministic rendering)."""
        spot = 100.0
        contracts = self._make_realistic_chain(spot)

        result1 = calc_flip_zones(spot, contracts, window_pct=0.05)
        result2 = calc_flip_zones(spot, contracts, window_pct=0.05)
        assert result1 == result2

        result3 = calc_air_pockets(spot, contracts)
        result4 = calc_air_pockets(spot, contracts)
        assert result3 == result4

    def test_node_lifecycle_nan_guard(self):
        """
        I-8 NaN guard: node lifecycle with NaN spot in history must not crash
        and must not produce NaN coordinates.
        """
        spot = 100.0
        contracts = [_c(100.0, "C", 0.05, 1000)]
        history = [
            {"timestamp": "2026-05-18T00:00:00Z", "spot": float("nan")},
            {"timestamp": "2026-05-18T01:00:00Z", "spot": 100.05},
        ]
        result = calc_node_lifecycle(spot, contracts, history)
        for node in result["nodes"]:
            assert math.isfinite(node["strike"])
            assert math.isfinite(node["net_gex"])

    def test_beach_ball_nan_guard(self):
        """
        I-8 NaN guard: beach ball with NaN spot must return inactive without crash.
        """
        result = detect_beach_ball(float("nan"), [])
        assert result["active"] is False

    def test_gex_per_strike_nan_gamma_skipped(self):
        """NaN gamma contracts must be silently skipped in GEX aggregation."""
        spot = 100.0
        contracts = [
            _c(100.0, "C", float("nan"), 1000),
            _c(105.0, "C", 0.05, 500),
        ]
        gex = _gex_per_strike(spot, contracts)
        # NaN gamma → _gamma returns 0.0 → skipped (gamma <= 0 check)
        assert 100.0 not in gex or gex[100.0] == 0.0
        assert 105.0 in gex

    def test_gex_per_strike_inf_handling(self):
        """Inf gamma contracts must not produce Inf GEX values."""
        spot = 100.0
        contracts = [
            _c(100.0, "C", float("inf"), 1000),
            _c(105.0, "C", 0.05, 500),
        ]
        gex = _gex_per_strike(spot, contracts)
        for k, v in gex.items():
            assert math.isfinite(v), f"Non-finite GEX at strike {k}: {v}"
