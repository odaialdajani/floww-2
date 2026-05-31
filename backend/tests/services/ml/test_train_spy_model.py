"""
Tests for ML training pipeline (scripts/train_spy_model.py).

Tests the Sharpe calculation, walk-forward CV splits, gate evaluation,
and model training on real data from MongoDB.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from scripts.train_spy_model import (
    compute_sharpe,
    gate_evaluate,
    prepare_data,
    walk_forward_cv,
)

# ── Sharpe calculation tests ───────────────────────────────────────────────

class TestComputeSharpe:

    def test_basic_sharpe(self):
        """All correct predictions → capped Sharpe."""
        preds = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        actuals = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        result = compute_sharpe(preds, actuals)
        assert result <= 10.0  # Should be capped

    def test_all_wrong(self):
        """All wrong predictions → negative Sharpe."""
        preds = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        actuals = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        result = compute_sharpe(preds, actuals)
        assert result < 0

    def test_mixed_predictions(self):
        """Mixed correct/wrong → moderate Sharpe."""
        preds = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        actuals = [1, 1, 1, 0, 0, 1, 0, 1, 0, 1]
        result = compute_sharpe(preds, actuals)
        assert -5.0 < result < 5.0

    def test_few_trades_returns_zero(self):
        """Fewer than 5 trades → 0.0."""
        preds = [1, 1, 1]
        actuals = [1, 1, 1]
        result = compute_sharpe(preds, actuals)
        assert result == 0.0

    def test_no_trades_returns_zero(self):
        """No trades (all pred=0) → 0.0."""
        preds = [0, 0, 0, 0, 0]
        actuals = [1, 1, 1, 1, 1]
        result = compute_sharpe(preds, actuals)
        assert result == 0.0

    def test_sharpe_capped_at_10(self):
        """Sharpe should never exceed 10.0."""
        # Create a scenario with very high win rate
        preds = [1] * 100
        actuals = [1] * 95 + [0] * 5
        result = compute_sharpe(preds, actuals)
        assert result <= 10.0

    def test_sharpe_not_nan(self):
        """Sharpe should never be NaN."""
        preds = [1, 1, 1, 1, 1]
        actuals = [1, 1, 1, 1, 1]
        result = compute_sharpe(preds, actuals)
        assert not math.isnan(result)
        assert not math.isinf(result)


# ── Walk-forward CV tests ──────────────────────────────────────────────────

class TestWalkForwardCV:

    def test_basic_splits(self):
        """5 folds with default params on 167 samples."""
        X = np.random.rand(167, 10)
        y = np.random.randint(0, 2, 167)
        dates = [f"2024-01-{i+1:02d}" for i in range(167)]

        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=60, test_size=20, step=20)
        assert len(splits) == 5

    def test_split_shapes(self):
        """Each split should have correct train/test sizes."""
        X = np.random.rand(167, 10)
        y = np.random.randint(0, 2, 167)
        dates = [f"2024-01-{i+1:02d}" for i in range(167)]

        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=60, test_size=20, step=20)

        for train_idx, test_idx in splits:
            assert len(train_idx) >= 60
            assert len(test_idx) == 20
            # No overlap
            assert len(set(train_idx) & set(test_idx)) == 0

    def test_expanding_window(self):
        """Train window should expand with each fold."""
        X = np.random.rand(167, 10)
        y = np.random.randint(0, 2, 167)
        dates = [f"2024-01-{i+1:02d}" for i in range(167)]

        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=60, test_size=20, step=20)

        train_ends = [max(train_idx) for train_idx, _ in splits]
        # Each fold's train should be larger than the previous
        for i in range(1, len(train_ends)):
            assert train_ends[i] > train_ends[i - 1]

    def test_insufficient_data(self):
        """Not enough data → empty splits."""
        X = np.random.rand(10, 5)
        y = np.random.randint(0, 2, 10)
        dates = [f"2024-01-{i+1:02d}" for i in range(10)]

        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=60, test_size=20)
        assert len(splits) == 0


# ── Gate evaluation tests ──────────────────────────────────────────────────

class TestGateEvaluate:

    def test_ship_when_all_criteria_met(self):
        result = {
            "model_name": "test",
            "train_accuracy": 0.75,
            "test_accuracy": 0.70,
            "train_sharpe": 5.0,
            "test_sharpe": 3.0,
            "majority_sharpe": 1.0,
            "beats_majority": True,
            "beats_persistence": True,
        }
        gated = gate_evaluate(result)
        assert gated["verdict"] == "SHIP"
        assert len(gated["rejection_reasons"]) == 0

    def test_reject_when_beats_nothing(self):
        result = {
            "model_name": "test",
            "train_accuracy": 0.60,
            "test_accuracy": 0.55,
            "train_sharpe": 1.0,
            "test_sharpe": 0.5,
            "majority_sharpe": 2.0,
            "persistence_sharpe": 1.5,
            "beats_majority": False,
            "beats_persistence": False,
        }
        gated = gate_evaluate(result)
        assert gated["verdict"] == "REJECT"

    def test_reject_when_overfit(self):
        result = {
            "model_name": "test",
            "train_accuracy": 0.99,
            "test_accuracy": 0.70,
            "train_sharpe": 9.8,
            "test_sharpe": 5.0,
            "majority_sharpe": 1.0,
            "beats_majority": True,
            "beats_persistence": True,
        }
        gated = gate_evaluate(result)
        assert gated["verdict"] == "REJECT"
        assert any("overfit" in r.lower() or "near-perfect" in r.lower()
                    for r in gated["rejection_reasons"])

    def test_reject_when_low_accuracy(self):
        result = {
            "model_name": "test",
            "train_accuracy": 0.55,
            "test_accuracy": 0.45,
            "train_sharpe": 2.0,
            "test_sharpe": 1.0,
            "majority_sharpe": 0.5,
            "beats_majority": True,
            "beats_persistence": True,
        }
        gated = gate_evaluate(result)
        assert gated["verdict"] == "REJECT"
        assert any("accuracy" in r.lower() for r in gated["rejection_reasons"])

    def test_reject_when_train_test_gap_large(self):
        result = {
            "model_name": "test",
            "train_accuracy": 0.95,
            "test_accuracy": 0.70,
            "train_sharpe": 8.0,
            "test_sharpe": 5.0,
            "majority_sharpe": 1.0,
            "beats_majority": True,
            "beats_persistence": True,
        }
        gated = gate_evaluate(result)
        assert gated["verdict"] == "REJECT"
        assert any("gap" in r.lower() for r in gated["rejection_reasons"])


# ── Data preparation tests ─────────────────────────────────────────────────

class TestPrepareData:

    def test_excludes_target_columns(self):
        """Target columns should not appear in feature matrix."""
        import pandas as pd
        df = pd.DataFrame({
            "date": ["2024-01-01"] * 10,
            "ticker": ["SPY"] * 10,
            "feature_a": np.random.rand(10),
            "feature_b": np.random.rand(10),
            "target_directional_move": np.random.randint(0, 2, 10),
            "target_return_pct": np.random.rand(10),
        })
        X, y, feature_names, dates = prepare_data(df)
        assert "target_directional_move" not in feature_names
        assert "target_return_pct" not in feature_names
        assert "date" not in feature_names
        assert "ticker" not in feature_names
        assert "feature_a" in feature_names
        assert "feature_b" in feature_names

    def test_handles_nan_values(self):
        """NaN values should be filled with 0."""
        import pandas as pd
        df = pd.DataFrame({
            "date": ["2024-01-01"] * 10,
            "ticker": ["SPY"] * 10,
            "feature_a": [1.0, float("nan"), 3.0] + [0.0] * 7,
            "feature_b": np.random.rand(10),
            "target_directional_move": np.random.randint(0, 2, 10),
        })
        X, y, feature_names, dates = prepare_data(df)
        assert not np.any(np.isnan(X))

    def test_handles_inf_values(self):
        """Inf values should be replaced."""
        import pandas as pd
        df = pd.DataFrame({
            "date": ["2024-01-01"] * 10,
            "ticker": ["SPY"] * 10,
            "feature_a": [1.0, float("inf"), 3.0] + [0.0] * 7,
            "feature_b": np.random.rand(10),
            "target_directional_move": np.random.randint(0, 2, 10),
        })
        X, y, feature_names, dates = prepare_data(df)
        assert not np.any(np.isinf(X))
