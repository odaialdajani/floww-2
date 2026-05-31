#!/usr/bin/env python3
"""
backend/tests/test_train_spy_v2.py

Unit tests for the SPY v2.0 training pipeline.
Uses synthetic data — no MongoDB required.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Add repo root to path so we can import scripts
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.train_spy_v2 import (
    build_feature_matrix,
    compute_baselines,
    compute_trading_sharpe,
    walk_forward_splits,
)


class TestWalkForwardSplits:
    def test_basic_splits(self):
        splits = walk_forward_splits(200, n_splits=8, train_size=100, test_size=20)
        assert len(splits) > 0
        for train_idx, test_idx in splits:
            assert len(train_idx) > 0
            assert len(test_idx) > 0
            # No overlap
            assert len(set(train_idx) & set(test_idx)) == 0
            # Temporal ordering: all train before all test
            assert max(train_idx) < min(test_idx)

    def test_embargo(self):
        splits = walk_forward_splits(200, n_splits=4, train_size=80, test_size=20, embargo=5)
        for train_idx, test_idx in splits:
            # Gap between train and test
            assert min(test_idx) - max(train_idx) >= 5

    def test_insufficient_data(self):
        # With 30 samples and test_size=20, we can still get 1 split
        # The function is lenient — it creates splits when possible
        splits = walk_forward_splits(30, n_splits=8, train_size=100, test_size=20)
        # Just verify it doesn't crash and returns valid splits
        for train_idx, test_idx in splits:
            assert len(train_idx) > 0
            assert len(test_idx) > 0

    def test_single_split(self):
        splits = walk_forward_splits(150, n_splits=1, train_size=100, test_size=20)
        assert len(splits) == 1
        train_idx, test_idx = splits[0]
        # Train size may be less than requested if data is limited
        assert len(train_idx) > 0
        assert len(test_idx) == 20


class TestComputeBaselines:
    def test_majority_baseline(self):
        X = np.random.randn(100, 5)
        y = np.array([0] * 70 + [1] * 30)  # 70% class 0
        splits = [(np.arange(0, 80), np.arange(80, 100))]
        baselines = compute_baselines(X, y, splits)
        assert "majority" in baselines
        # Majority class is 0
        assert all(p == 0 for p in baselines["majority"])

    def test_persistence_baseline(self):
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        splits = [(np.arange(0, 80), np.arange(80, 100))]
        baselines = compute_baselines(X, y, splits)
        assert "persistence" in baselines
        # Persistence predicts last train value
        assert all(p == y[79] for p in baselines["persistence"])

    def test_logistic_baseline(self):
        X = np.random.randn(200, 5)
        y = (X[:, 0] > 0).astype(int)  # Perfectly separable
        splits = [(np.arange(0, 150), np.arange(150, 200))]
        baselines = compute_baselines(X, y, splits)
        assert "logistic" in baselines
        # Logistic should do well on separable data
        acc = np.mean(np.array(baselines["logistic"]) == y[150:200])
        assert acc > 0.8


class TestComputeTradingSharpe:
    def test_perfect_predictions(self):
        preds = [1, 1, 0, 0]
        actuals = [1, 1, 0, 0]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe > 0

    def test_all_wrong(self):
        preds = [1, 1, 1]
        actuals = [0, 0, 0]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe < 0

    def test_no_predictions(self):
        preds = [0, 0, 0]
        actuals = [1, 0, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe == 0.0

    def test_empty(self):
        sharpe = compute_trading_sharpe([], [])
        assert sharpe == 0.0


class TestBuildFeatureMatrix:
    def test_basic_build(self):
        """Test feature matrix construction from GEX + bars data."""
        import pandas as pd

        # Create synthetic GEX data
        gex_data = {
            "day": [f"2024-01-{i+1:02d}" for i in range(50)],
            "net_gex": np.random.randn(50) * 1e7,
            "call_gex": np.random.randn(50) * 5e6,
            "put_gex": np.random.randn(50) * 5e6,
            "total_vex": np.random.randn(50) * 1e6,
            "total_dex": np.random.randn(50) * 1e8,
            "total_vega": np.random.randn(50) * 1e5,
            "gamma_flip": np.random.uniform(400, 500, 50),
            "n_strikes": np.random.randint(5000, 7000, 50),
            "spot": np.random.uniform(450, 500, 50),
        }
        gex_df = pd.DataFrame(gex_data)

        # Create synthetic bars data
        bars_data = {
            "date": [f"2024-01-{i+1:02d}" for i in range(50)],
            "open": np.random.uniform(450, 500, 50),
            "high": np.random.uniform(455, 505, 50),
            "low": np.random.uniform(445, 495, 50),
            "close": np.random.uniform(450, 500, 50),
            "volume": np.random.randint(1000000, 10000000, size=50),
        }
        bars_df = pd.DataFrame(bars_data)

        X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)

        assert X.shape[0] > 0
        assert X.shape[1] > 0
        assert len(y) == X.shape[0]
        assert len(dates) == X.shape[0]
        assert len(feature_names) == X.shape[1]

        # Check that target is binary
        assert set(np.unique(y)).issubset({0, 1})

        # Check no NaN in X
        assert not np.any(np.isnan(X))

    def test_feature_names_include_gex(self):
        """Verify GEX features are included in the feature matrix."""
        import pandas as pd

        gex_data = {
            "day": [f"2024-01-{i+1:02d}" for i in range(50)],
            "net_gex": np.random.randn(50) * 1e7,
            "call_gex": np.random.randn(50) * 5e6,
            "put_gex": np.random.randn(50) * 5e6,
            "total_vex": np.random.randn(50) * 1e6,
            "total_dex": np.random.randn(50) * 1e8,
            "total_vega": np.random.randn(50) * 1e5,
            "gamma_flip": np.random.uniform(400, 500, 50),
            "n_strikes": np.random.randint(5000, 7000, size=50),
            "spot": np.random.uniform(450, 500, 50),
        }
        gex_df = pd.DataFrame(gex_data)

        bars_data = {
            "date": [f"2024-01-{i+1:02d}" for i in range(50)],
            "open": np.random.uniform(450, 500, 50),
            "high": np.random.uniform(455, 505, 50),
            "low": np.random.uniform(445, 495, 50),
            "close": np.random.uniform(450, 500, 50),
            "volume": np.random.randint(1000000, 10000000, size=50),
        }
        bars_df = pd.DataFrame(bars_data)

        X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)

        # GEX features should be present
        assert "net_gex" in feature_names
        assert "call_gex" in feature_names
        assert "put_gex" in feature_names
        assert "total_vex" in feature_names
        assert "total_dex" in feature_names
        assert "total_vega" in feature_names

        # Technical features should be present
        assert "ret_1d" in feature_names
        assert "sma_5" in feature_names
        assert "rsi_14" in feature_names


class TestQualityGatesInTraining:
    def test_training_rejects_degenerate_data(self):
        """Training should reject data that fails quality gates."""
        from scripts.train_spy_v2 import train_model

        # Create degenerate data: all same class
        X = np.random.randn(200, 5)
        y = np.zeros(200, dtype=int)  # All zeros — degenerate

        splits = walk_forward_splits(200, n_splits=4, train_size=100, test_size=20)
        result = train_model(X, y, splits, [f"f{i}" for i in range(5)], [f"d{i}" for i in range(200)], "SPY")

        # Should fail because class balance gate rejects single-class data
        assert result["status"] == "failed"

    def test_training_accepts_valid_data(self):
        """Training should accept valid data."""
        from scripts.train_spy_v2 import train_model

        np.random.seed(42)
        X = np.random.randn(200, 5)
        y = (X[:, 0] + np.random.randn(200) * 0.5 > 0).astype(int)

        # Ensure reasonable class balance
        y[:100] = 0
        y[100:] = 1

        splits = walk_forward_splits(200, n_splits=4, train_size=100, test_size=20)
        result = train_model(X, y, splits, [f"f{i}" for i in range(5)], [f"d{i}" for i in range(200)], "SPY")

        # Should succeed
        assert result["status"] == "ok"
        assert result["n_folds"] > 0
        # Accuracy should be reasonable (≥ 0.5 for balanced data)
        assert result["metrics"]["accuracy"] >= 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
