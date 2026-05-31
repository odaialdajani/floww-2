#!/usr/bin/env python3
"""
scripts/retrain_models.py

Automated model retraining script.
Designed to be run as a cron job (e.g., weekly on Sunday at 3am).

Steps:
1. For each registered ticker:
   a. Load latest cached features
   b. Retrain model with same pipeline
   c. Compare new model against current production model (walk-forward Sharpe)
   d. If new model is better by >5% Sharpe improvement, promote to production
2. Log results to MongoDB (ml_retraining_log collection)
3. Generate report

Usage:
    .venv/bin/python3 scripts/retrain_models.py --dry-run
    .venv/bin/python3 scripts/retrain_models.py --promote
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("retrain")

REPO_ROOT = SCRIPT_DIR.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"
REPORTS_DIR = SCRIPT_DIR.parent / "reports"
MODELS_DIR = SCRIPT_DIR.parent / "models"

UP_THRESHOLD = 0.003
DOWN_THRESHOLD = -0.003
SHARPE_IMPROVEMENT_THRESHOLD = 0.05  # 5% minimum improvement to promote

META_COLS = {"ticker", "date", "feature_version", "_computed_at", "_id", "spot_price"}
TARGET_COLS = {
    "target_directional_move", "target_return_pct", "target_gap_move",
    "target_range_expansion", "target_any_materialization",
}


def load_cached_features(ticker: str) -> pd.DataFrame:
    for version in ["v1.0", "v1.5_gex_merged", "v2.0_gex"]:
        path = CACHE_DIR / f"{ticker}_{version}.csv"
        if path.exists():
            return pd.read_csv(path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    raise ValueError(f"No cached features for {ticker}")


def prepare_features(df: pd.DataFrame) -> tuple:
    """Prepare feature matrix and target from cached data."""
    df = df.copy()
    df["target_3class"] = 1
    df.loc[df["target_return_pct"] > UP_THRESHOLD, "target_3class"] = 2
    df.loc[df["target_return_pct"] < DOWN_THRESHOLD, "target_3class"] = 0

    feature_cols = [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS and c != "target_3class"]
    df = df.dropna(subset=["target_3class", "target_return_pct"])

    X = df[feature_cols].values.astype(float)
    y = df["target_3class"].values.astype(int)
    return X, y, feature_cols


def quick_feature_select(X, y, feature_names, max_features=25):
    """Quick variance + importance feature selection."""
    from sklearn.ensemble import RandomForestClassifier

    variances = np.var(X, axis=0)
    mask = variances >= 0.0005
    remaining = np.where(mask)[0]

    if len(remaining) > max_features:
        rf = RandomForestClassifier(n_estimators=30, max_depth=3, random_state=42, n_jobs=-1)
        rf.fit(X[:, remaining], y)
        top = np.argsort(rf.feature_importances_)[-max_features:]
        selected = [remaining[i] for i in top]
    else:
        selected = remaining.tolist()

    return [feature_names[i] for i in selected], selected


def walk_forward_sharpe(model, X, y, n_splits=3, embargo=5):
    """Quick walk-forward CV returning mean Sharpe."""
    from sklearn.base import clone
    from sklearn.metrics import accuracy_score
    from sklearn.preprocessing import StandardScaler

    fold_size = len(X) // (n_splits + 1)
    sharpes = []

    for fold in range(n_splits):
        train_end = fold_size * (fold + 1)
        test_start = train_end + embargo
        test_end = min(test_start + fold_size, len(X))
        if test_end > len(X) or test_start >= len(X):
            break

        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X[:train_end])
        X_te = scaler.transform(X[test_start:test_end])
        y_tr = y[:train_end]
        y_te = y[test_start:test_end]

        try:
            m = clone(model)
            m.fit(X_tr, y_tr)
            acc = accuracy_score(y_te, m.predict(X_te))
            sharpes.append(acc / (1.0 - acc + 0.01))
        except Exception:
            pass

    return float(np.mean(sharpes)) if sharpes else 0.0


def retrain_ticker(ticker: str, dry_run: bool = True) -> dict:
    """Retrain a single ticker and compare against production model."""
    log.info(f"Retraining {ticker}...")
    t0 = time.time()

    # Load data
    df = load_cached_features(ticker)
    X, y, feature_cols = prepare_features(df)
    log.info(f"  {len(X)} samples, {len(feature_cols)} features")

    # Feature selection
    selected_names, selected_idx = quick_feature_select(X, y, feature_cols)
    X_sel = X[:, selected_idx]

    # Train new model
    from sklearn.ensemble import RandomForestClassifier
    new_model = RandomForestClassifier(
        n_estimators=200, max_depth=4, min_samples_leaf=15,
        max_features="sqrt", random_state=42, n_jobs=-1,
    )
    new_sharpe = walk_forward_sharpe(new_model, X_sel, y)
    log.info(f"  New model WF Sharpe: {new_sharpe:.4f}")

    # Load production model for comparison
    prod_manifests = list(MODELS_DIR.glob(f"{ticker}_*_production_manifest.json"))
    prod_sharpe = 0.0
    prod_model_type = "none"
    if prod_manifests:
        m = json.load(open(sorted(prod_manifests)[-1]))
        prod_sharpe = m.get("walk_forward_sharpe", 0)
        prod_model_type = m.get("model_type", "?")
        log.info(f"  Production model ({prod_model_type}) WF Sharpe: {prod_sharpe:.4f}")

    # Decision
    improvement = (new_sharpe - prod_sharpe) / (prod_sharpe + 0.01)
    should_promote = improvement > SHARPE_IMPROVEMENT_THRESHOLD

    log.info(f"  Improvement: {improvement:.1%} → {'PROMOTE' if should_promote else 'KEEP'}")

    result = {
        "ticker": ticker,
        "new_sharpe": new_sharpe,
        "prod_sharpe": prod_sharpe,
        "prod_model_type": prod_model_type,
        "improvement": improvement,
        "should_promote": should_promote,
        "n_samples": len(X),
        "n_features": len(selected_names),
        "time_sec": time.time() - t0,
    }

    if should_promote and not dry_run:
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_sel)
        new_model.fit(X_scaled, y)

        # Save with timestamp
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_path = MODELS_DIR / f"{ticker}_rf_retrain_{ts}.joblib"
        scaler_path = MODELS_DIR / f"{ticker}_rf_retrain_{ts}_scaler.joblib"

        joblib.dump(new_model, model_path)
        joblib.dump(scaler, scaler_path)

        # Also copy to production
        prod_model = MODELS_DIR / f"{ticker}_rf_production.joblib"
        prod_scaler = MODELS_DIR / f"{ticker}_rf_production_scaler.joblib"
        shutil.copy2(model_path, prod_model)
        shutil.copy2(scaler_path, prod_scaler)

        log.info(f"  Promoted to production: {prod_model.name}")
        result["promoted"] = True
    else:
        result["promoted"] = False

    return result


def main():
    parser = argparse.ArgumentParser(description="Automated model retraining")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate but don't promote")
    parser.add_argument("--promote", action="store_true", help="Allow promotion (default: dry-run)")
    parser.add_argument("--tickers", nargs="+", default=["SPY", "QQQ", "DIA", "IWM", "TLT"])
    args = parser.parse_args()

    dry_run = not args.promote
    tickers = [t.upper() for t in args.tickers]

    log.info(f"Retraining: {tickers} (dry_run={dry_run})")
    results = []

    for ticker in tickers:
        try:
            result = retrain_ticker(ticker, dry_run=dry_run)
            results.append(result)
        except Exception as e:
            log.error(f"{ticker} failed: {e}", exc_info=True)
            results.append({"ticker": ticker, "error": str(e)})

    # Summary
    log.info(f"\n{'=' * 60}")
    log.info("RETRAINING SUMMARY")
    log.info(f"{'=' * 60}")
    for r in results:
        if "error" in r:
            log.info(f"  {r['ticker']}: ERROR - {r['error']}")
        else:
            log.info(f"  {r['ticker']}: new_sharpe={r['new_sharpe']:.4f} prod_sharpe={r['prod_sharpe']:.4f} improve={r['improvement']:.1%} → {'PROMOTED' if r.get('promoted') else 'no change'}")

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"retrain_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Report: {report_path}")

    # Log to MongoDB
    try:
        import asyncio

        from dotenv import load_dotenv
        from motor.motor_asyncio import AsyncIOMotorClient

        load_dotenv(SCRIPT_DIR.parent / ".env")
        uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        db_name = os.getenv("MONGO_DB", "floww")

        async def log_to_mongo():
            client = AsyncIOMotorClient(uri)
            db = client[db_name]
            await db["ml_retraining_log"].insert_one({
                "run_at": datetime.now(timezone.utc),
                "dry_run": dry_run,
                "results": results,
            })
            client.close()

        asyncio.run(log_to_mongo())
    except Exception as e:
        log.warning(f"MongoDB logging failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
