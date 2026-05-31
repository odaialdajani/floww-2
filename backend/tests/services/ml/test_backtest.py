"""Tests for ModelBacktester and BacktestReport."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.ml.backtest import BacktestReport, DailyPrediction, ModelBacktester
from services.ml.inference import DOWN, HOLD, UP


class TestBacktestReport:
    def test_summary_non_empty(self):
        report = BacktestReport(
            ticker="SPY", model_type="gbm", period="2y", n_days=100,
            n_predictions=80, n_hold_signals=20,
            overall_accuracy=0.60, up_accuracy=0.65, down_accuracy=0.55,
            hold_fraction=0.20, high_conf_accuracy=0.70,
            high_conf_fraction=0.30, low_conf_accuracy=0.50,
            strategy_sharpe=1.2, strategy_total_return=0.15,
            strategy_max_drawdown=-0.08, strategy_win_rate=0.58,
            strategy_avg_win=0.012, strategy_avg_loss=-0.008,
            strategy_profit_factor=1.8,
        )
        summary = report.summary()
        assert "SPY" in summary
        assert "60.0%" in summary

    def test_summary_with_regime(self):
        report = BacktestReport(
            ticker="SPY", model_type="gbm", period="2y", n_days=100,
            n_predictions=80, n_hold_signals=20,
            overall_accuracy=0.60, up_accuracy=0.65, down_accuracy=0.55,
            hold_fraction=0.20, high_conf_accuracy=0.70,
            high_conf_fraction=0.30, low_conf_accuracy=0.50,
            strategy_sharpe=1.2, strategy_total_return=0.15,
            strategy_max_drawdown=-0.08, strategy_win_rate=0.58,
            strategy_avg_win=0.012, strategy_avg_loss=-0.008,
            strategy_profit_factor=1.8,
            by_regime={"positive_gamma": 0.65, "negative_gamma": 0.55},
        )
        assert "positive_gamma" in report.summary()


class TestComputeReport:
    def _make_daily(self, n=50, seed=42):
        import numpy as np
        np.random.seed(seed)
        daily = []
        for i in range(n):
            pred = int(np.random.choice([UP, DOWN, HOLD], p=[0.4, 0.4, 0.2]))
            conf = float(np.random.uniform(0.45, 0.85))
            ret = float(np.random.normal(0.0003, 0.012))
            if pred == UP:
                correct = ret > 0
                p_down, p_hold, p_up = 0.2, 0.1, 0.7
            elif pred == DOWN:
                correct = ret < 0
                p_down, p_hold, p_up = 0.7, 0.1, 0.2
            else:
                correct = abs(ret) < 0.005
                p_down, p_hold, p_up = 0.25, 0.5, 0.25
            daily.append(DailyPrediction(
                date=f"2024-01-{i+1:02d}", ticker="SPY", prediction=pred,
                confidence=conf, proba_down=p_down, proba_hold=p_hold, proba_up=p_up,
                spot=450.0 + i * 0.1, next_day_return=ret,
                next_day_direction=1 if ret > 0 else 0, correct=correct,
            ))
        return daily

    def test_compute_report_basic(self):
        tester = ModelBacktester.__new__(ModelBacktester)
        report = tester._compute_report(
            daily=self._make_daily(n=50), ticker="TEST", model_type="test",
            period="1y", manifest={"model_path": "/tmp/test.joblib", "n_features": 5},
        )
        assert report.ticker == "TEST"
        assert report.n_days == 50
        assert 0.0 <= report.overall_accuracy <= 1.0

    def test_compute_report_all_correct(self):
        daily = [
            DailyPrediction(
                date="2024-01-01", ticker="SPY", prediction=UP,
                confidence=0.8, proba_down=0.1, proba_hold=0.1, proba_up=0.8,
                spot=450.0, next_day_return=0.01, next_day_direction=1, correct=True,
            )
            for _ in range(20)
        ]
        tester = ModelBacktester.__new__(ModelBacktester)
        report = tester._compute_report(
            daily=daily, ticker="SPY", model_type="test",
            period="1y", manifest={"model_path": "/tmp/t.joblib", "n_features": 3},
        )
        assert report.overall_accuracy == 1.0

    def test_compute_report_all_wrong(self):
        daily = [
            DailyPrediction(
                date="2024-01-01", ticker="SPY", prediction=UP,
                confidence=0.8, proba_down=0.1, proba_hold=0.1, proba_up=0.8,
                spot=450.0, next_day_return=-0.01, next_day_direction=0, correct=False,
            )
            for _ in range(20)
        ]
        tester = ModelBacktester.__new__(ModelBacktester)
        report = tester._compute_report(
            daily=daily, ticker="SPY", model_type="test",
            period="1y", manifest={"model_path": "/tmp/t.joblib", "n_features": 3},
        )
        assert report.overall_accuracy == 0.0

    def test_compute_report_confidence_calibration(self):
        daily = []
        for i in range(10):
            daily.append(DailyPrediction(
                date=f"2024-01-{i+1:02d}", ticker="SPY", prediction=UP,
                confidence=0.8, proba_down=0.1, proba_hold=0.1, proba_up=0.8,
                spot=450.0, next_day_return=0.01, next_day_direction=1, correct=True,
            ))
        for i in range(10):
            daily.append(DailyPrediction(
                date=f"2024-02-{i+1:02d}", ticker="SPY", prediction=UP,
                confidence=0.5, proba_down=0.25, proba_hold=0.25, proba_up=0.5,
                spot=450.0, next_day_return=-0.01, next_day_direction=0, correct=False,
            ))
        tester = ModelBacktester.__new__(ModelBacktester)
        report = tester._compute_report(
            daily=daily, ticker="SPY", model_type="test",
            period="1y", manifest={"model_path": "/tmp/t.joblib", "n_features": 3},
        )
        assert report.high_conf_accuracy == 1.0
        assert report.low_conf_accuracy == 0.0

    def test_compute_report_empty_hold_only(self):
        daily = [
            DailyPrediction(
                date="2024-01-01", ticker="SPY", prediction=HOLD,
                confidence=0.5, proba_down=0.25, proba_hold=0.5, proba_up=0.25,
                spot=450.0, next_day_return=0.001, next_day_direction=1, correct=True,
            )
            for _ in range(10)
        ]
        tester = ModelBacktester.__new__(ModelBacktester)
        report = tester._compute_report(
            daily=daily, ticker="SPY", model_type="test",
            period="1y", manifest={"model_path": "/tmp/t.joblib", "n_features": 3},
        )
        assert report.n_predictions == 0
        assert report.hold_fraction == 1.0
