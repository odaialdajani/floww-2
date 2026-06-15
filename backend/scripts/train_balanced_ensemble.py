#!/usr/bin/env python3
"""
scripts/train_balanced_ensemble.py

Improved ML training with:
  1. class_weight='balanced' to fix class imbalance
  2. Per-model-type training (GBM + RF + Logistic) with best Sharpe selection
  3. Optional ensemble: average probabilities from all 3 model types
  4. Proper walk-forward CV with embargo
  5. Saves production artifacts

Usage:
    cd backend && .venv/bin/python3 -m scripts.train_balanced_ensemble --ticker SPY
    cd backend && .venv/bin/python3 -m scripts.train_balanced_ensemble --all
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import joblib

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("train_balanced_ensemble")

# ── Config ──────────────────────────────────────────────────────────────
UP_THRESHOLD = 0.003
DOWN_THRESHOLD = -0.003

FEATURE_NAMES = [
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_21d",
    "log_ret_1d", "overnight_gap",
    "sma_5", "price_vs_sma_5", "sma_10", "price_vs_sma_10",
    "sma_21", "price_vs_sma_21", "sma_50", "price_vs_sma_50",
    "atr_14", "volume_sma_5", "volume_sma_21", "relative_volume",
    "realized_vol_5d", "realized_vol_10d", "realized_vol_21d", "realized_vol_60d",
    "rsi_14", "rsi_overbought", "rsi_oversold",
    "macd", "macd_signal", "macd_hist",
    "bb_position", "vol_ratio_5_21", "vol_ratio_5_60",
    "sma_5_21_diff", "sma_5_21_cross", "sma_10_50_diff",
    "ret_momentum", "ret_accel", "vol_spike",
    "gap_abs", "gap_large", "is_month_end", "is_month_start",
]


def compute_features(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Compute technical features from yfinance OHLCV + 3-class target."""
    # Import compute_features from train_real_data_ml
    # Reuse the existing feature computation
    import importlib.util
    spec = importlib.util.spec_from_file_location("train_real_data_ml", SCRIPT_DIR / "train_real_data_ml.py")
    mod = importlib.util.load_from_spec = spec
    # Actually, let's just import it properly
    from scripts.train_real_data_ml import compute_features as _orig_compute
    return _orig_compute(ticker, period=period)


def walk_forward_cv(model, X, y, n_splits=5, embargo=5):
    """Walk-forward CV with embargo. Returns dict of metrics."""
    from sklearn.metrics import accuracy_score
    from sklearn.base import clone

    fold_size = len(X) // (n_splits + 1)
    scores, train_scores, sharpe_scores = [], [], []

    for fold in range(n_splits):
        train_end = fold_size * (fold + 1)
        test_start = train_end + embargo
        test_end = min(test_start + fold_size, len(X))
        if test_end > len(X) or test_start >= len(X):
            break

        X_tr, y_tr = X[:train_end], y[:train_end]
        X_te, y_te = X[test_start:test_end], y[test_start:test_end]

        fm = clone(model)
        fm.fit(X_tr, y_tr)
        tr_acc = accuracy_score(y_tr, fm.predict(X_tr))
        te_acc = accuracy_score(y_te, fm.predict(X_te))

        # Sharpe proxy
        sharpe = te_acc / (1.0 - te_acc + 0.01)
        scores.append(te_acc)
        train_scores.append(tr_acc)
        sharpe_scores.append(sharpe)

        log.info("  Fold %d: train=%.4f test=%.4f gap=%.4f sharpe=%.2f",
                 fold+1, tr_acc, te_acc, tr_acc-te_acc, sharpe)

    return {
        "n_folds": len(scores),
        "mean_train": float(np.mean(train_scores)) if train_scores else 0,
        "mean_test": float(np.mean(scores)) if scores else 0,
        "std_test": float(np.std(scores)) if scores else 0,
        "mean_gap": float(np.mean([t-s for t,s in zip(train_scores, scores)])) if scores else 0,
        "mean_sharpe": float(np.mean(sharpe_scores)) if sharpe_scores else 0,
        "fold_scores": [float(s) for s in scores],
    }


def train_ticker(ticker: str, output_dir: Path, quick: bool = False) -> Dict:
    """Train balanced models for a ticker. Returns results dict."""
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score

    log.info("=" * 60)
    log.info("Training %s (balanced, quick=%s)...", ticker, quick)

    # Compute features
    features_df = compute_features(ticker, period="24mo")
    feature_cols = [c for c in FEATURE_NAMES if c in features_df.columns]
    target_col = "target_3class"
    clean = features_df[feature_cols + [target_col]].dropna()
    clean = clean.iloc[:-1]  # remove last row (no next-day target)

    X_full = clean[feature_cols].values.astype(float)
    y = clean[target_col].values.astype(int)

    # Feature selection (simplified: variance filter)
    from scripts.train_real_data_ml import select_features
    selected_names, selected_indices = select_features(
        X_full, y, feature_cols, min_variance=0.0005,
        max_correlation=0.90, max_features=20, quick=quick
    )
    X = X_full[:, selected_indices]

    # Scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Split
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X_scaled[:split_idx], X_scaled[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    log.info("Train: %d | Test: %d | Classes: %s",
             len(X_train), len(X_test),
             {i: int((y_train == i).sum()) for i in range(3)})

    # ── Candidate models with class_weight='balanced' ─────────────────
    n_est = 50 if quick else 200
    candidates = {
        "gbm": GradientBoostingClassifier(
            n_estimators=n_est, max_depth=3, learning_rate=0.05,
            subsample=0.7, min_samples_leaf=20, random_state=42,
        ),
        "rf_balanced": RandomForestClassifier(
            n_estimators=n_est, max_depth=4, min_samples_leaf=15,
            max_features="sqrt", class_weight="balanced",
            random_state=42, n_jobs=-1,
        ),
        "logistic_balanced": LogisticRegression(
            C=0.1, max_iter=1000, 
            class_weight="balanced", random_state=42,
        ),
    }

    # Walk-forward CV each candidate
    best_model = None
    best_name = None
    best_sharpe = -999
    best_cv = None
    cv_results = {}

    for name, model in candidates.items():
        log.info("Evaluating %s %s...", ticker, name)
        cv = walk_forward_cv(model, X_train, y_train,
                             n_splits=3 if quick else 5, embargo=5)
        sharpe = cv["mean_sharpe"]
        cv_results[name] = cv
        log.info("  %s: test_acc=%.4f ± %.4f, gap=%.4f, sharpe=%.2f",
                 name, cv["mean_test"], cv["std_test"], cv["mean_gap"], sharpe)

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_model = model
            best_name = name
            best_cv = cv

    # Train best model on full training set
    log.info("Best for %s: %s (sharpe=%.2f)", ticker, best_name, best_sharpe)
    best_model.fit(X_train, y_train)

    train_pred = best_model.predict(X_train)
    test_pred = best_model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)

    log.info("Final %s %s: train=%.4f, test=%.4f, gap=%.4f",
             ticker, best_name, train_acc, test_acc, train_acc - test_acc)

    # Class-specific accuracy
    for cls, label in [(0, "DOWN"), (1, "HOLD"), (2, "UP")]:
        mask = y_test == cls
        if mask.sum() > 0:
            cls_acc = accuracy_score(y_test[mask], test_pred[mask])
            log.info("  %s: %.1f%% (%d/%d)", label, cls_acc*100,
                     int(cls_acc * mask.sum()), int(mask.sum()))

    # ── Also build ensemble (average probas from all 3) ──────────────
    log.info("Building ensemble for %s...", ticker)
    from sklearn.base import clone
    ensemble_models = {}
    for name, model in candidates.items():
        m = clone(model)  # fresh clone
        m.fit(X_train, y_train)
        ensemble_models[name] = m

    # Ensemble prediction: average probabilities
    probas = []
    for name, m in ensemble_models.items():
        if hasattr(m, 'predict_proba'):
            probas.append(m.predict_proba(X_test))
    ensemble_proba = np.mean(probas, axis=0)
    ensemble_pred = np.argmax(ensemble_proba, axis=1)
    ensemble_acc = accuracy_score(y_test, ensemble_pred)
    log.info("Ensemble: test_acc=%.4f", ensemble_acc)

    # Save artifacts
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Save best model
    model_path = output_dir / f"{ticker}_balanced_{ts}.joblib"
    scaler_path = output_dir / f"{ticker}_balanced_{ts}_scaler.joblib"
    manifest_path = output_dir / f"{ticker}_balanced_{ts}_manifest.json"

    joblib.dump(best_model, model_path)
    joblib.dump(scaler, scaler_path)

    manifest = {
        "ticker": ticker,
        "model_type": best_name,
        "n_samples": len(X),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_features": len(selected_names),
        "feature_names": selected_names,
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "walk_forward_mean": best_cv["mean_test"],
        "walk_forward_std": best_cv["std_test"],
        "walk_forward_sharpe": best_cv["mean_sharpe"],
        "overfit_gap": train_acc - test_acc,
        "fold_scores": best_cv["fold_scores"],
        "class_accuracy": {},
        "ensemble_test_accuracy": ensemble_acc,
        "model_path": str(model_path.name),
        "scaler_path": str(scaler_path.name),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": f"{ticker}_balanced_v3",
        "class_weight": "balanced",
    }
    for cls, label in [(0, "down"), (1, "hold"), (2, "up")]:
        mask = y_test == cls
        if mask.sum() > 0:
            manifest["class_accuracy"][label] = float(accuracy_score(y_test[mask], test_pred[mask]))

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Save ensemble (all 3 models + scaler)
    ensemble_path = output_dir / f"{ticker}_ensemble_{ts}.joblib"
    ensemble_artifacts = {
        "models": {name: m for name, m in ensemble_models.items()},
        "scaler": scaler,
        "feature_names": selected_names,
        "model_id": f"{ticker}_ensemble_v3",
        "test_accuracy": ensemble_acc,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    joblib.dump(ensemble_artifacts, ensemble_path)

    log.info("Saved: %s", model_path)
    log.info("Saved: %s", ensemble_path)

    return {
        "ticker": ticker,
        "best_model": best_name,
        "test_accuracy": test_acc,
        "train_accuracy": train_acc,
        "walk_forward_mean": best_cv["mean_test"],
        "walk_forward_sharpe": best_cv["mean_sharpe"],
        "ensemble_accuracy": ensemble_acc,
        "class_accuracy": manifest["class_accuracy"],
        "n_features": len(selected_names),
        "n_samples": len(X),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    tickers = ["SPY", "QQQ", "DIA", "IWM", "TLT"] if args.all else [args.ticker.upper()]
    output_dir = SCRIPT_DIR.parent / "models"

    results = {}
    for ticker in tickers:
        try:
            t0 = time.time()
            r = train_ticker(ticker, output_dir, quick=args.quick)
            r["total_time_sec"] = time.time() - t0
            results[ticker] = r
            log.info("✓ %s: %s test=%.4f ensemble=%.4f sharpe=%.2f in %.1fs",
                     ticker, r["best_model"], r["test_accuracy"],
                     r["ensemble_accuracy"], r["walk_forward_sharpe"],
                     r["total_time_sec"])
        except Exception as e:
            log.error("✗ %s FAILED: %s", ticker, e, exc_info=True)
            results[ticker] = {"error": str(e)}

    # Summary
    log.info("=" * 60)
    log.info("TRAINING SUMMARY")
    for ticker, r in results.items():
        if "error" in r:
            log.info("%s: ERROR — %s", ticker, r["error"])
        else:
            log.info("%s: %s | test=%.4f | ensemble=%.4f | sharpe=%.2f | classes=%s",
                     ticker, r["best_model"], r["test_accuracy"],
                     r["ensemble_accuracy"], r["walk_forward_sharpe"],
                     r.get("class_accuracy", {}))

    # Save report
    report_path = SCRIPT_DIR.parent / "reports" / f"training_balanced_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("Report: %s", report_path)

    return 0 if all("error" not in r for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
