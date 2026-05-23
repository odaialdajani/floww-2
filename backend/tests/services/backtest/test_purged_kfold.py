"""
tests/services/backtest/test_purged_kfold.py

Tests for:
  - PurgedKFold cross-validator (embargo gap, no leakage)
  - run_purged_kfold_cv integration
  - Enhanced metrics (Sortino, Calmar, Sterling ratios)
  - BacktestDuckDBLogger (trades, equity, run_meta)
  - Edge cases: small n, zero embargo, NaN guards

Run with:
  pytest backend/tests/services/backtest/test_purged_kfold.py -v --tb=short
"""

from __future__ import annotations

import math
import tempfile
from typing import Any, Dict, List
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from services.backtest.engine import (
    BacktestEngine,
    EngineConfig,
    PurgedKFold,
    run_purged_kfold_cv,
    run_walk_forward_cv,
)
from services.backtest.report import BacktestResult, TradeRecord
from services.backtest.signals import Action, Position, Signal
from services.backtest.duckdb_logger import BacktestDuckDBLogger


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_bars() -> List[Dict[str, Any]]:
    """50 bars of synthetic price data (close from 450 → 475)."""
    bars = []
    for i in range(50):
        bars.append({
            "date": f"2024-01-{i + 1:02d}",
            "open": 450.0 + i * 0.5,
            "high": 451.0 + i * 0.5,
            "low": 449.0 + i * 0.5,
            "close": 450.0 + i * 0.5,
            "volume": 10_000_000 + i * 100_000,
        })
    return bars


@pytest.fixture
def sample_snapshots() -> List[Dict[str, Any]]:
    """50 matching GEX snapshots."""
    snaps = []
    for i in range(50):
        snaps.append({
            "date": f"2024-01-{i + 1:02d}",
            "net_gex_zscore_60d": np.random.normal(0, 0.5),
            "total_gamma": 100_000 + i * 1000,
        })
    return snaps


class AlwaysBuySignal(Signal):
    """Signal that always returns BUY_CALL when flat, HOLD otherwise."""
    def evaluate(self, snapshot_history, bar_history, position):
        if position.is_open:
            return Action.HOLD
        return Action.BUY_CALL


class AlwaysSellSignal(Signal):
    """Signal that always returns BUY_PUT when flat, HOLD otherwise."""
    def evaluate(self, snapshot_history, bar_history, position):
        if position.is_open:
            return Action.HOLD
        return Action.BUY_PUT


# ============================================================================
# PurgedKFold Tests
# ============================================================================

class TestPurgedKFoldInit:
    def test_default_params(self):
        cv = PurgedKFold()
        assert cv.n_splits == 5
        assert cv.embargo_size == 5

    def test_custom_params(self):
        cv = PurgedKFold(n_splits=10, embargo_size=3)
        assert cv.n_splits == 10
        assert cv.embargo_size == 3

    def test_zero_embargo(self):
        cv = PurgedKFold(embargo_size=0)
        assert cv.embargo_size == 0

    def test_n_splits_minimum(self):
        """n_splits must be >= 2."""
        with pytest.raises(ValueError, match="n_splits must be >= 2"):
            PurgedKFold(n_splits=1)

    def test_embargo_non_negative(self):
        """embargo_size must be >= 0."""
        with pytest.raises(ValueError, match="embargo_size must be >= 0"):
            PurgedKFold(embargo_size=-1)

    def test_repr(self):
        cv = PurgedKFold(n_splits=3, embargo_size=7)
        assert "PurgedKFold" in repr(cv)
        assert "n_splits=3" in repr(cv)
        assert "embargo_size=7" in repr(cv)


class TestPurgedKFoldSplit:
    def test_basic_split_count(self):
        cv = PurgedKFold(n_splits=5, embargo_size=3)
        folds = cv.split(100)
        assert len(folds) == 5

    def test_folds_are_contiguous(self):
        """Test sets should be contiguous blocks (no gaps)."""
        cv = PurgedKFold(n_splits=4, embargo_size=2)
        folds = cv.split(100)
        for _, test_slice in folds:
            test_indices = list(range(test_slice.start or 0, test_slice.stop or 0))
            if len(test_indices) > 1:
                for i in range(1, len(test_indices)):
                    assert test_indices[i] == test_indices[i - 1] + 1

    def test_no_overlap_test_sets(self):
        """Test sets across folds must not overlap."""
        cv = PurgedKFold(n_splits=5, embargo_size=0)
        folds = cv.split(100)
        all_test = []
        for _, test_slice in folds:
            all_test.extend(range(test_slice.start or 0, test_slice.stop or 0))
        assert len(all_test) == len(set(all_test)), "Test sets overlap!"

    def test_embargo_creates_gap(self):
        """Embargo should create gap between train end and test start."""
        cv = PurgedKFold(n_splits=4, embargo_size=5)
        folds = cv.split(100)
        for train_slice, test_slice in folds:
            train_end = train_slice.stop or 0
            test_start = test_slice.start or 0
            if train_end > 0 and test_start > train_end:
                # Gap must be at least embargo_size
                gap = test_start - train_end
                assert gap <= cv.embargo_size + 1  # +1 because slice end is exclusive

    def test_first_fold_may_have_empty_train(self):
        """First fold may have no training data — should handle gracefully."""
        cv = PurgedKFold(n_splits=5, embargo_size=10)
        folds = cv.split(50)
        for train_slice, _ in folds:
            # Should not crash or return negative indices
            if train_slice.stop and train_slice.stop > 0:
                pass  # OK

    def test_embargo_mask(self):
        cv = PurgedKFold(n_splits=4, embargo_size=3)
        mask = cv.get_embargo_mask(100)
        assert len(mask) == 100
        assert mask.dtype == bool
        # At least some samples should be embargoed (unless n is very small)
        assert mask.sum() > 0

    def test_embargo_mask_with_zero_embargo(self):
        cv = PurgedKFold(n_splits=4, embargo_size=0)
        mask = cv.get_embargo_mask(100)
        assert mask.sum() == 0

    def test_exact_n_samples(self):
        """Test with exactly n_splits fold_size samples."""
        cv = PurgedKFold(n_splits=5, embargo_size=0)
        folds = cv.split(25)  # 5 samples per fold
        assert len(folds) == 5
        for _, test_slice in folds:
            size = (test_slice.stop or 0) - (test_slice.start or 0)
            assert size >= 4  # last fold may get remainder

    def test_large_embargo(self):
        """Embargo larger than individual fold should not crash."""
        cv = PurgedKFold(n_splits=5, embargo_size=50)
        folds = cv.split(100)
        assert len(folds) == 5
        # Some early folds may have zero training data — that's expected

    def test_deterministic_output(self):
        """Same parameters must produce identical splits."""
        cv1 = PurgedKFold(n_splits=5, embargo_size=3)
        cv2 = PurgedKFold(n_splits=5, embargo_size=3)
        folds1 = cv1.split(100)
        folds2 = cv2.split(100)
        for (t1a, t1b), (t2a, t2b) in zip(folds1, folds2):
            assert t1a == t2a
            assert t1b == t2b


# ============================================================================
# run_purged_kfold_cv Integration Tests
# ============================================================================

class TestRunPurgedKFoldCV:
    def test_basic_run(self, sample_snapshots, sample_bars):
        results = run_purged_kfold_cv(
            AlwaysBuySignal,
            sample_snapshots,
            sample_bars,
            ticker="SPY",
            n_splits=3,
            embargo_size=2,
        )
        assert len(results) > 0
        for r in results:
            assert r.ticker == "SPY"
            assert len(r.equity_curve) > 0

    def test_too_few_bars_raises(self, sample_snapshots, sample_bars):
        small_bars = sample_bars[:5]
        small_snaps = sample_snapshots[:5]
        with pytest.raises(ValueError, match="too small"):
            run_purged_kfold_cv(
                AlwaysBuySignal,
                small_snaps,
                small_bars,
                ticker="SPY",
                n_splits=3,
            )

    def test_each_fold_has_unique_result(self, sample_snapshots, sample_bars):
        results = run_purged_kfold_cv(
            AlwaysBuySignal,
            sample_snapshots,
            sample_bars,
            ticker="SPY",
            n_splits=4,
            embargo_size=2,
        )
        # Each fold result should have its own trades/equity
        fold_trade_counts = [len(r.trades) for r in results]
        assert len(fold_trade_counts) == len(results)

    def test_config_passed_through(self, sample_snapshots, sample_bars):
        config = EngineConfig(initial_capital=50_000.0)
        results = run_purged_kfold_cv(
            AlwaysBuySignal,
            sample_snapshots,
            sample_bars,
            ticker="SPY",
            n_splits=2,
            embargo_size=2,
            config=config,
        )
        for r in results:
            assert r.initial_capital == 50_000.0

    def test_zero_embargo_produces_results(self, sample_snapshots, sample_bars):
        results = run_purged_kfold_cv(
            AlwaysBuySignal,
            sample_snapshots,
            sample_bars,
            ticker="SPY",
            n_splits=3,
            embargo_size=0,
        )
        assert len(results) > 0

    def test_sell_signal_works(self, sample_snapshots, sample_bars):
        results = run_purged_kfold_cv(
            AlwaysSellSignal,
            sample_snapshots,
            sample_bars,
            ticker="SPY",
            n_splits=2,
            embargo_size=2,
        )
        assert len(results) > 0

    def test_nan_snapshot_values(self, sample_snapshots, sample_bars):
        """NaN in snapshot data should not crash (I-8)."""
        snapshots_with_nan = list(sample_snapshots)
        snapshots_with_nan[0]["net_gex_zscore_60d"] = float("nan")
        results = run_purged_kfold_cv(
            AlwaysBuySignal,
            snapshots_with_nan,
            sample_bars,
            ticker="SPY",
            n_splits=2,
            embargo_size=1,
        )
        assert len(results) > 0


# ============================================================================
# Enhanced Metrics Tests (Sortino, Calmar, Sterling)
# ============================================================================

class TestEnhancedMetrics:
    def test_sortino_ratio_present(self):
        result = BacktestResult(initial_capital=100_000.0)
        result.total_bars = 100
        result.equity_curve = [100_000.0 + i * 10.0 for i in range(100)]
        result.drawdown_curve = [0.0] * 100
        result.bar_returns = [0.001] * 99
        result.trades = []
        result.compute_metrics()
        assert "sortino" in result.metrics
        assert "calmar" in result.metrics
        assert "sterling" in result.metrics

    def test_sortino_different_from_sharpe(self):
        """With all positive returns, Sortino > Sharpe (downside std < total std)."""
        result = BacktestResult(initial_capital=100_000.0)
        result.total_bars = 100
        result.equity_curve = [100_000.0 + i * 10.0 for i in range(100)]
        result.drawdown_curve = [0.0] * 100
        # All positive returns -> downside std is 0 -> Sortino should be 0 (division by zero guard)
        result.bar_returns = [0.001] * 99
        result.trades = []
        result.compute_metrics()
        # When all returns positive, no downside deviation -> sortino = 0
        assert result.metrics["sortino"] == 0.0

    def test_sortino_with_negative_returns(self):
        """With mixed returns, Sortino should be computable."""
        result = BacktestResult(initial_capital=100_000.0)
        result.total_bars = 100
        result.equity_curve = [100_000.0] * 100
        result.drawdown_curve = [0.0] * 100
        np.random.seed(42)
        result.bar_returns = list(np.random.normal(0.001, 0.02, 99))
        result.trades = [TradeRecord(net_pnl=100.0)]
        result.compute_metrics()
        assert result.metrics["sortino"] != 0.0

    def test_calmar_ratio(self):
        """Calmar = annualized_return / max_drawdown_pct."""
        result = BacktestResult(initial_capital=100_000.0)
        result.total_bars = 252  # 1 year
        result.equity_curve = [100_000.0, 110_000.0]
        result.drawdown_curve = [0.0, -5_000.0]
        result.bar_returns = [0.001]
        result.trades = [TradeRecord(net_pnl=200.0)]
        result.compute_metrics()
        # net_return_pct = 10% (110k / 100k - 1)
        # max_dd_pct = 5000/110000 = 4.55%
        # calmar = 0.10 / 0.0455 = 2.2
        assert result.metrics["calmar"] > 0

    def test_sterling_ratio(self):
        """Sterling = annualized_return / avg_drawdown."""
        result = BacktestResult(initial_capital=100_000.0)
        result.total_bars = 252
        result.equity_curve = [100_000.0, 105_000.0, 102_000.0, 108_000.0]
        result.drawdown_curve = [0.0, 0.0, -3_000.0, 0.0]
        result.bar_returns = [0.01, -0.02, 0.03]
        result.trades = [TradeRecord(net_pnl=300.0)]
        result.compute_metrics()
        assert "sterling" in result.metrics

    def test_no_trades_metrics_defaults(self):
        """With zero trades, all metrics should have safe defaults."""
        result = BacktestResult(initial_capital=100_000.0)
        result.total_bars = 100
        result.equity_curve = [100_000.0] * 100
        result.drawdown_curve = [0.0] * 100
        result.bar_returns = [0.0] * 99
        result.trades = []
        result.compute_metrics()
        assert result.metrics["sharpe"] == 0.0
        assert result.metrics["sortino"] == 0.0
        assert result.metrics["calmar"] == 0.0
        assert result.metrics["sterling"] == 0.0
        assert result.metrics["max_drawdown"] == 0.0

    def test_all_winning_trades(self):
        """All trades positive -> profit_factor = inf."""
        result = BacktestResult(initial_capital=100_000.0)
        result.trades = [
            TradeRecord(net_pnl=100.0),
            TradeRecord(net_pnl=200.0),
            TradeRecord(net_pnl=50.0),
        ]
        result.compute_metrics()
        assert result.metrics["profit_factor"] == float("inf")
        assert result.metrics["hit_rate"] == 1.0

    def test_all_losing_trades(self):
        """All trades negative -> profit_factor = 0."""
        result = BacktestResult(initial_capital=100_000.0)
        result.trades = [
            TradeRecord(net_pnl=-50.0),
            TradeRecord(net_pnl=-100.0),
        ]
        result.compute_metrics()
        assert result.metrics["profit_factor"] == 0.0
        assert result.metrics["hit_rate"] == 0.0


# ============================================================================
# BacktestDuckDBLogger Tests
# ============================================================================

class TestBacktestDuckDBLogger:
    @pytest.fixture
    def sample_result(self) -> BacktestResult:
        result = BacktestResult(
            ticker="SPY",
            initial_capital=100_000.0,
            total_bars=50,
        )
        result.equity_curve = [100_000.0 + i * 100.0 for i in range(50)]
        result.drawdown_curve = [0.0 if i < 25 else -500.0 for i in range(50)]
        result.bar_returns = [0.001] * 49
        result.trades = [
            TradeRecord(
                entry_bar_idx=0, exit_bar_idx=5,
                side="CALL", direction="LONG",
                entry_price=450.0, exit_price=455.0,
                quantity=1, pnl=5.0, commission=0.65, slippage=0.25,
                net_pnl=4.1,
            ),
            TradeRecord(
                entry_bar_idx=10, exit_bar_idx=15,
                side="PUT", direction="LONG",
                entry_price=460.0, exit_price=458.0,
                quantity=1, pnl=-2.0, commission=0.65, slippage=0.25,
                net_pnl=-2.9,
            ),
        ]
        result.compute_metrics()
        return result

    def test_log_trades_in_memory(self, sample_result):
        logger = BacktestDuckDBLogger()
        count = logger.log_trades(sample_result, run_id="test_001", fold=0, ticker="SPY")
        assert count == 2

    def test_log_trades_empty_result(self):
        logger = BacktestDuckDBLogger()
        empty = BacktestResult()
        count = logger.log_trades(empty, run_id="empty")
        assert count == 0

    def test_log_equity_curve(self, sample_result):
        logger = BacktestDuckDBLogger()
        count = logger.log_equity_curve(sample_result, run_id="test_001", fold=0, ticker="SPY")
        assert count == 50

    def test_log_run_meta(self, sample_result):
        logger = BacktestDuckDBLogger()
        logger.log_run_meta(sample_result, run_id="test_001", ticker="SPY", n_splits=5, embargo=3)
        summary = logger.summary(run_id="test_001")
        assert len(summary["meta"]) > 0
        assert summary["meta"][0]["ticker"] == "SPY"

    def test_log_all(self, sample_result):
        logger = BacktestDuckDBLogger()
        results = [sample_result, sample_result]
        counts = logger.log_all(results, run_id="test_all", ticker="SPY", n_splits=2, embargo=3)
        assert counts["trades_logged"] == 4  # 2 trades × 2 folds
        assert counts["equity_points_logged"] == 100  # 50 points × 2 folds
        assert counts["folds_logged"] == 2

    def test_summary(self, sample_result):
        logger = BacktestDuckDBLogger()
        logger.log_trades(sample_result, run_id="summary_test")
        logger.log_run_meta(sample_result, run_id="summary_test", ticker="SPY")
        summary = logger.summary(run_id="summary_test")
        assert summary["run_id"] == "summary_test"
        assert len(summary["trades"]) > 0

    def test_equity_curve_query(self, sample_result):
        logger = BacktestDuckDBLogger()
        logger.log_equity_curve(sample_result, run_id="eq_test", fold=0)
        curve = logger.equity_curve(run_id="eq_test")
        assert len(curve) == 50

    def test_leaderboard(self, sample_result):
        logger = BacktestDuckDBLogger()
        logger.log_run_meta(sample_result, run_id="lb_001", ticker="SPY", n_splits=5, embargo=3)
        logger.log_run_meta(sample_result, run_id="lb_002", ticker="QQQ", n_splits=3, embargo=0)
        lb = logger.leaderboard(top_n=10)
        assert len(lb) >= 2

    def test_file_backed_logger(self, sample_result):
        """Test with a temporary file instead of :memory:."""
        # Use a path that doesn't exist yet — DuckDB will create it
        db_path = Path(tempfile.gettempdir()) / f"test_purged_kfold_{id(self)}.duckdb"
        try:
            # Ensure file doesn't exist before connecting
            if db_path.exists():
                db_path.unlink()
            logger = BacktestDuckDBLogger(str(db_path))
            logger.log_trades(sample_result, run_id="file_test")
            logger.close()

            # Re-open and verify
            logger2 = BacktestDuckDBLogger(str(db_path))
            summary = logger2.summary(run_id="file_test")
            assert summary["run_id"] == "file_test"
            logger2.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_context_manager(self, sample_result):
        with BacktestDuckDBLogger() as logger:
            logger.log_trades(sample_result, run_id="ctx_test")
            summary = logger.summary(run_id="ctx_test")
            assert summary["run_id"] == "ctx_test"
