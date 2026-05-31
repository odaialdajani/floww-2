"""
backend/tests/services/test_atlas_overlays.py

Tests for atlas_overlays.py — overlay computation for the Atlas tab.
"""
import pytest

from services.atlas_overlays import (
    _compute_alignment_score,
    build_all_overlays,
    compute_air_pockets,
    compute_anomaly_markers,
    compute_king_nodes,
    compute_trinity_sparkline,
    compute_zero_gamma,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_contracts():
    """Sample options contracts."""
    return [
        {"type": "call", "strike": 500.0, "expiry": "2026-06-15",
         "iv": 0.15, "gamma": 0.02, "oi": 1000, "volume": 500},
        {"type": "put", "strike": 495.0, "expiry": "2026-06-15",
         "iv": 0.16, "gamma": 0.019, "oi": 800, "volume": 300},
        {"type": "call", "strike": 505.0, "expiry": "2026-06-22",
         "iv": 0.14, "gamma": 0.015, "oi": 600, "volume": 200},
    ]


# ── King Nodes ───────────────────────────────────────────────────────────────

class TestKingNodes:
    def test_empty_contracts(self):
        assert compute_king_nodes(500.0, []) == []

    def test_zero_spot(self):
        assert compute_king_nodes(0, [{"strike": 500}]) == []

    def test_returns_list(self, sample_contracts):
        result = compute_king_nodes(500.0, sample_contracts)
        assert isinstance(result, list)

    def test_max_three_nodes(self, sample_contracts):
        result = compute_king_nodes(500.0, sample_contracts)
        assert len(result) <= 3

    def test_nodes_have_required_keys(self, sample_contracts):
        result = compute_king_nodes(500.0, sample_contracts)
        for node in result:
            assert "strike" in node
            assert "magnitude" in node
            assert "label" in node

    def test_nodes_sorted_by_magnitude_desc(self, sample_contracts):
        result = compute_king_nodes(500.0, sample_contracts)
        if len(result) >= 2:
            assert result[0]["magnitude"] >= result[1]["magnitude"]


# ── Zero Gamma ───────────────────────────────────────────────────────────────

class TestZeroGamma:
    def test_empty_contracts(self):
        assert compute_zero_gamma(500.0, []) is None

    def test_zero_spot(self):
        assert compute_zero_gamma(0, [{"strike": 500}]) is None

    def test_returns_float_or_none(self, sample_contracts):
        result = compute_zero_gamma(500.0, sample_contracts)
        assert result is None or isinstance(result, float)


# ── Air Pockets ──────────────────────────────────────────────────────────────

class TestAirPockets:
    def test_empty_contracts(self):
        assert compute_air_pockets(500.0, []) == []

    def test_zero_spot(self):
        assert compute_air_pockets(0, [{"strike": 500}]) == []

    def test_returns_list(self, sample_contracts):
        result = compute_air_pockets(500.0, sample_contracts)
        assert isinstance(result, list)

    def test_pockets_have_required_keys(self, sample_contracts):
        result = compute_air_pockets(500.0, sample_contracts)
        for pocket in result:
            assert "lo" in pocket
            assert "hi" in pocket
            assert "label" in pocket
            assert pocket["hi"] > pocket["lo"]


# ── Anomaly Markers ──────────────────────────────────────────────────────────

class TestAnomalyMarkers:
    def test_empty_timestamps(self):
        assert compute_anomaly_markers([]) == []

    def test_empty_vpin(self):
        result = compute_anomaly_markers(["14:00", "14:01"])
        assert isinstance(result, list)

    def test_returns_list(self):
        result = compute_anomaly_markers(["14:00"], [0.5], [1.0])
        assert isinstance(result, list)

    def test_malformed_input(self):
        result = compute_anomaly_markers(["14:00"], None, None)
        assert isinstance(result, list)


# ── Trinity Sparkline ────────────────────────────────────────────────────────

class TestTrinitySparkline:
    def test_empty(self):
        result = compute_trinity_sparkline()
        assert result == {"timestamps": [], "spy_vals": [], "qqq_vals": [], "spx_vals": [], "score": 0}

    def test_with_spy_data(self):
        data = [{"ts": "14:00", "level": 498.0}, {"ts": "14:01", "level": 499.0}]
        result = compute_trinity_sparkline(spy_zg=data)
        assert result["timestamps"] == ["14:00", "14:01"]
        assert result["spy_vals"] == [498.0, 499.0]

    def test_with_all_three(self):
        spy = [{"ts": "14:00", "level": 498.0}, {"ts": "14:01", "level": 499.0}]
        qqq = [{"ts": "14:00", "level": 438.0}, {"ts": "14:01", "level": 439.0}]
        spx = [{"ts": "14:00", "level": 5980.0}, {"ts": "14:01", "level": 5985.0}]
        result = compute_trinity_sparkline(spy_zg=spy, qqq_zg=qqq, spx_zg=spx)
        assert len(result["timestamps"]) == 2
        assert result["score"] > 0


# ── Alignment Score ──────────────────────────────────────────────────────────

class TestAlignmentScore:
    def test_all_empty(self):
        assert _compute_alignment_score([], [], []) == 0.0

    def test_all_up(self):
        score = _compute_alignment_score([1, 2, 3], [10, 20, 30], [100, 200, 300])
        assert score == 85.0

    def test_mixed(self):
        score = _compute_alignment_score([1, 2, 3], [3, 2, 1], [100, 200, 300])
        assert score == 25.0

    def test_two_aligned(self):
        # SPY and QQQ up, SPX flat (direction 0) → two non-zero aligned
        score = _compute_alignment_score([1, 2, 3], [10, 20, 30], [100, 100, 100])
        assert score == 60.0


# ── Build All Overlays ───────────────────────────────────────────────────────

class TestBuildAllOverlays:
    def test_empty(self):
        result = build_all_overlays()
        assert "king_nodes" in result
        assert "zero_gamma" in result
        assert "air_pockets" in result
        assert "anomaly_markers" in result
        assert "trinity_sparkline" in result

    def test_with_data(self, sample_contracts):
        result = build_all_overlays(spot=500.0, contracts=sample_contracts)
        assert isinstance(result["king_nodes"], list)
        assert isinstance(result["air_pockets"], list)
        assert isinstance(result["anomaly_markers"], list)
        assert isinstance(result["trinity_sparkline"], dict)
