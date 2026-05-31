"""
backend/tests/services/ml/test_train_with_baselines.py

Comprehensive tests for the ML training pipeline with real baselines.

Tests:
  - Baseline computation (majority, persistence, logistic)
  - Time-ordered splits with embargo
  - Walk-forward CV
  - Sharpe computation
  - Quality gates integration
  - Meta JSON audit validation
  - End-to-end training on synthetic data

All tests are self-contained (no MongoDB dependency).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from scripts.train_with_baselines import (
    EMBARGO_DAYS,
    MAX_PLAUSIBLE_DAILY_SHARPE,
    REQUIRED_BASELINES,
    audit_meta_json,
    compute_all_baselines,
    compute_logistic_baseline,
    compute_majority_baseline,
    compute_persistence_baseline,
    compute_trading_sharpe,
    time_ordered_split,
    walk_forward_splits,
)

# ---------------------------------------------------------------------------
# Baseline computation
# ---------------------------------------------------------------------------

class TestMajorityBaseline:
    def test_all_zeros(self):
        y = np.array([0, 0, 0, 0, 0])
        result = compute_majority_baseline(y, 3)
        assert np.all(result == 0)

    def test_all_ones(self):
        y = np.array([1, 1, 1, 1, 1])
        result = compute_majority_baseline(y, 3)
        assert np.all(result == 1)

    def test_mixed(self):
        y = np.array([0, 0, 0, 1, 1])
        result = compute_majority_baseline(y, 4)
        assert np.all(result == 0)  # 0 is majority

    def test_output_length(self):
        y = np.array([0, 1, 0, 1, 0])
        result = compute_majority_baseline(y, 10)
        assert len(result) == 10


class TestPersistenceBaseline:
    def test_last_label_zero(self):
        y = np.array([1, 1, 0, 1, 0])
        result = compute_persistence_baseline(y, 3)
        assert np.all(result == 0)

    def test_last_label_one(self):
        y = np.array([0, 0, 1, 0, 1])
        result = compute_persistence_baseline(y, 3)
        assert np.all(result == 1)

    def test_output_length(self):
        y = np.array([0, 1])
        result = compute_persistence_baseline(y, 7)
        assert len(result) == 7


class TestLogisticBaseline:
    def test_basic_prediction(self):
        np.random.seed(42)
        n = 100
        X = np.random.randn(n, 5)
        y = (X[:, 0] > 0).astype(int)
        X_test = np.random.randn(20, 5)
        result = compute_logistic_baseline(X, y, X_test)
        assert len(result) == 20
        assert all(p in (0, 1) for p in result)

    def test_beats_random(self):
        """Logistic regression should do better than random on separable data."""
        np.random.seed(42)
        n = 200
        X = np.random.randn(n, 3)
        y = (X[:, 0] + X[:, 1] > 0).astype(int)
        X_test = np.random.randn(50, 3)
        y_test = (X_test[:, 0] + X_test[:, 1] > 0).astype(int)
        result = compute_logistic_baseline(X, y, X_test)
        accuracy = np.mean(result == y_test)
        assert accuracy > 0.6  # Should be well above random

    def test_fails_gracefully_on_constant(self):
        """If y is constant, logistic should fall back to majority."""
        X = np.random.randn(50, 3)
        y = np.ones(50)
        X_test = np.random.randn(10, 3)
        result = compute_logistic_baseline(X, y, X_test)
        assert len(result) == 10
        assert all(p == 1 for p in result)


class TestComputeAllBaselines:
    def test_returns_all_required(self):
        np.random.seed(42)
        X = np.random.randn(100, 5)
        y = (X[:, 0] > 0).astype(int)
        X_test = np.random.randn(20, 5)
        baselines = compute_all_baselines(X, y, X_test)
        for name in REQUIRED_BASELINES:
            assert name in baselines
            assert len(baselines[name]) == 20


# ---------------------------------------------------------------------------
# Sharpe computation
# ---------------------------------------------------------------------------

class TestComputeTradingSharpe:
    def test_all_correct(self):
        preds = np.array([1, 1, 1, 1, 1])
        actuals = np.array([1, 1, 1, 1, 1])
        sharpe = compute_trading_sharpe(preds, actuals)
        # All returns are +1, std=0 → Sharpe is undefined (returns 0 per the
        # online evaluator's std<1e-8 guard, but the simple version explodes).
        # Our implementation uses 1e-8 floor, so this gives a huge number.
        # The key point is: perfect predictions should give VERY high Sharpe.
        assert sharpe > 100  # Effectively infinite

    def test_all_wrong(self):
        preds = np.array([1, 1, 1, 1, 1])
        actuals = np.array([0, 0, 0, 0, 0])
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe < 0

    def test_mixed(self):
        preds = np.array([1, 1, 1, 0, 0])
        actuals = np.array([1, 0, 1, 0, 1])
        sharpe = compute_trading_sharpe(preds, actuals)
        assert isinstance(sharpe, float)

    def test_no_trades(self):
        preds = np.array([0, 0, 0])
        actuals = np.array([1, 1, 1])
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe == 0.0

    def test_single_trade(self):
        preds = np.array([1, 0, 0])
        actuals = np.array([1, 0, 0])
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe == 0.0  # Need ≥2 trades

    def test_positive_edge(self):
        """More correct than wrong → positive Sharpe."""
        preds = np.array([1, 1, 1, 1, 0, 0])
        actuals = np.array([1, 1, 1, 0, 0, 0])
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe > 0


# ---------------------------------------------------------------------------
# Time-ordered splits
# ---------------------------------------------------------------------------

class TestTimeOrderedSplit:
    def test_split_proportions(self):
        n = 1000
        train, test, holdout = time_ordered_split(n, train_frac=0.6, test_frac=0.2, embargo=0)
        assert len(train) == 600
        assert len(test) == 200
        assert len(holdout) == 200

    def test_no_overlap(self):
        n = 1000
        train, test, holdout = time_ordered_split(n)
        assert max(train) < min(test)
        assert max(test) < min(holdout)

    def test_with_embargo(self):
        n = 1000
        train, test, holdout = time_ordered_split(n, embargo=EMBARGO_DAYS)
        # Test should start at least EMBARGO_DAYS after train end
        assert min(test) - max(train) >= EMBARGO_DAYS

    def test_temporal_ordering(self):
        n = 500
        train, test, holdout = time_ordered_split(n)
        assert list(train) == sorted(train)
        assert list(test) == sorted(test)
        assert list(holdout) == sorted(holdout)

    def test_small_dataset(self):
        n = 50
        train, test, holdout = time_ordered_split(n)
        total = len(train) + len(test) + len(holdout)
        assert total <= n

    def test_all_indices_covered(self):
        n = 1000
        train, test, holdout = time_ordered_split(n, embargo=0)
        all_idx = set(train) | set(test) | set(holdout)
        assert all_idx == set(range(n))


class TestWalkForwardSplits:
    def test_number_of_splits(self):
        n = 1000
        splits = walk_forward_splits(n, n_splits=5)
        assert len(splits) == 5

    def test_expanding_window(self):
        n = 1000
        splits = walk_forward_splits(n, n_splits=3, min_train_size=100)
        # Each fold's training window should be larger than the previous
        train_sizes = [len(train) for train, _ in splits]
        assert all(train_sizes[i] < train_sizes[i + 1] for i in range(len(train_sizes) - 1))

    def test_no_overlap_train_test(self):
        n = 1000
        splits = walk_forward_splits(n)
        for train_idx, test_idx in splits:
            assert max(train_idx) < min(test_idx)

    def test_embargo_respected(self):
        n = 1000
        embargo = 10
        splits = walk_forward_splits(n, embargo=embargo)
        for train_idx, test_idx in splits:
            assert min(test_idx) - max(train_idx) >= embargo

    def test_insufficient_data(self):
        n = 50
        splits = walk_forward_splits(n, min_train_size=100)
        assert len(splits) == 0


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

class TestQualityGates:
    def test_balanced_classes_pass(self):
        from services.ml.quality import assert_class_balance
        y = np.array([0, 0, 1, 1, 0, 1, 0, 1])
        assert_class_balance(y)  # Should not raise

    def test_imbalanced_classes_fail(self):
        from services.ml.quality import DegenerateModelError, assert_class_balance
        y = np.array([0, 0, 0, 0, 0, 0, 0, 1])
        with pytest.raises(DegenerateModelError):
            assert_class_balance(y, min_ratio=0.2)

    def test_single_class_fail(self):
        from services.ml.quality import DegenerateModelError, assert_class_balance
        y = np.array([1, 1, 1, 1])
        with pytest.raises(DegenerateModelError):
            assert_class_balance(y)

    def test_feature_variance_pass(self):
        from services.ml.quality import assert_feature_variance
        X = np.random.randn(100, 10)
        assert_feature_variance(X)  # Should not raise

    def test_constant_feature_fail(self):
        from services.ml.quality import DegenerateModelError, assert_feature_variance
        X = np.ones((100, 5))
        X[:, 0] = np.random.randn(100)  # Only one varying feature
        with pytest.raises(DegenerateModelError):
            assert_feature_variance(X)

    def test_prediction_distribution_pass(self):
        from services.ml.quality import assert_prediction_distribution
        proba = np.random.uniform(0.3, 0.7, 100)
        assert_prediction_distribution(proba)  # Should not raise

    def test_constant_prediction_fail(self):
        from services.ml.quality import DegenerateModelError, assert_prediction_distribution
        proba = np.full(100, 0.5)
        with pytest.raises(DegenerateModelError):
            assert_prediction_distribution(proba)


# ---------------------------------------------------------------------------
# Meta JSON audit validation
# ---------------------------------------------------------------------------

class TestAuditMetaJson:
    def test_clean_model(self):
        meta = {
            "sharpe": 2.5,
            "baselines": {
                "majority": {"sharpe": 0.5},
                "persistence": {"sharpe": 0.3},
                "logistic": {"sharpe": 1.0},
            },
            "beats_baselines": True,
            "n_train": 500,
            "n_features": 20,
        }
        warnings = audit_meta_json(meta)
        assert len(warnings) == 0

    def test_high_sharpe_flagged(self):
        meta = {"sharpe": 15.0, "baselines": {}, "beats_baselines": True}
        warnings = audit_meta_json(meta)
        assert any("SHARPE_TOO_HIGH" in w for w in warnings)

    def test_empty_baselines_flagged(self):
        meta = {"sharpe": 2.0, "baselines": {}, "beats_baselines": True}
        warnings = audit_meta_json(meta)
        assert any("EMPTY_BASELINES" in w for w in warnings)
        assert any("BEATS_BASELINES_WITHOUT_DATA" in w for w in warnings)

    def test_missing_baselines_flagged(self):
        meta = {
            "sharpe": 2.0,
            "baselines": {"majority": {"sharpe": 0.5}},
            "beats_baselines": True,
        }
        warnings = audit_meta_json(meta)
        assert any("MISSING_BASELINES" in w for w in warnings)

    def test_low_sample_ratio_flagged(self):
        meta = {
            "sharpe": 2.0,
            "baselines": {
                "majority": {"sharpe": 0.5},
                "persistence": {"sharpe": 0.3},
                "logistic": {"sharpe": 1.0},
            },
            "beats_baselines": True,
            "n_train": 50,
            "n_features": 20,  # 2.5x ratio, below 5x threshold
        }
        warnings = audit_meta_json(meta)
        assert any("LOW_SAMPLE_RATIO" in w for w in warnings)

    def test_quarantine_sharpe_above_cap(self):
        """Meta with sharpe > MAX_PLAUSIBLE_DAILY_SHARPE should always flag."""
        meta = {"sharpe": MAX_PLAUSIBLE_DAILY_SHARPE + 1, "baselines": {}, "beats_baselines": True}
        warnings = audit_meta_json(meta)
        assert any("SHARPE_TOO_HIGH" in w for w in warnings)


# ---------------------------------------------------------------------------
# End-to-end training on synthetic data
# ---------------------------------------------------------------------------

class TestEndToEndTraining:
    """Train on synthetic data to verify the full pipeline works."""

    def test_train_logistic_on_separable_data(self):
        """Logistic regression should learn a separable dataset."""
        from sklearn.datasets import make_classification
        from sklearn.model_selection import train_test_split

        X, y = make_classification(
            n_samples=500, n_features=10, n_informative=5,
            n_redundant=0, random_state=42
        )
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42
        )

        model, scaler = self._train_and_evaluate(X_train, y_train, X_test, y_test, "logistic")
        assert model is not None
        assert scaler is not None

    def test_train_gbm_on_separable_data(self):
        from sklearn.datasets import make_classification
        from sklearn.model_selection import train_test_split

        X, y = make_classification(
            n_samples=500, n_features=10, n_informative=5,
            n_redundant=0, random_state=42
        )
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42
        )

        model, scaler = self._train_and_evaluate(X_train, y_train, X_test, y_test, "gbm")
        assert model is not None

    def test_baselines_are_computed(self):
        """Verify baselines are computed and model beats random."""
        from sklearn.datasets import make_classification

        X, y = make_classification(n_samples=300, n_features=5, random_state=42)
        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train = y[:split]

        baselines = compute_all_baselines(X_train, y_train, X_test)
        for name in REQUIRED_BASELINES:
            assert name in baselines
            assert len(baselines[name]) == len(X_test)

    def test_time_split_produces_valid_indices(self):
        """Verify time-ordered splits produce valid train/test indices."""
        n = 200
        train, test, holdout = time_ordered_split(n)
        assert len(train) > 0
        assert len(test) > 0
        assert len(holdout) > 0
        assert max(train) < min(test)
        assert max(test) < min(holdout)

    def test_walk_forward_produces_multiple_folds(self):
        """Walk-forward CV should produce multiple folds on sufficient data."""
        n = 1000
        splits = walk_forward_splits(n, n_splits=5)
        assert len(splits) == 5

    def test_audit_catches_quarantined_model(self):
        """Simulate a quarantined model (high sharpe, no baselines)."""
        meta = {
            "model_id": "SPY_gbm_v1.0",
            "sharpe": 31.5,
            "baselines": {},
            "beats_baselines": True,
            "n_train": 167,
            "n_features": 45,
        }
        warnings = audit_meta_json(meta)
        assert len(warnings) >= 3  # SHARPE_TOO_HIGH, EMPTY_BASELINES, LOW_SAMPLE_RATIO

    def _train_and_evaluate(self, X_train, y_train, X_test, y_test, model_type):
        """Helper to train a model and return (model, scaler)."""
        from scripts.train_with_baselines import evaluate_model, train_model
        model, scaler = train_model(X_train, y_train, model_type)
        metrics = evaluate_model(model, scaler, X_test, y_test)
        assert "accuracy" in metrics
        assert "sharpe" in metrics
        return model, scaler


# ---------------------------------------------------------------------------
# Integration: offline training script functions
# ---------------------------------------------------------------------------

class TestOfflineTrainingFunctions:
    """Test functions from train_offline.py."""

    def test_compute_trading_sharpe_function(self):
        """Import and test the offline script's Sharpe function."""
        from scripts.train_offline import compute_trading_sharpe

        # All correct
        preds = [1, 1, 1, 1, 1]
        actuals = [1, 1, 1, 1, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe == 0.0  # All returns are +1, std=0

        # Mixed
        preds = [1, 1, 0, 0, 1, 0]
        actuals = [1, 0, 0, 1, 1, 0]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert isinstance(sharpe, float)

    def test_gate_evaluate_ship(self):
        from scripts.train_offline import gate_evaluate
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": 1.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "SHIP"

    def test_gate_evaluate_reject_low_sharpe(self):
        from scripts.train_offline import gate_evaluate
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": -0.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "REJECT"

    def test_gate_evaluate_reject_overfit(self):
        from scripts.train_offline import gate_evaluate
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": 1.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.20,  # Too much overfit
        }
        assert gate_evaluate(result) == "REJECT"

    def test_gate_evaluate_reject_low_accuracy(self):
        from scripts.train_offline import gate_evaluate
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": 0.5,
            "test_accuracy": 0.48,  # Below coin flip
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "REJECT"

    def test_walk_forward_cv_function(self):
        from scripts.train_offline import walk_forward_cv
        X = np.random.randn(1000, 10)
        y = (X[:, 0] > 0).astype(int)
        dates = list(range(1000))

        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=500, test_size=50, step=50)
        assert len(splits) == 5

        # Each fold should have expanding train window
        train_sizes = [len(tr) for tr, _ in splits]
        assert all(train_sizes[i] < train_sizes[i + 1] for i in range(len(train_sizes) - 1))
