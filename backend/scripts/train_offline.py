"""
backend/scripts/train_offline.py

Offline ML training pipeline — loads feature data from cached CSVs,
trains with walk-forward CV, evaluates gate, ships best model.

No MongoDB dependency. Runs entirely from data/cached_features/*.csv.

Usage:
    cd backend && source venv/bin/activate
    python scripts/train_offline.py --ticker SPY --model-type gbm
    python scripts/train_offline.py --ticker IWM --model-type all
    python scripts/train_offline.py --ticker all --model-type gbm --save
    python scripts/train_offline.py --ticker all --all --save --output-dir models/

Walk-forward CV: expanding window, configurable train/test sizes.
Default: 500 train, 50 test, step 50 (good for 2800-row datasets).
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

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data" / "cached_features"
MODEL_DIR = REPO_ROOT / "models"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
log = logging.getLogger("train_offline")

TARGET_COL = "target_directional_move"

# Columns never used as features
EXCLUDE_COLS = {
    "ticker", "date", "day", "feature_version", "_computed_at",
    "target_directional_move", "target_return_pct",
    "target_range_expansion", "target_gap_move",
    "target_any_materialization", "_id",
}

# All cached feature CSVs by ticker
TICKER_FILES = {
    "DIA": "DIA_v1.0.csv",
    "IWM": "IWM_v1.0.csv",
    "QQQ": "QQQ_v1.0.csv",
    "SPY": "SPY_v1.0.csv",
    "TLT": "TLT_v1.0.csv",
}


def load_csv(ticker: str) -> pd.DataFrame:
    """Load cached feature CSV for a ticker."""
    fname = TICKER_FILES.get(ticker)
    if not fname:
        log.error(f"No file mapping for {ticker}")
        return pd.DataFrame()
    fpath = DATA_DIR / fname
    if not fpath.exists():
        log.error(f"File not found: {fpath}")
        return pd.DataFrame()
    df = pd.read_csv(fpath)
    df = df.sort_values("date").reset_index(drop=True)
    df["ticker"] = ticker
    log.info(f"Loaded {len(df)} rows for {ticker} from {fname}")
    return df


def prepare_data(df: pd.DataFrame) -> tuple:
    """Split DataFrame into feature matrix X, target y, feature names, dates."""
    feature_cols = [c for c in df.columns if c not in EXCLUDE_COLS]
    X = df[feature_cols].copy()
    y = df[TARGET_COL].copy() if TARGET_COL in df.columns else None

    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0.0)

    date_col = "date" if "date" in df.columns else "day"
    dates = df[date_col].values if date_col in df.columns else np.arange(len(df))

    return X.values, y.values if y is not None else None, list(X.columns), dates


def walk_forward_cv(X, y, dates, n_splits=5, train_size=500, test_size=50, step=50):
    """Expanding-window walk-forward CV.

    Each fold: train on expanding window of `train_size` samples,
    test on next `test_size` samples. The expanding window grows:
    fold 1 trains on [0:train_size], fold 2 on [0:train_size+step], etc.
    """
    n = len(X)
    splits = []
    for i in range(n_splits):
        train_start = 0
        train_end = train_size + i * step
        test_start = train_end
        test_end = min(test_start + test_size, n)

        if train_end < 50 or test_end <= test_start:
            continue
        if test_end > n:
            continue

        splits.append((
            list(range(train_start, train_end)),
            list(range(test_start, test_end)),
        ))
    return splits


def compute_trading_sharpe(predictions, actuals):
    """Annualized Sharpe of long-only-on-positive-prediction strategy."""
    rets = []
    for pred, actual in zip(predictions, actuals):
        if pred == 1:
            rets.append(1.0 if actual == 1 else -1.0)
    if len(rets) < 2:
        return 0.0
    std = np.std(rets)
    if std < 1e-10:
        return 0.0
    return float(np.mean(rets) / std * np.sqrt(252))


def train_gbm(X_train, y_train):
    """Train Gradient Boosting model."""
    from sklearn.ensemble import GradientBoostingClassifier
    model = GradientBoostingClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        subsample=0.7, min_samples_leaf=10, random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def train_rf(X_train, y_train):
    """Train Random Forest model."""
    from sklearn.ensemble import RandomForestClassifier
    model = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=10,
        max_features="sqrt", random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def train_logistic(X_train, y_train):
    """Train Logistic Regression model."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_train)
    model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    model.fit(X_s, y_train)
    return {"model": model, "scaler": scaler, "type": "logistic"}


def predict_model(model, X):
    """Get predictions from a model (handles pipeline dict for logistic)."""
    if isinstance(model, dict) and model.get("type") == "logistic":
        X_s = model["scaler"].transform(X)
        return model["model"].predict(X_s)
    return model.predict(X)


def evaluate_fold(name, model, X_train, y_train, X_test, y_test, dates_test):
    """Evaluate a single fold. Only reports OOS (test) metrics for gate."""
    test_pred = predict_model(model, X_test).astype(int)
    y_test_i = y_test.astype(int)

    test_acc = float(np.mean(test_pred == y_test_i))
    test_sharpe = compute_trading_sharpe(test_pred, y_test_i)

    # Baselines computed on test fold
    y_train_i = y_train.astype(int)
    majority_class = int(np.bincount(y_train_i).argmax())
    majority_pred = np.full_like(y_test_i, majority_class)
    majority_sharpe = compute_trading_sharpe(majority_pred, y_test_i)

    persistence_pred = np.full_like(y_test_i, y_train_i[-1])
    persistence_sharpe = compute_trading_sharpe(persistence_pred, y_test_i)

    # Train metrics reported for monitoring only (not gated)
    train_pred = predict_model(model, X_train).astype(int)
    train_acc = float(np.mean(train_pred == y_train_i))
    train_test_gap = train_acc - test_acc

    return {
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "train_test_gap": train_test_gap,
        "test_sharpe": test_sharpe,
        "majority_sharpe": majority_sharpe,
        "persistence_sharpe": persistence_sharpe,
        "beats_majority": test_sharpe > majority_sharpe,
        "beats_persistence": test_sharpe > persistence_sharpe,
        "n_train": len(y_train),
        "n_test": len(y_test),
        "test_date_start": str(dates_test[0])[:10],
        "test_date_end": str(dates_test[-1])[:10],
    }


def gate_evaluate(result: dict) -> str:
    """Apply ML promotion gate. Returns verdict string.

    All criteria must hold for SHIP:
      1. test_sharpe > majority_sharpe (beats majority baseline)
      2. test_sharpe > persistence_sharpe (beats persistence baseline)
      3. test_sharpe > 0.0 (positive edge)
      4. test_accuracy > 0.50 (better than coin flip)
      5. train_test_gap < 0.15 (no severe overfit)
    """
    if not result["beats_majority"]:
        return "REJECT"
    if not result["beats_persistence"]:
        return "REJECT"
    if result["test_sharpe"] <= 0.0:
        return "REJECT"
    if result["test_accuracy"] <= 0.50:
        return "REJECT"
    if result["train_test_gap"] > 0.15:
        return "REJECT"
    return "SHIP"


MODEL_TRAINERS = {
    "gbm": train_gbm,
    "rf": train_rf,
    "logistic": train_logistic,
}


def train_ticker(ticker: str, model_types: list, n_splits: int = 5,
                 train_size: int = 500, test_size: int = 50, step: int = 50):
    """Full training pipeline for one ticker."""
    df = load_csv(ticker)
    if df.empty:
        return None

    X, y, feature_names, dates = prepare_data(df)
    if y is None:
        log.error(f"No target column for {ticker}")
        return None

    unique_targets = np.unique(y)
    if len(unique_targets) < 2:
        log.error(f"Degenerate target for {ticker}: only {unique_targets}")
        return None

    log.info(f"{ticker}: {X.shape[0]} samples, {X.shape[1]} features, "
             f"target dist: {np.bincount(y.astype(int))}")

    splits = walk_forward_cv(X, y, dates, n_splits, train_size, test_size, step)
    if not splits:
        log.error(f"Not enough data for walk-forward CV ({ticker}): "
                  f"need {train_size + n_splits * step + test_size}, have {len(X)}")
        return None

    log.info(f"CV: {len(splits)} folds, train={train_size}+expanding, "
             f"test={test_size}, step={step}")

    all_results = {}

    for model_type in model_types:
        log.info(f"\n{'='*60}")
        log.info(f"Training {ticker} / {model_type}")
        log.info(f"{'='*60}")

        fold_results = []
        trainer = MODEL_TRAINERS[model_type]

        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            dates_test = dates[test_idx]

            try:
                model = trainer(X_train, y_train)
            except Exception as e:
                log.error(f"  Fold {fold_idx+1} training failed: {e}")
                continue

            result = evaluate_fold(
                f"{model_type}_fold{fold_idx+1}", model,
                X_train, y_train, X_test, y_test, dates_test,
            )
            result["verdict"] = gate_evaluate(result)
            result["fold"] = fold_idx + 1
            fold_results.append(result)

            status = result["verdict"]
            log.info(
                f"  Fold {fold_idx+1} [{result['test_date_start']}->{result['test_date_end']}]: "
                f"test_acc={result['test_accuracy']:.3f} "
                f"test_sharpe={result['test_sharpe']:.3f} "
                f"gap={result['train_test_gap']:.3f} "
                f"-> {status}"
            )

        if not fold_results:
            log.warning(f"  No successful folds for {model_type}")
            continue

        ship_folds = [r for r in fold_results if r["verdict"] == "SHIP"]
        avg_result = {
            "model_type": model_type,
            "n_folds": len(fold_results),
            "avg_test_sharpe": round(np.mean([r["test_sharpe"] for r in fold_results]), 4),
            "avg_test_accuracy": round(np.mean([r["test_accuracy"] for r in fold_results]), 4),
            "avg_train_test_gap": round(np.mean([r["train_test_gap"] for r in fold_results]), 4),
            "median_test_sharpe": round(np.median([r["test_sharpe"] for r in fold_results]), 4),
            "best_test_sharpe": round(max(r["test_sharpe"] for r in fold_results), 4),
            "folds_ship": len(ship_folds),
            "folds_reject": len(fold_results) - len(ship_folds),
            "ship_rate": round(len(ship_folds) / len(fold_results), 2),
            "fold_details": fold_results,
        }
        all_results[model_type] = avg_result

        log.info(
            f"  {model_type} Summary: "
            f"median_sharpe={avg_result['median_test_sharpe']:.3f} "
            f"best_sharpe={avg_result['best_test_sharpe']:.3f} "
            f"avg_acc={avg_result['avg_test_accuracy']:.3f} "
            f"SHIP={avg_result['folds_ship']}/{avg_result['n_folds']}"
        )

    return {
        "ticker": ticker,
        "n_samples": X.shape[0],
        "n_features": X.shape[1],
        "feature_names": feature_names,
        "models": all_results,
    }


def save_model(ticker: str, model_type: str, result: dict, feature_names: list,
               X_full: np.ndarray, y_full: np.ndarray, output_dir: Path):
    """Retrain on full data and save artifact + manifest."""
    trainer = MODEL_TRAINERS[model_type]
    try:
        model = trainer(X_full, y_full)
    except Exception as e:
        log.error(f"  Final training failed: {e}")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    model_filename = f"{ticker}_{model_type}_offline_{ts}.joblib"
    model_path = output_dir / model_filename
    joblib.dump({
        "model": model,
        "feature_names": feature_names,
        "model_type": model_type,
        "ticker": ticker,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }, model_path)
    log.info(f"  Saved model to {model_path}")

    manifest = {
        "ticker": ticker,
        "model": model_type,
        "feature_version": "v1.0_offline",
        "target": TARGET_COL,
        "n_samples": int(X_full.shape[0]),
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "avg_test_accuracy": result["avg_test_accuracy"],
        "avg_test_sharpe": result["avg_test_sharpe"],
        "median_test_sharpe": result["median_test_sharpe"],
        "best_test_sharpe": result["best_test_sharpe"],
        "avg_train_test_gap": result["avg_train_test_gap"],
        "folds_ship": result["folds_ship"],
        "folds_total": result["n_folds"],
        "ship_rate": result["ship_rate"],
        "model_params": {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.7,
            "random_state": 42,
        },
        "model_path": str(model_path),
        "verdict": "SHIP" if result["folds_ship"] > 0 else "REJECT",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    manifest_path = output_dir / f"{ticker}_{model_type}_offline_manifest_{ts}.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    log.info(f"  Saved manifest to {manifest_path}")

    return model_path, manifest_path


def main():
    parser = argparse.ArgumentParser(description="Offline ML training from cached CSVs")
    parser.add_argument("--ticker", default="IWM",
                        help="Ticker or 'all' (default: IWM)")
    parser.add_argument("--model-type", default="gbm",
                        choices=["gbm", "rf", "logistic", "all"])
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--train-size", type=int, default=500,
                        help="Initial training window size (default: 500)")
    parser.add_argument("--test-size", type=int, default=50,
                        help="Test fold size (default: 50)")
    parser.add_argument("--step", type=int, default=50,
                        help="Step size for expanding window (default: 50)")
    parser.add_argument("--save", action="store_true", help="Save best model artifacts")
    parser.add_argument("--output-dir", default=str(MODEL_DIR),
                        help="Directory for saved models")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.ticker == "all":
        tickers = ["DIA", "IWM", "QQQ", "TLT"]
    else:
        tickers = [args.ticker.upper()]

    if args.model_type == "all":
        model_types = list(MODEL_TRAINERS.keys())
    else:
        model_types = [args.model_type]

    log.info(f"Tickers: {tickers}")
    log.info(f"Model types: {model_types}")
    log.info(f"Walk-forward: {args.n_splits} folds, "
             f"train={args.train_size}+expanding, test={args.test_size}, step={args.step}")

    all_ticker_results = {}

    for ticker in tickers:
        result = train_ticker(
            ticker, model_types,
            args.n_splits, args.train_size, args.test_size, args.step,
        )
        if result is None:
            continue
        all_ticker_results[ticker] = result

        # Print summary
        log.info(f"\n{'='*60}")
        log.info(f"{ticker} FINAL RESULTS")
        log.info(f"{'='*60}")
        for mt, r in result["models"].items():
            log.info(
                f"  {mt:12s}: median_sharpe={r['median_test_sharpe']:.3f} "
                f"best_sharpe={r['best_test_sharpe']:.3f} "
                f"acc={r['avg_test_accuracy']:.3f} "
                f"gap={r['avg_train_test_gap']:.3f} "
                f"SHIP={r['folds_ship']}/{r['n_folds']}"
            )

        # Save best model
        if args.save:
            best_type = None
            best_median_sharpe = -999
            for mt, r in result["models"].items():
                if r["folds_ship"] > 0 and r["median_test_sharpe"] > best_median_sharpe:
                    best_median_sharpe = r["median_test_sharpe"]
                    best_type = mt

            if best_type:
                log.info(f"\n  Best model for {ticker}: {best_type} "
                         f"(median Sharpe={best_median_sharpe:.3f})")
                # Reload full data for final training
                df = load_csv(ticker)
                X, y, feature_names, _ = prepare_data(df)
                save_model(ticker, best_type, result["models"][best_type],
                           feature_names, X, y, output_dir)
            else:
                log.warning(f"  No model passed the gate for {ticker}")

    # Summary JSON
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "tickers": tickers,
            "model_types": model_types,
            "n_splits": args.n_splits,
            "train_size": args.train_size,
            "test_size": args.test_size,
            "step": args.step,
        },
        "results": {},
    }
    for ticker, result in all_ticker_results.items():
        summary["results"][ticker] = {
            mt: {
                "median_test_sharpe": r["median_test_sharpe"],
                "best_test_sharpe": r["best_test_sharpe"],
                "avg_test_accuracy": r["avg_test_accuracy"],
                "avg_train_test_gap": r["avg_train_test_gap"],
                "folds_ship": r["folds_ship"],
                "folds_total": r["n_folds"],
                "ship_rate": r["ship_rate"],
            }
            for mt, r in result["models"].items()
        }

    summary_path = output_dir / "offline_training_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    log.info(f"\nSummary saved to {summary_path}")

    logger.info(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
