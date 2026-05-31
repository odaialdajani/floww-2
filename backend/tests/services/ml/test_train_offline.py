"""
backend/tests/services/ml/test_train_offline.py

Tests for the offline ML training pipeline (scripts/train_offline.py).

Tests use the actual cached CSV data and verify:
  - Data loading and preparation
  - Walk-forward CV split generation
  - Sharpe calculation edge cases
  - Gate logic
  - End-to-end training for one ticker (smoke test)
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.train_offline import (
    compute_trading_sharpe,
    evaluate_fold,
    gate_evaluate,
    load_csv,
    prepare_data,
    train_gbm,
    train_logistic,
    train_rf,
    walk_forward_cv,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadCsv:
    def test_load_iwm(self):
        df = load_csv("IWM")
        assert not df.empty
        assert len(df) == 2799
        assert "target_directional_move" in df.columns

    def test_load_tlt(self):
        df = load_csv("TLT")
        assert not df.empty
        assert len(df) == 2799

    def test_load_dia(self):
        df = load_csv("DIA")
        assert not df.empty

    def test_load_qqq(self):
        df = load_csv("QQQ")
        assert not df.empty

    def test_unknown_ticker_returns_empty(self):
        df = load_csv("INVALID")
        assert df.empty


class TestPrepareData:
    def test_basic_shape(self):
        df = load_csv("IWM")
        X, y, feature_names, dates = prepare_data(df)
        assert X.shape[0] == 2799
        assert X.shape[1] == len(feature_names)
        assert y is not None
        assert len(y) == 2799

    def test_target_values(self):
        df = load_csv("IWM")
        X, y, _, _ = prepare_data(df)
        unique = set(np.unique(y))
        assert unique.issubset({0.0, 1.0})

    def test_no_inf_values(self):
        df = load_csv("IWM")
        X, _, _, _ = prepare_data(df)
        assert not np.any(np.isinf(X))

    def test_feature_names_are_strings(self):
        df = load_csv("IWM")
        _, _, feature_names, _ = prepare_data(df)
        assert all(isinstance(f, str) for f in feature_names)


# ═══════════════════════════════════════════════════════════════════════════════
# Walk-forward CV
# ═══════════════════════════════════════════════════════════════════════════════

class TestWalkForwardCV:
    def test_five_folds(self):
        X = np.zeros((1000, 5))
        y = np.ones(1000)
        dates = np.arange(1000)
        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=500, test_size=50, step=50)
        assert len(splits) == 5

    def test_expanding_window(self):
        X = np.zeros((1000, 5))
        y = np.ones(1000)
        dates = np.arange(1000)
        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=500, test_size=50, step=50)
        # Each fold should have a larger training set
        train_sizes = [len(tr) for tr, _ in splits]
        assert train_sizes[0] == 500
        assert train_sizes[1] == 550
        assert train_sizes[4] == 700

    def test_test_size(self):
        X = np.zeros((1000, 5))
        y = np.ones(1000)
        dates = np.arange(1000)
        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=500, test_size=50, step=50)
        for _, test_idx in splits:
            assert len(test_idx) == 50

    def test_not_enough_data(self):
        X = np.zeros((50, 5))
        y = np.ones(50)
        dates = np.arange(50)
        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=500, test_size=50, step=50)
        assert splits == []

    def test_no_overlap(self):
        X = np.zeros((1000, 5))
        y = np.ones(1000)
        dates = np.arange(1000)
        splits = walk_forward_cv(X, y, dates, n_splits=5, train_size=500, test_size=50, step=50)
        for train_idx, test_idx in splits:
            assert set(train_idx).isdisjoint(set(test_idx))


# ═══════════════════════════════════════════════════════════════════════════════
# Sharpe calculation
# ═══════════════════════════════════════════════════════════════════════════════

class TestSharpe:
    def test_all_correct(self):
        """When all trades win, returns are all +1.0, std=0, Sharpe=0 (not inf)."""
        preds = [1, 1, 1]
        actuals = [1, 1, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        # std of [1,1,1] = 0, so Sharpe returns 0.0 (guarded)
        assert sharpe == 0.0

    def test_all_wrong(self):
        preds = [1, 1, 1]
        actuals = [0, 0, 0]
        sharpe = compute_trading_sharpe(preds, actuals)
        # std of [-1,-1,-1] = 0, so Sharpe returns 0.0 (guarded against inf)
        assert sharpe == 0.0

    def test_no_trades(self):
        preds = [0, 0, 0]
        actuals = [1, 1, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe == 0.0

    def test_mixed(self):
        preds = [1, 0, 1, 0, 1]
        actuals = [1, 1, 0, 0, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert isinstance(sharpe, float)

    def test_constant_returns(self):
        """When all trades have the same return, std=0, Sharpe=0."""
        preds = [1, 1, 1]
        actuals = [1, 1, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert np.isfinite(sharpe)


# ═══════════════════════════════════════════════════════════════════════════════
# Gate evaluation
# ═══════════════════════════════════════════════════════════════════════════════

class TestGate:
    def test_ship_when_all_pass(self):
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": 1.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "SHIP"

    def test_reject_beats_majority_false(self):
        result = {
            "beats_majority": False,
            "beats_persistence": True,
            "test_sharpe": 1.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "REJECT"

    def test_reject_beats_persistence_false(self):
        result = {
            "beats_majority": True,
            "beats_persistence": False,
            "test_sharpe": 1.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "REJECT"

    def test_reject_negative_sharpe(self):
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": -0.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "REJECT"

    def test_reject_zero_sharpe(self):
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": 0.0,
            "test_accuracy": 0.55,
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "REJECT"

    def test_reject_low_accuracy(self):
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": 1.5,
            "test_accuracy": 0.48,
            "train_test_gap": 0.05,
        }
        assert gate_evaluate(result) == "REJECT"

    def test_reject_overfit(self):
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": 1.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.25,
        }
        assert gate_evaluate(result) == "REJECT"

    def test_boundary_fifteen_pct_gap(self):
        """Exactly 15% gap should pass."""
        result = {
            "beats_majority": True,
            "beats_persistence": True,
            "test_sharpe": 1.5,
            "test_accuracy": 0.55,
            "train_test_gap": 0.15,
        }
        assert gate_evaluate(result) == "SHIP"


# ═══════════════════════════════════════════════════════════════════════════════
# Model training (smoke tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestModelTrainers:
    def test_train_logistic(self):
        np.random.seed(42)
        X = np.random.randn(100, 10)
        y = (X[:, 0] > 0).astype(int)
        result = train_logistic(X, y)
        assert result is not None
        assert result["type"] == "logistic"
        preds = result["model"].predict(result["scaler"].transform(X))
        assert len(preds) == 100

    def test_train_gbm(self):
        np.random.seed(42)
        X = np.random.randn(200, 10)
        y = (X[:, 0] > 0).astype(int)
        model = train_gbm(X, y)
        assert model is not None
        preds = model.predict(X)
        assert len(preds) == 200

    def test_train_rf(self):
        np.random.seed(42)
        X = np.random.randn(200, 10)
        y = (X[:, 0] > 0).astype(int)
        model = train_rf(X, y)
        assert model is not None
        preds = model.predict(X)
        assert len(preds) == 200


class TestEvaluateFold:
    def test_returns_expected_keys(self):
        np.random.seed(42)
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression(random_state=42)
        X = np.random.randn(200, 10)
        y = (X[:, 0] > 0).astype(int)
        model.fit(X[:150], y[:150])
        result = evaluate_fold(
            "test", model,
            X[:150], y[:150], X[150:], y[150:],
            np.arange(50),
        )
        assert "test_accuracy" in result
        assert "test_sharpe" in result
        assert "train_test_gap" in result
        assert "beats_majority" in result
        assert "beats_persistence" in result
        assert 0 <= result["test_accuracy"] <= 1


# ═══════════════════════════════════════════════════════════════════════════════
# End-to-end smoke test
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    def test_tlt_logistic_training(self):
        """Train TLT logistic end-to-end and verify it produces SHIP folds."""
        from scripts.train_offline import train_ticker
        result = train_ticker("TLT", ["logistic"], n_splits=5,
                              train_size=500, test_size=50, step=50)
        assert result is not None
        assert "logistic" in result["models"]
        logistic_result = result["models"]["logistic"]
        # TLT should have at least 3 SHIP folds
        assert logistic_result["folds_ship"] >= 3
        assert logistic_result["avg_test_accuracy"] > 0.50

    def test_iwm_logistic_training(self):
        """Train IWM logistic end-to-end."""
        from scripts.train_offline import train_ticker
        result = train_ticker("IWM", ["logistic"], n_splits=5,
                              train_size=500, test_size=50, step=50)
        assert result is not None
        assert "logistic" in result["models"]
        # IWM should have at least 1 SHIP fold
        assert result["models"]["logistic"]["folds_ship"] >= 1
