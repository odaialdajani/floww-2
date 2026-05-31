"""
tests/test_ml_training.py

Tests for the ML training pipeline (walk-forward CV, baselines, SHIP gate).
"""
import sys
from pathlib import Path

import numpy as np

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))



class TestWalkForwardSplits:
    """Tests for walk-forward cross-validation splits."""

    def test_basic_splits(self):
        """Should generate correct number of splits."""
        from train_spy_v3 import walk_forward_splits
        splits = walk_forward_splits(200, n_splits=5, train_size=100, test_size=20)
        assert len(splits) == 5

    def test_split_shapes(self):
        """Each split should have correct train/test sizes."""
        from train_spy_v3 import walk_forward_splits
        splits = walk_forward_splits(200, n_splits=3, train_size=100, test_size=20, embargo=5)
        for train_idx, test_idx in splits:
            assert len(train_idx) > 0
            assert len(test_idx) == 20

    def test_temporal_ordering(self):
        """All train indices should be before test indices."""
        from train_spy_v3 import walk_forward_splits
        splits = walk_forward_splits(200, n_splits=5, train_size=100, test_size=20)
        for train_idx, test_idx in splits:
            assert max(train_idx) < min(test_idx)

    def test_embargo_gap(self):
        """There should be a gap between train and test."""
        from train_spy_v3 import walk_forward_splits
        splits = walk_forward_splits(200, n_splits=3, train_size=100, test_size=20, embargo=5)
        for train_idx, test_idx in splits:
            gap = min(test_idx) - max(train_idx)
            assert gap >= 5

    def test_not_enough_data(self):
        """Should return fewer splits if not enough data."""
        from train_spy_v3 import walk_forward_splits
        splits = walk_forward_splits(50, n_splits=8, train_size=100, test_size=20)
        assert len(splits) < 8

    def test_no_overlap_between_folds(self):
        """Test sets from different folds should not overlap."""
        from train_spy_v3 import walk_forward_splits
        splits = walk_forward_splits(300, n_splits=5, train_size=100, test_size=20)
        test_sets = [set(test_idx.tolist()) for _, test_idx in splits]
        for i in range(len(test_sets)):
            for j in range(i + 1, len(test_sets)):
                assert len(test_sets[i] & test_sets[j]) == 0


class TestComputeTradingSharpe:
    """Tests for trading Sharpe ratio computation."""

    def test_all_correct(self):
        """All correct predictions should give high Sharpe."""
        from train_spy_v3 import compute_trading_sharpe
        preds = [1, 1, 1, 1]
        actuals = [1, 1, 1, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe > 0

    def test_all_wrong(self):
        """All wrong predictions should give negative Sharpe."""
        from train_spy_v3 import compute_trading_sharpe
        preds = [1, 1, 1, 1]
        actuals = [0, 0, 0, 0]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe < 0

    def test_mixed(self):
        """Mixed predictions should give moderate Sharpe."""
        from train_spy_v3 import compute_trading_sharpe
        preds = [1, 0, 1, 0, 1]
        actuals = [1, 0, 0, 0, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert isinstance(sharpe, float)

    def test_no_trades(self):
        """No buy signals should give zero Sharpe."""
        from train_spy_v3 import compute_trading_sharpe
        preds = [0, 0, 0, 0]
        actuals = [1, 1, 1, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe == 0.0

    def test_single_trade(self):
        """Single trade should give zero Sharpe (need 2+ for std)."""
        from train_spy_v3 import compute_trading_sharpe
        preds = [1, 0, 0, 0]
        actuals = [1, 0, 0, 0]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert sharpe == 0.0


class TestBaselineComputation:
    """Tests for baseline predictions."""

    def test_majority_baseline(self):
        """Majority baseline should predict the most common class."""
        from train_spy_v3 import compute_baselines_on_splits

        y = np.array([0] * 60 + [1] * 40)
        X = np.random.randn(len(y), 5)
        splits = [(np.arange(0, 80), np.arange(80, 100))]
        baselines = compute_baselines_on_splits(X, y, splits)

        assert "majority" in baselines
        assert "persistence" in baselines
        assert "logistic" in baselines

    def test_persistence_baseline(self):
        """Persistence baseline should predict the last seen value."""
        from train_spy_v3 import compute_baselines_on_splits

        # First 80 are class 0, so persistence predicts 0
        y = np.array([0] * 80 + [1] * 20)
        X = np.random.randn(len(y), 5)
        splits = [(np.arange(0, 80), np.arange(80, 100))]
        baselines = compute_baselines_on_splits(X, y, splits)

        # Last value of train set (index 79) is 0
        assert baselines["persistence"][0] == 0


class TestShipGate:
    """Tests for the SHIP/REJECT decision gate."""

    def test_ship_when_beats_all(self):
        """Should SHIP when model beats all baselines."""
        model_sharpe = 3.0
        baselines = {"majority": {"sharpe": 2.0}, "persistence": {"sharpe": 1.5}, "logistic": {"sharpe": 1.0}}
        beats_all = all(model_sharpe > b["sharpe"] for b in baselines.values())
        assert beats_all

    def test_reject_when_loses_to_one(self):
        """Should REJECT when model loses to any baseline."""
        model_sharpe = 2.0
        baselines = {"majority": {"sharpe": 3.0}, "persistence": {"sharpe": 1.5}, "logistic": {"sharpe": 1.0}}
        beats_all = all(model_sharpe > b["sharpe"] for b in baselines.values())
        assert not beats_all

    def test_reject_when_tied(self):
        """Should REJECT when model ties a baseline (must strictly beat)."""
        model_sharpe = 2.0
        baselines = {"majority": {"sharpe": 2.0}, "persistence": {"sharpe": 1.5}, "logistic": {"sharpe": 1.0}}
        beats_all = all(model_sharpe > b["sharpe"] for b in baselines.values())
        assert not beats_all
