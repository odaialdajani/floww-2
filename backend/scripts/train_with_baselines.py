"""
backend/scripts/train_with_baselines.py

Production ML training script with:
  - Real baseline computation (majority, persistence, logistic regression)
  - Proper time-ordered train/test/holdout splits (60/20/20) with embargo
  - Walk-forward CV with per-fold Sharpe reporting
  - Pre-save quality gates (class balance, feature variance, prediction distribution)
  - Meta JSON audit validation (flags sharpe>5, empty baselines)
  - Model registry integration via ModelRegistry

Usage:
    python train_with_baselines.py --ticker SPY --feature-version v2.0
    python train_with_baselines.py --ticker QQQ --feature-version v2.0 --walk-forward
    python train_with_baselines.py --all-tickers --feature-version v2.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BACKEND_DIR / "logs" / "train_with_baselines.log"),
    ],
)
log = logging.getLogger("train_baselines")

BACKEND_DIR.joinpath("logs").mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBARGO_DAYS = 5  # gap between train and test to prevent leakage
MAX_PLAUSIBLE_DAILY_SHARPE = 10.0  # above this = in-sample artifact
MIN_SAMPLES = 50  # minimum rows to attempt training
MIN_CLASS_RATIO = 0.20  # minimum minority class fraction

REQUIRED_BASELINES = ("majority", "persistence", "logistic")

MODEL_DIR = BACKEND_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

REPORTS_DIR = BACKEND_DIR.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Baseline computation
# ---------------------------------------------------------------------------

def compute_majority_baseline(y_train: np.ndarray, n_test: int) -> np.ndarray:
    """Predict the majority class for every test sample."""
    majority_class = int(np.bincount(y_train.astype(int)).argmax())
    return np.full(n_test, majority_class)


def compute_persistence_baseline(y_train: np.ndarray, n_test: int) -> np.ndarray:
    """Predict the last observed label for every test sample."""
    last_label = int(y_train[-1])
    return np.full(n_test, last_label)


def compute_logistic_baseline(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
) -> np.ndarray:
    """Train a penalized logistic regression and predict on test."""
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_train)
        X_te = scaler.transform(X_test)

        clf = LogisticRegression(
            C=1.0, max_iter=1000, random_state=42, solver="lbfgs"
        )
        clf.fit(X_tr, y_train)
        return clf.predict(X_te)
    except Exception as e:
        log.warning(f"Logistic baseline failed: {e}; falling back to majority")
        return compute_majority_baseline(y_train, len(X_test))


def compute_all_baselines(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
) -> Dict[str, np.ndarray]:
    """Compute all required baselines. Returns dict of name -> predictions."""
    n_test = len(X_test)
    return {
        "majority": compute_majority_baseline(y_train, n_test),
        "persistence": compute_persistence_baseline(y_train, n_test),
        "logistic": compute_logistic_baseline(X_train, y_train, X_test),
    }


# ---------------------------------------------------------------------------
# Sharpe computation
# ---------------------------------------------------------------------------

def compute_trading_sharpe(predictions: np.ndarray, actuals: np.ndarray) -> float:
    """Annualized Sharpe of a simple long-only-on-positive-prediction strategy.

    Trade only when pred == 1. Win = +1 if actual == 1, else -1.
    Flat predictions (pred == 0) are skipped.
    """
    rets = []
    for pred, actual in zip(predictions, actuals):
        if pred == 1:
            rets.append(1.0 if actual == 1 else -1.0)
    if len(rets) < 2:
        return 0.0
    arr = np.array(rets)
    return float(np.mean(arr) / (np.std(arr) + 1e-8) * np.sqrt(252))


# ---------------------------------------------------------------------------
# Time-ordered split with embargo
# ---------------------------------------------------------------------------

def time_ordered_split(
    n_samples: int,
    train_frac: float = 0.60,
    test_frac: float = 0.20,
    embargo: int = EMBARGO_DAYS,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split indices into train/test/holdout with temporal ordering and embargo.

    Args:
        n_samples: Total number of samples (already sorted by time)
        train_frac: Fraction for training
        test_frac: Fraction for testing (remainder is holdout)
        embargo: Number of samples to skip between train and test

    Returns:
        (train_indices, test_indices, holdout_indices)
    """
    train_end = int(n_samples * train_frac)
    test_end = int(n_samples * (train_frac + test_frac))

    # Apply embargo: skip `embargo` samples between train and test
    test_start = min(train_end + embargo, n_samples)
    # If embargo pushes test into holdout, reduce test size
    if test_start >= test_end:
        test_start = train_end
        test_end = min(train_end + max(1, (test_end - train_end) // 2), n_samples)

    train_idx = np.arange(0, train_end)
    test_idx = np.arange(test_start, test_end)
    holdout_idx = np.arange(test_end, n_samples)

    return train_idx, test_idx, holdout_idx


def walk_forward_splits(
    n_samples: int,
    n_splits: int = 5,
    min_train_size: int = 100,
    embargo: int = EMBARGO_DAYS,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Generate walk-forward train/test splits.

    Each split expands the training window and tests on the next chunk.
    An embargo gap is maintained between train and test.
    """
    splits = []
    test_size = max(20, (n_samples - min_train_size) // (n_splits + 1))

    for i in range(n_splits):
        train_end = min_train_size + i * test_size
        test_start = train_end + embargo
        test_end = min(test_start + test_size, n_samples)

        if test_start >= n_samples or test_end - test_start < 5:
            break

        train_idx = np.arange(0, train_end)
        test_idx = np.arange(test_start, test_end)
        splits.append((train_idx, test_idx))

    return splits


# ---------------------------------------------------------------------------
# Feature loading from MongoDB
# ---------------------------------------------------------------------------

async def load_features_from_db(
    ticker: str,
    feature_version: str = "v1.0",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """Load computed features from MongoDB ml_features collection."""
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "confluence_decoder")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    col = db["ml_features"]

    query: Dict[str, Any] = {"ticker": ticker, "feature_version": feature_version}
    if start or end:
        date_q: Dict[str, Any] = {}
        if start:
            date_q["$gte"] = start
        if end:
            date_q["$lte"] = end
        query["date"] = date_q

    cursor = col.find(query, {"_id": 0}).sort("date", 1)
    rows = await cursor.to_list(length=100000)
    client.close()

    if not rows:
        log.warning(f"No features found for {ticker} v{feature_version}")
        return None

    df = pd.DataFrame(rows)
    log.info(f"Loaded {len(df)} feature rows for {ticker} v{feature_version}")
    return df


def prepare_feature_matrix(
    df: pd.DataFrame,
    target_col: str = "target_directional_move",
    exclude_cols: Optional[List[str]] = None,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Extract feature matrix X, target vector y, and feature names from DataFrame."""
    if exclude_cols is None:
        exclude_cols = [
            "ticker", "date", "feature_version", "_computed_at",
            "target_directional_move", "target_return_pct",
            "target_range_expansion", "target_gap_move",
            "target_any_materialization",
        ]

    feature_names = [c for c in df.columns if c not in exclude_cols]
    X = df[feature_names].values.astype(float)
    y = df[target_col].values.astype(float) if target_col in df.columns else np.zeros(len(df))

    # Replace NaN/inf with 0
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    return X, y, feature_names


# ---------------------------------------------------------------------------
# Model training with full pipeline
# ---------------------------------------------------------------------------

def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    model_type: str = "gbm",
) -> Any:
    """Train a model. Supports gbm, rf, logistic."""
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)

    if model_type == "gbm":
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42,
            subsample=0.8, min_samples_leaf=10,
        )
    elif model_type == "rf":
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(
            n_estimators=100, max_depth=5, random_state=42,
            min_samples_leaf=10, n_jobs=-1,
        )
    elif model_type == "logistic":
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    model.fit(X_scaled, y_train)
    return model, scaler


def evaluate_model(
    model: Any,
    scaler: Any,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> Dict[str, float]:
    """Evaluate a trained model. Returns metrics dict."""
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    X_scaled = scaler.transform(X_test)
    y_pred = model.predict(X_scaled)
    _y_proba = model.predict_proba(X_scaled)[:, 1] if hasattr(model, "predict_proba") else y_pred.astype(float)

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "sharpe": compute_trading_sharpe(y_pred, y_test),
        "n_test": len(y_test),
        "class_balance_test": float(np.mean(y_test)) if len(y_test) > 0 else 0.0,
    }
    return metrics


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

def run_quality_gates(
    X_train: np.ndarray,
    y_train: np.ndarray,
    y_pred_proba: np.ndarray,
    y_test: Optional[np.ndarray] = None,
) -> Dict[str, bool]:
    """Run pre-save quality gates. Raises on failure."""
    from services.ml import DegenerateModelError
    from services.ml.quality import (
        assert_class_balance,
        assert_feature_variance,
        assert_prediction_distribution,
    )

    results = {}
    try:
        assert_class_balance(y_train, label="y_train")
        results["class_balance_train"] = True
    except DegenerateModelError as e:
        log.error(f"Quality gate FAILED (class_balance_train): {e}")
        raise

    if y_test is not None and len(y_test) > 0:
        try:
            assert_class_balance(y_test, label="y_test")
            results["class_balance_test"] = True
        except DegenerateModelError as e:
            log.warning(f"Quality gate warning (class_balance_test): {e}")

    try:
        assert_feature_variance(X_train)
        results["feature_variance"] = True
    except DegenerateModelError as e:
        log.error(f"Quality gate FAILED (feature_variance): {e}")
        raise

    try:
        assert_prediction_distribution(y_pred_proba)
        results["prediction_distribution"] = True
    except DegenerateModelError as e:
        log.error(f"Quality gate FAILED (prediction_distribution): {e}")
        raise

    return results


# ---------------------------------------------------------------------------
# Audit validation
# ---------------------------------------------------------------------------

def audit_meta_json(meta: Dict[str, Any]) -> List[str]:
    """Validate training meta JSON. Returns list of warnings."""
    warnings = []

    sharpe = meta.get("sharpe", 0.0)
    if sharpe > MAX_PLAUSIBLE_DAILY_SHARPE:
        warnings.append(
            f"SHARPE_TOO_HIGH: {sharpe:.2f} > {MAX_PLAUSIBLE_DAILY_SHARPE} "
            f"(likely in-sample artifact)"
        )

    baselines = meta.get("baselines", {})
    if not baselines:
        warnings.append("EMPTY_BASELINES: no baselines computed — model is unverified")
    else:
        missing = [b for b in REQUIRED_BASELINES if b not in baselines]
        if missing:
            warnings.append(f"MISSING_BASELINES: {missing}")

    beats = meta.get("beats_baselines")
    if beats is True and not baselines:
        warnings.append("BEATS_BASELINES_WITHOUT_DATA: beats_baselines=True but baselines empty")

    n_samples = meta.get("n_train", 0)
    n_features = meta.get("n_features", 0)
    if n_features > 0 and n_samples > 0 and n_samples / n_features < 5:
        warnings.append(
            f"LOW_SAMPLE_RATIO: {n_samples} samples / {n_features} features "
            f"= {n_samples/n_features:.1f}x (need >= 5x)"
        )

    return warnings


# ---------------------------------------------------------------------------
# Main training pipeline
# ---------------------------------------------------------------------------

async def train_one_ticker(
    ticker: str,
    feature_version: str = "v1.0",
    model_types: Optional[List[str]] = None,
    walk_forward: bool = False,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """Full training pipeline for one ticker.

    Loads features, splits data, trains models, computes baselines,
    runs quality gates, saves artifacts, and returns a report.
    """
    if model_types is None:
        model_types = ["gbm", "rf", "logistic"]

    log.info(f"{'='*60}")
    log.info(f"Training {ticker} v{feature_version} | walk_forward={walk_forward}")
    log.info(f"{'='*60}")

    # 1. Load features
    df = await load_features_from_db(ticker, feature_version, start=start, end=end)
    if df is None or len(df) < MIN_SAMPLES:
        msg = f"Insufficient data for {ticker}: {len(df) if df is not None else 0} rows"
        log.warning(msg)
        return {"status": "insufficient_data", "ticker": ticker, "message": msg}

    X, y, feature_names = prepare_feature_matrix(df)
    _dates = df["date"].tolist() if "date" in df.columns else [str(i) for i in range(len(df))]

    log.info(f"Feature matrix: {X.shape[0]} samples, {X.shape[1]} features")
    log.info(f"Target balance: {np.mean(y):.3f} positive rate")

    # 2. Split data
    if walk_forward:
        splits = walk_forward_splits(len(X), n_splits=5)
        log.info(f"Walk-forward: {len(splits)} folds")
    else:
        train_idx, test_idx, holdout_idx = time_ordered_split(len(X))
        splits = [(train_idx, test_idx)]
        log.info(f"Single split: train={len(train_idx)}, test={len(test_idx)}, holdout={len(holdout_idx)}")

    # 3. Train each model type
    all_results: Dict[str, Any] = {}
    _best_model = None
    best_sharpe = -np.inf
    _best_model_type = None

    for model_type in model_types:
        log.info(f"\n--- Training {model_type} ---")

        fold_sharpes = []
        fold_accuracies = []
        all_test_actuals = []
        all_test_preds = []
        all_test_probas = []

        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            # Skip if too few samples
            if len(train_idx) < MIN_SAMPLES // 2 or len(test_idx) < 10:
                log.warning(f"  Fold {fold_idx}: skipping (train={len(train_idx)}, test={len(test_idx)})")
                continue

            try:
                model, scaler = train_model(X_train, y_train, model_type)
            except Exception as e:
                log.warning(f"  Fold {fold_idx}: training failed: {e}")
                continue

            # Evaluate
            metrics = evaluate_model(model, scaler, X_test, y_test)
            fold_sharpes.append(metrics["sharpe"])
            fold_accuracies.append(metrics["accuracy"])

            all_test_actuals.extend(y_test.tolist())
            X_test_scaled = scaler.transform(X_test)
            y_pred = model.predict(X_test_scaled)
            all_test_preds.extend(y_pred.tolist())
            if hasattr(model, "predict_proba"):
                all_test_probas.extend(model.predict_proba(X_test_scaled)[:, 1].tolist())

            log.info(
                f"  Fold {fold_idx}: acc={metrics['accuracy']:.3f}, "
                f"sharpe={metrics['sharpe']:.2f}, n_test={metrics['n_test']}"
            )

        if not fold_sharpes:
            log.warning(f"  {model_type}: no successful folds")
            all_results[model_type] = {"status": "no_successful_folds"}
            continue

        # Aggregate across folds
        avg_sharpe = float(np.mean(fold_sharpes))
        avg_accuracy = float(np.mean(fold_accuracies))

        # Compute baselines on the last fold's train/test split
        last_train_idx, last_test_idx = splits[-1]
        X_train_last, X_test_last = X[last_train_idx], X[last_test_idx]
        y_train_last, y_test_last = y[last_train_idx], y[last_test_idx]

        baselines = compute_all_baselines(X_train_last, y_train_last, X_test_last)
        baseline_metrics = {}
        for name, preds in baselines.items():
            baseline_metrics[name] = {
                "accuracy": float(np.mean(preds == y_test_last)),
                "sharpe": compute_trading_sharpe(preds, y_test_last),
            }

        # Check if model beats all baselines
        beats_all = all(
            avg_sharpe > baseline_metrics[b]["sharpe"]
            for b in REQUIRED_BASELINES
            if b in baseline_metrics
        )

        # Sanity cap on Sharpe
        if avg_sharpe > MAX_PLAUSIBLE_DAILY_SHARPE:
            beats_all = False
            log.warning(f"  {model_type}: Sharpe {avg_sharpe:.2f} > cap {MAX_PLAUSIBLE_DAILY_SHARPE}, REJECTED")

        result = {
            "status": "ok" if beats_all else "rejected",
            "model_type": model_type,
            "avg_sharpe": round(avg_sharpe, 4),
            "avg_accuracy": round(avg_accuracy, 4),
            "fold_sharpes": [round(s, 4) for s in fold_sharpes],
            "fold_accuracies": [round(a, 4) for a in fold_accuracies],
            "baselines": baseline_metrics,
            "beats_baselines": beats_all,
            "n_folds": len(fold_sharpes),
            "n_train": int(len(last_train_idx)),
            "n_test": int(len(last_test_idx)),
            "n_features": len(feature_names),
        }

        if not beats_all:
            reasons = []
            for b in REQUIRED_BASELINES:
                if b in baseline_metrics:
                    if avg_sharpe <= baseline_metrics[b]["sharpe"]:
                        reasons.append(f"{b}({baseline_metrics[b]['sharpe']:.2f})")
            if avg_sharpe > MAX_PLAUSIBLE_DAILY_SHARPE:
                reasons.append(f"sharpe>{MAX_PLAUSIBLE_DAILY_SHARPE}")
            result["rejection_reason"] = "did not beat: " + ", ".join(reasons)

        all_results[model_type] = result

        log.info(
            f"  {model_type}: avg_sharpe={avg_sharpe:.2f}, "
            f"beats_baselines={beats_all}"
        )
        for b, m in baseline_metrics.items():
            log.info(f"    baseline {b}: sharpe={m['sharpe']:.2f}, acc={m['accuracy']:.3f}")

        if beats_all and avg_sharpe > best_sharpe:
            best_sharpe = avg_sharpe
            best_model_type = model_type

    # 4. Train final model on best type and save
    saved_model = None
    if best_model_type is not None:
        log.info(f"\nBest model: {best_model_type} (sharpe={best_sharpe:.2f})")

        # Retrain on the full training portion (train + test, not holdout)
        if walk_forward:
            # Use the last fold's train+test for final training
            last_train_idx, last_test_idx = splits[-1]
            final_train_idx = np.concatenate([last_train_idx, last_test_idx])
        else:
            train_idx, test_idx, holdout_idx = time_ordered_split(len(X))
            final_train_idx = np.concatenate([train_idx, test_idx])

        X_final = X[final_train_idx]
        y_final = y[final_train_idx]

        try:
            model, scaler = train_model(X_final, y_final, best_model_type)

            # Run quality gates
            X_final_scaled = scaler.transform(X_final)
            y_pred_proba = model.predict_proba(X_final_scaled)[:, 1]
            gate_results = run_quality_gates(X_final, y_final, y_pred_proba)

            # Save
            model_id = f"{ticker}_{best_model_type}_v2.0"
            model_path = str(MODEL_DIR / f"{model_id}.joblib")
            scaler_path = str(MODEL_DIR / f"{model_id}_scaler.joblib")

            import joblib
            joblib.dump(model, model_path)
            joblib.dump(scaler, scaler_path)

            # Build meta JSON
            meta = {
                "model_id": model_id,
                "ticker": ticker,
                "feature_version": feature_version,
                "model_type": best_model_type,
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "n_train": len(final_train_idx),
                "n_features": len(feature_names),
                "feature_names": feature_names,
                "sharpe": round(best_sharpe, 4),
                "baselines": all_results[best_model_type]["baselines"],
                "beats_baselines": True,
                "quality_gates": gate_results,
                "walk_forward": walk_forward,
                "n_folds": all_results[best_model_type]["n_folds"],
                "fold_sharpes": all_results[best_model_type]["fold_sharpes"],
                "model_path": model_path,
                "scaler_path": scaler_path,
            }

            # Audit
            audit_warnings = audit_meta_json(meta)
            meta["audit_warnings"] = audit_warnings
            if audit_warnings:
                log.warning(f"Audit warnings: {audit_warnings}")

            meta_path = str(MODEL_DIR / f"{model_id}_meta.json")
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2, default=str)

            log.info(f"Saved model to {model_path}")
            log.info(f"Saved meta to {meta_path}")

            saved_model = {
                "model_id": model_id,
                "model_path": model_path,
                "scaler_path": scaler_path,
                "meta_path": meta_path,
            }

        except Exception as e:
            log.error(f"Failed to save best model: {e}")
            all_results["save_error"] = str(e)
    else:
        log.warning("No model passed the SHIP gate")

    # 5. Build report
    report = {
        "ticker": ticker,
        "feature_version": feature_version,
        "n_samples": len(X),
        "n_features": len(feature_names),
        "walk_forward": walk_forward,
        "model_results": all_results,
        "best_model_type": best_model_type,
        "best_sharpe": round(best_sharpe, 4) if best_model_type else None,
        "saved_model": saved_model,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    # Save report
    report_path = str(REPORTS_DIR / f"training_{ticker}_v2.0_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info(f"Report saved to {report_path}")

    return report


async def main():
    parser = argparse.ArgumentParser(description="Train ML models with real baselines")
    parser.add_argument("--ticker", default="SPY", help="Ticker to train")
    parser.add_argument("--feature-version", default="v1.0", help="Feature version")
    parser.add_argument("--walk-forward", action="store_true", help="Use walk-forward CV")
    parser.add_argument("--model-types", default="gbm,rf,logistic", help="Comma-separated model types")
    parser.add_argument("--all-tickers", action="store_true", help="Train all configured tickers")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    tickers = ["SPY", "QQQ", "IWM", "DIA", "TLT"] if args.all_tickers else [args.ticker]
    model_types = args.model_types.split(",")

    all_reports = {}
    for ticker in tickers:
        try:
            report = await train_one_ticker(
                ticker=ticker,
                feature_version=args.feature_version,
                model_types=model_types,
                walk_forward=args.walk_forward,
                start=args.start,
                end=args.end,
            )
            all_reports[ticker] = report
        except Exception as e:
            log.error(f"Training failed for {ticker}: {e}")
            all_reports[ticker] = {"status": "error", "message": str(e)}

    # Summary
    log.info(f"\n{'='*60}")
    log.info("TRAINING SUMMARY")
    log.info(f"{'='*60}")
    for ticker, report in all_reports.items():
        status = report.get("status", "unknown")
        best_type = report.get("best_model_type", "none")
        best_sharpe = report.get("best_sharpe", 0)
        log.info(f"  {ticker}: status={status}, best={best_type}, sharpe={best_sharpe}")

    # Save combined report
    combined_path = str(REPORTS_DIR / f"training_combined_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(combined_path, "w") as f:
        json.dump(all_reports, f, indent=2, default=str)
    log.info(f"Combined report: {combined_path}")


if __name__ == "__main__":
    asyncio.run(main())
