#!/usr/bin/env python3
import logging

logger = logging.getLogger(__name__)

"""
backend/scripts/backtest_regime_filtered.py

Regime-filtered ML backtest.

Only takes trades when:
  1. Model confidence >= threshold (default 0.55)
  2. GEX regime is "positive" (favorable for mean-reversion)
  3. Volatility is below threshold (avoid high-vol whipsaws)

Uses the same walk-forward CV as train_spy_ml.py but filters trades.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("backtest_regime")

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts.train_spy_ml import (
    build_dataset,
    fetch_spot_history,
)
from scripts.train_with_baselines import compute_trading_sharpe


def _sharpe(predictions, actuals):
    """Compute annualized trading Sharpe."""
    rets = []
    for p, a in zip(predictions, actuals):
        if p == 1:
            rets.append(1.0 if a == 1 else -1.0)
    if len(rets) < 2:
        return 0.0
    std = np.std(rets)
    if std < 1e-10:
        return 0.0
    return float(np.mean(rets) / std * np.sqrt(252))


def make_walk_forward_splits(X, y, timestamps, n_splits=5):
    """Create walk-forward train/test splits."""
    n = len(X)
    split_size = n // (n_splits + 1)
    splits = []
    for i in range(n_splits):
        train_end = split_size * (i + 1)
        test_end = min(train_end + split_size, n)
        if test_end <= train_end or train_end < 50:
            continue
        splits.append((
            X[:train_end], y[:train_end],
            X[train_end:test_end], y[train_end:test_end],
            timestamps[train_end:test_end],
        ))
    return splits


def load_gex_regime(ticker: str, dates: list) -> dict:
    """Load GEX regime for given dates from cached data."""
    try:
        import yfinance as yf

        # Use a simple heuristic: if spot > 20-day SMA, regime is "positive"
        data = yf.download(ticker, period="6mo", progress=False)
        if data.empty:
            return {d: "unknown" for d in dates}
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        sma20 = data["Close"].rolling(20).mean()
        regimes = {}
        for d in dates:
            try:
                idx = data.index.get_loc(d) if d in data.index else None
                if idx is not None and idx >= 20:
                    regimes[d] = "positive" if data["Close"].iloc[idx] > sma20.iloc[idx] else "negative"
                else:
                    regimes[d] = "unknown"
            except Exception:
                regimes[d] = "unknown"
        return regimes
    except Exception:
        return {d: "unknown" for d in dates}


def backtest_regime_filtered(
    ticker: str = "SPY",
    days: int = 252,
    n_splits: int = 5,
    confidence_threshold: float = 0.55,
    vol_threshold: float = 0.25,
    require_positive_regime: bool = True,
    model_type: str = "rf",
) -> dict:
    """Run regime-filtered backtest.

    Args:
        ticker: Ticker symbol
        days: Lookback period
        n_splits: Number of walk-forward splits
        confidence_threshold: Minimum prediction confidence to trade
        vol_threshold: Maximum annualized volatility to trade
        require_positive_regime: Only trade when GEX regime is positive
        model_type: "rf" or "gbm"

    Returns:
        Dict with backtest results
    """
    log.info(f"Regime-filtered backtest: {ticker} days={days} splits={n_splits}")
    log.info(f"  confidence_threshold={confidence_threshold} vol_threshold={vol_threshold}")
    log.info(f"  require_positive_regime={require_positive_regime}")

    t0 = time.time()

    # Fetch data
    price_df = fetch_spot_history(ticker, days)
    if price_df is None or len(price_df) < 100:
        return {"status": "error", "reason": "insufficient data"}

    # Build features
    X, y, feature_names, timestamps = build_dataset(price_df, live_chain=None, days_back=days)
    if X is None or len(X) < 100:
        return {"status": "error", "reason": "insufficient features"}

    # Load GEX regime
    date_strs = [str(d)[:10] for d in timestamps]
    regime_map = load_gex_regime(ticker, date_strs)

    # Compute realized vol for filtering
    returns = np.diff(np.log(X[:, 0])) if X.shape[1] > 0 else np.zeros(len(X))
    vol_20d = pd.Series(returns).rolling(20).std().values * np.sqrt(252)

    # Walk-forward backtest
    splits = make_walk_forward_splits(X, y, timestamps, n_splits=n_splits)

    all_preds = []
    all_actuals = []
    all_dates = []
    all_confidences = []
    filtered_count = 0
    total_signals = 0

    for fold_idx, (train_X, train_y, test_X, test_y, test_ts) in enumerate(splits):
        if len(train_X) < 50 or len(test_X) < 10:
            continue

        # Train model
        if model_type == "rf":
            model = RandomForestClassifier(
                n_estimators=100, max_depth=5, min_samples_leaf=20,
                random_state=42, n_jobs=-1,
            )
        else:
            model = GradientBoostingClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.05,
                subsample=0.7, min_samples_leaf=20, random_state=42,
            )

        model.fit(train_X, train_y)

        # Predict with confidence
        preds = model.predict(test_X)
        if hasattr(model, "predict_proba"):
            probas = model.predict_proba(test_X)
            confidences = np.max(probas, axis=1)
        else:
            confidences = np.ones(len(preds)) * 0.5

        # Apply regime filter
        for i in range(len(preds)):
            total_signals += 1
            date_str = str(test_ts[i])[:10] if i < len(test_ts) else ""
            regime = regime_map.get(date_str, "unknown")
            vol = vol_20d[min(len(vol_20d) - 1, len(train_X) + i)] if len(vol_20d) > 0 else 0.0

            # Filter conditions
            skip = False
            if confidences[i] < confidence_threshold:
                skip = True
            if require_positive_regime and regime != "positive":
                skip = True
            if vol > vol_threshold:
                skip = True

            if skip:
                filtered_count += 1
                # Don't count this as a trade (skip it)
                continue

            all_preds.append(preds[i])
            all_actuals.append(test_y[i])
            all_dates.append(date_str)
            all_confidences.append(confidences[i])

    # Compute results
    if len(all_preds) < 5:
        return {
            "status": "insufficient_trades",
            "total_signals": total_signals,
            "filtered": filtered_count,
            "trades_taken": len(all_preds),
        }

    all_preds = np.array(all_preds)
    all_actuals = np.array(all_actuals)

    accuracy = float(np.mean(all_preds == all_actuals))
    sharpe = compute_trading_sharpe(all_preds.tolist(), all_actuals.tolist())

    # Compute baseline (buy-and-hold)
    bh_returns = []
    for i in range(len(all_preds)):
        bh_returns.append(1.0 if all_actuals[i] == 1 else -1.0)
    bh_sharpe = float(np.mean(bh_returns) / (np.std(bh_returns) + 1e-8) * np.sqrt(252)) if len(bh_returns) > 1 else 0.0

    elapsed = time.time() - t0

    result = {
        "status": "ok",
        "ticker": ticker,
        "model_type": model_type,
        "days": days,
        "n_splits": n_splits,
        "confidence_threshold": confidence_threshold,
        "vol_threshold": vol_threshold,
        "require_positive_regime": require_positive_regime,
        "total_signals": total_signals,
        "filtered_count": filtered_count,
        "filter_rate": round(filtered_count / max(total_signals, 1), 4),
        "trades_taken": len(all_preds),
        "accuracy": round(accuracy, 4),
        "sharpe": round(sharpe, 4),
        "buy_hold_sharpe": round(bh_sharpe, 4),
        "beats_baseline": sharpe > bh_sharpe,
        "avg_confidence": round(float(np.mean(all_confidences)), 4),
        "elapsed_sec": round(elapsed, 2),
    }

    log.info(f"Results: accuracy={accuracy:.4f} sharpe={sharpe:.4f} "
             f"filtered={filtered_count}/{total_signals} ({result['filter_rate']:.1%}) "
             f"beats_baseline={result['beats_baseline']}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regime-filtered ML backtest")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--days", type=int, default=252)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument("--vol-threshold", type=float, default=0.25)
    parser.add_argument("--no-regime-filter", action="store_true")
    parser.add_argument("--model-type", default="rf", choices=["rf", "gbm"])
    parser.add_argument("--output", default=None, help="Output JSON file")
    args = parser.parse_args()

    result = backtest_regime_filtered(
        ticker=args.ticker,
        days=args.days,
        n_splits=args.n_splits,
        confidence_threshold=args.confidence,
        vol_threshold=args.vol_threshold,
        require_positive_regime=not args.no_regime_filter,
        model_type=args.model_type,
    )

    logger.info(json.dumps(result, indent=2))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        log.info(f"Results saved to {args.output}")
