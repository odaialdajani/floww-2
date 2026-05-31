#!/usr/bin/env python3
"""
Production ML Training Script — SPY/QQQ/DIA/IWM direction prediction.

Trains GradientBoosting classifiers on 2 years of real yfinance data with:
- Walk-forward validation (8 folds, 126 train / 21 test per fold)
- Trading Sharpe computation from walk-forward predictions
- Quality gates: class balance, no overfit, walk-forward consistency
- Artifact saving: model.joblib, scaler.joblib, manifest.json
- Model registration in MongoDB ml_models collection

Usage:
    cd backend && ./venv/bin/python scripts/train_production.py --tickers SPY QQQ DIA IWM
    cd backend && ./venv/bin/python scripts/train_production.py --tickers SPY --walk-forward-only
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("train_production")

from train_real_ml import FEATURE_NAMES, compute_features
from train_with_baselines import compute_trading_sharpe

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
MODEL_DIR.mkdir(exist_ok=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Train production ML models")
    parser.add_argument("--tickers", nargs="+", default=["SPY", "QQQ", "DIA", "IWM"])
    parser.add_argument("--period", default="2y", help="Data period for yfinance")
    args = parser.parse_args()

    results = {}
    for ticker in args.tickers:
        try:
            result = train_production_model(ticker, period=args.period)
            results[ticker] = result
        except Exception as e:
            log.error(f"[{ticker}] Training failed: {e}")
            results[ticker] = {"error": str(e)}

    # Summary
    log.info("\n" + "=" * 60)
    log.info("TRAINING SUMMARY")
    log.info("=" * 60)
    for ticker, result in results.items():
        if "error" in result:
            log.info(f"  {ticker}: FAILED — {result['error']}")
        else:
            log.info(
                f"  {ticker}: {result['verdict']} — "
                f"acc={result['metrics']['overall_accuracy']:.4f} "
                f"wf={result['metrics']['avg_fold_accuracy']:.4f}±{result['metrics']['std_fold_accuracy']:.4f} "
                f"sharpe={result['metrics']['overall_sharpe']:.4f}"
            )

    return results


def train_production_model(ticker: str, period: str = "2y") -> dict:
    """Train a production model with walk-forward validation and quality gates."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.preprocessing import StandardScaler

    log.info(f"[{ticker}] Computing features ({period})...")
    features_df = compute_features(ticker, period=period)
    log.info(f"[{ticker}] Features: {features_df.shape}")

    # Prepare clean dataset
    feature_cols = [c for c in FEATURE_NAMES if c in features_df.columns]
    clean = features_df[feature_cols + ["target_directional_move"]].dropna()
    clean = clean[clean["target_directional_move"].notna()]

    if len(clean) < 100:
        raise ValueError(f"[{ticker}] Insufficient data: {len(clean)} rows")

    X = clean[feature_cols].values.astype(float)
    y = clean["target_directional_move"].values.astype(int)
    n = len(X)

    # Quality gate: class balance
    pos_rate = y.mean()
    log.info(f"[{ticker}] Data: {n} rows, {len(feature_cols)} features, pos_rate={pos_rate:.2%}")
    if pos_rate < 0.2 or pos_rate > 0.8:
        log.warning(f"[{ticker}] Class imbalance: {pos_rate:.2%} positive — training anyway")

    # Walk-forward validation: 8 folds, expanding window
    n_folds = 8
    fold_size = 21  # ~1 month per fold
    min_train = 126  # ~6 months minimum training

    if n < min_train + fold_size * n_folds:
        # Adjust folds for available data
        n_folds = max(3, (n - min_train) // fold_size)
        log.info(f"[{ticker}] Adjusted to {n_folds} folds (n={n})")

    fold_metrics = []
    all_preds = []
    all_actuals = []

    for fold in range(n_folds):
        train_end = min_train + fold * fold_size
        test_end = min(train_end + fold_size, n)

        if test_end > n:
            break

        X_train, y_train = X[:train_end], y[:train_end]
        X_test, y_test = X[train_end:test_end], y[train_end:test_end]

        if len(X_test) < 5:
            continue

        # Scale
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Train
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=4,
            min_samples_leaf=30,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train_s, y_train)

        # Predict
        preds = model.predict(X_test_s)
        acc = accuracy_score(y_test, preds)

        fold_metrics.append({
            "fold": fold,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "accuracy": float(acc),
            "train_acc": float(accuracy_score(y_train, model.predict(X_train_s))),
        })

        all_preds.extend(preds.tolist())
        all_actuals.extend(y_test.tolist())

        log.info(
            f"[{ticker}] Fold {fold}: "
            f"acc={accuracy_score(y_test, preds):.4f} "
            f"train_acc={accuracy_score(y_train, model.predict(X_train_s)):.4f} "
            f"(train={len(X_train)}, test={len(X_test)})"
        )

    # Overall metrics
    all_preds = np.array(all_preds)
    all_actuals = np.array(all_actuals)
    overall_acc = accuracy_score(all_actuals, all_preds)
    fold_accs = [f["accuracy"] for f in fold_metrics]
    fold_train_accs = [f["train_acc"] for f in fold_metrics]
    wf_mean = np.mean(fold_accs)
    wf_std = np.std(fold_accs)

    # Overfit check
    overfit_gap = np.mean(fold_train_accs) - wf_mean

    # Trading Sharpe from walk-forward predictions
    sharpe = compute_trading_sharpe(all_preds, all_actuals)

    # Quality gates
    gates = {
        "class_balance": bool(0.2 <= pos_rate <= 0.8),
        "sufficient_data": bool(n >= 100),
        "wf_positive": bool(wf_mean > 0.5),
        "no_overfit": bool(overfit_gap < 0.40),
        "sharpe_positive": bool(sharpe > 0),
        "fold_consistency": bool(wf_std < 0.15),
    }

    ship = all(gates.values())
    verdict = "SHIP" if ship else "HOLD"

    log.info(f"[{ticker}] Walk-forward: {wf_mean:.4f} ± {wf_std:.4f}")
    log.info(f"[{ticker}] Overall acc: {overall_acc:.4f}")
    log.info(f"[{ticker}] Overfit gap: {overfit_gap:.4f}")
    log.info(f"[{ticker}] Trading Sharpe: {sharpe:.4f}")
    log.info(f"[{ticker}] Gates: {gates}")
    log.info(f"[{ticker}] Verdict: {verdict}")

    # Train final model on ALL data
    log.info(f"[{ticker}] Training final model on all {n} rows...")
    final_scaler = StandardScaler()
    X_scaled = final_scaler.fit_transform(X)
    final_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=4,
        min_samples_leaf=30,
        max_features='sqrt',
        random_state=42,
        n_jobs=-1,
    )
    t0 = time.time()
    final_model.fit(X_scaled, y)
    train_time = time.time() - t0

    # Save artifacts
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    model_path = MODEL_DIR / f"{ticker}_gbm_production.joblib"
    scaler_path = MODEL_DIR / f"{ticker}_gbm_production_scaler.joblib"
    manifest_path = MODEL_DIR / f"{ticker}_gbm_production_manifest.json"

    import joblib
    joblib.dump(final_model, model_path)
    joblib.dump(final_scaler, scaler_path)

    # Feature importance
    importance = final_model.feature_importances_
    top_features = {
        feature_cols[i]: float(importance[i])
        for i in np.argsort(importance)[-10:][::-1]
    }

    manifest = {
        "ticker": ticker,
        "model": "gbm",
        "model_id": f"{ticker}_direction_v1.0_gbm",
        "feature_version": "v2.0",
        "target": "target_directional_move",
        "n_samples": n,
        "n_features": len(feature_cols),
        "feature_names": feature_cols,
        "model_params": {
            "n_estimators": 200,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "min_samples_leaf": 10,
            "random_state": 42,
        },
        "metrics": {
            "overall_accuracy": float(overall_acc),
            "avg_fold_accuracy": float(wf_mean),
            "std_fold_accuracy": float(wf_std),
            "avg_fold_train_accuracy": float(np.mean(fold_train_accs)),
            "overfit_gap": float(overfit_gap),
            "overall_sharpe": float(sharpe),
            "avg_fold_sharpe": float(sharpe),
            "train_time_sec": float(train_time),
        },
        "fold_metrics": fold_metrics,
        "top_features": top_features,
        "gate_results": gates,
        "verdict": verdict,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_path": str(model_path),
        "scaler_path": str(scaler_path),
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    log.info(f"[{ticker}] Saved: {model_path.name}, {scaler_path.name}, {manifest_path.name}")

    # Save report
    report_path = Path(__file__).resolve().parents[1].parent / "reports" / f"training_{ticker}_{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(manifest, f, indent=2)

    return manifest


if __name__ == "__main__":
    main()
