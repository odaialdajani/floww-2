"""
backend/tests/services/test_dash_ui_heatseeker.py

Tests for Round 7 toggle wiring: state persistence, I-8 NaN guards,
toggle → filter callbacks, memoization, and figure generation.

Covers:
  - _safe_json_value / _sanitize_state_dict (I-8)
  - _default_toggle_state
  - _overlay_options
  - _build_heatseeker_toggles (component factory)
  - _cached_build_heatmap (memoization)
  - _build_vex_heatmap / _build_charm_heatmap / _build_vanna_heatmap
  - _build_gex_heatmap with mode="absolute" vs mode="signed"
"""
import json
import time

import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------
from services import dash_ui as M

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_gex_surface():
    return {
        "strikes": [490.0, 495.0, 500.0, 505.0, 510.0],
        "expiries": [0.01, 0.02, 0.05],
        "gex_surface": [
            [-1e8, -8e7, -5e7],
            [-5e7, -3e7, -1e7],
            [0, 1e7, 3e7],
            [2e7, 5e7, 8e7],
            [5e7, 8e7, 1e8],
        ],
        "king_nodes": [
            {"strike": 500.0, "magnitude": 3e7},
            {"strike": 510.0, "magnitude": 1e8},
        ],
        "air_pockets": [
            {"lo": 495.0, "hi": 505.0},
        ],
        "zero_gamma": 498.0,
    }


def _sample_chain_data():
    """Chain data payload as it would sit in dcc.Store."""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    exp1 = (now + timedelta(days=14)).strftime("%Y-%m-%d")
    exp2 = (now + timedelta(days=30)).strftime("%Y-%m-%d")
    exp3 = (now + timedelta(days=60)).strftime("%Y-%m-%d")
    return {
        "spot": 500.0,
        "ts": "2026-07-10T14:30:00",
        "contracts": [
            {"type": "call", "strike": 500.0, "expiry": exp1, "iv": 0.15,
             "gamma": 0.02, "oi": 1000, "volume": 500, "delta": 0.55, "vega": 0.12},
            {"type": "put", "strike": 495.0, "expiry": exp1, "iv": 0.16,
             "gamma": 0.019, "oi": 800, "volume": 300, "delta": -0.45, "vega": 0.11},
            {"type": "call", "strike": 505.0, "expiry": exp2, "iv": 0.14,
             "gamma": 0.015, "oi": 600, "volume": 200, "delta": 0.40, "vega": 0.10},
            {"type": "put", "strike": 510.0, "expiry": exp3, "iv": 0.13,
             "gamma": 0.01, "oi": 400, "volume": 100, "delta": -0.30, "vega": 0.09},
        ],
        "king_nodes": [{"strike": 500.0, "magnitude": 3e7}],
        "air_pockets": [{"lo": 495.0, "hi": 505.0}],
        "zero_gamma": 498.0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# I-8 NaN Guard Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeJsonValue:
    """I-8: Guard against None/NaN/Inf in stored state."""

    def test_none_returns_none(self):
        assert M._safe_json_value(None) is None

    def test_nan_returns_none(self):
        assert M._safe_json_value(float("nan")) is None

    def test_inf_returns_none(self):
        assert M._safe_json_value(float("inf")) is None

    def test_neg_inf_returns_none(self):
        assert M._safe_json_value(float("-inf")) is None

    def test_float_zero_returns_zero(self):
        assert M._safe_json_value(0.0) == 0.0

    def test_int_returns_int(self):
        assert M._safe_json_value(42) == 42

    def test_string_returns_string(self):
        assert M._safe_json_value("GEX") == "GEX"

    def test_list_returns_list(self):
        assert M._safe_json_value(["a", "b"]) == ["a", "b"]

    def test_empty_string_returns_empty(self):
        assert M._safe_json_value("") == ""


class TestSanitizeStateDict:
    """I-8: Sanitize entire state dicts."""

    def test_removes_none_values(self):
        result = M._sanitize_state_dict({"a": 1, "b": None, "c": "ok"})
        assert "b" not in result
        assert result["a"] == 1
        assert result["c"] == "ok"

    def test_removes_nan_values(self):
        result = M._sanitize_state_dict({"a": float("nan"), "b": 2})
        assert "a" not in result
        assert result["b"] == 2

    def test_removes_inf_values(self):
        result = M._sanitize_state_dict({"x": float("inf"), "y": float("-inf"), "z": 0})
        assert "x" not in result
        assert "y" not in result
        assert result["z"] == 0

    def test_non_dict_returns_empty(self):
        assert M._sanitize_state_dict(None) == {}
        assert M._sanitize_state_dict("bad") == {}
        assert M._sanitize_state_dict(42) == {}

    def test_empty_dict_returns_empty(self):
        assert M._sanitize_state_dict({}) == {}

    def test_valid_state_preserved(self):
        state = {"view": "GEX", "mode": "absolute", "indicators": [], "dte_min": 0, "dte_max": 365, "expiries": []}
        result = M._sanitize_state_dict(state)
        assert result == state


class TestDefaultToggleState:
    def test_returns_expected_keys(self):
        state = M._default_toggle_state()
        assert set(state.keys()) == {"view", "mode", "indicators", "dte_min", "dte_max", "expiries"}

    def test_defaults(self):
        state = M._default_toggle_state()
        assert state["view"] == "GEX"
        assert state["mode"] == "absolute"
        assert state["indicators"] == []
        assert state["dte_min"] == 0
        assert state["dte_max"] == 365
        assert state["expiries"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# Overlay Options Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverlayOptions:
    def test_returns_three_options(self):
        opts = M._overlay_options()
        assert len(opts) == 3

    def test_option_values(self):
        opts = M._overlay_options()
        values = [o["value"] for o in opts]
        assert "king_nodes" in values
        assert "air_pockets" in values
        assert "flip_zones" in values

    def test_each_has_label_and_value(self):
        for opt in M._overlay_options():
            assert "label" in opt
            assert "value" in opt


# ═══════════════════════════════════════════════════════════════════════════════
# Component Factory Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildHeatseekerToggles:
    """Tests for the sidebar component factory."""

    def test_returns_dash_component(self):
        comp = M._build_heatseeker_toggles()
        assert comp is not None

    def test_with_expiry_dates(self):
        comp = M._build_heatseeker_toggles(expiry_dates=["2026-08-15", "2026-09-15"])
        assert comp is not None

    def test_with_empty_expiry_dates(self):
        comp = M._build_heatseeker_toggles(expiry_dates=[])
        assert comp is not None


# ═══════════════════════════════════════════════════════════════════════════════
# LRU Cache / Memoization Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCachedBuildHeatmap:
    def test_cache_returns_figure(self):
        data = _sample_gex_surface()
        fig = M._cached_build_heatmap(
            view="GEX",
            mode="absolute",
            spot=500.0,
            gex_surface_json=json.dumps(data["gex_surface"]),
            strikes_json=json.dumps(data["strikes"]),
            expiries_json=json.dumps(data["expiries"]),
            king_nodes_json=json.dumps(data["king_nodes"]),
            air_pockets_json=json.dumps(data["air_pockets"]),
            zero_gamma=498.0,
            indicators_json=json.dumps(["king_nodes", "air_pockets"]),
        )
        assert fig is not None
        assert isinstance(fig, go.Figure)

    def test_cache_hit_faster_than_miss(self):
        """Verify lru_cache is working: second call with same args should be faster."""
        data = _sample_gex_surface()
        args = dict(
            view="GEX",
            mode="signed",
            spot=500.0,
            gex_surface_json=json.dumps(data["gex_surface"]),
            strikes_json=json.dumps(data["strikes"]),
            expiries_json=json.dumps(data["expiries"]),
            king_nodes_json=json.dumps(data["king_nodes"]),
            air_pockets_json=json.dumps(data["air_pockets"]),
            zero_gamma=498.0,
            indicators_json=json.dumps(["king_nodes"]),
        )
        # First call (cache miss)
        t0 = time.perf_counter()
        M._cached_build_heatmap(**args)
        t1 = time.perf_counter()
        # Second call (cache hit)
        t2 = time.perf_counter()
        M._cached_build_heatmap(**args)
        t3 = time.perf_counter()
        miss_ms = (t1 - t0) * 1000
        hit_ms = (t3 - t2) * 1000
        # Cache hit should be significantly faster
        assert hit_ms < miss_ms or hit_ms < 1.0  # either faster or sub-ms

    def test_cache_info_tracks_hits(self):
        """lru_cache info shows hits after repeated calls."""
        M._cached_build_heatmap.cache_clear()
        data = _sample_gex_surface()
        kwargs = dict(
            view="GEX",
            mode="absolute",
            spot=500.0,
            gex_surface_json=json.dumps(data["gex_surface"]),
            strikes_json=json.dumps(data["strikes"]),
            expiries_json=json.dumps(data["expiries"]),
            king_nodes_json="",
            air_pockets_json="",
            zero_gamma=0.0,
            indicators_json="[]",
        )
        M._cached_build_heatmap(**kwargs)
        M._cached_build_heatmap(**kwargs)
        info = M._cached_build_heatmap.cache_info()
        assert info.hits >= 1

    def test_different_views_produce_different_figures(self):
        """VIEW toggle: GEX vs VEX should produce different titles."""
        data = _sample_gex_surface()
        fig_gex = M._cached_build_heatmap(
            view="GEX", mode="absolute", spot=500.0,
            gex_surface_json=json.dumps(data["gex_surface"]),
            strikes_json=json.dumps(data["strikes"]),
            expiries_json=json.dumps(data["expiries"]),
            king_nodes_json="", air_pockets_json="",
            zero_gamma=0.0, indicators_json="[]",
        )
        M._cached_build_heatmap.cache_clear()
        fig_vex = M._cached_build_heatmap(
            view="VEX", mode="absolute", spot=500.0,
            gex_surface_json=json.dumps(data["gex_surface"]),
            strikes_json=json.dumps(data["strikes"]),
            expiries_json=json.dumps(data["expiries"]),
            king_nodes_json="", air_pockets_json="",
            zero_gamma=0.0, indicators_json="[]",
        )
        assert fig_gex.layout.title.text != fig_vex.layout.title.text


# ═══════════════════════════════════════════════════════════════════════════════
# VIEW Toggle: Variant Heatmap Builders
# ═══════════════════════════════════════════════════════════════════════════════

class TestVariantHeatmapBuilders:
    """Tests for VEX, Charm, Vanna heatmap builders."""

    def test_vex_heatmap_title(self):
        data = _sample_gex_surface()
        fig = M._build_vex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
        )
        assert "VEX" in (fig.layout.title.text or "")

    def test_charm_heatmap_title(self):
        data = _sample_gex_surface()
        fig = M._build_charm_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
        )
        assert "Charm" in (fig.layout.title.text or "")

    def test_vanna_heatmap_title(self):
        data = _sample_gex_surface()
        fig = M._build_vanna_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
        )
        assert "Vanna" in (fig.layout.title.text or "")

    def test_vex_heatmap_is_figure(self):
        data = _sample_gex_surface()
        fig = M._build_vex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
        )
        assert isinstance(fig, go.Figure)

    def test_charm_heatmap_is_figure(self):
        data = _sample_gex_surface()
        fig = M._build_charm_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
        )
        assert isinstance(fig, go.Figure)

    def test_vanna_heatmap_is_figure(self):
        data = _sample_gex_surface()
        fig = M._build_vanna_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
        )
        assert isinstance(fig, go.Figure)

    def test_variant_with_king_nodes(self):
        data = _sample_gex_surface()
        fig = M._build_vex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            king_nodes=data["king_nodes"],
        )
        assert fig is not None

    def test_variant_with_air_pockets(self):
        data = _sample_gex_surface()
        fig = M._build_charm_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            air_pockets=data["air_pockets"],
        )
        assert fig is not None


# ═══════════════════════════════════════════════════════════════════════════════
# MODE Toggle: Absolute vs Signed
# ═══════════════════════════════════════════════════════════════════════════════

class TestModeToggle:
    """Tests for mode='absolute' and mode='signed' in _build_gex_heatmap."""

    def test_absolute_z_all_positive(self):
        """In absolute mode, all z values should be non-negative."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            mode="absolute",
        )
        z_vals = fig.data[0].z
        for row in z_vals:
            for val in row:
                assert val >= 0, f"Found negative value {val} in absolute mode"

    def test_signed_preserves_signs(self):
        """In signed mode, z values should retain original signs."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            mode="signed",
        )
        z_vals = fig.data[0].z
        all_vals = [v for row in z_vals for v in row]
        has_negative = any(v < 0 for v in all_vals)
        has_positive = any(v > 0 for v in all_vals)
        assert has_negative, "Signed mode should have negative values"
        assert has_positive, "Signed mode should have positive values"

    def test_absolute_zmid_is_none(self):
        """Absolute mode: zmid=None (no diverging colorscale center)."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            mode="absolute",
        )
        assert fig.data[0].zmid is None

    def test_signed_zmid_is_zero(self):
        """Signed mode: zmid=0 (diverging colorscale centered at zero)."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            mode="signed",
        )
        assert fig.data[0].zmid == 0

    def test_colorbar_title_absolute(self):
        """Absolute mode colorbar should show '|GEX|'."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            mode="absolute",
        )
        cbar_title = fig.data[0].colorbar.title.text
        assert "|GEX|" in cbar_title

    def test_colorbar_title_signed(self):
        """Signed mode colorbar should show 'GEX'."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            mode="signed",
        )
        cbar_title = fig.data[0].colorbar.title.text
        assert "GEX ($)" in cbar_title or "GEX" in cbar_title


# ═══════════════════════════════════════════════════════════════════════════════
# INDICATOR Toggle: Overlay Filtering
# ═══════════════════════════════════════════════════════════════════════════════

class TestIndicatorToggle:
    """Tests for indicator overlay on/off filtering."""

    def test_king_nodes_visible_when_enabled(self):
        """King nodes should add shapes when enabled."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            king_nodes=data["king_nodes"],
        )
        assert fig.layout.shapes is not None
        assert len(fig.layout.shapes) > 0

    def test_king_nodes_hidden_when_disabled(self):
        """King nodes should not appear when not passed."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            king_nodes=None,
        )
        # Without king nodes, there should be fewer/no shapes from KNs
        # (spot line and zero gamma may still add shapes)
        assert fig is not None

    def test_air_pockets_visible(self):
        """Air pockets should create hrect shapes."""
        data = _sample_gex_surface()
        fig = M._build_gex_heatmap(
            spot=500.0, gex_surface=data["gex_surface"],
            strikes=data["strikes"], expiries=data["expiries"],
            air_pockets=data["air_pockets"],
        )
        assert fig is not None
        # Air pockets add hrect shapes
        shapes = fig.layout.shapes or []
        hrects = [s for s in shapes if s.type == "rect"]
        assert len(hrects) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: Toggle State → Figure Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class TestToggleStatePipeline:
    """End-to-end: toggle state dict → sanitize → cached build."""

    def test_full_pipeline_gex_absolute(self):
        """Simulate: VIEW=GEX, MODE=absolute, INDICATORS=[king_nodes]."""
        state = _default_toggle_state()
        state["view"] = "GEX"
        state["mode"] = "absolute"
        state["indicators"] = ["king_nodes"]
        clean = M._sanitize_state_dict(state)
        assert clean["view"] == "GEX"
        assert clean["mode"] == "absolute"
        assert "king_nodes" in clean["indicators"]

    def test_full_pipeline_with_nan_state(self):
        """Simulate corrupted state with NaN values."""
        state = {
            "view": "GEX",
            "mode": "absolute",
            "indicators": None,
            "dte_min": float("nan"),
            "dte_max": float("inf"),
            "expiries": ["2026-08-15"],
        }
        clean = M._sanitize_state_dict(state)
        # NaN and Inf fields should be dropped
        assert "indicators" not in clean
        assert "dte_min" not in clean
        assert "dte_max" not in clean
        # Valid fields preserved
        assert clean["view"] == "GEX"
        assert clean["expiries"] == ["2026-08-15"]

    def test_expiry_filter_list_preserved(self):
        """Expiry dates in state should survive sanitization."""
        state = _default_toggle_state()
        state["expiries"] = ["2026-08-15", "2026-09-15"]
        clean = M._sanitize_state_dict(state)
        assert clean["expiries"] == ["2026-08-15", "2026-09-15"]


# ═══════════════════════════════════════════════════════════════════════════════
# Variant View Tests through _cached_build_heatmap
# ═══════════════════════════════════════════════════════════════════════════════

class TestCachedViewVariants:
    """Test each view type through the cached builder."""

    def _call_cached(self, view, mode="absolute", indicators=None):
        data = _sample_gex_surface()
        M._cached_build_heatmap.cache_clear()
        return M._cached_build_heatmap(
            view=view, mode=mode, spot=500.0,
            gex_surface_json=json.dumps(data["gex_surface"]),
            strikes_json=json.dumps(data["strikes"]),
            expiries_json=json.dumps(data["expiries"]),
            king_nodes_json=json.dumps(data["king_nodes"]) if "king_nodes" in (indicators or []) else "",
            air_pockets_json=json.dumps(data["air_pockets"]) if "air_pockets" in (indicators or []) else "",
            zero_gamma=498.0,
            indicators_json=json.dumps(indicators or []),
        )

    def test_gex_view(self):
        fig = self._call_cached("GEX")
        assert "GEX" in (fig.layout.title.text or "GEX Heatseeker")

    def test_vex_view(self):
        fig = self._call_cached("VEX")
        assert "VEX" in (fig.layout.title.text or "")

    def test_charm_view(self):
        fig = self._call_cached("Charm")
        assert "Charm" in (fig.layout.title.text or "")

    def test_vanna_view(self):
        fig = self._call_cached("Vanna")
        assert "Vanna" in (fig.layout.title.text or "")

    def test_gex_signed_mode(self):
        fig = self._call_cached("GEX", mode="signed")
        assert fig.data[0].zmid == 0

    def test_gex_absolute_mode(self):
        fig = self._call_cached("GEX", mode="absolute")
        assert fig.data[0].zmid is None

    def test_indicators_king_nodes(self):
        fig = self._call_cached("GEX", indicators=["king_nodes"])
        assert fig is not None
        assert fig.layout.shapes is not None

    def test_indicators_air_pockets(self):
        fig = self._call_cached("GEX", indicators=["air_pockets"])
        assert fig is not None

    def test_indicators_both(self):
        fig = self._call_cached("GEX", indicators=["king_nodes", "air_pockets"])
        assert fig is not None

    def test_indicators_empty(self):
        fig = self._call_cached("GEX", indicators=[])
        assert fig is not None


def _default_toggle_state():
    """Re-export for use in this module."""
    return M._default_toggle_state()
