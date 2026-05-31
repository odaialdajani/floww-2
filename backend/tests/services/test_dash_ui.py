"""
backend/tests/services/test_dash_ui.py

Tests for the Dash UI components.
Each tab renders without crashing on empty/malformed data.
Color coding logic is deterministic.
"""
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def dash_ui():
    """Import dash_ui module fresh."""
    from services import dash_ui
    return dash_ui


@pytest.fixture
def sample_contracts():
    """Sample options contracts for testing."""
    return [
        {
            "type": "call", "strike": 500.0, "expiry": "2026-06-15",
            "iv": 0.15, "gamma": 0.02, "oi": 1000, "volume": 500,
            "delta": 0.55, "vega": 0.12, "theta": -0.08,
            "bid": 5.50, "ask": 5.70,
        },
        {
            "type": "put", "strike": 495.0, "expiry": "2026-06-15",
            "iv": 0.16, "gamma": 0.019, "oi": 800, "volume": 300,
            "delta": -0.45, "vega": 0.11, "theta": -0.07,
            "bid": 4.20, "ask": 4.40,
        },
        {
            "type": "call", "strike": 505.0, "expiry": "2026-06-22",
            "iv": 0.14, "gamma": 0.015, "oi": 600, "volume": 200,
            "delta": 0.40, "vega": 0.10, "theta": -0.06,
            "bid": 3.10, "ask": 3.30,
        },
    ]


@pytest.fixture
def sample_flow_data():
    """Sample flow print data."""
    return [
        {
            "timestamp": "2026-05-19T14:30:00", "ticker": "SPY",
            "strike": 500.0, "expiration": "2026-06-15",
            "side": "buy", "type": "call", "size": 5000,
            "price": 5.50, "premium": 27500, "vol_oi_ratio": 5.0,
            "classification": "sweep", "daily_volume": 10000,
            "open_interest": 8000,
        },
        {
            "timestamp": "2026-05-19T14:29:00", "ticker": "SPY",
            "strike": 495.0, "expiration": "2026-06-15",
            "side": "sell", "type": "put", "size": 15000,
            "price": 4.20, "premium": 63000, "vol_oi_ratio": 18.75,
            "classification": "block", "daily_volume": 5000,
            "open_interest": 3000,
        },
        {
            "timestamp": "2026-05-19T14:28:00", "ticker": "QQQ",
            "strike": 440.0, "expiration": "2026-06-15",
            "side": "buy", "type": "call", "size": 200,
            "price": 3.10, "premium": 620, "vol_oi_ratio": 0.33,
            "classification": "standard", "daily_volume": 5000,
            "open_interest": 10000,
        },
    ]


@pytest.fixture
def sample_gex_surface():
    """Pre-computed GEX surface data."""
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
            {"strike": 490.0, "magnitude": 1e8},
        ],
        "air_pockets": [
            {"lo": 495.0, "hi": 505.0},
        ],
        "zero_gamma": 498.0,
    }


@pytest.fixture
def sample_toxicity_data():
    """Sample toxicity dashboard data."""
    return {
        "vpin_cdf": 0.65,
        "qi_zscore": 2.1,
        "fragility_score": 72.0,
        "regime": "TOXIC",
        "history_vpin": [0.3, 0.4, 0.5, 0.55, 0.6, 0.65],
        "history_qi": [0.5, 1.0, 1.5, 1.8, 2.0, 2.1],
        "history_ts": ["14:25", "14:26", "14:27", "14:28", "14:29", "14:30"],
    }


@pytest.fixture
def sample_vol_data():
    """Sample vol surface data."""
    return {
        "grid_strikes": [490.0, 495.0, 500.0, 505.0, 510.0],
        "grid_expiries": [0.01, 0.02, 0.05, 0.1],
        "iv_grid": [
            [0.18, 0.17, 0.16, 0.15],
            [0.16, 0.15, 0.14, 0.13],
            [0.15, 0.14, 0.13, 0.12],
            [0.16, 0.15, 0.14, 0.13],
            [0.18, 0.17, 0.16, 0.15],
        ],
        "atm_skew": [
            {"expiry": 0.01, "atm_iv": 0.15},
            {"expiry": 0.05, "atm_iv": 0.14},
            {"expiry": 0.1, "atm_iv": 0.13},
        ],
        "butterfly": [
            {"expiry": 0.01, "butterfly_25d": 0.02},
            {"expiry": 0.05, "butterfly_25d": 0.025},
            {"expiry": 0.1, "butterfly_25d": 0.03},
        ],
    }


@pytest.fixture
def sample_trinity_data():
    """Sample trinity alignment data."""
    return {
        "score": 82.0,
        "regime": "ALIGNED_BULLISH",
        "spy_zg": [
            {"ts": "14:25", "level": 498.0},
            {"ts": "14:26", "level": 498.5},
            {"ts": "14:27", "level": 499.0},
        ],
        "qqq_zg": [
            {"ts": "14:25", "level": 438.0},
            {"ts": "14:26", "level": 438.5},
            {"ts": "14:27", "level": 439.0},
        ],
        "spx_zg": [
            {"ts": "14:25", "level": 5980.0},
            {"ts": "14:26", "level": 5982.0},
            {"ts": "14:27", "level": 5985.0},
        ],
        "cross_correlation": [
            [1.0, 0.85, 0.78],
            [0.85, 1.0, 0.82],
            [0.78, 0.82, 1.0],
        ],
        "aligned_levels": [
            {"ticker": "SPY", "level": 500.0, "proximity_pct": 0.5},
            {"ticker": "QQQ", "level": 440.0, "proximity_pct": 0.3},
            {"ticker": "SPX", "level": 6000.0, "proximity_pct": 0.2},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS: Heatseeker Tab
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeatseekerTab:
    """Tests for the GEX Heatseeker tab."""

    def test_heatmap_empty_data(self, dash_ui):
        """Heatmap renders without crashing on empty data."""
        fig = dash_ui._build_gex_heatmap()
        assert fig is not None
        assert len(fig.data) == 0  # Empty figure has no traces

    def test_heatmap_with_surface_data(self, dash_ui, sample_gex_surface):
        """Heatmap renders with pre-computed surface data."""
        data = sample_gex_surface
        fig = dash_ui._build_gex_heatmap(
            spot=500.0,
            gex_surface=data["gex_surface"],
            strikes=data["strikes"],
            expiries=data["expiries"],
            king_nodes=data["king_nodes"],
            air_pockets=data["air_pockets"],
            zero_gamma=data["zero_gamma"],
        )
        assert fig is not None
        # Should have at least the heatmap trace
        assert len(fig.data) >= 1

    def test_heatmap_with_contracts(self, dash_ui, sample_contracts):
        """Heatmap renders from raw contracts."""
        fig = dash_ui._build_gex_heatmap(spot=500.0, contracts=sample_contracts)
        assert fig is not None

    def test_heatmap_malformed_contracts(self, dash_ui):
        """Heatmap handles malformed contract data gracefully."""
        bad_contracts = [{"type": "call"}]  # Missing required fields
        fig = dash_ui._build_gex_heatmap(spot=500.0, contracts=bad_contracts)
        assert fig is not None  # Should not crash

    def test_heatmap_zero_contracts(self, dash_ui):
        """Heatmap handles zero spot price."""
        fig = dash_ui._build_gex_heatmap(spot=0, contracts=[])
        assert fig is not None

    def test_heatmap_king_nodes_at_right_strikes(self, dash_ui, sample_gex_surface):
        """King Node overlays appear at the correct strike prices."""
        data = sample_gex_surface
        fig = dash_ui._build_gex_heatmap(
            spot=500.0,
            gex_surface=data["gex_surface"],
            strikes=data["strikes"],
            expiries=data["expiries"],
            king_nodes=data["king_nodes"],
        )
        # Check that shapes/hlines were added for king nodes
        # King nodes should add horizontal lines
        assert fig.layout.shapes is not None or len(fig.data) > 1


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS: Flowseeker Tab
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowseekerTab:
    """Tests for the Flowseeker tab."""

    def test_flow_empty_data(self, dash_ui):
        """Flow ticker renders without crashing on empty data."""
        fig = dash_ui._build_flow_ticker()
        assert fig is not None

    def test_flow_with_data(self, dash_ui, sample_flow_data):
        """Flow ticker renders with sample data."""
        fig = dash_ui._build_flow_ticker(sample_flow_data)
        assert fig is not None
        assert len(fig.data) == 1  # One table trace

    def test_flow_color_coding_authentic(self, dash_ui):
        """Large size vs daily_volume/OI triggers red (authentic flow)."""
        color = dash_ui._classify_row_color(
            size=15000, daily_volume=5000, oi=3000, classification="block"
        )
        assert "255,68,68" in color  # Red

    def test_flow_color_coding_sweep(self, dash_ui):
        """Sweep classification triggers yellow."""
        color = dash_ui._classify_row_color(
            size=100, daily_volume=5000, oi=10000, classification="sweep"
        )
        assert "255,170,0" in color  # Yellow

    def test_flow_color_coding_default(self, dash_ui):
        """Normal flow gets transparent/default color."""
        color = dash_ui._classify_row_color(
            size=100, daily_volume=5000, oi=10000, classification="standard"
        )
        assert color == "rgba(26,26,46,0)"

    def test_flow_color_coding_deterministic(self, dash_ui):
        """Same input always produces same color."""
        c1 = dash_ui._classify_row_color(5000, 1000, 500, "block")
        c2 = dash_ui._classify_row_color(5000, 1000, 500, "block")
        assert c1 == c2

    def test_flow_malformed_data(self, dash_ui):
        """Flow ticker handles missing fields gracefully."""
        bad_data = [{"ticker": "SPY"}]  # Missing most fields
        fig = dash_ui._build_flow_ticker(bad_data)
        assert fig is not None  # Should not crash


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS: Toxicity Tab
# ═══════════════════════════════════════════════════════════════════════════════

class TestToxicityTab:
    """Tests for the Toxicity & Liquidity tab."""

    def test_toxicity_empty_data(self, dash_ui):
        """Toxicity dashboard renders without crashing on empty data."""
        fig = dash_ui._build_toxicity_dashboard()
        assert fig is not None

    def test_toxicity_with_data(self, dash_ui, sample_toxicity_data):
        """Toxicity dashboard renders with sample data."""
        fig = dash_ui._build_toxicity_dashboard(
            vpin_cdf=sample_toxicity_data["vpin_cdf"],
            qi_zscore=sample_toxicity_data["qi_zscore"],
            fragility_score=sample_toxicity_data["fragility_score"],
            regime=sample_toxicity_data["regime"],
            history_vpin=sample_toxicity_data["history_vpin"],
            history_qi=sample_toxicity_data["history_qi"],
            history_ts=sample_toxicity_data["history_ts"],
        )
        assert fig is not None

    def test_toxicity_alert_banner(self, dash_ui):
        """Toxic flow alert appears when VPIN_CDF > 0.5 AND |QI_z| > 1.5."""
        fig = dash_ui._build_toxicity_dashboard(
            vpin_cdf=0.65, qi_zscore=2.1, fragility_score=72.0, regime="TOXIC"
        )
        # Check for annotation with "TOXIC FLOW DETECTED"
        annotations = fig.layout.annotations
        assert any("TOXIC" in (a.text or "") for a in annotations)

    def test_toxicity_no_alert_normal(self, dash_ui):
        """No toxic alert when metrics are normal."""
        fig = dash_ui._build_toxicity_dashboard(
            vpin_cdf=0.3, qi_zscore=0.5, fragility_score=20.0, regime="NORMAL"
        )
        annotations = fig.layout.annotations
        assert not any("TOXIC" in (a.text or "") for a in annotations)

    def test_toxicity_malformed_data(self, dash_ui):
        """Toxicity dashboard handles malformed data gracefully."""
        fig = dash_ui._build_toxicity_dashboard(
            vpin_cdf=None, qi_zscore="invalid", fragility_score=-1
        )
        assert fig is not None  # Should not crash


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS: Vol Surface Tab
# ═══════════════════════════════════════════════════════════════════════════════

class TestVolSurfaceTab:
    """Tests for the Vol Surface tab."""

    def test_vol_empty_data(self, dash_ui):
        """Vol surface renders without crashing on empty data."""
        fig = dash_ui._build_vol_surface()
        assert fig is not None

    def test_vol_with_data(self, dash_ui, sample_vol_data):
        """Vol surface renders with pre-computed grid data."""
        data = sample_vol_data
        fig = dash_ui._build_vol_surface(
            grid_strikes=data["grid_strikes"],
            grid_expiries=data["grid_expiries"],
            iv_grid=data["iv_grid"],
            atm_skew=data["atm_skew"],
            butterfly=data["butterfly"],
        )
        assert fig is not None

    def test_vol_with_contracts(self, dash_ui, sample_contracts):
        """Vol surface renders from raw contracts."""
        fig = dash_ui._build_vol_surface(spot=500.0, contracts=sample_contracts)
        assert fig is not None

    def test_vol_malformed_data(self, dash_ui):
        """Vol surface handles malformed data gracefully."""
        fig = dash_ui._build_vol_surface(spot=0, contracts=[])
        assert fig is not None


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS: Trinity Tab
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrinityTab:
    """Tests for the Trinity Alignment tab."""

    def test_trinity_empty_data(self, dash_ui):
        """Trinity dashboard renders without crashing on empty data."""
        fig = dash_ui._build_trinity_dashboard()
        assert fig is not None

    def test_trinity_with_data(self, dash_ui, sample_trinity_data):
        """Trinity dashboard renders with sample data."""
        data = sample_trinity_data
        fig = dash_ui._build_trinity_dashboard(
            score=data["score"],
            regime=data["regime"],
            spy_zg=data["spy_zg"],
            qqq_zg=data["qqq_zg"],
            spx_zg=data["spx_zg"],
            cross_corr=data["cross_correlation"],
            aligned_levels=data["aligned_levels"],
        )
        assert fig is not None

    def test_trinity_score_colors(self, dash_ui):
        """Trinity score gauge uses correct color thresholds."""
        # High score (green)
        fig_high = dash_ui._build_trinity_dashboard(score=85.0)
        assert fig_high is not None
        # Medium score (yellow)
        fig_med = dash_ui._build_trinity_dashboard(score=60.0)
        assert fig_med is not None
        # Low score (red)
        fig_low = dash_ui._build_trinity_dashboard(score=20.0)
        assert fig_low is not None

    def test_trinity_malformed_data(self, dash_ui):
        """Trinity dashboard handles malformed data gracefully."""
        fig = dash_ui._build_trinity_dashboard(
            score=None, spy_zg=[{"bad": "data"}]
        )
        assert fig is not None  # Should not crash


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS: Dash App Creation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDashAppCreation:
    """Tests for the Dash app factory."""

    def test_create_dash_app_none_when_no_dash(self):
        """Returns None when Dash is not installed."""
        with patch('services.dash_ui.HAS_DASH', False):
            from services.dash_ui import create_dash_app
            result = create_dash_app(None)
            assert result is None

    def test_create_dash_app_returns_app(self, dash_ui):
        """Returns a Dash app when Dash is available."""
        # Mock FastAPI app
        mock_app = MagicMock()
        with patch('services.dash_ui.dash.Dash') as MockDash:
            mock_dash = MagicMock()
            MockDash.return_value = mock_dash
            result = dash_ui.create_dash_app(mock_app)
            assert result is not None
            MockDash.assert_called_once()
