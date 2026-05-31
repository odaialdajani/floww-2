#!/usr/bin/env python3
"""
Backtest trained models on held-out data (last 3 months).

Loads production models, computes features on recent data not seen during training,
and evaluates prediction accuracy and trading P&L.

Usage:
    cd backend && ./venv/bin/python scripts/backtest_heldout.py
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backtest")

from train_real_ml import compute_features

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"


def backtest_ticker(ticker: str, period: str = "3mo") -> dict:
    """Backtest a single ticker on recent data."""
    log.info(f"[{ticker}] Loading model...")
    model_path = MODEL_DIR / f"{ticker}_gbm_production.joblib"
    scaler_path = MODEL_DIR / f"{ticker}_gbm_production_scaler.joblib"
    manifest_path = MODEL_DIR / f"{ticker}_gbm_production_manifest.json"

    if not model_path.exists():
        return {"error": f"Model not found: {model_path}"}

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    with open(manifest_path) as f:
        manifest = json.load(f)

    train_feature_names = manifest.get("feature_names", [])
    log.info(f"[{ticker}] Model expects {len(train_feature_names)} features")

    # Compute features on backtest period
    log.info(f"[{ticker}] Computing features ({period})...")
    features_df = compute_features(ticker, period=period)
    log.info(f"[{ticker}] Raw features: {features_df.shape}")

    # Prepare features
    feature_cols = [c for c in train_feature_names if c in features_df.columns]
    missing = [c for c in train_feature_names if c not in features_df.columns]
    if missing:
        log.warning(f"[{ticker}] Missing features: {missing[:5]}...")

    clean = features_df[feature_cols + ["target_directional_move"]].dropna()
    clean = clean[clean["target_directional_move"].notna()]

    if len(clean) < 10:
        return {"error": f"Insufficient data: {len(clean)} rows"}

    X = clean[feature_cols].values.astype(float)
    y = clean["target_directional_move"].values.astype(int)

    # Scale
    X_scaled = scaler.transform(X)

    # Predict
    preds = model.predict(X_scaled)
    proba = model.predict_proba(X_scaled) if hasattr(model, "predict_proba") else None

    # Metrics
    acc = float(np.mean(preds == y))
    pos_rate = float(y.mean())

    # Trading simulation: go long when pred=1, flat when pred=0
    returns = []
    for i in range(len(preds) - 1):
        if preds[i] == 1:
            # Long: capture next-day return
            next_ret = (clean.iloc[i + 1]["target_directional_move"] - 0.5) * 0.02  # Simplified
            returns.append(next_ret)
        else:
            returns.append(0.0)

    returns = np.array(returns) if returns else np.array([0.0])
    total_ret = float(np.sum(returns))
    sharpe = float(np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)) if len(returns) > 1 else 0.0

    # Confidence analysis
    if proba is not None:
        confidences = np.max(proba, axis=1)
        high_conf_mask = confidences > 0.6
        high_conf_acc = float(np.mean(preds[high_conf_mask] == y[high_conf_mask])) if high_conf_mask.sum() > 0 else 0.0
        high_conf_count = int(high_conf_mask.sum())
    else:
        high_conf_acc = 0.0
        high_conf_count = 0

    result = {
        "ticker": ticker,
        "period": period,
        "n_days": len(clean),
        "accuracy": acc,
        "pos_rate": pos_rate,
        "total_return": total_ret,
        "sharpe": sharpe,
        "high_conf_accuracy": high_conf_acc,
        "high_conf_count": high_conf_count,
        "pred_positive_rate": float(preds.mean()),
        "train_wf_acc": manifest.get("metrics", {}).get("avg_fold_accuracy", 0),
        "train_sharpe": manifest.get("metrics", {}).get("overall_sharpe", 0),
    }

    log.info(f"[{ticker}] Backtest: acc={acc:.4f}, sharpe={sharpe:.4f}, days={len(clean)}")
    log.info(f"[{ticker}]   Train WF={result['train_wf_acc']:.4f} → Backtest={acc:.4f}")
    log.info(f"[{ticker}]   High-conf acc={high_conf_acc:.4f} ({high_conf_count} days)")

    return result


def main():
    tickers = ["SPY", "QQQ", "DIA", "IWM"]
    results = {}

    for ticker in tickers:
        try:
            result = backtest_ticker(ticker, period="3mo")
            results[ticker] = result
        except Exception as e:
            log.error(f"[{ticker}] Backtest failed: {e}")
            results[ticker] = {"error": str(e)}

    # Summary
    log.info("\n" + "=" * 70)
    log.info("BACKTEST SUMMARY (3-month held-out data)")
    log.info("=" * 70)
    log.info(f"{'Ticker':<8} {'Days':>5} {'Acc':>7} {'Sharpe':>8} {'HighConf':>9} {'Train→Test':>12}")
    log.info("-" * 70)
    for ticker, r in results.items():
        if "error" in r:
            log.info(f"  {ticker}: ERROR — {r['error']}")
        else:
            drift = r['accuracy'] - r['train_wf_acc']
            log.info(
                f"  {ticker:<6} {r['n_days']:>5} {r['accuracy']:>7.4f} {r['sharpe']:>8.4f} "
                f"{r['high_conf_accuracy']:>9.4f} {r['train_wf_acc']:.4f}→{r['accuracy']:.4f} ({drift:+.4f})"
            )

    # Save report
    report_path = Path(__file__).resolve().parents[1].parent / "reports" / f"backtest_heldout_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info(f"\nReport saved: {report_path}")

    return results


if __name__ == "__main__":
    main()
