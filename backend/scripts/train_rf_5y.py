#!/usr/bin/env python3
"""
backend/scripts/train_rf_5y.py

Retrain RandomForest production models with 5 years of real yfinance data.
Uses walk-forward CV, quality gates, and saves artifacts with _rf_5y_production suffix.

Updates MODEL_REGISTRY in inference.py if models pass quality gates.

Usage:
    cd backend && .venv/bin/python3 scripts/train_rf_5y.py --tickers SPY QQQ DIA IWM TLT
    cd backend && .venv/bin/python3 scripts/train_rf_5y.py --tickers SPY --period 5y
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_rf_5y")

from train_real_ml import FEATURE_NAMES, compute_features
from train_with_baselines import compute_trading_sharpe

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
MODEL_DIR.mkdir(exist_ok=True)

REPORTS_DIR = Path(__file__).resolve().parents[1].parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def train_rf_5y_model(ticker: str, period: str = "5y") -> dict:
    """Train a RandomForest model with 5 years of data and walk-forward CV."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.preprocessing import StandardScaler

    log.info(f"[{ticker}] Computing features (period={period})...")
    features_df = compute_features(ticker, period=period)
    log.info(f"[{ticker}] Raw features: {features_df.shape}")

    feature_cols = [c for c in FEATURE_NAMES if c in features_df.columns]
    clean = features_df[feature_cols + ["target_directional_move"]].dropna()
    clean = clean[clean["target_directional_move"].notna()]

    if len(clean) < 200:
        raise ValueError(f"[{ticker}] Insufficient data: {len(clean)} rows (need 200+)")

    X = clean[feature_cols].values.astype(float)
    y = clean["target_directional_move"].values.astype(int)
    n = len(X)

    pos_rate = y.mean()
    log.info(f"[{ticker}] Data: {n} rows, {len(feature_cols)} features, pos_rate={pos_rate:.2%}")

    # Walk-forward CV: expanding window, ~1 month per fold
    n_folds = 10
    fold_size = 21
    min_train = 252  # 1 year minimum training

    if n < min_train + fold_size * n_folds:
        n_folds = max(5, (n - min_train) // fold_size)
        log.info(f"[{ticker}] Adjusted to {n_folds} folds (n={n})")

    fold_metrics = []
    all_preds = []
    all_actuals = []

    for fold in range(n_folds):
        train_end = min_train + fold * fold_size
        test_end = min(train_end + fold_size, n)
        if test_end > n or test_end - train_end < 5:
            break

        X_train, y_train = X[:train_end], y[:train_end]
        X_test, y_test = X[train_end:test_end], y[train_end:test_end]

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model = RandomForestClassifier(
            n_estimators=300,
            max_depth=5,
            min_samples_leaf=20,
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)

        fold_acc = accuracy_score(y_test, preds)
        train_acc = accuracy_score(y_train, model.predict(X_train_s))
        fold_metrics.append({
            "fold": fold,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "accuracy": float(fold_acc),
            "train_acc": float(train_acc),
        })
        all_preds.extend(preds.tolist())
        all_actuals.extend(y_test.tolist())
        log.info(f"[{ticker}] Fold {fold}: acc={fold_acc:.4f} train_acc={train_acc:.4f} (train={len(X_train)}, test={len(X_test)})")

    all_preds = np.array(all_preds)
    all_actuals = np.array(all_actuals)
    overall_acc = accuracy_score(all_actuals, all_preds)
    fold_accs = [f["accuracy"] for f in fold_metrics]
    fold_train_accs = [f["train_acc"] for f in fold_metrics]
    wf_mean = np.mean(fold_accs)
    wf_std = np.std(fold_accs)
    overfit_gap = np.mean(fold_train_accs) - wf_mean
    sharpe = compute_trading_sharpe(all_preds, all_actuals)

    gates = {
        "class_balance": bool(0.15 <= pos_rate <= 0.85),
        "sufficient_data": bool(n >= 200),
        "wf_positive": bool(wf_mean > 0.5),
        "no_overfit": bool(overfit_gap < 0.15),
        "sharpe_positive": bool(sharpe > 0),
        "fold_consistency": bool(wf_std < 0.10),
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
        n_estimators=300,
        max_depth=5,
        min_samples_leaf=20,
        max_features="sqrt",
        random_state=42,
        n_jobs=-1,
    )
    t0 = time.time()
    final_model.fit(X_scaled, y)
    train_time = time.time() - t0

    # Save artifacts with _rf_5y_production naming
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    model_path = MODEL_DIR / f"{ticker}_rf_5y_production.joblib"
    scaler_path = MODEL_DIR / f"{ticker}_rf_5y_production_scaler.joblib"
    manifest_path = MODEL_DIR / f"{ticker}_rf_5y_production_manifest.json"

    import joblib
    joblib.dump(final_model, model_path)
    joblib.dump(final_scaler, scaler_path)

    importance = final_model.feature_importances_
    top_features = {
        feature_cols[i]: float(importance[i])
        for i in np.argsort(importance)[-15:][::-1]
    }

    manifest = {
        "ticker": ticker,
        "model_type": "rf",
        "model_id": f"{ticker}_rf_5y_v1",
        "feature_version": "v2.0",
        "target": "target_directional_move",
        "n_samples": n,
        "n_features": len(feature_cols),
        "feature_names": feature_cols,
        "model_params": {
            "n_estimators": 300,
            "max_depth": 5,
            "min_samples_leaf": 20,
            "max_features": "sqrt",
            "random_state": 42,
        },
        "metrics": {
            "overall_accuracy": float(overall_acc),
            "avg_fold_accuracy": float(wf_mean),
            "std_fold_accuracy": float(wf_std),
            "avg_fold_train_accuracy": float(np.mean(fold_train_accs)),
            "overfit_gap": float(overfit_gap),
            "overall_sharpe": float(sharpe),
            "train_time_sec": float(train_time),
        },
        "fold_metrics": fold_metrics,
        "top_features": top_features,
        "gate_results": gates,
        "verdict": verdict,
        "created_at": datetime.now(UTC).isoformat(),
        "model_path": str(model_path),
        "scaler_path": str(scaler_path),
        "period": period,
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Save report
    report_path = REPORTS_DIR / f"training_{ticker}_rf_5y_{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(manifest, f, indent=2)

    log.info(f"[{ticker}] Saved: {model_path.name}, {scaler_path.name}, {manifest_path.name}")
    log.info(f"[{ticker}] Top features: {list(top_features.keys())[:5]}")

    return manifest


def update_model_registry(ticker: str) -> None:
    """Update MODEL_REGISTRY in inference.py to point to new _rf_5y_production artifacts."""
    inference_path = Path(__file__).resolve().parents[1] / "services" / "ml" / "inference.py"

    with open(inference_path) as f:
        content = f.read()

    old_entry = f'    "{ticker}": (\n        str(MODEL_DIR / "{ticker}_rf_production.joblib"),\n        str(MODEL_DIR / "{ticker}_rf_production_scaler.joblib"),\n        str(MODEL_DIR / "{ticker}_rf_production_manifest.json"),\n    ),'
    new_entry = f'    "{ticker}": (\n        str(MODEL_DIR / "{ticker}_rf_5y_production.joblib"),\n        str(MODEL_DIR / "{ticker}_rf_5y_production_scaler.joblib"),\n        str(MODEL_DIR / "{ticker}_rf_5y_production_manifest.json"),\n    ),'

    if old_entry in content:
        content = content.replace(old_entry, new_entry)
        with open(inference_path, "w") as f:
            f.write(content)
        log.info(f"[{ticker}] Updated MODEL_REGISTRY in inference.py")
    else:
        # Try the gbm pattern
        old_gbm = f'    "{ticker}": (\n        str(MODEL_DIR / "{ticker}_gbm_production.joblib"),\n        str(MODEL_DIR / "{ticker}_gbm_production_scaler.joblib"),\n        str(MODEL_DIR / "{ticker}_gbm_production_manifest.json"),\n    ),'
        if old_gbm in content:
            content = content.replace(old_gbm, new_entry)
            with open(inference_path, "w") as f:
                f.write(content)
            log.info(f"[{ticker}] Updated MODEL_REGISTRY in inference.py (from gbm)")
        else:
            log.warning(f"[{ticker}] Could not find MODEL_REGISTRY entry to update — manual update needed")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Train RF 5y production models")
    parser.add_argument("--tickers", nargs="+", default=["SPY", "QQQ", "DIA", "IWM", "TLT"])
    parser.add_argument("--period", default="5y", help="Data period for yfinance")
    parser.add_argument("--skip-registry", action="store_true", help="Don't update inference.py registry")
    args = parser.parse_args()

    results = {}
    for ticker in args.tickers:
        try:
            result = train_rf_5y_model(ticker, period=args.period)
            results[ticker] = result
            if result.get("verdict") == "SHIP" and not args.skip_registry:
                update_model_registry(ticker)
        except Exception as e:
            log.error(f"[{ticker}] Training failed: {e}")
            import traceback
            traceback.print_exc()
            results[ticker] = {"error": str(e)}

    # Summary
    log.info("\n" + "=" * 70)
    log.info("TRAINING SUMMARY — RF 5Y Models")
    log.info("=" * 70)
    for ticker, result in results.items():
        if "error" in result:
            log.info(f"  {ticker}: FAILED — {result['error']}")
        else:
            m = result.get("metrics", {})
            log.info(
                f"  {ticker}: {result.get('verdict', '?')} — "
                f"wf_acc={m.get('avg_fold_accuracy', 0):.4f}±{m.get('std_fold_accuracy', 0):.4f} "
                f"sharpe={m.get('overall_sharpe', 0):.4f} "
                f"overfit={m.get('overfit_gap', 0):.4f} "
                f"n={result.get('n_samples', 0)}"
            )
    log.info("=" * 70)
    return results


if __name__ == "__main__":
    main()
