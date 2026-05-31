"""
backend/tests/services/ml/test_quality.py

Unit tests for ML quality gates. Each gate has positive (pass) and negative (fail) tests.
"""

import os
import sys

import numpy as np
import pytest

# Add backend/ to path so services.ml is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    def test_balanced_classes_pass(self):
        y = [0, 0, 0, 1, 1, 1]  # 50/50
        assert_class_balance(y, min_ratio=0.20)  # should not raise

    def test_slightly_imbalanced_pass(self):
        y = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1]  # 80/20
        assert_class_balance(y, min_ratio=0.20)  # exactly at threshold

    def test_very_imbalanced_fail(self):
        y = [0, 0, 0, 0, 0, 0, 0, 0, 0, 1]  # 90/10
        with pytest.raises(DegenerateModelError, match="class 1"):
            assert_class_balance(y, min_ratio=0.20)

    def test_single_class_fail(self):
        y = [0, 0, 0, 0, 0]
        with pytest.raises(DegenerateModelError, match="only 1 unique class"):
            assert_class_balance(y, min_ratio=0.20)

    def test_empty_fail(self):
        y = []
        with pytest.raises(DegenerateModelError, match="empty"):
            assert_class_balance(y)

    def test_multiclass_balanced(self):
        y = [0, 1, 2, 0, 1, 2, 0, 1, 2]
        assert_class_balance(y, min_ratio=0.30)

    def test_multiclass_imbalanced(self):
        y = [0, 0, 0, 0, 0, 0, 0, 1, 2]  # class 2 = 1/9 = 0.11
        with pytest.raises(DegenerateModelError):
            assert_class_balance(y, min_ratio=0.20)


class TestAssertFeatureVariance:
    def test_normal_features_pass(self):
        X = np.random.randn(100, 5)
        assert_feature_variance(X, min_var=1e-6)

    def test_constant_feature_fail(self):
        X = np.column_stack([np.random.randn(100), np.ones(100)])
        with pytest.raises(DegenerateModelError, match="feature_1"):
            assert_feature_variance(X, min_var=1e-6)

    def test_all_constant_fail(self):
        X = np.ones((50, 3))
        with pytest.raises(DegenerateModelError):
            assert_feature_variance(X, min_var=1e-6)

    def test_single_sample_fail(self):
        X = np.array([[1.0, 2.0, 3.0]])
        with pytest.raises(DegenerateModelError, match="only 1 sample"):
            assert_feature_variance(X)

    def test_with_feature_names(self):
        X = np.column_stack([np.random.randn(100), np.ones(100)])
        with pytest.raises(DegenerateModelError, match="my_feature"):
            assert_feature_variance(X, feature_names=["good_feature", "my_feature"])

    def test_1d_array(self):
        X = np.random.randn(100)
        assert_feature_variance(X)


class TestAssertPredictionDistribution:
    def test_varied_predictions_pass(self):
        proba = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        assert_prediction_distribution(proba, min_std=0.05)

    def test_constant_predictions_fail(self):
        proba = np.array([0.5, 0.5, 0.5, 0.5, 0.5])
        with pytest.raises(DegenerateModelError, match="always predicts"):
            assert_prediction_distribution(proba, min_std=0.05)

    def test_near_constant_fail(self):
        proba = np.array([0.50001, 0.50002, 0.50001, 0.50003])
        with pytest.raises(DegenerateModelError):
            assert_prediction_distribution(proba, min_std=0.05)

    def test_multiclass_proba(self):
        proba = np.array([[0.1, 0.9], [0.8, 0.2], [0.3, 0.7], [0.6, 0.4]])
        assert_prediction_distribution(proba, min_std=0.05)

    def test_multiclass_constant_fail(self):
        proba = np.array([[0.5, 0.5], [0.5, 0.5], [0.5, 0.5]])
        with pytest.raises(DegenerateModelError):
            assert_prediction_distribution(proba, min_std=0.05)


class TestAssertTemporalOrdering:
    def test_sorted_dates_pass(self):
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        assert_temporal_ordering(dates)

    def test_unsorted_dates_fail(self):
        dates = ["2024-01-03", "2024-01-01", "2024-01-02"]
        with pytest.raises(DegenerateModelError, match="not sorted"):
            assert_temporal_ordering(dates)

    def test_duplicate_dates_fail(self):
        dates = ["2024-01-01", "2024-01-01", "2024-01-02"]
        with pytest.raises(DegenerateModelError):
            assert_temporal_ordering(dates)

    def test_single_date_pass(self):
        dates = ["2024-01-01"]
        assert_temporal_ordering(dates)  # should not raise

    def test_empty_pass(self):
        dates = []
        assert_temporal_ordering(dates)  # should not raise


class TestAssertNoFutureLeakage:
    def test_no_leakage_pass(self):
        feat_dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        tgt_dates = ["2024-01-04", "2024-01-05"]
        assert_no_future_leakage(feat_dates, tgt_dates)

    def test_leakage_fail(self):
        feat_dates = ["2024-01-01", "2024-01-05"]
        tgt_dates = ["2024-01-04", "2024-01-06"]
        with pytest.raises(DegenerateModelError, match="future leakage"):
            assert_no_future_leakage(feat_dates, tgt_dates)


class TestAssertHoldoutUntouched:
    def test_no_overlap_pass(self):
        train = np.array([0, 1, 2, 3, 4])
        val = np.array([5, 6])
        holdout = np.array([7, 8, 9])
        assert_holdout_untouched(train, val, holdout)

    def test_train_overlap_fail(self):
        train = np.array([0, 1, 2, 7])  # 7 in holdout
        val = np.array([5, 6])
        holdout = np.array([7, 8, 9])
        with pytest.raises(DegenerateModelError, match="train indices"):
            assert_holdout_untouched(train, val, holdout)

    def test_val_overlap_fail(self):
        train = np.array([0, 1, 2])
        val = np.array([5, 8])  # 8 in holdout
        holdout = np.array([7, 8, 9])
        with pytest.raises(DegenerateModelError, match="val indices"):
            assert_holdout_untouched(train, val, holdout)


class TestAssertTrainTestTemporalSplit:
    def test_proper_split_pass(self):
        train = ["2024-01-01", "2024-06-01"]
        test = ["2024-07-01", "2024-12-01"]
        assert_train_test_temporal_split(train, test)

    def test_overlapping_split_fail(self):
        train = ["2024-01-01", "2024-08-01"]
        test = ["2024-07-01", "2024-12-01"]
        with pytest.raises(DegenerateModelError, match="leaks"):
            assert_train_test_temporal_split(train, test)

    def test_empty_pass(self):
        assert_train_test_temporal_split([], ["2024-01-01"])
        assert_train_test_temporal_split(["2024-01-01"], [])


class TestRunAllGates:
    def test_all_pass(self):
        np.random.seed(42)
        n = 200
        X = np.random.randn(n, 5)
        y = np.array([0] * 100 + [1] * 100)
        y_pred_proba = np.random.uniform(0.1, 0.9, n)
        from datetime import date, timedelta
        # Non-overlapping: features from H1, targets from H2
        feat_base = date(2024, 1, 1)
        tgt_base = date(2025, 1, 1)
        feature_dates = [(feat_base + timedelta(days=i)).isoformat() for i in range(n)]
        target_dates = [(tgt_base + timedelta(days=i)).isoformat() for i in range(n)]

        results = run_all_gates(
            X=X,
            y=y,
            y_pred_proba=y_pred_proba,
            feature_dates=feature_dates,
            target_dates=target_dates,
            train_dates=feature_dates[:150],
            test_dates=feature_dates[150:],
            train_indices=np.arange(0, 120),
            val_indices=np.arange(120, 150),
            holdout_indices=np.arange(150, 200),
            feature_names=[f"f{i}" for i in range(5)],
        )
        assert len(results) == 7
        assert all(results.values())

    def test_degenerate_model_caught(self):
        """Simulate Session 7's degenerate model: always predicts same class."""
        n = 200
        X = np.random.randn(n, 3)
        y = np.array([0] * 199 + [1])  # 99.5/0.5 split
        y_pred_proba = np.full(n, 0.9998)  # always predicts 0.9998

        with pytest.raises(DegenerateModelError):
            run_all_gates(X=X, y=y, y_pred_proba=y_pred_proba)
