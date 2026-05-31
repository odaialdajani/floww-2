#!/usr/bin/env python3
"""
backend/tests/test_pipeline_integration.py

Integration tests for the full ML pipeline.
Uses synthetic data — no MongoDB required.
Tests the complete flow: data → features → training → prediction → audit.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.train_spy_v2 import (
    build_feature_matrix,
    compute_baselines,
    compute_trading_sharpe,
    train_model,
    walk_forward_splits,
)


class TestEndToEndPipeline:
    """Test the full pipeline with synthetic data."""

    def _make_synthetic_data(self, n_samples=300, n_features=23, seed=42):
        """Create synthetic GEX + bars data."""
        np.random.seed(seed)

        # Create dates
        dates = pd.date_range("2024-01-01", periods=n_samples, freq="B")
        date_strs = [d.strftime("%Y-%m-%d") for d in dates]

        # Create synthetic GEX data
        gex_data = {
            "day": date_strs,
            "net_gex": np.random.randn(n_samples) * 1e7,
            "call_gex": np.abs(np.random.randn(n_samples) * 5e6),
            "put_gex": -np.abs(np.random.randn(n_samples) * 5e6),
            "total_vex": np.random.randn(n_samples) * 1e5,
            "total_dex": np.random.randn(n_samples) * 1e8,
            "total_vega": np.abs(np.random.randn(n_samples) * 1e5),
            "gamma_flip": np.random.uniform(400, 500, n_samples),
            "n_strikes": np.random.randint(5000, 7000, size=n_samples),
            "spot": np.cumsum(np.random.randn(n_samples) * 2) + 470,
        }
        gex_df = pd.DataFrame(gex_data)

        # Create synthetic bars data
        closes = gex_df["spot"].values
        bars_data = {
            "date": date_strs,
            "open": closes + np.random.randn(n_samples) * 0.5,
            "high": closes + np.abs(np.random.randn(n_samples)) * 2,
            "low": closes - np.abs(np.random.randn(n_samples)) * 2,
            "close": closes,
            "volume": np.random.randint(1000000, 10000000, size=n_samples),
        }
        bars_df = pd.DataFrame(bars_data)

        return gex_df, bars_df

    def test_full_pipeline_with_synthetic_data(self):
        """Test the complete pipeline from data to trained model."""
        gex_df, bars_df = self._make_synthetic_data(n_samples=300)

        # Build feature matrix
        X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)

        assert X.shape[0] > 0
        assert X.shape[1] > 0
        assert len(y) == X.shape[0]

        # Create walk-forward splits
        n_splits = min(6, (len(y) - 40) // 20)
        splits = walk_forward_splits(len(y), n_splits=n_splits, train_size=100, test_size=20)

        assert len(splits) >= 3

        # Compute baselines
        baselines = compute_baselines(X, y, splits)
        assert "majority" in baselines
        assert "persistence" in baselines
        assert "logistic" in baselines

        # Train model
        result = train_model(X, y, splits, feature_names, dates, "SPY")

        assert result["status"] == "ok"
        assert result["n_folds"] > 0
        assert result["metrics"]["accuracy"] > 0.4  # Should be better than random

        # Compute Sharpe
        sharpe = compute_trading_sharpe(result["predictions"], result["actuals"])
        assert isinstance(sharpe, float)

    def test_pipeline_rejects_degenerate_data(self):
        """Pipeline should reject data that fails quality gates."""
        gex_df, bars_df = self._make_synthetic_data(n_samples=200)

        X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)

        # Make data degenerate: all same class
        y[:] = 0

        splits = walk_forward_splits(len(y), n_splits=4, train_size=80, test_size=20)
        result = train_model(X, y, splits, feature_names, dates, "SPY")

        # Should fail because class balance gate rejects single-class data
        assert result["status"] == "failed"

    def test_pipeline_with_separable_data(self):
        """Pipeline should achieve high accuracy on perfectly separable data."""
        np.random.seed(42)
        n_samples = 300

        # Create perfectly separable data
        X = np.random.randn(n_samples, 10)
        y = (X[:, 0] > 0).astype(int)

        feature_names = [f"f{i}" for i in range(10)]
        dates = [f"2024-01-{i+1:02d}" for i in range(n_samples)]

        splits = walk_forward_splits(n_samples, n_splits=6, train_size=100, test_size=20)
        result = train_model(X, y, splits, feature_names, dates, "SPY")

        assert result["status"] == "ok"
        # Should achieve high accuracy on separable data
        assert result["metrics"]["accuracy"] > 0.8

    def test_baselines_are_computed_correctly(self):
        """Verify baseline computations are correct."""
        np.random.seed(42)
        X = np.random.randn(200, 5)
        y = np.array([0] * 140 + [1] * 60)  # 70% class 0

        splits = [(np.arange(0, 150), np.arange(150, 200))]
        baselines = compute_baselines(X, y, splits)

        # Majority baseline should predict class 0
        assert all(p == 0 for p in baselines["majority"])

        # Persistence baseline should predict last train value
        assert all(p == y[149] for p in baselines["persistence"])

    def test_sharpe_computation(self):
        """Test Sharpe ratio computation."""
        # Perfect predictions
        sharpe = compute_trading_sharpe([1, 1, 0, 0], [1, 1, 0, 0])
        assert sharpe > 0

        # All wrong
        sharpe = compute_trading_sharpe([1, 1, 1], [0, 0, 0])
        assert sharpe < 0

        # No trades
        sharpe = compute_trading_sharpe([0, 0, 0], [1, 0, 1])
        assert sharpe == 0.0

    def test_walk_forward_temporal_integrity(self):
        """Verify walk-forward splits maintain temporal ordering."""
        n_samples = 500
        splits = walk_forward_splits(n_samples, n_splits=10, train_size=100, test_size=20)

        for i, (train_idx, test_idx) in enumerate(splits):
            # All train indices must come before all test indices
            assert max(train_idx) < min(test_idx), f"Split {i}: train/test overlap"

            # No overlap
            assert len(set(train_idx) & set(test_idx)) == 0

        # Splits should be sequential (no gaps between test sets)
        for i in range(1, len(splits)):
            prev_test_end = max(splits[i-1][1])
            curr_test_start = min(splits[i][1])
            assert curr_test_start >= prev_test_end, f"Gap between splits {i-1} and {i}"


class TestFeatureEngineering:
    """Test feature engineering pipeline."""

    def test_feature_matrix_shape(self):
        """Verify feature matrix has correct shape."""
        gex_df, bars_df = TestEndToEndPipeline()._make_synthetic_data(n_samples=200)
        X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)

        # Should have fewer rows than input due to NaN from rolling calculations
        assert X.shape[0] < 200
        assert X.shape[0] > 100  # But not too few

        # Should have many features
        assert X.shape[1] > 10

    def test_no_nan_in_features(self):
        """Feature matrix should have no NaN values."""
        gex_df, bars_df = TestEndToEndPipeline()._make_synthetic_data(n_samples=200)
        X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)

        assert not np.any(np.isnan(X))
        assert not np.any(np.isinf(X))

    def test_target_is_binary(self):
        """Target variable should be binary (0 or 1)."""
        gex_df, bars_df = TestEndToEndPipeline()._make_synthetic_data(n_samples=200)
        X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)

        assert set(np.unique(y)).issubset({0, 1})

    def test_class_balance_reasonable(self):
        """Target should have reasonable class balance."""
        gex_df, bars_df = TestEndToEndPipeline()._make_synthetic_data(n_samples=300)
        X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)

        pos_rate = np.mean(y)
        # Should be between 20% and 80%
        assert 0.2 < pos_rate < 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
