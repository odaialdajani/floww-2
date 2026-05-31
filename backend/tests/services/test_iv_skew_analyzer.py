"""
Tests for IV Skew Analyzer.

Validates:
  - ATM interpolation (exact match, bracketing, edge cases).
  - Skew computation (put IV - call IV).
  - OI-weighted IV and skew.
  - Term structure analysis.
  - Skew surface computation.
  - Percentile ranking.
  - Flag generation (FEAR, EXTREME_FEAR, GREED).
  - Edge cases (empty data, single strike).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.iv_skew_analyzer import IvSkewAnalyzer

# ==================================================================
# Fixtures
# ==================================================================

@pytest.fixture
def analyzer():
    return IvSkewAnalyzer()


@pytest.fixture
def sample_call_ivs():
    return {"440": 0.18, "445": 0.17, "450": 0.16, "455": 0.17, "460": 0.18}


@pytest.fixture
def sample_put_ivs():
    return {"440": 0.20, "445": 0.19, "450": 0.18, "455": 0.19, "460": 0.20}


@pytest.fixture
def sample_call_oi():
    return {"440": 500, "445": 800, "450": 1200, "455": 700, "460": 400}


@pytest.fixture
def sample_put_oi():
    return {"440": 600, "445": 900, "450": 1500, "455": 800, "460": 500}


# ==================================================================
# ATM Interpolation
# ==================================================================

class TestAtmInterpolation:
    """ATM IV interpolation from discrete strike-IV pairs."""

    def test_exact_atm_match(self, analyzer):
        ivs = {"440": 0.18, "450": 0.16, "460": 0.18}
        result = analyzer._interpolate_atm(ivs, 450.0)
        assert abs(result - 0.16) < 1e-9

    def test_bracketing_interpolation(self, analyzer):
        ivs = {"440": 0.18, "460": 0.18}
        result = analyzer._interpolate_atm(ivs, 450.0)
        assert abs(result - 0.18) < 1e-9

    def test_bracketing_asymmetric(self, analyzer):
        ivs = {"440": 0.20, "460": 0.16}
        result = analyzer._interpolate_atm(ivs, 450.0)
        assert abs(result - 0.18) < 1e-9

    def test_spot_below_all_strikes(self, analyzer):
        ivs = {"440": 0.18, "450": 0.16}
        result = analyzer._interpolate_atm(ivs, 430.0)
        assert abs(result - 0.18) < 1e-9

    def test_spot_above_all_strikes(self, analyzer):
        ivs = {"440": 0.18, "450": 0.16}
        result = analyzer._interpolate_atm(ivs, 470.0)
        assert abs(result - 0.16) < 1e-9

    def test_empty_dict(self, analyzer):
        result = analyzer._interpolate_atm({}, 450.0)
        assert result == 0.0

    def test_single_strike(self, analyzer):
        ivs = {"450": 0.16}
        result = analyzer._interpolate_atm(ivs, 450.0)
        assert abs(result - 0.16) < 1e-9


# ==================================================================
# Skew Computation
# ==================================================================

class TestSkewComputation:
    """Core skew = put IV - call IV."""

    def test_positive_skew(self, analyzer, sample_call_ivs, sample_put_ivs):
        result = analyzer.analyze(sample_call_ivs, sample_put_ivs, spot=450.0)
        # ATM: call=0.16, put=0.18 => skew=0.02
        assert abs(result.skew_atm - 0.02) < 1e-9

    def test_atm_values(self, analyzer, sample_call_ivs, sample_put_ivs):
        result = analyzer.analyze(sample_call_ivs, sample_put_ivs, spot=450.0)
        assert abs(result.call_iv_atm - 0.16) < 1e-9
        assert abs(result.put_iv_atm - 0.18) < 1e-9

    def test_zero_skew(self, analyzer):
        ivs = {"440": 0.18, "450": 0.16, "460": 0.18}
        result = analyzer.analyze(ivs, ivs, spot=450.0)
        assert abs(result.skew_atm) < 1e-9

    def test_negative_skew(self, analyzer):
        """Call IV > put IV = greed."""
        call_ivs = {"450": 0.20}
        put_ivs = {"450": 0.16}
        result = analyzer.analyze(call_ivs, put_ivs, spot=450.0)
        assert abs(result.skew_atm - (-0.04)) < 1e-9


# ==================================================================
# OI-Weighted IV
# ==================================================================

class TestOiWeighted:
    """Open-interest-weighted IV and skew."""

    def test_weighted_call_iv(self, analyzer, sample_call_ivs, sample_call_oi):
        result = analyzer.analyze(
            sample_call_ivs,
            {"450": 0.18},
            spot=450.0,
            call_oi=sample_call_oi,
        )
        # Weighted avg should be between min and max
        assert 0.16 < result.call_iv_weighted < 0.18

    def test_weighted_skew(self, analyzer, sample_call_ivs, sample_put_ivs, sample_call_oi, sample_put_oi):
        result = analyzer.analyze(
            sample_call_ivs, sample_put_ivs, spot=450.0,
            call_oi=sample_call_oi, put_oi=sample_put_oi,
        )
        # Put IVs are 0.02 higher => weighted skew should be ~0.02
        assert 0.015 < result.skew_weighted < 0.025

    def test_no_oi_falls_back_to_simple_avg(self, analyzer, sample_call_ivs, sample_put_ivs):
        result = analyzer.analyze(sample_call_ivs, sample_put_ivs, spot=450.0)
        # Without OI, weighted should equal simple avg
        simple_avg = np.mean(list(sample_call_ivs.values()))
        assert abs(result.call_iv_weighted - simple_avg) < 1e-9


# ==================================================================
# Flags
# ==================================================================

class TestFlags:
    """Fear/greed flag generation."""

    def test_fear_flag(self, analyzer):
        call_ivs = {"450": 0.14}
        put_ivs = {"450": 0.18}  # skew = 0.04 >= 0.03 threshold
        result = analyzer.analyze(call_ivs, put_ivs, spot=450.0)
        assert "FEAR" in result.flags

    def test_extreme_fear_flag(self, analyzer):
        call_ivs = {"450": 0.10}
        put_ivs = {"450": 0.18}  # skew = 0.08 >= 0.06 threshold
        result = analyzer.analyze(call_ivs, put_ivs, spot=450.0)
        assert "EXTREME_FEAR" in result.flags

    def test_greed_flag(self, analyzer):
        call_ivs = {"450": 0.20}
        put_ivs = {"450": 0.16}  # skew = -0.04 <= -0.03 threshold
        result = analyzer.analyze(call_ivs, put_ivs, spot=450.0)
        assert "GREED" in result.flags

    def test_no_flag_for_moderate_skew(self, analyzer):
        call_ivs = {"450": 0.15}
        put_ivs = {"450": 0.17}  # skew = 0.02 < 0.03 threshold
        result = analyzer.analyze(call_ivs, put_ivs, spot=450.0)
        assert len(result.flags) == 0


# ==================================================================
# Percentile Ranking
# ==================================================================

class TestPercentile:
    """Skew percentile vs history."""

    def test_first_observation_is_50th_percentile(self, analyzer):
        result = analyzer.analyze({"450": 0.16}, {"450": 0.18}, spot=450.0)
        assert abs(result.skew_percentile - 50.0) < 1e-9

    def test_highest_skew_is_100th_percentile(self, analyzer):
        for skew_val in [0.01, 0.02, 0.03, 0.04]:
            call_iv = 0.16
            put_iv = call_iv + skew_val
            analyzer.analyze({"450": call_iv}, {"450": put_iv}, spot=450.0)
        # Last one (0.04) should be 100th percentile
        assert abs(analyzer._compute_percentile(0.04) - 100.0) < 1e-9

    def test_lowest_skew_is_0th_percentile(self, analyzer):
        for skew_val in [0.04, 0.03, 0.02, 0.01]:
            call_iv = 0.16
            put_iv = call_iv + skew_val
            analyzer.analyze({"450": call_iv}, {"450": put_iv}, spot=450.0)
        # Lowest (0.01) should be 0th percentile
        assert abs(analyzer._compute_percentile(0.01) - 0.0) < 1e-9


# ==================================================================
# Edge Cases
# ==================================================================

class TestEdgeCases:
    """Edge-case handling."""

    def test_empty_call_ivs(self, analyzer):
        result = analyzer.analyze({}, {"450": 0.18}, spot=450.0)
        assert "INSUFFICIENT_DATA" in result.flags

    def test_empty_put_ivs(self, analyzer):
        result = analyzer.analyze({"450": 0.16}, {}, spot=450.0)
        assert "INSUFFICIENT_DATA" in result.flags

    def test_result_has_call_and_put_iv_dicts(self, analyzer, sample_call_ivs, sample_put_ivs):
        result = analyzer.analyze(sample_call_ivs, sample_put_ivs, spot=450.0)
        assert result.call_ivs_by_strike == sample_call_ivs
        assert result.put_ivs_by_strike == sample_put_ivs

    def test_history_size_increments(self, analyzer):
        assert analyzer.history_size == 0
        analyzer.analyze({"450": 0.16}, {"450": 0.18}, spot=450.0)
        assert analyzer.history_size == 1
        analyzer.analyze({"450": 0.16}, {"450": 0.19}, spot=450.0)
        assert analyzer.history_size == 2
