"""
Tests for Composite Retail Flow Score.

Validates:
  - Score in [-100, +100] range.
  - CPR subscore mapping (log2-based).
  - OI subscore mapping (linear).
  - IV skew subscore mapping (inverted).
  - Composite score reflects sentiment correctly.
  - Batch computation.
  - Label assignment.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.retail_flow_score import (
    RetailFlowScore,
    compute_cpr_subscore,
    compute_iv_skew_subscore,
    compute_oi_subscore,
)


class TestCprSubscore:
    """CPR -> subscore mapping."""

    def test_cpr_1_is_neutral(self):
        assert abs(compute_cpr_subscore(1.0)) < 1e-6

    def test_cpr_above_1_is_positive(self):
        score = compute_cpr_subscore(2.0)
        assert score > 0

    def test_cpr_below_1_is_negative(self):
        score = compute_cpr_subscore(0.5)
        assert score < 0

    def test_cpr_4_is_100(self):
        assert abs(compute_cpr_subscore(4.0) - 100.0) < 1e-6

    def test_cpr_025_is_neg100(self):
        assert abs(compute_cpr_subscore(0.25) - (-100.0)) < 1e-6

    def test_cpr_clamped_at_bounds(self):
        assert compute_cpr_subscore(100.0) <= 100.0
        assert compute_cpr_subscore(0.001) >= -100.0

    def test_cpr_nan_defaults_to_neutral(self):
        score = compute_cpr_subscore(float("nan"))
        assert abs(score) < 1e-6


class TestOiSubscore:
    """OI % change -> subscore mapping."""

    def test_zero_change_is_zero(self):
        assert abs(compute_oi_subscore(0.0)) < 1e-6

    def test_positive_change_is_positive(self):
        assert compute_oi_subscore(0.10) > 0

    def test_negative_change_is_negative(self):
        assert compute_oi_subscore(-0.10) < 0

    def test_20pct_is_100(self):
        assert abs(compute_oi_subscore(0.20) - 100.0) < 1e-6

    def test_neg20pct_is_neg100(self):
        assert abs(compute_oi_subscore(-0.20) - (-100.0)) < 1e-6

    def test_clamped(self):
        assert compute_oi_subscore(1.0) <= 100.0
        assert compute_oi_subscore(-1.0) >= -100.0


class TestIvSkewSubscore:
    """IV skew -> subscore mapping."""

    def test_zero_skew_is_zero(self):
        assert abs(compute_iv_skew_subscore(0.0)) < 1e-6

    def test_positive_skew_is_negative(self):
        """Put IV > Call IV = fear = bearish."""
        assert compute_iv_skew_subscore(0.05) < 0

    def test_negative_skew_is_positive(self):
        """Call IV > Put IV = greed = bullish."""
        assert compute_iv_skew_subscore(-0.05) > 0

    def test_5pct_skew_is_neg100(self):
        assert abs(compute_iv_skew_subscore(0.05) - (-100.0)) < 1e-6

    def test_neg5pct_skew_is_pos100(self):
        assert abs(compute_iv_skew_subscore(-0.05) - 100.0) < 1e-6


class TestCompositeScore:
    """Full composite score."""

    def setup_method(self):
        self.scorer = RetailFlowScore()

    def test_neutral_inputs_give_neutral_score(self):
        result = self.scorer.compute(cpr=1.0, oi_change_pct=0.0, iv_skew=0.0)
        assert abs(result.value) < 5.0
        assert result.label == "Neutral"

    def test_extreme_bullish(self):
        result = self.scorer.compute(cpr=3.5, oi_change_pct=0.25, iv_skew=-0.04)
        assert result.value > 60
        assert result.label == "Extreme Bullish"

    def test_extreme_bearish(self):
        result = self.scorer.compute(cpr=0.3, oi_change_pct=-0.20, iv_skew=0.04)
        assert result.value < -60
        assert result.label == "Extreme Bearish"

    def test_score_in_bounds(self):
        rng = np.random.default_rng(123)
        for _ in range(100):
            cpr = float(rng.uniform(0.1, 5.0))
            oi = float(rng.uniform(-0.5, 0.5))
            skew = float(rng.uniform(-0.1, 0.1))
            result = self.scorer.compute(cpr, oi, skew)
            assert -100.0 <= result.value <= 100.0

    def test_subscores_sum_to_composite(self):
        result = self.scorer.compute(cpr=2.0, oi_change_pct=0.10, iv_skew=0.02)
        expected = (
            self.scorer.w_cpr * result.cpr_score
            + self.scorer.w_oi * result.oi_score
            + self.scorer.w_iv * result.iv_skew_score
        )
        assert abs(result.value - max(-100, min(100, expected))) < 1e-6

    def test_bullish_label(self):
        result = self.scorer.compute(cpr=2.0, oi_change_pct=0.05, iv_skew=-0.01)
        assert 30 <= result.value < 60
        assert result.label == "Bullish"

    def test_bearish_label(self):
        result = self.scorer.compute(cpr=0.4, oi_change_pct=-0.10, iv_skew=0.03)
        assert -60 < result.value <= -30
        assert result.label == "Bearish"


class TestCompositeBatch:
    """Vectorized batch computation."""

    def setup_method(self):
        self.scorer = RetailFlowScore()

    def test_batch_returns_correct_length(self):
        scores = self.scorer.compute_batch(
            cprs=np.array([1.0, 2.0, 0.5]),
            oi_changes=np.array([0.0, 0.10, -0.10]),
            iv_skews=np.array([0.0, -0.02, 0.02]),
        )
        assert len(scores) == 3

    def test_batch_values_in_bounds(self):
        rng = np.random.default_rng(99)
        scores = self.scorer.compute_batch(
            cprs=rng.uniform(0.1, 5.0, 200),
            oi_changes=rng.uniform(-0.5, 0.5, 200),
            iv_skews=rng.uniform(-0.1, 0.1, 200),
        )
        assert np.all(scores >= -100.0)
        assert np.all(scores <= 100.0)

    def test_batch_matches_single(self):
        scorer = RetailFlowScore()
        cprs = np.array([1.5, 0.7, 3.0])
        oi = np.array([0.05, -0.03, 0.15])
        skew = np.array([-0.01, 0.02, -0.03])
        batch = scorer.compute_batch(cprs, oi, skew)
        for i in range(3):
            single = scorer.compute(float(cprs[i]), float(oi[i]), float(skew[i]))
            assert abs(batch[i] - single.value) < 1e-6
