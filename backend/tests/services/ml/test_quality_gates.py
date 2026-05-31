"""
Integration tests for ML quality gates.
Verifies assert_class_balance, assert_feature_variance,
assert_prediction_distribution, and the full run_all_gates pipeline.
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
    def test_balanced_passes(self):
        y = np.array([0, 1, 0, 1, 0, 1])
        assert_class_balance(y)  # Should not raise

    def test_slightly_imbalanced_passes(self):
        y = np.array([0, 0, 0, 1, 1])  # 60/40
        assert_class_balance(y, min_ratio=0.20)

    def test_heavily_imbalanced_fails(self):
        y = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 1])
        with pytest.raises(DegenerateModelError, match="class 1"):
            assert_class_balance(y)

    def test_single_class_fails(self):
        y = np.array([1, 1, 1, 1])
        with pytest.raises(DegenerateModelError, match="only 1 unique class"):
            assert_class_balance(y)

    def test_empty_fails(self):
        y = np.array([])
        with pytest.raises(DegenerateModelError, match="empty target"):
            assert_class_balance(y)


class TestAssertFeatureVariance:
    def test_normal_passes(self):
        X = np.random.randn(100, 5)
        assert_feature_variance(X)

    def test_constant_feature_fails(self):
        X = np.random.randn(100, 3)
        X[:, 1] = 5.0  # constant
        with pytest.raises(DegenerateModelError, match="variance"):
            assert_feature_variance(X, feature_names=["a", "b", "c"])

    def test_near_zero_variance_fails(self):
        X = np.random.randn(100, 2)
        X[:, 0] = 1e-10  # near-zero variance
        with pytest.raises(DegenerateModelError):
            assert_feature_variance(X)

    def test_single_sample_fails(self):
        X = np.array([[1.0, 2.0]])
        with pytest.raises(DegenerateModelError, match="only 1 sample"):
            assert_feature_variance(X)


class TestAssertPredictionDistribution:
    def test_varied_predictions_pass(self):
        proba = np.array([0.3, 0.7, 0.4, 0.6, 0.2, 0.8])
        assert_prediction_distribution(proba)

    def test_all_same_fails(self):
        proba = np.array([0.5, 0.5, 0.5, 0.5])
        with pytest.raises(DegenerateModelError, match="degenerate"):
            assert_prediction_distribution(proba)

    def test_multiclass_passes(self):
        proba = np.array([[0.3, 0.7], [0.6, 0.4], [0.2, 0.8]])
        assert_prediction_distribution(proba)


class TestAssertTemporalOrdering:
    def test_sorted_passes(self):
        ts = ["2024-01-01", "2024-01-02", "2024-01-03"]
        assert_temporal_ordering(ts)

    def test_unsorted_fails(self):
        ts = ["2024-01-03", "2024-01-01", "2024-01-02"]
        with pytest.raises(DegenerateModelError, match="not sorted"):
            assert_temporal_ordering(ts)

    def test_single_element_passes(self):
        assert_temporal_ordering(["2024-01-01"])


class TestAssertNoFutureLeakage:
    def test_no_leakage_passes(self):
        feat_dates = ["2024-01-01", "2024-01-02"]
        tgt_dates = ["2024-01-03", "2024-01-04"]
        assert_no_future_leakage(feat_dates, tgt_dates)

    def test_leakage_fails(self):
        feat_dates = ["2024-01-01", "2024-01-05"]
        tgt_dates = ["2024-01-03", "2024-01-04"]
        with pytest.raises(DegenerateModelError, match="future leakage"):
            assert_no_future_leakage(feat_dates, tgt_dates)
