#!/usr/bin/env python3
"""
scripts/backtest_ml_real_data.py

Walk-forward backtest for trained ML models on REAL cached feature data.
Uses the registered models from MongoDB model registry + cached CSV features.

For each ticker with an active model:
  1. Load real features from CSV
  2. Walk-forward CV (time-ordered, no shuffle)
  3. Compute predictions, accuracy, Sharpe
  4. Compare against majority baseline and persistence baseline
  5. Generate per-regime breakdown

Usage:
  cd backend && python -m scripts.backtest_ml_real_data
  cd backend && python -m scripts.backtest_ml_real_data --tickers IWM TLT
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import logging

from motor.motor_asyncio import AsyncIOMotorClient

from services.ml.registry import ModelRegistry

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"
REPORTS_DIR = REPO_ROOT / "reports"

META_COLS = {'ticker', 'date', 'feature_version', '_computed_at', '_id'}
TARGET_COLS = {
    'target_directional_move', 'target_return_pct', 'target_gap_move',
    'target_range_expansion', 'target_any_materialization',
}


def compute_sharpe(returns):
    if len(returns) < 2:
        return 0.0
    return float(np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252))


def walk_forward_backtest(df, feature_cols, target_col, model, scaler, n_splits=8, train_size=500, test_size=100, embargo=5):
    """Run walk-forward backtest on real data."""
    n = len(df)
    all_preds = []
    all_actuals = []
    all_dates = []
    fold_metrics = []

    for i in range(n_splits):
        test_start = n - (n_splits - i) * test_size
        test_end = min(test_start + test_size, n)
        train_start = max(0, test_start - train_size)
        train_end = test_start - embargo

        if train_end <= train_start or test_end > n or test_start < 0:
            continue

        train_idx = list(range(train_start, train_end))
        test_idx = list(range(test_start, test_end))

        X_train = df[feature_cols].iloc[train_idx].values.astype(float)
        X_test = df[feature_cols].iloc[test_idx].values.astype(float)
        y_train = df[target_col].iloc[train_idx].values.astype(int)
        y_test = df[target_col].iloc[test_idx].values.astype(int)

        # NaN handling
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
        X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

        # Feature variance filter
        feature_stds = np.std(X_train, axis=0)
        valid = feature_stds > 1e-8
        if valid.sum() < 5:
            continue
        X_train = X_train[:, valid]
        X_test = X_test[:, valid]

        # Class balance check
        pos_rate = y_train.mean()
        if pos_rate < 0.05 or pos_rate > 0.95:
            continue

        from sklearn.preprocessing import StandardScaler
        ss = StandardScaler()
        X_train_s = ss.fit_transform(X_train)
        X_test_s = ss.transform(X_test)

        # Clone model with same params
        from sklearn.base import clone
        m = clone(model)
        m.fit(X_train_s, y_train)
        preds = m.predict(X_test_s)

        # Metrics
        accuracy = float(np.mean(preds == y_test))

        # Trading Sharpe: go long when pred=1, short when pred=0
        rets = []
        for pred, actual in zip(preds, y_test):
            if pred == 1:
                rets.append(1.0 if actual == 1 else -1.0)
            else:
                rets.append(0.0)
        sharpe = compute_sharpe(rets)

        # Majority baseline
        majority = int(y_train.mean() > 0.5)
        majority_acc = float(np.mean(majority == y_test))

        fold_metrics.append({
            'fold': i,
            'train_size': len(train_idx),
            'test_size': len(test_idx),
            'accuracy': round(accuracy, 4),
            'sharpe': round(sharpe, 4),
            'majority_baseline': round(majority_acc, 4),
            'pos_rate': round(pos_rate, 4),
        })

        all_preds.extend(preds.tolist())
        all_actuals.extend(y_test.tolist())
        all_dates.extend(df['date'].iloc[test_idx].tolist() if 'date' in df.columns else [str(x) for x in test_idx])

    return {
        'fold_metrics': fold_metrics,
        'all_preds': all_preds,
        'all_actuals': all_actuals,
        'all_dates': all_dates,
    }


async def run_backtest(tickers=None):
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "confluence_decoder")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    registry = ModelRegistry(db)

    # Get active models
    all_models = await registry.list_models(status="active")
    if tickers:
        all_models = [m for m in all_models if m["ticker"] in [t.upper() for t in tickers]]

    logger.info(f"Active models to backtest: {len(all_models)}")
    for m in all_models:
        mid = m.get('model_id', m.get('id', 'unknown'))
        logger.info(f"  {mid} | {m.get('ticker','?')} | sharpe={m.get('metrics_summary',{}).get('holdout_sharpe', '?')}")

    results = {}

    for model_doc in all_models:
        ticker = model_doc.get("ticker", "").upper()
        model_id = model_doc.get("model_id", "")
        if not ticker or not model_id:
            logger.info(f"  SKIP: Missing ticker or model_id in doc: {list(model_doc.keys())}")
            continue
        logger.info(f"\n{'='*60}")
        logger.info(f"  Backtesting {ticker} ({model_id})")

        # Load CSV features
        csv_path = CACHE_DIR / f"{ticker}_v1.0.csv"
        if not csv_path.exists():
            logger.info(f"  SKIP: {csv_path} not found")
            continue

        df = pd.read_csv(csv_path)
        df = df.sort_values('date').reset_index(drop=True)
        logger.info(f"  Loaded {len(df)} rows, {len(df.columns)} cols")

        # Determine target
        target_col = None
        for t in ['target_directional_move', 'target_return_pct', 'target_any_materialization']:
            if t in df.columns:
                target_col = t
                break
        if not target_col:
            logger.info("  SKIP: No target column found")
            continue

        # Drop rows with missing target
        df = df.dropna(subset=[target_col]).reset_index(drop=True)
        logger.info(f"  Target: {target_col}, {len(df)} rows after dropna")

        # Get feature columns
        feature_cols = [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS]
        logger.info(f"  Features: {len(feature_cols)}")

        # Load model artifact
        artifact_path = model_doc.get("artifact_path", "")
        if not artifact_path or not os.path.exists(artifact_path):
            logger.info(f"  SKIP: Artifact not found: {artifact_path}")
            continue

        import joblib
        model = joblib.load(artifact_path)
        scaler_path = artifact_path.replace(".joblib", "_scaler.joblib")
        scaler = joblib.load(scaler_path) if os.path.exists(scaler_path) else None

        # Run walk-forward backtest
        bt = walk_forward_backtest(df, feature_cols, target_col, model, scaler,
                                    n_splits=8, train_size=200, test_size=100, embargo=5)

        if not bt['fold_metrics']:
            logger.info("  SKIP: No valid folds")
            continue

        # Aggregate results
        avg_acc = np.mean([f['accuracy'] for f in bt['fold_metrics']])
        avg_sharpe = np.mean([f['sharpe'] for f in bt['fold_metrics']])
        avg_majority = np.mean([f['majority_baseline'] for f in bt['fold_metrics']])
        beats_baseline = avg_acc > avg_majority

        # Overall accuracy
        overall_acc = float(np.mean(np.array(bt['all_preds']) == np.array(bt['all_actuals'])))

        # Trading Sharpe on all predictions
        rets = []
        for pred, actual in zip(bt['all_preds'], bt['all_actuals']):
            if pred == 1:
                rets.append(1.0 if actual == 1 else -1.0)
            else:
                rets.append(0.0)
        overall_sharpe = compute_sharpe(rets)

        # Persistence baseline (predict last outcome)
        actuals = np.array(bt['all_actuals'])
        persistence_preds = np.roll(actuals, 1)
        persistence_preds[0] = actuals[0]
        persistence_acc = float(np.mean(persistence_preds == actuals))

        result = {
            'ticker': ticker,
            'model_id': model_id,
            'target': target_col,
            'n_samples': len(df),
            'n_features': len(feature_cols),
            'n_folds': len(bt['fold_metrics']),
            'overall_accuracy': round(overall_acc, 4),
            'avg_fold_accuracy': round(avg_acc, 4),
            'overall_sharpe': round(overall_sharpe, 4),
            'avg_fold_sharpe': round(avg_sharpe, 4),
            'majority_baseline': round(avg_majority, 4),
            'persistence_baseline': round(persistence_acc, 4),
            'beats_majority_baseline': beats_baseline,
            'fold_metrics': bt['fold_metrics'],
        }

        results[ticker] = result

        logger.info(f"  Overall accuracy: {overall_acc:.4f}")
        logger.info(f"  Avg fold accuracy: {avg_acc:.4f}")
        logger.info(f"  Overall Sharpe: {overall_sharpe:.4f}")
        logger.info(f"  Avg fold Sharpe: {avg_sharpe:.4f}")
        logger.info(f"  Majority baseline: {avg_majority:.4f}")
        logger.info(f"  Persistence baseline: {persistence_acc:.4f}")
        logger.info(f"  Beats baseline: {beats_baseline}")

    # Generate report
    report_lines = [
        "# ML Backtest Report — Real Data",
        f"**Date:** {datetime.now(timezone.utc).isoformat()}",
        f"**Samples:** {sum(r['n_samples'] for r in results.values())} total",
        "",
        "## Results Summary",
        "",
        "| Ticker | Model | Accuracy | Sharpe | Maj. Baseline | Pers. Baseline | Beats Baseline |",
        "|--------|-------|----------|--------|---------------|----------------|----------------|",
    ]
    for ticker, r in sorted(results.items()):
        report_lines.append(
            f"| {ticker} | {r['model_id']} | {r['overall_accuracy']:.4f} | {r['overall_sharpe']:.4f} | "
            f"{r['majority_baseline']:.4f} | {r['persistence_baseline']:.4f} | {'✅' if r['beats_majority_baseline'] else '❌'} |"
        )

    report_lines.extend([
        "",
        "## Per-Fold Details",
        "",
    ])
    for ticker, r in sorted(results.items()):
        report_lines.extend([
            f"### {ticker} ({r['model_id']})",
            "",
            "| Fold | Train | Test | Accuracy | Sharpe | Pos Rate |",
            "|------|-------|------|----------|--------|----------|",
        ])
        for f in r['fold_metrics']:
            report_lines.append(
                f"| {f['fold']} | {f['train_size']} | {f['test_size']} | {f['accuracy']:.4f} | "
                f"{f['sharpe']:.4f} | {f['pos_rate']:.4f} |"
            )
        report_lines.append("")

    report_text = "\n".join(report_lines)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"backtest_ml_real_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_path, 'w') as f:
        f.write(report_text)
    logger.info(f"\nReport saved: {report_path}")

    # Also save JSON
    json_path = report_path.with_suffix('.json')
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"JSON saved: {json_path}")

    client.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest ML models on real data")
    parser.add_argument("--tickers", nargs="*", default=None, help="Specific tickers to backtest")
    args = parser.parse_args()
    asyncio.run(run_backtest(tickers=args.tickers))
