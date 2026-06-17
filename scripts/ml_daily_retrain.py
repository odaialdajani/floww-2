#!/usr/bin/env python3
"""
scripts/ml_daily_retrain.py

Daily ML model retraining pipeline.
- Loads cached features for all tickers
- Walk-forward validation with expanding window
- Saves best model per ticker with manifest
- Updates MongoDB model registry

Usage:
  python scripts/ml_daily_retrain.py                  # retrain all tickers
  python scripts/ml_daily_retrain.py --ticker SPY     # retrain single ticker
  python scripts/ml_daily_retrain.py --dry-run        # evaluate only, don't save
"""
import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from sklearn.ensemble import GradientBoostingClassifier  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score  # type: ignore[import-untyped]

warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from services.ml.quality import (  # type: ignore[import-not-found]
    assert_class_balance, assert_feature_variance,
    assert_prediction_distribution, DegenerateModelError,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ml.retrain")

MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data" / "cached_features"

TICKER_FILES = {
    "SPY": DATA_DIR / "SPY_v1.0.csv",
    "DIA": DATA_DIR / "DIA_v1.0.csv",
    "IWM": DATA_DIR / "IWM_v1.0.csv",
    "QQQ": DATA_DIR / "QQQ_v1.0.csv",
    "TLT": DATA_DIR / "TLT_v1.0.csv",
}

META_COLS = {
    "ticker", "date", "day", "feature_version", "_computed_at",
    "target_directional_move", "target_return_pct",
    "target_range_expansion", "target_gap_move", "target_any_materialization",
}

TARGET_COL = "target_directional_move"

MODEL_PARAMS = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "min_samples_leaf": 10,
    "random_state": 42,
}

# Walk-forward: expanding window, 63-day (~3mo) test folds
MIN_TRAIN = 200
STEP_SIZE = 63
EMBARGO = 5


def load_and_prepare(ticker: str) -> Tuple[Any, Any, List[str], List[Any], Any]:
    path = TICKER_FILES.get(ticker)
    if path is None or not path.exists():
        raise FileNotFoundError(f"No cached data for {ticker}: {path}")
    df = pd.read_csv(path)
    df = df.sort_values(by="date" if "date" in df.columns else "day").reset_index(drop=True)
    feature_names = [c for c in df.columns if c not in META_COLS]
    df = df.dropna(subset=[TARGET_COL]).reset_index(drop=True)
    X = df[feature_names].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df[TARGET_COL].values.astype(int)
    dates = df["date"].tolist() if "date" in df.columns else list(range(len(y)))
    return X, y, feature_names, dates, df


def walk_forward_evaluate(X: Any, y: Any, feature_names: List[str], dates: List[Any]) -> Optional[Dict[str, Any]]:
    """Walk-forward evaluation with expanding window."""
    n = len(y)
    if n < MIN_TRAIN + STEP_SIZE:
        logger.warning(f"Insufficient data: {n} samples (need {MIN_TRAIN + STEP_SIZE})")
        return None

    all_preds, all_probas, all_actuals, all_dates = [], [], [], []
    fold_metrics = []

    n_splits = max(1, (n - MIN_TRAIN) // STEP_SIZE)
    for i in range(n_splits):
        test_start = MIN_TRAIN + i * STEP_SIZE
        test_end = min(test_start + STEP_SIZE, n)
        train_end = max(MIN_TRAIN, test_start - EMBARGO)
        train_start = 0

        if train_end - train_start < MIN_TRAIN or test_end <= test_start:
            continue

        X_train = X[train_start:train_end]
        y_train = y[train_start:train_end]
        X_test = X[test_start:test_end]
        y_test = y[test_start:test_end]

        feature_stds = np.std(X_train, axis=0)
        valid = feature_stds > 1e-8
        if valid.sum() < 5:
            continue

        X_train_v = X_train[:, valid]
        X_test_v = X_test[:, valid]
        valid_names = [feature_names[j] for j in range(len(valid)) if valid[j]]

        try:
            assert_class_balance(y_train, min_ratio=0.05)
            assert_feature_variance(X_train_v, min_var=1e-6)
        except DegenerateModelError:
            continue

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train_v)
        X_test_s = scaler.transform(X_test_v)

        model = GradientBoostingClassifier(**MODEL_PARAMS)
        model.fit(X_train_s, y_train)

        preds = model.predict(X_test_s)
        probas = model.predict_proba(X_test_s) if hasattr(model, "predict_proba") else None

        acc = accuracy_score(y_test, preds)
        prec = precision_score(y_test, preds, zero_division=0)
        rec = recall_score(y_test, preds, zero_division=0)
        f1 = f1_score(y_test, preds, zero_division=0)

        all_preds.extend(preds.tolist())
        all_actuals.extend(y_test.tolist())
        all_dates.extend(dates[test_start:test_end])
        if probas is not None:
            all_probas.extend(probas.tolist())

        fold_metrics.append({
            "fold": i,
            "train_size": len(y_train),
            "test_size": len(y_test),
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "test_date_start": str(dates[test_start]) if test_start < len(dates) else "unknown",
            "test_date_end": str(dates[test_end - 1]) if test_end - 1 < len(dates) else "unknown",
        })

    if not fold_metrics:
        return None

    # Overall metrics
    overall_acc = accuracy_score(all_actuals, all_preds)
    overall_prec = precision_score(all_actuals, all_preds, zero_division=0)
    overall_rec = recall_score(all_actuals, all_preds, zero_division=0)
    overall_f1 = f1_score(all_actuals, all_preds, zero_division=0)

    # Feature importance from final model using all data
    all_valid = np.std(X, axis=0) > 1e-8
    X_valid = X[:, all_valid]
    valid_names = [feature_names[j] for j in range(len(all_valid)) if all_valid[j]]
    final_scaler = StandardScaler()
    X_s = final_scaler.fit_transform(X_valid)
    final_model = GradientBoostingClassifier(**MODEL_PARAMS)
    final_model.fit(X_s, y)

    importances = final_model.feature_importances_
    top_features = sorted(zip(valid_names, importances), key=lambda x: -x[1])[:15]

    return {
        "n_total": n,
        "n_folds": len(fold_metrics),
        "overall_accuracy": round(overall_acc, 4),
        "overall_precision": round(overall_prec, 4),
        "overall_recall": round(overall_rec, 4),
        "overall_f1": round(overall_f1, 4),
        "baseline_accuracy": round(max(sum(y) / len(y), 1 - sum(y) / len(y)), 4),
        "fold_metrics": fold_metrics,
        "top_features": {name: round(float(imp), 6) for name, imp in top_features},
        "model": final_model,
        "scaler": final_scaler,
        "feature_names": valid_names,
    }


def save_model(ticker: str, result: Dict[str, Any], dry_run: bool = False) -> Optional[Dict[str, Any]]:
    """Save model artifact and manifest."""
    if dry_run:
        logger.info(f"[DRY RUN] Would save model for {ticker}: acc={result['overall_accuracy']}")
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    model_id = f"{ticker}_gbm_wf_{ts}"
    model_path = MODELS_DIR / f"{model_id}.joblib"
    scaler_path = MODELS_DIR / f"{model_id}_scaler.joblib"
    manifest_path = MODELS_DIR / f"{model_id}_manifest.json"

    joblib.dump(result["model"], model_path)
    joblib.dump(result["scaler"], scaler_path)

    manifest = {
        "model_id": model_id,
        "ticker": ticker,
        "model": "gbm_walkforward",
        "feature_version": "v1.0",
        "target": TARGET_COL,
        "n_samples": result["n_total"],
        "n_folds": result["n_folds"],
        "n_features": len(result["feature_names"]),
        "metrics": {
            "overall_accuracy": result["overall_accuracy"],
            "overall_precision": result["overall_precision"],
            "overall_recall": result["overall_recall"],
            "overall_f1": result["overall_f1"],
            "baseline_accuracy": result["baseline_accuracy"],
        },
        "top_features": result["top_features"],
        "fold_summary": result["fold_metrics"][-3:] if len(result["fold_metrics"]) >= 3 else result["fold_metrics"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_path": str(model_path),
        "scaler_path": str(scaler_path),
        "verdict": "SHIP" if result["overall_accuracy"] > result["baseline_accuracy"] else "HOLD",
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    logger.info(f"Saved {model_id}: acc={result['overall_accuracy']}, f1={result['overall_f1']}, verdict={manifest['verdict']}")
    return manifest


def retrain_ticker(ticker: str, dry_run: bool = False) -> Optional[Dict[str, Any]]:
    """Retrain a single ticker."""
    logger.info(f"=== Retraining {ticker} ===")
    try:
        X, y, feature_names, dates, df = load_and_prepare(ticker)
        logger.info(f"Loaded {len(y)} samples, {len(feature_names)} features")
        logger.info(f"Date range: {dates[0]} to {dates[-1]}")
        logger.info(f"Class balance: {sum(y)}/{len(y)} positive ({sum(y)/len(y)*100:.1f}%)")
    except Exception as e:
        logger.error(f"Failed to load data for {ticker}: {e}")
        return None

    result = walk_forward_evaluate(X, y, feature_names, dates)
    if result is None:
        logger.warning(f"Walk-forward evaluation failed for {ticker}")
        return None

    logger.info(f"Walk-forward results ({result['n_folds']} folds):")
    logger.info(f"  Overall accuracy: {result['overall_accuracy']:.4f} (baseline: {result['baseline_accuracy']:.4f})")
    logger.info(f"  Overall F1:       {result['overall_f1']:.4f}")
    logger.info(f"  Precision:        {result['overall_precision']:.4f}")
    logger.info(f"  Recall:           {result['overall_recall']:.4f}")
    logger.info(f"  Top features:     {list(result['top_features'].keys())[:5]}")

    if result["overall_accuracy"] <= result["baseline_accuracy"]:
        logger.warning(f"  VERDICT: HOLD — model doesn't beat baseline ({result['overall_accuracy']:.4f} <= {result['baseline_accuracy']:.4f})")
    else:
        logger.info(f"  VERDICT: SHIP — model beats baseline ({result['overall_accuracy']:.4f} > {result['baseline_accuracy']:.4f})")

    manifest = save_model(ticker, result, dry_run=dry_run)
    return manifest


def main() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Daily ML retraining pipeline")
    parser.add_argument("--ticker", type=str, help="Retrain specific ticker")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate only, don't save")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else list(TICKER_FILES.keys())

    results = {}
    for ticker in tickers:
        manifest = retrain_ticker(ticker, dry_run=args.dry_run)
        if manifest:
            results[ticker] = manifest

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("RETRAINING SUMMARY")
    logger.info("=" * 60)
    for ticker, manifest in results.items():
        m = manifest["metrics"]
        logger.info(f"{ticker}: acc={m['overall_accuracy']:.4f} f1={m['overall_f1']:.4f} verdict={manifest['verdict']}")

    return results


if __name__ == "__main__":
    main()
