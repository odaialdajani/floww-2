"""
backend/scripts/train_spy_model.py

Train SPY directional ML model on real data from MongoDB.

Usage:
    cd backend && source venv/bin/activate
    python scripts/train_spy_model.py --ticker SPY --model-type gbm
    python scripts/train_spy_model.py --ticker SPY --model-type logistic
    python scripts/train_spy_model.py --ticker SPY --model-type rf
    python scripts/train_spy_model.py --ticker SPY --all  # train all models

Walk-forward CV: expanding window, 60-day train, 20-day test, step 20 days.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
log = logging.getLogger("train_spy")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
MODEL_DIR = BACKEND_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

# Target: 1 if next-day return > 0, else 0
TARGET_COL = "target_directional_move"

# Columns to exclude from features
EXCLUDE_COLS = {
    "ticker", "date", "feature_version", "_computed_at",
    "target_directional_move", "target_return_pct",
    "target_range_expansion", "target_gap_move",
    "target_any_materialization", "_id",
}


def load_features_from_db(ticker: str = "SPY") -> pd.DataFrame:
    """Load feature documents from MongoDB into a DataFrame."""
    import pymongo

    client = pymongo.MongoClient(MONGO_URL)
    db = client[DB_NAME]
    docs = list(db["ml_features"].find({"ticker": ticker}).sort("date", 1))
    client.close()

    if not docs:
        log.error(f"No ml_features found for {ticker}")
        return pd.DataFrame()

    df = pd.DataFrame(docs)
    df = df.sort_values("date").reset_index(drop=True)
    log.info(f"Loaded {len(df)} rows for {ticker}, {len(df.columns)} columns")
    return df


def prepare_data(df: pd.DataFrame) -> tuple:
    """Split DataFrame into feature matrix X and target y."""
    feature_cols = [c for c in df.columns if c not in EXCLUDE_COLS]
    X = df[feature_cols].copy()
    y = df[TARGET_COL].copy() if TARGET_COL in df.columns else None

    # Replace inf/-inf with NaN, then fill NaN with 0
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # Convert to numeric
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0.0)

    feature_names = list(X.columns)
    log.info(f"Feature matrix: {X.shape}, target: {y.shape if y is not None else None}")
    return X.values, y.values if y is not None else None, feature_names, df["date"].values


def walk_forward_cv(X, y, dates, n_splits=5, train_size=60, test_size=20, step=20):
    """Expanding-window walk-forward cross-validation splits.

    Each fold: train on expanding window of at least train_size samples,
    test on next test_size samples.
    """
    n = len(X)
    splits = []
    for i in range(n_splits):
        test_start = train_size + i * step
        test_end = min(test_start + test_size, n)
        train_end = test_start

        if train_end < 30 or test_end <= test_start:
            continue

        train_idx = list(range(0, train_end))
        test_idx = list(range(test_start, test_end))

        splits.append((train_idx, test_idx))
        log.info(
            f"Fold {i+1}: train[{train_idx[0]}:{train_end}] ({len(train_idx)} samples) "
            f"test[{test_start}:{test_end}] ({len(test_idx)} samples) "
            f"dates {dates[test_start]} to {dates[test_end-1]}"
        )

    return splits


def compute_sharpe(predictions, actuals):
    """Annualized Sharpe of long-only-on-positive-prediction strategy.

    Trade only when pred==1. Win=+1 if actual==1, else -1.
    Returns 0.0 if fewer than 5 trades or std is negligible.
    Caps Sharpe at 10.0 to avoid numerical artifacts.
    """
    rets = []
    for pred, actual in zip(predictions, actuals):
        if pred == 1:
            rets.append(1.0 if actual == 1 else -1.0)
    if len(rets) < 5:
        return 0.0
    std = np.std(rets)
    if std < 0.05:  # Nearly all same-side returns — Sharpe unreliable
        # Return signed cap based on direction
        return 2.0 if np.mean(rets) > 0 else -2.0
    sharpe = float(np.mean(rets) / std * np.sqrt(252))
    # Cap to avoid numerical explosions
    return max(min(sharpe, 10.0), -10.0)


def train_gbm(X_train, y_train, X_test, y_test):
    """Train Gradient Boosting model."""
    try:
        from sklearn.ensemble import GradientBoostingClassifier
    except ImportError:
        log.error("sklearn not installed. Run: pip install scikit-learn")
        return None

    model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=10,
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def train_logistic(X_train, y_train, X_test, y_test):
    """Train Logistic Regression model."""
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        log.error("sklearn not installed.")
        return None

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    _X_test_s = scaler.transform(X_test)

    model = LogisticRegression(
        C=1.0,
        max_iter=1000,
        random_state=42,
    )
    model.fit(X_train_s, y_train)

    # Return both model and scaler as a pipeline dict
    return {"model": model, "scaler": scaler, "type": "logistic"}


def train_rf(X_train, y_train, X_test, y_test):
    """Train Random Forest model."""
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        log.error("sklearn not installed.")
        return None

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=5,
        min_samples_leaf=10,
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def predict_model(model, X):
    """Get predictions from a model (handles pipeline dict for logistic)."""
    if isinstance(model, dict) and model.get("type") == "logistic":
        X_s = model["scaler"].transform(X)
        return model["model"].predict(X_s)
    return model.predict(X)


def evaluate_model(name, model, X_train, y_train, X_test, y_test, dates_test):
    """Full evaluation with walk-forward metrics."""
    train_pred = predict_model(model, X_train).astype(int)
    test_pred = predict_model(model, X_test).astype(int)
    y_train_int = y_train.astype(int)
    y_test_int = y_test.astype(int)

    train_acc = float(np.mean(train_pred == y_train_int))
    test_acc = float(np.mean(test_pred == y_test_int))

    train_sharpe = compute_sharpe(train_pred, y_train_int)
    test_sharpe = compute_sharpe(test_pred, y_test_int)

    # Majority baseline
    majority_class = int(np.bincount(y_train_int).argmax())
    majority_pred = np.full_like(y_test, majority_class)
    majority_acc = float(np.mean(majority_pred == y_test_int))
    majority_sharpe = compute_sharpe(majority_pred, y_test_int)

    # Persistence baseline (predict same as last known)
    persistence_pred = np.full_like(y_test, y_train_int[-1])
    persistence_acc = float(np.mean(persistence_pred == y_test_int))
    persistence_sharpe = compute_sharpe(persistence_pred, y_test_int)

    result = {
        "model_name": name,
        "train_accuracy": round(train_acc, 4),
        "test_accuracy": round(test_acc, 4),
        "train_sharpe": round(train_sharpe, 4),
        "test_sharpe": round(test_sharpe, 4),
        "majority_accuracy": round(majority_acc, 4),
        "majority_sharpe": round(majority_sharpe, 4),
        "persistence_accuracy": round(persistence_acc, 4),
        "persistence_sharpe": round(persistence_sharpe, 4),
        "beats_majority": test_sharpe > majority_sharpe,
        "beats_persistence": test_sharpe > persistence_sharpe,
        "n_train": len(y_train),
        "n_test": len(y_test),
        "test_date_start": str(dates_test[0]) if len(dates_test) > 0 else "N/A",
        "test_date_end": str(dates_test[-1]) if len(dates_test) > 0 else "N/A",
    }

    log.info(f"  {name}: train_acc={train_acc:.4f} test_acc={test_acc:.4f} "
             f"test_sharpe={test_sharpe:.4f} beats_majority={result['beats_majority']} "
             f"beats_persistence={result['beats_persistence']}")

    return result


def gate_evaluate(result: dict) -> dict:
    """Apply the ML promotion gate. Returns dict with verdict and reasons."""
    reasons = []
    verdict = "SHIP"

    # Rule 1: Must beat majority baseline on Sharpe
    if not result["beats_majority"]:
        verdict = "REJECT"
        reasons.append(f"Sharpe {result['test_sharpe']:.4f} <= majority {result['majority_sharpe']:.4f}")

    # Rule 2: Must beat persistence baseline on Sharpe
    if not result["beats_persistence"]:
        verdict = "REJECT"
        reasons.append(f"Sharpe {result['test_sharpe']:.4f} <= persistence {result['persistence_sharpe']:.4f}")

    # Rule 3: Max Sharpe cap (in-sample artifact detection)
    # With our Sharpe cap at 10.0, this now catches extreme cases only
    if result["train_sharpe"] >= 9.5 and result["train_accuracy"] > 0.95:
        verdict = "REJECT"
        reasons.append(f"Train Sharpe {result['train_sharpe']:.4f} >= 9.5 with accuracy {result['train_accuracy']:.4f} (near-perfect overfit)")

    # Rule 4: Test accuracy must be > 50%
    if result["test_accuracy"] <= 0.50:
        verdict = "REJECT"
        reasons.append(f"Test accuracy {result['test_accuracy']:.4f} <= 0.50")

    # Rule 5: Train-test accuracy gap < 20% (overfit check)
    gap = result["train_accuracy"] - result["test_accuracy"]
    if gap > 0.20:
        verdict = "REJECT"
        reasons.append(f"Train-test accuracy gap {gap:.4f} > 0.20 (overfit)")

    result["verdict"] = verdict
    result["rejection_reasons"] = reasons

    if verdict == "SHIP":
        log.info(f"  ✅ {result['model_name']}: SHIP — Sharpe={result['test_sharpe']:.4f}")
    else:
        log.info(f"  ❌ {result['model_name']}: REJECT — {'; '.join(reasons)}")

    return result


def save_model(name, model, feature_names, result: dict, ticker: str):
    """Save model artifact and metadata."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    model_filename = f"{ticker}_{name}_{timestamp}.joblib"
    model_path = MODEL_DIR / model_filename

    artifact = {
        "model": model,
        "feature_names": feature_names,
        "model_name": name,
        "ticker": ticker,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": result,
    }
    joblib.dump(artifact, model_path)
    log.info(f"  Saved model to {model_path}")

    # Also save metadata as JSON
    meta_path = MODEL_DIR / f"{ticker}_{name}_{timestamp}_meta.json"
    meta = {k: v for k, v in result.items() if k != "model"}
    meta["model_file"] = str(model_path)
    meta["feature_names"] = feature_names
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, default=str)

    return model_path


async def main():
    parser = argparse.ArgumentParser(description="Train SPY ML model")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--model-type", default="gbm", choices=["gbm", "logistic", "rf", "all"])
    parser.add_argument("--train-size", type=int, default=60)
    parser.add_argument("--test-size", type=int, default=20)
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--save", action="store_true", help="Save best model")
    args = parser.parse_args()

    log.info(f"Training {args.ticker} model (type={args.model_type})")

    # Load data
    df = load_features_from_db(args.ticker)
    if df.empty:
        log.error("No data available. Run feature computation first.")
        sys.exit(1)

    X, y, feature_names, dates = prepare_data(df)
    if y is None:
        log.error("No target column found in features.")
        sys.exit(1)

    log.info(f"Dataset: {X.shape[0]} samples, {X.shape[1]} features")
    log.info(f"Target distribution: {np.bincount(y.astype(int))}")

    # Walk-forward CV
    splits = walk_forward_cv(X, y, dates, args.n_splits, args.train_size, args.test_size, args.step)
    if not splits:
        log.error("Not enough data for walk-forward CV with these parameters.")
        sys.exit(1)

    # Train models
    model_trainers = {
        "gbm": train_gbm,
        "logistic": train_logistic,
        "rf": train_rf,
    }

    if args.model_type == "all":
        types_to_train = list(model_trainers.keys())
    else:
        types_to_train = [args.model_type]

    all_results = []

    for model_type in types_to_train:
        log.info(f"\n{'='*60}")
        log.info(f"Training {model_type}")
        log.info(f"{'='*60}")

        fold_results = []
        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            dates_test = dates[test_idx]

            model = model_trainers[model_type](X_train, y_train, X_test, y_test)
            if model is None:
                continue

            result = evaluate_model(
                f"{model_type}_fold{fold_idx+1}",
                model, X_train, y_train, X_test, y_test, dates_test,
            )
            result = gate_evaluate(result)
            result["fold"] = fold_idx + 1
            fold_results.append(result)

        if fold_results:
            # Average metrics across folds
            avg_result = {
                "model_name": model_type,
                "n_folds": len(fold_results),
                "avg_test_sharpe": round(np.mean([r["test_sharpe"] for r in fold_results]), 4),
                "avg_test_accuracy": round(np.mean([r["test_accuracy"] for r in fold_results]), 4),
                "avg_train_sharpe": round(np.mean([r["train_sharpe"] for r in fold_results]), 4),
                "avg_train_accuracy": round(np.mean([r["train_accuracy"] for r in fold_results]), 4),
                "folds_ship": sum(1 for r in fold_results if r["verdict"] == "SHIP"),
                "folds_reject": sum(1 for r in fold_results if r["verdict"] == "REJECT"),
                "fold_details": fold_results,
            }
            all_results.append(avg_result)

            log.info(f"\n{model_type} Summary: avg_test_sharpe={avg_result['avg_test_sharpe']:.4f} "
                     f"SHIP={avg_result['folds_ship']}/{avg_result['n_folds']} folds")

    # Print final comparison
    log.info(f"\n{'='*60}")
    log.info("FINAL RESULTS")
    log.info(f"{'='*60}")
    for r in all_results:
        log.info(f"  {r['model_name']:12s}: Sharpe={r['avg_test_sharpe']:.4f} "
                 f"Acc={r['avg_test_accuracy']:.4f} "
                 f"SHIP={r['folds_ship']}/{r['n_folds']}")

    # Save best model
    if args.save and all_results:
        best = max(all_results, key=lambda r: r["avg_test_sharpe"])
        if best["folds_ship"] > 0:
            # Retrain on all available data
            log.info(f"\nRetraining best model ({best['model_name']}) on full dataset...")
            trainer = model_trainers[best["model_name"]]
            final_model = trainer(X, y, X[:10], y[:10])
            if final_model is not None:
                save_model(best["model_name"], final_model, feature_names, best, args.ticker)
        else:
            log.warning("No model passed the gate. Nothing to save.")

    # Output JSON summary
    output = {
        "ticker": args.ticker,
        "n_samples": X.shape[0],
        "n_features": X.shape[1],
        "feature_names": feature_names,
        "models": all_results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
