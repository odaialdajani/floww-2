#!/usr/bin/env python3
"""
backend/tests/test_backtest_model.py

Unit tests for the backtest script.
Uses synthetic data — no MongoDB required.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.backtest_model import (
    build_backtest_features,
    load_model_and_scaler,
    run_backtest,
)


class TestBuildBacktestFeatures:
    def test_basic_build(self):
        """Test feature matrix construction."""
        gex_data = {
            "day": [f"2024-01-{i+1:02d}" for i in range(50)],
            "net_gex": np.random.randn(50) * 1e7,
            "call_gex": np.abs(np.random.randn(50) * 5e6),
            "put_gex": -np.abs(np.random.randn(50) * 5e6),
            "total_vex": np.random.randn(50) * 1e5,
            "total_dex": np.random.randn(50) * 1e8,
            "total_vega": np.abs(np.random.randn(50) * 1e5),
            "gamma_flip": np.random.uniform(400, 500, 50),
            "n_strikes": np.random.randint(5000, 7000, size=50),
            "spot": np.cumsum(np.random.randn(50) * 2) + 470,
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

        X, y, feature_names, dates, next_returns = build_backtest_features(gex_df, bars_df)

        assert X.shape[0] > 0
        assert X.shape[1] > 0
        assert len(y) == X.shape[0]
        assert len(dates) == X.shape[0]
        assert len(next_returns) == X.shape[0]
        assert not np.any(np.isnan(X))

    def test_target_is_binary(self):
        """Target should be binary."""
        gex_data = {
            "day": [f"2024-01-{i+1:02d}" for i in range(50)],
            "net_gex": np.random.randn(50) * 1e7,
            "call_gex": np.abs(np.random.randn(50) * 5e6),
            "put_gex": -np.abs(np.random.randn(50) * 5e6),
            "total_vex": np.random.randn(50) * 1e5,
            "total_dex": np.random.randn(50) * 1e8,
            "total_vega": np.abs(np.random.randn(50) * 1e5),
            "gamma_flip": np.random.uniform(400, 500, 50),
            "n_strikes": np.random.randint(5000, 7000, size=50),
            "spot": np.cumsum(np.random.randn(50) * 2) + 470,
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

        X, y, feature_names, dates, next_returns = build_backtest_features(gex_df, bars_df)

        assert set(np.unique(y)).issubset({0, 1})


class TestRunBacktest:
    def test_basic_backtest(self):
        """Test basic backtest with synthetic data."""
        np.random.seed(42)
        n_samples = 200
        n_features = 15

        X = np.random.randn(n_samples, n_features)
        y = (X[:, 0] + np.random.randn(n_samples) * 0.3 > 0).astype(int)
        dates = [f"2024-01-{i+1:02d}" for i in range(n_samples)]
        next_returns = np.random.randn(n_samples) * 0.01

        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler

        model = GradientBoostingClassifier(n_estimators=10, random_state=42)
        model.fit(X[:100], y[:100])
        scaler = StandardScaler()
        scaler.fit(X[:100])

        feature_names = [f"f{i}" for i in range(n_features)]

        result = run_backtest(model, scaler, X, y, dates, next_returns, feature_names, n_splits=5)

        assert result["status"] == "ok"
        assert result["n_folds"] > 0
        assert "overall" in result
        assert "fold_results" in result

    def test_backtest_with_insufficient_data(self):
        """Test backtest with too few samples."""
        X = np.random.randn(20, 5)
        y = np.random.randint(0, 2, 20)
        dates = [f"2024-01-{i+1:02d}" for i in range(20)]
        next_returns = np.random.randn(20) * 0.01

        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler

        model = GradientBoostingClassifier(n_estimators=10, random_state=42)
        model.fit(X[:10], y[:10])
        scaler = StandardScaler()
        scaler.fit(X[:10])

        # With very few samples and many splits, should get few or no folds
        result = run_backtest(model, scaler, X, y, dates, next_returns, [f"f{i}" for i in range(5)], n_splits=10)

        # Should either fail or return very few folds
        if result["status"] == "ok":
            assert result["n_folds"] < 10  # Can't have 10 folds with 20 samples


class TestLoadModelAndScaler:
    def test_missing_model(self):
        """Test error when model file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_model_and_scaler("nonexistent_model.joblib")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
