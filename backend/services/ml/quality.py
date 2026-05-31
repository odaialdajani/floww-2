"""
backend/services/ml/quality.py

Data quality gates for the ML pipeline. Every gate raises DegenerateModelError
with a descriptive message on failure. Called before model.fit and after
model.predict. No model that fails any gate is allowed to be saved.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from . import DegenerateModelError

log = logging.getLogger("ml.quality")


def assert_class_balance(y: Sequence, min_ratio: float = 0.20, label: str = "target") -> None:
    """Assert that no class in y has fewer than min_ratio fraction of samples.

    Args:
        y: Target array-like
        min_ratio: Minimum fraction for the rarest class (default 20%)
        label: Name for error messages

    Raises:
        DegenerateModelError: If any class is below min_ratio
    """
    y_arr = np.asarray(y)
    unique, counts = np.unique(y_arr, return_counts=True)
    total = len(y_arr)

    if total == 0:
        raise DegenerateModelError(f"{label}: empty target array")

    if len(unique) < 2:
        raise DegenerateModelError(
            f"{label}: only 1 unique class ({unique[0]}) — model has nothing to learn"
        )

    min_count = counts.min()
    min_class = unique[counts.argmin()]
    ratio = min_count / total

    if ratio < min_ratio:
        raise DegenerateModelError(
            f"{label}: class {min_class} has {min_count}/{total} samples "
            f"({ratio:.4f} < {min_ratio} min_ratio). "
            f"Class distribution: {dict(zip(unique.tolist(), counts.tolist()))}"
        )

    log.info(f"assert_class_balance: OK — {len(unique)} classes, min ratio={ratio:.4f}")


def assert_feature_variance(X: Any, min_var: float = 1e-6, feature_names: Optional[List[str]] = None) -> None:
    """Assert that every feature has variance > min_var.

    Catches constant columns (all same value) which provide no signal.

    Args:
        X: Feature matrix (n_samples, n_features)
        min_var: Minimum variance threshold
        feature_names: Optional list of feature names for error messages

    Raises:
        DegenerateModelError: If any feature has variance <= min_var
    """
    X_arr = np.asarray(X, dtype=float)

    if X_arr.ndim == 1:
        X_arr = X_arr.reshape(-1, 1)

    if X_arr.shape[0] < 2:
        raise DegenerateModelError(f"features: only {X_arr.shape[0]} sample(s), need ≥ 2 for variance")

    variances = np.var(X_arr, axis=0)
    low_var_mask = variances <= min_var
    low_var_indices = np.where(low_var_mask)[0]

    if len(low_var_indices) > 0:
        names = feature_names or [f"feature_{i}" for i in range(X_arr.shape[1])]
        bad = [(names[i], variances[i]) for i in low_var_indices[:5]]
        bad_str = ", ".join(f"{n}={v:.2e}" for n, v in bad)
        raise DegenerateModelError(
            f"features: {len(low_var_indices)} feature(s) with variance <= {min_var}: {bad_str}"
        )

    log.info(f"assert_feature_variance: OK — {X_arr.shape[1]} features, min var={variances.min():.2e}")


def assert_prediction_distribution(y_pred_proba: Any, min_std: float = 0.05, label: str = "predictions") -> None:
    """Assert that predicted probabilities have std > min_std.

    Catches models that always predict the same probability (degenerate output).

    Args:
        y_pred_proba: Predicted probabilities (n_samples,) or (n_samples, n_classes)
        min_std: Minimum standard deviation threshold
        label: Name for error messages

    Raises:
        DegenerateModelError: If prediction std <= min_std
    """
    proba = np.asarray(y_pred_proba, dtype=float)

    if proba.ndim == 2:
        # For multi-class, check the max probability per sample
        proba = proba.max(axis=1)

    std = float(np.std(proba))
    mean = float(np.mean(proba))

    if std <= min_std:
        raise DegenerateModelError(
            f"{label}: predicted probability std={std:.6f} <= {min_std} (mean={mean:.4f}). "
            f"Model always predicts the same thing — degenerate."
        )

    log.info(f"assert_prediction_distribution: OK — std={std:.4f}, mean={mean:.4f}")


def assert_temporal_ordering(timestamps: Sequence, label: str = "timestamps") -> None:
    """Assert that timestamps are strictly monotonically increasing.

    Args:
        timestamps: Sequence of timestamps (datetime or string)
        label: Name for error messages

    Raises:
        DegenerateModelError: If timestamps are not sorted
    """
    ts = list(timestamps)
    if len(ts) < 2:
        return

    for i in range(1, len(ts)):
        if ts[i] <= ts[i - 1]:
            raise DegenerateModelError(
                f"{label}: not sorted at index {i}: {ts[i-1]} >= {ts[i]}"
            )

    log.info(f"assert_temporal_ordering: OK — {len(ts)} timestamps, {ts[0]} → {ts[-1]}")


def assert_no_future_leakage(
    feature_dates: Sequence,
    target_dates: Sequence,
    label: str = "features",
) -> None:
    """Assert that no feature date is >= any target date.

    Features at time t must only use data available at or before t.

    Args:
        feature_dates: Dates when features were computed
        target_dates: Dates of the prediction targets
        label: Name for error messages

    Raises:
        DegenerateModelError: If any feature date >= any target date
    """
    feat_max = max(feature_dates)
    tgt_min = min(target_dates)

    if feat_max >= tgt_min:
        raise DegenerateModelError(
            f"{label}: future leakage detected — max feature date {feat_max} >= "
            f"min target date {tgt_min}. Features must not use future data."
        )

    log.info(f"assert_no_future_leakage: OK — features ≤ {feat_max}, targets ≥ {tgt_min}")


def assert_holdout_untouched(
    train_indices: np.ndarray,
    val_indices: np.ndarray,
    holdout_indices: np.ndarray,
) -> None:
    """Assert that holdout indices don't overlap with train or val.

    Args:
        train_indices: Indices used for training
        val_indices: Indices used for validation
        holdout_indices: Indices reserved for holdout

    Raises:
        DegenerateModelError: If holdout overlaps with train or val
    """
    train_set = set(train_indices.tolist())
    val_set = set(val_indices.tolist())
    holdout_set = set(holdout_indices.tolist())

    train_overlap = train_set & holdout_set
    val_overlap = val_set & holdout_set

    if train_overlap or val_overlap:
        raise DegenerateModelError(
            f"holdout: overlap detected — {len(train_overlap)} train indices and "
            f"{len(val_overlap)} val indices leak into holdout set"
        )

    log.info(f"assert_holdout_untouched: OK — {len(holdout_set)} holdout samples, no overlap")


def assert_train_test_temporal_split(
    train_dates: Sequence,
    test_dates: Sequence,
) -> None:
    """Assert that all train dates are before all test dates.

    Args:
        train_dates: Dates in training set
        test_dates: Dates in test set

    Raises:
        DegenerateModelError: If any train date >= any test date
    """
    if not train_dates or not test_dates:
        return

    max_train = max(train_dates)
    min_test = min(test_dates)

    if max_train >= min_test:
        raise DegenerateModelError(
            f"temporal split: max train date {max_train} >= min test date {min_test}. "
            f"Test data leaks into training window."
        )

    log.info(f"assert_train_test_temporal_split: OK — train ≤ {max_train}, test ≥ {min_test}")


def run_all_gates(
    X: Any,
    y: Any,
    y_pred_proba: Any,
    feature_dates: Optional[Sequence] = None,
    target_dates: Optional[Sequence] = None,
    train_dates: Optional[Sequence] = None,
    test_dates: Optional[Sequence] = None,
    train_indices: Optional[np.ndarray] = None,
    val_indices: Optional[np.ndarray] = None,
    holdout_indices: Optional[np.ndarray] = None,
    feature_names: Optional[List[str]] = None,
) -> Dict[str, bool]:
    """Run all quality gates. Returns dict of gate_name -> passed.

    Raises DegenerateModelError on first failure.
    """
    results = {}

    # Gate 1: Class balance
    assert_class_balance(y)
    results["class_balance"] = True

    # Gate 2: Feature variance
    assert_feature_variance(X, feature_names=feature_names)
    results["feature_variance"] = True

    # Gate 3: Prediction distribution
    assert_prediction_distribution(y_pred_proba)
    results["prediction_distribution"] = True

    # Gate 4: Temporal ordering
    if feature_dates is not None:
        assert_temporal_ordering(feature_dates)
        results["temporal_ordering"] = True

    # Gate 5: No future leakage
    if feature_dates is not None and target_dates is not None:
        assert_no_future_leakage(feature_dates, target_dates)
        results["no_future_leakage"] = True

    # Gate 6: Holdout untouched
    if train_indices is not None and val_indices is not None and holdout_indices is not None:
        assert_holdout_untouched(train_indices, val_indices, holdout_indices)
        results["holdout_untouched"] = True

    # Gate 7: Train/test temporal split
    if train_dates is not None and test_dates is not None:
        assert_train_test_temporal_split(train_dates, test_dates)
        results["temporal_split"] = True

    log.info(f"All {len(results)} quality gates passed")
    return results
