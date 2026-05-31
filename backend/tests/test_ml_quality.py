"""
tests/test_ml_quality.py

Comprehensive tests for ML quality gates.
"""
import numpy as np
import pytest

from services.ml import DegenerateModelError
from services.ml.quality import (
    assert_class_balance,
    assert_feature_variance,
    assert_holdout_untouched,
    assert_no_future_leakage,
    assert_prediction_distribution,
    assert_temporal_ordering,
    assert_train_test_temporal_split,
    run_all_gates,
)


class TestAssertClassBalance:
    """Tests for class balance quality gate."""

    def test_balanced_binary(self):
        """Balanced binary target should pass."""
        y = [0, 1, 0, 1, 0, 1, 0, 1]
        assert_class_balance(y)  # Should not raise

    def test_balanced_multiclass(self):
        """Balanced 3-class target should pass."""
        y = [0, 1, 2, 0, 1, 2, 0, 1, 2]
        assert_class_balance(y)

    def test_slightly_imbalanced(self):
        """70/30 split should pass with default 20% threshold."""
        y = [0] * 70 + [1] * 30
        assert_class_balance(y)

    def test_heavily_imbalanced(self):
        """95/5 split should fail with default 20% threshold."""
        y = [0] * 95 + [1] * 5
        with pytest.raises(DegenerateModelError, match="min_ratio"):
            assert_class_balance(y)

    def test_custom_threshold(self):
        """Should pass with lower threshold."""
        y = [0] * 95 + [1] * 5
        assert_class_balance(y, min_ratio=0.04)

    def test_single_class(self):
        """Single class should fail."""
        y = [1, 1, 1, 1]
        with pytest.raises(DegenerateModelError, match="only 1 unique class"):
            assert_class_balance(y)

    def test_empty_array(self):
        """Empty array should fail."""
        y = []
        with pytest.raises(DegenerateModelError, match="empty"):
            assert_class_balance(y)

    def test_numpy_array(self):
        """Should work with numpy arrays."""
        y = np.array([0, 1, 0, 1, 0, 1])
        assert_class_balance(y)

    def test_label_in_error(self):
        """Error message should include label."""
        y = [0] * 99 + [1]
        with pytest.raises(DegenerateModelError, match="my_target"):
            assert_class_balance(y, label="my_target")


class TestAssertFeatureVariance:
    """Tests for feature variance quality gate."""

    def test_normal_features(self):
        """Features with good variance should pass."""
        X = np.random.randn(100, 5)
        assert_feature_variance(X)

    def test_constant_feature(self):
        """Constant feature should fail."""
        X = np.ones((100, 3))
        with pytest.raises(DegenerateModelError, match="variance"):
            assert_feature_variance(X)

    def test_one_constant_among_good(self):
        """One constant feature among good ones should fail."""
        X = np.random.randn(100, 5)
        X[:, 2] = 5.0  # constant column
        with pytest.raises(DegenerateModelError):
            assert_feature_variance(X)

    def test_single_sample(self):
        """Single sample should fail."""
        X = np.array([[1.0, 2.0, 3.0]])
        with pytest.raises(DegenerateModelError, match="only 1 sample"):
            assert_feature_variance(X)

    def test_1d_array(self):
        """1D array should work."""
        X = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert_feature_variance(X)

    def test_custom_threshold(self):
        """Custom variance threshold - higher threshold catches more."""
        X = np.random.randn(100, 3)
        X[:, 0] = np.random.uniform(-0.001, 0.001, 100)  # Very low variance
        # Should fail with default threshold
        with pytest.raises(DegenerateModelError):
            assert_feature_variance(X, min_var=1e-6)
        # Should pass with very low threshold
        assert_feature_variance(X, min_var=1e-10)

    def test_feature_names_in_error(self):
        """Error should include feature names."""
        X = np.ones((10, 2))
        with pytest.raises(DegenerateModelError, match="price"):
            assert_feature_variance(X, feature_names=["price", "volume"])

    def test_zero_variance(self):
        """Zero variance should fail."""
        X = np.zeros((50, 3))
        with pytest.raises(DegenerateModelError):
            assert_feature_variance(X)


class TestAssertPredictionDistribution:
    """Tests for prediction distribution quality gate."""

    def test_normal_predictions(self):
        """Normal probability distribution should pass."""
        probas = np.random.uniform(0.3, 0.7, 100)
        assert_prediction_distribution(probas)

    def test_all_same(self):
        """All same probability should fail."""
        probas = np.full(100, 0.5)
        with pytest.raises(DegenerateModelError, match="always predicts"):
            assert_prediction_distribution(probas)

    def test_near_constant(self):
        """Near-constant predictions should fail."""
        probas = np.full(100, 0.5) + np.random.uniform(-0.001, 0.001, 100)
        with pytest.raises(DegenerateModelError):
            assert_prediction_distribution(probas)

    def test_multiclass_predictions(self):
        """2D probability array should work."""
        np.random.seed(42)
        probas = np.random.uniform(0.2, 0.8, (100, 3))
        probas = probas / probas.sum(axis=1, keepdims=True)
        assert_prediction_distribution(probas)

    def test_custom_threshold(self):
        """Custom std threshold."""
        probas = np.full(100, 0.5) + np.random.uniform(-0.01, 0.01, 100)
        assert_prediction_distribution(probas, min_std=0.001)


class TestAssertTemporalOrdering:
    """Tests for temporal ordering quality gate."""

    def test_sorted_dates(self):
        """Sorted dates should pass."""
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        assert_temporal_ordering(dates)

    def test_unsorted_dates(self):
        """Unsorted dates should fail."""
        dates = ["2024-01-03", "2024-01-01", "2024-01-02"]
        with pytest.raises(DegenerateModelError, match="not sorted"):
            assert_temporal_ordering(dates)

    def test_duplicate_dates(self):
        """Duplicate dates should fail (not strictly increasing)."""
        dates = ["2024-01-01", "2024-01-01", "2024-01-02"]
        with pytest.raises(DegenerateModelError):
            assert_temporal_ordering(dates)

    def test_single_date(self):
        """Single date should pass."""
        dates = ["2024-01-01"]
        assert_temporal_ordering(dates)

    def test_empty(self):
        """Empty list should pass."""
        assert_temporal_ordering([])


class TestAssertNoFutureLeakage:
    """Tests for future leakage detection."""

    def test_no_leakage(self):
        """Features before targets should pass."""
        feat_dates = ["2024-01-01", "2024-01-02"]
        tgt_dates = ["2024-01-03", "2024-01-04"]
        assert_no_future_leakage(feat_dates, tgt_dates)

    def test_leakage_detected(self):
        """Feature date >= target date should fail."""
        feat_dates = ["2024-01-01", "2024-01-05"]
        tgt_dates = ["2024-01-03", "2024-01-04"]
        with pytest.raises(DegenerateModelError, match="future leakage"):
            assert_no_future_leakage(feat_dates, tgt_dates)


class TestAssertHoldoutUntouched:
    """Tests for holdout set integrity."""

    def test_no_overlap(self):
        """Non-overlapping sets should pass."""
        train = np.arange(0, 80)
        val = np.arange(80, 90)
        holdout = np.arange(90, 100)
        assert_holdout_untouched(train, val, holdout)

    def test_train_overlap(self):
        """Train/holdout overlap should fail."""
        train = np.arange(0, 91)
        val = np.arange(91, 95)
        holdout = np.arange(90, 100)
        with pytest.raises(DegenerateModelError, match="overlap"):
            assert_holdout_untouched(train, val, holdout)

    def test_val_overlap(self):
        """Val/holdout overlap should fail."""
        train = np.arange(0, 80)
        val = np.arange(80, 100)
        holdout = np.arange(90, 110)
        with pytest.raises(DegenerateModelError, match="overlap"):
            assert_holdout_untouched(train, val, holdout)


class TestAssertTrainTestTemporalSplit:
    """Tests for train/test temporal split."""

    def test_proper_split(self):
        """All train before all test should pass."""
        train = ["2024-01-01", "2024-06-01"]
        test = ["2024-07-01", "2024-12-01"]
        assert_train_test_temporal_split(train, test)

    def test_overlapping_split(self):
        """Overlapping dates should fail."""
        train = ["2024-01-01", "2024-08-01"]
        test = ["2024-07-01", "2024-12-01"]
        with pytest.raises(DegenerateModelError, match="temporal split"):
            assert_train_test_temporal_split(train, test)

    def test_empty_train(self):
        """Empty train should pass."""
        assert_train_test_temporal_split([], ["2024-01-01"])


class TestRunAllGates:
    """Tests for the combined gate runner."""

    def test_all_pass(self):
        """All gates should pass with good data."""
        np.random.seed(42)
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        probas = np.random.uniform(0.3, 0.7, 100)
        # Feature dates must be before target dates (no leakage)
        feat_dates = [f"2024-01-{i:02d}" for i in range(1, 32)] + [f"2024-02-{i:02d}" for i in range(1, 70)]
        tgt_dates = [f"2024-03-{i:02d}" for i in range(1, 32)] + [f"2024-04-{i:02d}" for i in range(1, 70)]

        results = run_all_gates(
            X, y, probas,
            feature_dates=feat_dates,
            target_dates=tgt_dates,
        )
        assert "class_balance" in results
        assert "feature_variance" in results
        assert "prediction_distribution" in results

    def test_fails_on_bad_class_balance(self):
        """Should fail on imbalanced classes."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 99 + [1])
        probas = np.random.uniform(0.3, 0.7, 100)

        with pytest.raises(DegenerateModelError):
            run_all_gates(X, y, probas)
