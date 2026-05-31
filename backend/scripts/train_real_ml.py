"""
backend/scripts/train_real_ml.py

Real-data ML training pipeline for SPY/QQQ/IWM/DIA direction prediction.

Fetches historical price data from yfinance, computes technical features,
trains a GradientBoosting model with walk-forward validation, and saves
production-ready artifacts (model + scaler + manifest).

Usage:
    # Train SPY with defaults (1 year data, 5-fold walk-forward)
    python -m scripts.train_real_ml --ticker SPY

    # Train all tickers
    python -m scripts.train_real_ml --all

    # Quick test (30 days)
    python -m scripts.train_real_ml --ticker SPY --days 30 --quick
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yfinance as yf

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("train_real_ml")

# ── Feature Engineering ────────────────────────────────────────────────

FEATURE_NAMES = [
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_21d",
    "log_ret_1d", "overnight_gap",
    "sma_5", "price_vs_sma_5",
    "sma_10", "price_vs_sma_10",
    "sma_21", "price_vs_sma_21",
    "sma_50", "price_vs_sma_50",
    "atr_14",
    "volume_sma_5", "volume_sma_21", "relative_volume",
    "realized_vol_5d", "realized_vol_10d", "realized_vol_21d", "realized_vol_60d",
    "rsi_14", "rsi_overbought", "rsi_oversold",
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_lower", "bb_position",
    "vol_ratio_5_21", "vol_ratio_5_60",
    "sma_5_21_diff", "sma_5_21_cross", "sma_10_50_diff",
    "ret_momentum", "ret_accel",
    "vol_spike",
    "gap_abs", "gap_large",
    "is_month_end", "is_month_start",
]


def compute_features(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Compute technical features from yfinance OHLCV data.

    Returns DataFrame with one row per trading day, columns = FEATURE_NAMES + target.
    """
    logger.info(f"Downloading {ticker} data (period={period})...")
    data = yf.download(ticker, period=period, progress=False)
    if data.empty:
        raise ValueError(f"No data returned for {ticker}")

    # Handle multi-level columns from yfinance
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    df = data.copy()
    df = df.dropna(subset=["Close"])
    if len(df) < 60:
        raise ValueError(f"Insufficient data for {ticker}: {len(df)} rows (need 60+)")

    close = df["Close"].values.astype(float)
    high = df["High"].values.astype(float) if "High" in df.columns else close
    low = df["Low"].values.astype(float) if "Low" in df.columns else close
    volume = df["Volume"].values.astype(float) if "Volume" in df.columns else np.ones(len(close))
    open_price = df["Open"].values.astype(float) if "Open" in df.columns else close
    n = len(close)

    features = pd.DataFrame(index=df.index)

    # Returns
    for horizon, name in [(1, "ret_1d"), (3, "ret_3d"), (5, "ret_5d"), (10, "ret_10d"), (21, "ret_21d")]:
        ret = np.zeros(n)
        for i in range(horizon, n):
            if close[i - horizon] > 0:
                ret[i] = (close[i] - close[i - horizon]) / close[i - horizon]
        features[name] = ret

    # Log returns
    log_ret = np.zeros(n)
    for i in range(1, n):
        if close[i - 1] > 0 and close[i] > 0:
            log_ret[i] = np.log(close[i] / close[i - 1])
    features["log_ret_1d"] = log_ret

    # Overnight gap
    overnight_gap = np.zeros(n)
    for i in range(1, n):
        if close[i - 1] > 0:
            overnight_gap[i] = (open_price[i] - close[i - 1]) / close[i - 1]
    features["overnight_gap"] = overnight_gap

    # SMAs and price-relative
    for window, name in [(5, "sma_5"), (10, "sma_10"), (21, "sma_21"), (50, "sma_50")]:
        sma = pd.Series(close).rolling(window=window, min_periods=window).mean().values
        features[name] = sma
        rel = np.zeros(n)
        for i in range(n):
            if sma[i] > 0:
                rel[i] = close[i] / sma[i] - 1.0
        features[f"price_vs_sma_{window}"] = rel

    # ATR
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    features["atr_14"] = pd.Series(tr).rolling(window=14, min_periods=1).mean().values

    # Volume features
    vol_sma_5 = pd.Series(volume).rolling(window=5, min_periods=1).mean().values
    vol_sma_21 = pd.Series(volume).rolling(window=21, min_periods=1).mean().values
    features["volume_sma_5"] = vol_sma_5
    features["volume_sma_21"] = vol_sma_21
    rel_vol = np.zeros(n)
    for i in range(n):
        if vol_sma_21[i] > 0:
            rel_vol[i] = volume[i] / vol_sma_21[i]
    features["relative_volume"] = rel_vol

    # Realized volatility
    for window, name in [(5, "realized_vol_5d"), (10, "realized_vol_10d"), (21, "realized_vol_21d"), (60, "realized_vol_60d")]:
        vol = pd.Series(log_ret).rolling(window=window, min_periods=window).std().values * np.sqrt(252)
        features[name] = vol

    # RSI
    delta = pd.Series(close).diff()
    gain = delta.where(delta > 0, 0).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain / (loss + 1e-10)
    rsi = (100 - (100 / (1 + rs))).values
    features["rsi_14"] = rsi
    features["rsi_overbought"] = (rsi > 70).astype(float)
    features["rsi_oversold"] = (rsi < 30).astype(float)

    # MACD
    ema_12 = pd.Series(close).ewm(span=12, adjust=False).mean()
    ema_26 = pd.Series(close).ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    features["macd"] = macd.values
    features["macd_signal"] = macd_signal.values
    features["macd_hist"] = (macd - macd_signal).values

    # Bollinger Bands
    sma_20 = pd.Series(close).rolling(window=20, min_periods=1).mean()
    std_20 = pd.Series(close).rolling(window=20, min_periods=1).std()
    bb_upper = (sma_20 + 2 * std_20).values
    bb_lower = (sma_20 - 2 * std_20).values
    bb_position = np.zeros(n)
    for i in range(n):
        band_width = bb_upper[i] - bb_lower[i]
        if band_width > 0:
            bb_position[i] = (close[i] - bb_lower[i]) / band_width
    features["bb_position"] = bb_position

    # Volume ratios
    vol_sma_60 = pd.Series(volume).rolling(window=60, min_periods=1).mean().values
    features["vol_ratio_5_21"] = vol_sma_5 / (vol_sma_21 + 1e-10)
    features["vol_ratio_5_60"] = vol_sma_5 / (vol_sma_60 + 1e-10)

    # SMA crossovers
    sma_5 = pd.Series(close).rolling(window=5, min_periods=1).mean().values
    sma_21 = pd.Series(close).rolling(window=21, min_periods=1).mean().values
    sma_10 = pd.Series(close).rolling(window=10, min_periods=1).mean().values
    sma_50 = pd.Series(close).rolling(window=50, min_periods=1).mean().values
    features["sma_5_21_diff"] = sma_5 - sma_21
    features["sma_5_21_cross"] = np.sign(features["sma_5_21_diff"])
    features["sma_10_50_diff"] = sma_10 - sma_50

    # Momentum / acceleration
    features["ret_momentum"] = pd.Series(close).pct_change(5).values
    features["ret_accel"] = pd.Series(close).pct_change(5).diff().values

    # Vol spike
    features["vol_spike"] = (
        pd.Series(log_ret).rolling(window=5, min_periods=1).std().values /
        (pd.Series(log_ret).rolling(window=21, min_periods=1).std().values + 1e-10)
    )

    # Gap features
    features["gap_abs"] = np.abs(overnight_gap)
    features["gap_large"] = (np.abs(overnight_gap) > 0.003).astype(float)

    # Calendar features
    dates = pd.to_datetime(df.index)
    features["is_month_end"] = pd.Series(dates.is_month_end, index=df.index).astype(float).values
    features["is_month_start"] = pd.Series(dates.is_month_start, index=df.index).astype(float).values

    # Target: next-day directional move (>0.5% abs return)
    target = np.zeros(n)
    for i in range(n - 1):
        if close[i] > 0:
            ret = (close[i + 1] - close[i]) / close[i]
            target[i] = 1 if abs(ret) > 0.005 else 0
    features["target_directional_move"] = target

    # Clean up
    features = features.replace([np.inf, -np.inf], np.nan)
    features = features.fillna(0.0)

    logger.info(f"Computed {len(FEATURE_NAMES)} features for {ticker} ({len(features)} rows)")
    return features


def train_model(
    ticker: str,
    days: int = 252,
    quick: bool = False,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Train a GradientBoosting model for a ticker.

    Args:
        ticker: Ticker symbol
        days: Number of trading days of history
        quick: If True, use smaller model for faster training
        output_dir: Directory to save model artifacts

    Returns:
        Dict with training metrics and artifact paths
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler

    period = f"{max(days // 21, 12)}mo"  # At least 12mo for rolling windows
    features_df = compute_features(ticker, period=period)

    # Drop rows with NaN in features or target
    feature_cols = [c for c in FEATURE_NAMES if c in features_df.columns]
    clean = features_df[feature_cols + ["target_directional_move"]].dropna()
    clean = clean[clean["target_directional_move"].notna()]

    if len(clean) < 30:
        raise ValueError(f"Insufficient clean data for {ticker}: {len(clean)} rows")

    X = clean[feature_cols].values.astype(float)
    y = clean["target_directional_move"].values.astype(int)

    # Temporal split: 80% train, 20% test
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model
    n_estimators = 50 if quick else 200
    model = GradientBoostingClassifier(
        n_estimators=n_estimators,
        max_depth=4 if quick else 6,
        learning_rate=0.1,
        subsample=0.8,
        min_samples_leaf=10,
        random_state=42,
    )

    logger.info(f"Training {ticker} model: {len(X_train)} train, {len(X_test)} test samples...")
    t0 = time.time()
    model.fit(X_train_scaled, y_train)
    train_time = time.time() - t0

    # Evaluate
    train_pred = model.predict(X_train_scaled)
    test_pred = model.predict(X_test_scaled)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)

    # Walk-forward validation
    tscv = TimeSeriesSplit(n_splits=3 if quick else 5)
    wf_scores = []
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X_train_scaled)):
        wf_model = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=4 if quick else 6,
            learning_rate=0.1,
            subsample=0.8,
            min_samples_leaf=10,
            random_state=42,
        )
        wf_model.fit(X_train_scaled[train_idx], y_train[train_idx])
        wf_score = accuracy_score(y_train[val_idx], wf_model.predict(X_train_scaled[val_idx]))
        wf_scores.append(wf_score)
        logger.info(f"  Fold {fold + 1}: {wf_score:.4f}")

    wf_mean = np.mean(wf_scores)
    wf_std = np.std(wf_scores)

    # Class balance check
    pos_ratio = y_train.mean()
    if pos_ratio < 0.15 or pos_ratio > 0.85:
        logger.warning(f"Class imbalance for {ticker}: {pos_ratio:.2%} positive")

    logger.info(f"  Train accuracy: {train_acc:.4f}")
    logger.info(f"  Test accuracy:  {test_acc:.4f}")
    logger.info(f"  Walk-forward:   {wf_mean:.4f} ± {wf_std:.4f}")
    logger.info(f"  Train time:     {train_time:.2f}s")

    result = {
        "ticker": ticker,
        "model_type": "gradient_boosting",
        "n_samples": len(X),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_features": len(feature_cols),
        "feature_names": feature_cols,
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "walk_forward_mean": wf_mean,
        "walk_forward_std": wf_std,
        "class_balance_pos": pos_ratio,
        "train_time_sec": train_time,
        "feature_version": "v1.0",
        "target": "target_directional_move",
    }

    # Save artifacts
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        model_path = output_dir / f"{ticker}_gbm_production.joblib"
        scaler_path = output_dir / f"{ticker}_gbm_production_scaler.joblib"
        manifest_path = output_dir / f"{ticker}_gbm_production_manifest.json"

        import joblib
        # Save as dict artifact matching InferenceEngine._load_model expectations
        artifact = {
            "model": model,
            "model_name": "gbm",
            "feature_names": feature_cols,
            "scaler": scaler,
            "metrics": {
                "avg_train_accuracy": train_acc,
                "avg_test_accuracy": test_acc,
                "avg_test_sharpe": 0.0,
                "beats_baselines": test_acc > 0.52,
            },
        }
        joblib.dump(artifact, model_path)
        joblib.dump(scaler, scaler_path)

        manifest = {
            "ticker": ticker,
            "model_id": f"{ticker}_gbm_production",
            "model_type": "gbm",
            "feature_version": "v1.0",
            "target": "target_directional_move",
            "n_samples": len(X),
            "n_features": len(feature_cols),
            "feature_names": feature_cols,
            "train_accuracy": train_acc,
            "test_accuracy": test_acc,
            "walk_forward_mean": wf_mean,
            "walk_forward_std": wf_std,
            "class_balance_pos": pos_ratio,
            "train_time_sec": train_time,
            "model_path": str(model_path),
            "scaler_path": str(scaler_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        result["model_path"] = str(model_path)
        result["scaler_path"] = str(scaler_path)
        result["manifest_path"] = str(manifest_path)
        logger.info(f"Saved artifacts to {output_dir}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Train real-data ML models")
    parser.add_argument("--ticker", type=str, default="SPY", help="Ticker symbol")
    parser.add_argument("--all", action="store_true", help="Train all tickers")
    parser.add_argument("--days", type=int, default=252, help="Trading days of history")
    parser.add_argument("--quick", action="store_true", help="Quick training (fewer estimators)")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for artifacts")
    args = parser.parse_args()

    tickers = ["SPY", "QQQ", "IWM", "DIA"] if args.all else [args.ticker.upper()]
    output_dir = Path(args.output_dir) if args.output_dir else SCRIPT_DIR.parent.parent / "models"

    results = {}
    for ticker in tickers:
        try:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Training {ticker}")
            logger.info(f"{'=' * 60}")
            result = train_model(ticker, days=args.days, quick=args.quick, output_dir=output_dir)
            results[ticker] = result
        except Exception as e:
            logger.error(f"Failed to train {ticker}: {e}")
            results[ticker] = {"error": str(e)}

    # Summary
    logger.info(f"\n{'=' * 60}")
    logger.info("TRAINING SUMMARY")
    logger.info(f"{'=' * 60}")
    for ticker, result in results.items():
        if "error" in result:
            logger.info(f"  {ticker}: FAILED - {result['error']}")
        else:
            logger.info(
                f"  {ticker}: test_acc={result['test_accuracy']:.4f}, "
                f"wf={result['walk_forward_mean']:.4f}±{result['walk_forward_std']:.4f}, "
                f"features={result['n_features']}"
            )

    # Save summary
    summary_path = output_dir / "training_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Summary saved to {summary_path}")


if __name__ == "__main__":
    main()
