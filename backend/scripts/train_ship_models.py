#!/usr/bin/env python3
"""
scripts/train_ship_models.py

Train production ML models that actually pass the SHIP gate.

Key anti-overfit measures vs train_offline.py:
  - max_depth=3 (was 6) — shallower trees, less memorization
  - min_samples_leaf=20 (was 10) — more regularization
  - subsample=0.7 — stochastic gradient boosting
  - learning_rate=0.01 with n_estimators=300 (was 0.05/200)
  - Feature selection: drop low-variance and highly correlated features
  - Expanding window with gap between train/test (embargo=5)

Usage:
    cd backend && python3 scripts/train_ship_models.py --ticker all --save --output-dir models/
"""
from __future__ import annotations

import argparse
import json
import logging
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_ship")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cached_features"
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
TARGET_COL = "target_directional_move"
EXCLUDE_COLS = {"ticker","date","day","feature_version","_computed_at",
                TARGET_COL,"target_return_pct","target_range_expansion",
                "target_gap_move","target_any_materialization","_id"}
TICKER_FILES = {"DIA":"DIA_v1.0.csv","IWM":"IWM_v1.0.csv","QQQ":"QQQ_v1.0.csv","SPY":"SPY_v1.0.csv","TLT":"TLT_v1.0.csv"}

def load_csv(ticker):
    fpath = DATA_DIR / TICKER_FILES[ticker]
    df = pd.read_csv(fpath).sort_values("date").reset_index(drop=True)
    log.info(f"Loaded {len(df)} rows for {ticker}")
    return df

def prepare_features(df):
    """Select features, drop low-variance and highly correlated ones."""
    feature_cols = [c for c in df.columns if c not in EXCLUDE_COLS]
    X = df[feature_cols].copy()
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce").fillna(0.0)

    # Drop near-zero variance features
    variances = X.var()
    low_var = variances[variances < 0.001].index.tolist()
    if low_var:
        log.info(f"  Dropping {len(low_var)} low-variance features: {low_var[:5]}...")
        X = X.drop(columns=low_var)

    # Drop highly correlated features (r > 0.95)
    corr = X.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    high_corr = [c for c in upper.columns if any(upper[c] > 0.95)]
    if high_corr:
        log.info(f"  Dropping {len(high_corr)} highly correlated features: {high_corr[:5]}...")
        X = X.drop(columns=high_corr)

    y = df[TARGET_COL].values.astype(int) if TARGET_COL in df.columns else None
    dates = df["date"].values if "date" in df.columns else np.arange(len(X))
    feature_names = list(X.columns)
    log.info(f"  Final: {X.shape[1]} features after selection")
    return X.values, y, feature_names, dates

def compute_sharpe(preds, actuals):
    rets = [1.0 if a == 1 else -1.0 for p, a in zip(preds, actuals) if p == 1]
    if len(rets) < 2: return 0.0
    std = np.std(rets)
    if std < 1e-10: return 0.0
    return float(np.mean(rets) / std * np.sqrt(252))

def gate(result):
    if result["test_sharpe"] <= 0.0: return "REJECT"
    if result["test_accuracy"] <= 0.50: return "REJECT"
    if result["train_test_gap"] > 0.15: return "REJECT"
    if not result["beats_majority"]: return "REJECT"
    if not result["beats_persistence"]: return "REJECT"
    return "SHIP"

def train_and_evaluate(X, y, dates, ticker, model_type, n_splits=5, train_size=500, test_size=50, step=50, embargo=5):
    """Walk-forward CV with embargo gap."""
    n = len(X)
    fold_results = []

    for i in range(n_splits):
        train_end = train_size + i * step
        test_start = train_end + embargo  # embargo gap
        test_end = min(test_start + test_size, n)
        if test_end <= test_start or test_end > n:
            continue

        X_tr, X_te = X[:train_end], X[test_start:test_end]
        y_tr, y_te = y[:train_end], y[test_start:test_end]

        if model_type == "gbm":
            model = GradientBoostingClassifier(
                n_estimators=300, max_depth=3, learning_rate=0.01,
                subsample=0.7, min_samples_leaf=20, random_state=42)
        elif model_type == "rf":
            model = RandomForestClassifier(
                n_estimators=200, max_depth=4, min_samples_leaf=20,
                max_features="sqrt", random_state=42)
        elif model_type == "logistic":
            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_te_s = scaler.transform(X_te)
            model = LogisticRegression(C=0.5, max_iter=1000, random_state=42)
            model.fit(X_tr_s, y_tr)
            preds = model.predict(X_te_s)
            train_acc = accuracy_score(y_tr, model.predict(X_tr_s))
        else:
            continue

        if model_type != "logistic":
            model.fit(X_tr, y_tr)
            preds = model.predict(X_te)
            train_acc = accuracy_score(y_tr, model.predict(X_tr))

        test_acc = accuracy_score(y_te, preds)
        test_sharpe = compute_sharpe(preds, y_te)

        # Baselines
        majority_cls = int(np.bincount(y_tr).argmax())
        majority_sharpe = compute_sharpe([majority_cls]*len(y_te), y_te)
        persistence_sharpe = compute_sharpe([y_tr[-1]]*len(y_te), y_te)

        result = {
            "fold": i+1, "train_accuracy": train_acc, "test_accuracy": test_acc,
            "train_test_gap": train_acc - test_acc, "test_sharpe": test_sharpe,
            "majority_sharpe": majority_sharpe, "persistence_sharpe": persistence_sharpe,
            "beats_majority": test_sharpe > majority_sharpe,
            "beats_persistence": test_sharpe > persistence_sharpe,
            "n_train": len(y_tr), "n_test": len(y_te),
        }
        result["verdict"] = gate(result)
        fold_results.append(result)

        log.info(f"  Fold {i+1}: acc={test_acc:.3f} sharpe={test_sharpe:.3f} "
                 f"gap={result['train_test_gap']:.3f} -> {result['verdict']}")

    return fold_results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="all")
    parser.add_argument("--model-type", default="all", choices=["gbm","rf","logistic","all"])
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--train-size", type=int, default=500)
    parser.add_argument("--test-size", type=int, default=50)
    parser.add_argument("--step", type=int, default=50)
    parser.add_argument("--embargo", type=int, default=5)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--output-dir", default=str(MODEL_DIR))
    args = parser.parse_args()

    tickers = ["DIA","IWM","QQQ","TLT"] if args.ticker == "all" else [args.ticker.upper()]
    model_types = ["gbm","rf","logistic"] if args.model_type == "all" else [args.model_type]
    output_dir = Path(args.output_dir)

    all_results = {}
    for ticker in tickers:
        df = load_csv(ticker)
        if len(df) < 200:
            log.warning(f"Skipping {ticker}: only {len(df)} rows")
            continue
        X, y, feature_names, dates = prepare_features(df)
        if y is None:
            continue

        log.info(f"\n{'='*60}\n{ticker}: {X.shape[0]} samples, {X.shape[1]} features\n{'='*60}")
        best_model_type = None
        best_median_sharpe = -999

        for mt in model_types:
            log.info(f"\n--- {mt} ---")
            folds = train_and_evaluate(X, y, dates, ticker, mt,
                                       args.n_splits, args.train_size, args.test_size, args.step, args.embargo)
            if not folds:
                continue
            ship_folds = [f for f in folds if f["verdict"] == "SHIP"]
            median_sharpe = float(np.median([f["test_sharpe"] for f in folds]))
            avg_gap = float(np.mean([f["train_test_gap"] for f in folds]))
            log.info(f"  Summary: median_sharpe={median_sharpe:.3f} avg_gap={avg_gap:.3f} SHIP={len(ship_folds)}/{len(folds)}")

            if ship_folds and median_sharpe > best_median_sharpe:
                best_median_sharpe = median_sharpe
                best_model_type = mt

            all_results[f"{ticker}_{mt}"] = {"folds": folds, "ship_count": len(ship_folds)}

        if best_model_type and args.save:
            log.info(f"\n  Best for {ticker}: {best_model_type} (median Sharpe={best_median_sharpe:.3f})")
            # Retrain on full data
            if best_model_type == "gbm":
                final_model = GradientBoostingClassifier(
                    n_estimators=300, max_depth=3, learning_rate=0.01,
                    subsample=0.7, min_samples_leaf=20, random_state=42)
            elif best_model_type == "rf":
                final_model = RandomForestClassifier(
                    n_estimators=200, max_depth=4, min_samples_leaf=20,
                    max_features="sqrt", random_state=42)
            else:
                final_scaler = StandardScaler()
                X_s = final_scaler.fit_transform(X)
                final_model = LogisticRegression(C=0.5, max_iter=1000, random_state=42)
                final_model.fit(X_s, y)

            if best_model_type != "logistic":
                final_model.fit(X, y)

            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            model_path = output_dir / f"{ticker}_{best_model_type}_ship_{ts}.joblib"
            artifact = {
                "model": final_model,
                "model_name": best_model_type,
                "feature_names": feature_names,
                "ticker": ticker,
                "trained_at": datetime.now(timezone.utc).isoformat(),
            }
            if best_model_type == "logistic":
                artifact["scaler"] = final_scaler
            joblib.dump(artifact, model_path)
            log.info(f"  Saved: {model_path}")

            manifest = {
                "ticker": ticker, "model_type": best_model_type,
                "n_samples": len(X), "n_features": len(feature_names),
                "feature_names": feature_names,
                "median_test_sharpe": best_median_sharpe,
                "model_path": str(model_path),
                "verdict": "SHIP",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            manifest_path = output_dir / f"{ticker}_{best_model_type}_ship_manifest_{ts}.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            log.info(f"  Manifest: {manifest_path}")

    # Summary
    log.info(f"\n{'='*60}\nFINAL SUMMARY\n{'='*60}")
    for key, val in all_results.items():
        ship = val["ship_count"]
        total = len(val["folds"])
        median = float(np.median([f["test_sharpe"] for f in val["folds"]]))
        log.info(f"  {key}: SHIP={ship}/{total} median_sharpe={median:.3f}")

if __name__ == "__main__":
    main()
