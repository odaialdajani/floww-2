"""
backend/tests/services/causal/test_ate.py

Unit tests for causal/ate_estimator.py — ATE estimation.

Coverage:
    - Propensity score estimation
    - IPTW ATE estimation
    - Doubly-robust ATE estimation
    - Bootstrap confidence intervals
    - Edge cases (small samples, extreme propensity)
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


class TestPropensityScoreEstimator:
    def test_fit_predict(self):
        from services.causal.ate_estimator import PropensityScoreEstimator
        np.random.seed(42)
        n = 500
        X = np.random.randn(n, 3)
        # Treatment depends on first covariate
        prob = 1.0 / (1.0 + np.exp(-X[:, 0]))
        treatment = (np.random.random(n) < prob).astype(float)

        est = PropensityScoreEstimator()
        est.fit(X, treatment)
        scores = est.predict(X)

        assert scores.shape == (n,)
        assert np.all(scores > 0)
        assert np.all(scores < 1)
        # Scores should be correlated with treatment
        assert np.corrcoef(scores, treatment)[0, 1] > 0.3

    def test_predict_before_fit_raises(self):
        from services.causal.ate_estimator import PropensityScoreEstimator
        est = PropensityScoreEstimator()
        with pytest.raises(RuntimeError):
            est.predict(np.random.randn(10, 3))


class TestATEEstimator:
    def test_iptw_ate_known_effect(self):
        """IPTW should recover a known treatment effect."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 2000
        X = np.random.randn(n, 2)
        # Balanced treatment (propensity ~ 0.5)
        treatment = (np.random.random(n) < 0.5).astype(float)
        # Outcome with known ATE = 2.0
        outcome = X[:, 0] + 2.0 * treatment + np.random.randn(n) * 0.1
        propensity = np.full(n, 0.5)

        ate = ATEEstimator.iptw_ate(outcome, treatment, propensity)
        assert abs(ate - 2.0) < 0.5, f"ATE={ate}, expected ~2.0"

    def test_iptw_ate_zero_effect(self):
        """IPTW should return ~0 when treatment has no effect."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 1000
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = np.random.randn(n)  # No treatment effect
        propensity = np.full(n, 0.5)

        ate = ATEEstimator.iptw_ate(outcome, treatment, propensity)
        assert abs(ate) < 0.2, f"ATE={ate}, expected ~0"

    def test_doubly_robust_ate(self):
        """Doubly robust ATE should be consistent."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 2000
        X = np.random.randn(n, 3)
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = X[:, 0] + 1.5 * treatment + np.random.randn(n) * 0.1
        propensity = np.full(n, 0.5)

        ate = ATEEstimator.doubly_robust_ate(outcome, treatment, propensity, X)
        assert abs(ate - 1.5) < 0.5, f"ATE={ate}, expected ~1.5"

    def test_bootstrap_ci(self):
        """Bootstrap CI should contain the true effect."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 1000
        X = np.random.randn(n, 2)
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = 2.0 * treatment + np.random.randn(n) * 0.5
        propensity = np.full(n, 0.5)

        point, lower, upper = ATEEstimator.bootstrap_ci(
            outcome, treatment, propensity, n_bootstrap=500
        )
        # CI should contain the true effect (2.0)
        assert lower < 2.0 < upper, f"CI=[{lower}, {upper}] doesn't contain 2.0"

    def test_bootstrap_ci_width(self):
        """CI width should be reasonable."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 500
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = treatment + np.random.randn(n) * 0.5
        propensity = np.full(n, 0.5)

        point, lower, upper = ATEEstimator.bootstrap_ci(
            outcome, treatment, propensity, n_bootstrap=200
        )
        width = upper - lower
        assert width > 0, "CI width should be positive"
        assert width < 5.0, f"CI width {width} too large"

    def test_extreme_propensity_handling(self):
        """IPTW should handle extreme propensity scores gracefully."""
        from services.causal.ate_estimator import ATEEstimator
        n = 100
        treatment = np.ones(n)
        outcome = np.random.randn(n)
        # Very extreme propensity
        propensity = np.full(n, 0.99)

        # Should not raise
        ate = ATEEstimator.iptw_ate(outcome, treatment, propensity)
        assert np.isfinite(ate)

    def test_small_sample(self):
        """ATE should work with small samples."""
        from services.causal.ate_estimator import ATEEstimator
        n = 50
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = treatment + np.random.randn(n) * 0.1
        propensity = np.full(n, 0.5)

        ate = ATEEstimator.iptw_ate(outcome, treatment, propensity)
        assert np.isfinite(ate)
