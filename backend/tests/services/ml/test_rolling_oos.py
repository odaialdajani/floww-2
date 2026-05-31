"""
backend/tests/services/ml/test_rolling_oos.py

Unit tests for the rolling-OOS evaluator core logic (scripts/rolling_oos.py).

Tests use synthetic feature data + stub model/scaler so they're independent
of Mongo, sklearn, or any shipped artifacts. The CLI / Mongo loading parts
of rolling_oos.py are intentionally not tested here — they're integration
concerns covered by running the script against real data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add backend/ + repo root to path so `scripts.rolling_oos` is importable.
HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))               # backend/
sys.path.insert(0, str(HERE.parents[3].parent))        # repo root (for scripts/)

from scripts.rolling_oos import (  # noqa: E402
    _build_feature_matrix,
    _f1_binary,
    _make_folds,
    _verdict_from_results,
    evaluate_rolling_oos,
    render_report,
)

# ────────────────────────────────────────────────────────────────────────────
# Stub model / scaler
# ────────────────────────────────────────────────────────────────────────────


class _AlwaysOnesModel:
    """Predicts class 1 for every input."""
    def predict(self, X):
        return np.ones(len(X), dtype=int)


class _AlternatingModel:
    """Predicts 1, 0, 1, 0, ... — useful for testing accuracy/F1."""
    def predict(self, X):
        return np.array([i % 2 for i in range(len(X))], dtype=int)


class _PassThroughScaler:
    def transform(self, X):
        return np.asarray(X, dtype=float)


# ────────────────────────────────────────────────────────────────────────────
# _make_folds
# ────────────────────────────────────────────────────────────────────────────


def test_make_folds_clean_division():
    folds = _make_folds(n=100, fold_size=20)
    assert folds == [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]


def test_make_folds_drops_partial_tail():
    folds = _make_folds(n=95, fold_size=20)
    assert folds == [(0, 20), (20, 40), (40, 60), (60, 80)]


def test_make_folds_embargo_gap():
    folds = _make_folds(n=100, fold_size=20, embargo=5)
    # 20 + 5 stride: [0,20), [25,45), [50,70), [75,95) — last starts at 100 → cut
    assert folds == [(0, 20), (25, 45), (50, 70), (75, 95)]


def test_make_folds_n_smaller_than_fold():
    assert _make_folds(n=10, fold_size=20) == []


# ────────────────────────────────────────────────────────────────────────────
# _f1_binary
# ────────────────────────────────────────────────────────────────────────────


def test_f1_perfect():
    assert _f1_binary(np.array([1, 1, 0, 0]), np.array([1, 1, 0, 0])) == pytest.approx(1.0)


def test_f1_all_wrong():
    assert _f1_binary(np.array([0, 0, 1, 1]), np.array([1, 1, 0, 0])) == 0.0


def test_f1_zero_when_no_true_positives():
    assert _f1_binary(np.array([0, 0, 0]), np.array([1, 1, 1])) == 0.0


def test_f1_balanced_case():
    # tp=2, fp=1, fn=1 → precision=2/3, recall=2/3 → F1 = 2/3
    preds = np.array([1, 1, 1, 0])
    actuals = np.array([1, 1, 0, 1])
    assert _f1_binary(preds, actuals) == pytest.approx(2 / 3)


# ────────────────────────────────────────────────────────────────────────────
# _verdict_from_results
# ────────────────────────────────────────────────────────────────────────────


def test_verdict_fail_on_negative_fold():
    v, reason = _verdict_from_results(agg_sharpe=2.5, fold_sharpes=[2.0, -0.5, 1.5])
    assert v == "FAIL"
    assert "non-positive" in reason


def test_verdict_fail_on_low_aggregate():
    v, reason = _verdict_from_results(agg_sharpe=0.5, fold_sharpes=[0.4, 0.6, 0.5])
    assert v == "FAIL"
    assert "< 1.0" in reason


def test_verdict_pass_on_consistent_good():
    v, _ = _verdict_from_results(agg_sharpe=2.5, fold_sharpes=[2.0, 2.5, 3.0])
    assert v == "PASS"


def test_verdict_suspect_on_wide_spread():
    v, reason = _verdict_from_results(agg_sharpe=2.5, fold_sharpes=[0.6, 1.0, 5.0])
    assert v == "SUSPECT"


def test_verdict_suspect_on_borderline_aggregate():
    v, _ = _verdict_from_results(agg_sharpe=1.5, fold_sharpes=[1.2, 1.4, 1.7])
    assert v == "SUSPECT"


# ────────────────────────────────────────────────────────────────────────────
# _build_feature_matrix
# ────────────────────────────────────────────────────────────────────────────


def test_feature_matrix_uses_provided_names():
    df = pd.DataFrame({
        "feat_a": [1.0, 2.0, 3.0],
        "feat_b": [4.0, 5.0, 6.0],
        "ignored": ["x", "y", "z"],
    })
    X = _build_feature_matrix(df, ["feat_a", "feat_b"])
    assert X.shape == (3, 2)
    np.testing.assert_array_equal(X, [[1.0, 4.0], [2.0, 5.0], [3.0, 6.0]])


def test_feature_matrix_fills_missing_with_zero():
    df = pd.DataFrame({"feat_a": [1.0, 2.0]})
    X = _build_feature_matrix(df, ["feat_a", "feat_missing"])
    assert X.shape == (2, 2)
    np.testing.assert_array_equal(X, [[1.0, 0.0], [2.0, 0.0]])


def test_feature_matrix_auto_select_when_no_names():
    df = pd.DataFrame({
        "_id": ["a", "b"],
        "ticker": ["SPY", "SPY"],
        "date": ["2024-01-01", "2024-01-02"],
        "target_directional_move": [1, -1],
        "feat_x": [10.0, 20.0],
        "feat_y": [30.0, 40.0],
    })
    X = _build_feature_matrix(df, [])  # auto-select
    # Should pick feat_x + feat_y (numeric, not metadata, not target)
    assert X.shape == (2, 2)


# ────────────────────────────────────────────────────────────────────────────
# evaluate_rolling_oos — end-to-end with synthetic data
# ────────────────────────────────────────────────────────────────────────────


def _toy_df(n: int, positive_rate: float = 0.5, seed: int = 0) -> pd.DataFrame:
    """Build a synthetic feature DataFrame for testing."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "ticker": ["SPY"] * n,
        "feat_a": rng.normal(0, 1, n),
        "feat_b": rng.normal(0, 1, n),
        "target_directional_move": (rng.random(n) < positive_rate).astype(int) * 2 - 1,
    })


def test_evaluate_rolling_oos_basic_shape():
    df = _toy_df(n=100)
    result = evaluate_rolling_oos(
        df, _AlwaysOnesModel(), _PassThroughScaler(),
        feature_names=["feat_a", "feat_b"],
        fold_size=20,
    )
    assert result["n_total"] == 100
    assert len(result["folds"]) == 5
    assert "verdict" in result
    assert "aggregate" in result
    assert "spread" in result


def test_evaluate_rolling_oos_always_ones_breakeven():
    """Model always predicts 1; positive_rate=0.5 → ~50% accuracy → low Sharpe."""
    df = _toy_df(n=100, positive_rate=0.5, seed=1)
    result = evaluate_rolling_oos(
        df, _AlwaysOnesModel(), _PassThroughScaler(),
        feature_names=["feat_a", "feat_b"],
        fold_size=20,
    )
    # Aggregate accuracy near 0.5
    assert 0.3 < result["aggregate"]["accuracy"] < 0.7
    # Verdict will be FAIL or SUSPECT given the weak edge
    assert result["verdict"] in ("FAIL", "SUSPECT")


def test_evaluate_rolling_oos_alternating_predictions():
    """Alternating model (1,0,1,0,...) against random labels lands accuracy
    near 0.5. We're testing the plumbing, not the math of any specific oracle.
    """
    df = _toy_df(n=100, positive_rate=0.5, seed=3)
    result = evaluate_rolling_oos(
        df, _AlternatingModel(), _PassThroughScaler(),
        feature_names=["feat_a", "feat_b"],
        fold_size=20,
    )
    # All folds must produce a finite accuracy in [0, 1]
    for f in result["folds"]:
        assert 0.0 <= f["accuracy"] <= 1.0
        assert "sharpe" in f


def test_evaluate_rolling_oos_handles_empty_folds():
    """If fold_size > n, no folds; returns FAIL with explanation."""
    df = _toy_df(n=10)
    result = evaluate_rolling_oos(
        df, _AlwaysOnesModel(), _PassThroughScaler(),
        feature_names=["feat_a", "feat_b"],
        fold_size=50,
    )
    assert result["verdict"] == "FAIL"
    assert "no valid folds" in result["verdict_reason"]


def test_evaluate_rolling_oos_scaler_failure_short_circuits():
    class _BrokenScaler:
        def transform(self, X):
            raise RuntimeError("simulated scaler shape mismatch")

    df = _toy_df(n=100)
    result = evaluate_rolling_oos(
        df, _AlwaysOnesModel(), _BrokenScaler(),
        feature_names=["feat_a", "feat_b"],
        fold_size=20,
    )
    assert result["verdict"] == "FAIL"
    assert "scaler.transform failed" in result["verdict_reason"]


# ────────────────────────────────────────────────────────────────────────────
# render_report
# ────────────────────────────────────────────────────────────────────────────


def test_render_report_contains_verdict_line():
    fake_result = {
        "n_total": 100,
        "folds": [{"start": 0, "end": 50, "n": 50, "accuracy": 0.6, "f1": 0.55, "sharpe": 2.0}],
        "aggregate": {"accuracy": 0.6, "f1": 0.55, "sharpe": 2.0, "n": 50},
        "spread": {"mean_sharpe": 2.0, "std_sharpe": 0.0, "min_sharpe": 2.0, "max_sharpe": 2.0},
        "verdict": "PASS",
        "verdict_reason": "all folds healthy",
    }
    md = render_report("SPY", "models/SPY_direction_v1.0.joblib", fake_result)
    assert "VERDICT: PASS" in md
    assert "## Aggregate" in md
    assert "## Per-fold metrics" in md
    assert "SPY_direction_v1.0.joblib" in md
