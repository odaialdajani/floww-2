"""
services/ml/backtest.py

Model backtesting engine — evaluates trained models against historical data.

Walks through historical data day-by-day, computes features at each point,
runs model prediction, and compares against the actual next-day outcome.

Usage:
    from services.ml.backtest import ModelBacktester
    engine = InferenceEngine()
    backtester = ModelBacktester(engine)
    report = await backtester.run_backtest("SPY", period="2y")
    print(report.summary())
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from services.ml import DegenerateModelError
from services.ml.inference import (
    DOWN,
    HOLD,
    UP,
    InferenceEngine,
    compute_live_features,
)

log = logging.getLogger("ml.backtest")


@dataclass
class DailyPrediction:
    """Single day's prediction + outcome."""
    date: str
    ticker: str
    prediction: int
    confidence: float
    proba_down: float
    proba_hold: float
    proba_up: float
    spot: float
    next_day_return: Optional[float] = None
    next_day_direction: Optional[int] = None
    correct: Optional[bool] = None


@dataclass
class BacktestReport:
    """Full backtest results."""
    ticker: str
    model_type: str
    period: str
    n_days: int
    n_predictions: int
    n_hold_signals: int
    overall_accuracy: float
    up_accuracy: float
    down_accuracy: float
    hold_fraction: float
    high_conf_accuracy: float
    high_conf_fraction: float
    low_conf_accuracy: float
    strategy_sharpe: float
    strategy_total_return: float
    strategy_max_drawdown: float
    strategy_win_rate: float
    strategy_avg_win: float
    strategy_avg_loss: float
    strategy_profit_factor: float
    by_regime: Dict[str, float] = field(default_factory=dict)
    daily: List[DailyPrediction] = field(default_factory=list)
    computed_at: str = ""
    model_path: str = ""
    feature_count: int = 0

    def summary(self) -> str:
        lines = [
            f"=== Backtest Report: {self.ticker} ===",
            f"Model: {self.model_type} | Period: {self.period} | Days: {self.n_days}",
            "",
            "Accuracy:",
            f"  Overall:        {self.overall_accuracy:.1%}",
            f"  UP signals:     {self.up_accuracy:.1%}",
            f"  DOWN signals:   {self.down_accuracy:.1%}",
            f"  HOLD fraction:  {self.hold_fraction:.1%}",
            "",
            "Confidence Calibration:",
            f"  High conf (>.65): {self.high_conf_accuracy:.1%} ({self.high_conf_fraction:.1%} of signals)",
            f"  Low conf  (<=.55): {self.low_conf_accuracy:.1%}",
            "",
            "Strategy (go long/short on non-HOLD signals):",
            f"  Sharpe:         {self.strategy_sharpe:.2f}",
            f"  Total return:   {self.strategy_total_return:.1%}",
            f"  Max drawdown:   {self.strategy_max_drawdown:.1%}",
            f"  Win rate:       {self.strategy_win_rate:.1%}",
            f"  Avg win:        {self.strategy_avg_win:.2%}",
            f"  Avg loss:       {self.strategy_avg_loss:.2%}",
            f"  Profit factor:  {self.strategy_profit_factor:.2f}",
        ]
        if self.by_regime:
            lines.append("")
            lines.append("By Regime:")
            for regime, acc in sorted(self.by_regime.items()):
                lines.append(f"  {regime}: {acc:.1%}")
        return "\n".join(lines)


class ModelBacktester:
    """Walk-forward backtesting for ML models."""

    def __init__(self, engine: Optional[InferenceEngine] = None):
        self.engine = engine or InferenceEngine()

    async def run_backtest(
        self,
        ticker: str,
        period: str = "2y",
        min_history_days: int = 60,
    ) -> BacktestReport:
        """Run a full walk-forward backtest."""
        ticker = ticker.upper()
        log.info(f"Starting backtest for {ticker} (period={period})")

        features_df = await asyncio.to_thread(compute_live_features, ticker, period)
        if features_df is None or len(features_df) < min_history_days + 5:
            raise DegenerateModelError(
                f"Insufficient data for {ticker}: {len(features_df) if features_df is not None else 0} rows"
            )

        model, manifest = self.engine._load_model(ticker)
        feature_names = manifest.get("feature_names", [])
        model_type = manifest.get("model_type", "unknown")

        import yfinance as yf
        raw = await asyncio.to_thread(
            lambda: yf.download(ticker, period=period, progress=False)
        )
        if raw is None or (hasattr(raw, 'empty') and raw.empty):
            raise DegenerateModelError(f"Could not fetch price data for {ticker}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        close = raw["Close"].astype(float)
        close = close.reindex(features_df.index, method="ffill")

        daily_results: List[DailyPrediction] = []
        start_idx = min_history_days
        end_idx = len(features_df) - 1

        for i in range(start_idx, end_idx):
            current_date = features_df.index[i]
            next_date = features_df.index[i + 1]

            if feature_names:
                missing = [f for f in feature_names if f not in features_df.columns]
                for f in missing:
                    features_df[f] = 0.0
                X = features_df[feature_names].iloc[i:i + 1].values.astype(float)
            else:
                X = features_df.iloc[i:i + 1].values.astype(float)

            try:
                raw_pred = int(model.predict(X)[0])
                probabilities = None
                if hasattr(model, "predict_proba"):
                    probabilities = model.predict_proba(X)[0].tolist()
            except Exception as e:
                log.warning(f"Prediction failed for {ticker} on {current_date}: {e}")
                continue

            from services.ml.inference import _map_binary_to_3way
            if probabilities and len(probabilities) == 2:
                pred_3way, proba_3way = _map_binary_to_3way(raw_pred, probabilities)
                confidence = max(proba_3way)
                p_down, p_hold, p_up = proba_3way
            else:
                pred_3way = UP if raw_pred == 1 else DOWN
                p = 0.5 if not probabilities else probabilities[raw_pred]
                confidence = float(p)
                p_down, p_hold, p_up = (1.0 - p, 0.0, p) if pred_3way == UP else (p, 0.0, 1.0 - p)

            current_close = float(close.loc[current_date]) if current_date in close.index else None
            next_close = float(close.loc[next_date]) if next_date in close.index else None

            if current_close is None or next_close is None or current_close == 0:
                continue

            next_return = (next_close - current_close) / current_close
            next_direction = 1 if next_return > 0 else 0

            if pred_3way == UP:
                correct = next_return > 0
            elif pred_3way == DOWN:
                correct = next_return < 0
            else:
                correct = abs(next_return) < 0.005

            spot_val = float(features_df["close"].iloc[i]) if "close" in features_df.columns else current_close

            daily_results.append(DailyPrediction(
                date=str(current_date.date()) if hasattr(current_date, 'date') else str(current_date),
                ticker=ticker,
                prediction=pred_3way,
                confidence=confidence,
                proba_down=p_down,
                proba_hold=p_hold,
                proba_up=p_up,
                spot=spot_val,
                next_day_return=next_return,
                next_day_direction=next_direction,
                correct=correct,
            ))

        if not daily_results:
            raise DegenerateModelError(f"No predictions generated for {ticker}")

        return self._compute_report(daily_results, ticker, model_type, period, manifest)

    def _compute_report(
        self,
        daily: List[DailyPrediction],
        ticker: str,
        model_type: str,
        period: str,
        manifest: Dict,
    ) -> BacktestReport:
        """Compute performance metrics from daily predictions."""
        n = len(daily)
        non_hold = [d for d in daily if d.prediction != HOLD]
        n_non_hold = len(non_hold)
        n_correct = sum(1 for d in non_hold if d.correct)
        overall_accuracy = n_correct / n_non_hold if n_non_hold > 0 else 0.0

        up_signals = [d for d in daily if d.prediction == UP]
        down_signals = [d for d in daily if d.prediction == DOWN]
        up_accuracy = sum(1 for d in up_signals if d.correct) / len(up_signals) if up_signals else 0.0
        down_accuracy = sum(1 for d in down_signals if d.correct) / len(down_signals) if down_signals else 0.0
        hold_fraction = sum(1 for d in daily if d.prediction == HOLD) / n

        high_conf = [d for d in non_hold if d.confidence > 0.65]
        low_conf = [d for d in non_hold if d.confidence <= 0.55]
        high_conf_accuracy = sum(1 for d in high_conf if d.correct) / len(high_conf) if high_conf else 0.0
        low_conf_accuracy = sum(1 for d in low_conf if d.correct) / len(low_conf) if low_conf else 0.0
        high_conf_fraction = len(high_conf) / n_non_hold if n_non_hold > 0 else 0.0

        strategy_returns = []
        for d in daily:
            if d.prediction == UP and d.next_day_return is not None:
                strategy_returns.append(d.next_day_return)
            elif d.prediction == DOWN and d.next_day_return is not None:
                strategy_returns.append(-d.next_day_return)

        if strategy_returns:
            rets = np.array(strategy_returns)
            total_return = float(np.prod(1 + rets) - 1)
            mean_ret = np.mean(rets)
            std_ret = np.std(rets)
            sharpe = float(mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
            cumulative = np.cumprod(1 + rets)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            max_drawdown = float(np.min(drawdowns))
            wins = [r for r in strategy_returns if r > 0]
            losses = [r for r in strategy_returns if r < 0]
            win_rate = len(wins) / len(strategy_returns) if strategy_returns else 0.0
            avg_win = float(np.mean(wins)) if wins else 0.0
            avg_loss = float(np.mean(losses)) if losses else 0.0
            gross_profit = sum(wins)
            gross_loss = abs(sum(losses))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        else:
            sharpe = total_return = max_drawdown = win_rate = 0.0
            avg_win = avg_loss = profit_factor = 0.0

        return BacktestReport(
            ticker=ticker,
            model_type=model_type,
            period=period,
            n_days=n,
            n_predictions=n_non_hold,
            n_hold_signals=n - n_non_hold,
            overall_accuracy=overall_accuracy,
            up_accuracy=up_accuracy,
            down_accuracy=down_accuracy,
            hold_fraction=hold_fraction,
            high_conf_accuracy=high_conf_accuracy,
            high_conf_fraction=high_conf_fraction,
            low_conf_accuracy=low_conf_accuracy,
            strategy_sharpe=sharpe,
            strategy_total_return=total_return,
            strategy_max_drawdown=max_drawdown,
            strategy_win_rate=win_rate,
            strategy_avg_win=avg_win,
            strategy_avg_loss=avg_loss,
            strategy_profit_factor=profit_factor,
            daily=daily,
            computed_at=datetime.now(timezone.utc).isoformat(),
            model_path=manifest.get("model_path", ""),
            feature_count=manifest.get("n_features", 0),
        )
