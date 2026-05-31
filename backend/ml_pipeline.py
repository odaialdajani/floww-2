#!/usr/bin/env python3
"""
ML Training Pipeline Runner.

Can be run as:
- A cron job: python ml_pipeline.py --mode train
- A one-shot: python ml_pipeline.py --mode predict --ticker SPY
- A full pipeline: python ml_pipeline.py --mode full

Every model save in this file is gated by services.ml.quality. If any gate
fails (class imbalance, constant features, degenerate predictions, future
leakage, ...) the save is refused and DegenerateModelError propagates up.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import numpy as np

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/ml_pipeline.log"),
    ]
)
logger = logging.getLogger(__name__)

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)


# ---------------------------------------------------------------------------
# Gated persistence
# ---------------------------------------------------------------------------

def _save_with_gates(
    *,
    model: Any,
    scaler: Any,
    model_path: str,
    scaler_path: str,
    X_train: Any,
    y_train: Any,
    y_test: Optional[Any] = None,
    y_pred_proba: Any,
    feature_names: Optional[List[str]] = None,
    feature_dates: Optional[List[Any]] = None,
    target_dates: Optional[List[Any]] = None,
    train_dates: Optional[List[Any]] = None,
    test_dates: Optional[List[Any]] = None,
    ticker: str = "?",
) -> Dict[str, bool]:
    """Run all applicable quality gates, then save model + scaler with joblib.

    Every joblib.dump in this file goes through this helper. On any gate
    failure, the save is refused and DegenerateModelError propagates up.

    Args:
        model: Trained sklearn estimator.
        scaler: Fitted feature scaler.
        model_path: Destination path for the model.
        scaler_path: Destination path for the scaler.
        X_train: Training feature matrix (for feature-variance gate).
        y_train: Training labels (for class-balance gate).
        y_test: Optional test labels (also gated for balance if provided).
        y_pred_proba: Predicted probabilities on held-out data
            (for prediction-distribution gate).
        feature_names: Optional names for variance-gate error messages.
        feature_dates / target_dates: Optional for the no-future-leakage gate.
        train_dates / test_dates: Optional for the train/test temporal-split gate.
        ticker: Symbol label for log lines.

    Returns:
        Dict[str, bool] reporting which gates ran and passed.

    Raises:
        DegenerateModelError: If any gate fails. The save is refused.
    """
    import joblib

    from services.ml import DegenerateModelError
    from services.ml.quality import (
        assert_class_balance,
        assert_feature_variance,
        assert_no_future_leakage,
        assert_prediction_distribution,
        assert_temporal_ordering,
        assert_train_test_temporal_split,
    )

    gate_results: Dict[str, bool] = {}

    try:
        # Gate 1: class balance on training labels (catches 99/1 splits)
        assert_class_balance(y_train, label=f"{ticker} y_train")
        gate_results["class_balance_train"] = True

        # Gate 1b: class balance on test labels too (when provided)
        if y_test is not None and len(np.asarray(y_test)) > 0:
            assert_class_balance(y_test, label=f"{ticker} y_test")
            gate_results["class_balance_test"] = True

        # Gate 2: feature variance (catches all-constant feature columns)
        assert_feature_variance(X_train, feature_names=feature_names)
        gate_results["feature_variance"] = True

        # Gate 3: prediction distribution (catches always-predict-X models)
        assert_prediction_distribution(y_pred_proba, label=f"{ticker} predictions")
        gate_results["prediction_distribution"] = True

        # Gate 4: temporal ordering of feature timestamps (when provided)
        if feature_dates is not None:
            assert_temporal_ordering(feature_dates, label=f"{ticker} feature_dates")
            gate_results["temporal_ordering"] = True

        # Gate 5: no future leakage from features into targets (when provided)
        if feature_dates is not None and target_dates is not None:
            assert_no_future_leakage(feature_dates, target_dates, label=f"{ticker} features")
            gate_results["no_future_leakage"] = True

        # Gate 6: train/test temporal split (when provided)
        if train_dates is not None and test_dates is not None:
            assert_train_test_temporal_split(train_dates, test_dates)
            gate_results["train_test_temporal_split"] = True

    except DegenerateModelError as e:
        logger.error(f"REFUSED TO SAVE {ticker} — degenerate model: {e}")
        raise

    # All gates passed — persist.
    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    logger.info(
        f"{ticker}: saved model and scaler after {len(gate_results)} quality gates"
    )
    return gate_results


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

async def _build_dataset_from_snapshots(ticker: str, min_samples: int):
    """Load snapshots from Mongo and build (X, y, feature_names, timestamps).

    Returns a tuple (status_dict, X, y, feature_names, timestamps).
    When the dataset is unusable, status_dict is non-None and the other
    return values are None. Otherwise status_dict is None.
    """
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient

    from ml_price_prediction import extract_features

    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]

    cursor = db.snapshots.find({"ticker": ticker}).sort("ts", 1)
    snapshots = await cursor.to_list(length=10000)
    client.close()

    if len(snapshots) < min_samples:
        return (
            {"status": "insufficient_data", "samples": len(snapshots), "required": min_samples},
            None, None, None, None,
        )

    X: List[List[float]] = []
    y: List[float] = []
    timestamps: List[Any] = []
    for i in range(len(snapshots) - 1):
        features = extract_features(snapshots, i)
        if not features:
            continue
        current_spot = snapshots[i].get("spot", 0)
        next_spot = snapshots[i + 1].get("spot", 0)
        if current_spot <= 0 or next_spot <= 0:
            continue
        y.append(1.0 if next_spot > current_spot else 0.0)
        X.append(list(features.values()))
        timestamps.append(snapshots[i].get("ts"))

    if len(X) < min_samples:
        return (
            {"status": "insufficient_training_data", "samples": len(X), "required": min_samples},
            None, None, None, None,
        )

    feature_names = list(extract_features(snapshots, 0).keys())
    return None, np.array(X), np.array(y), feature_names, timestamps


async def collect_data():
    """Collect GEX snapshots for all tracked tickers."""
    logger.info("collect_data: mode not implemented in this pipeline")
    return {"status": "noop"}


async def train_models():
    """Train ML models on collected data."""
    logger.info("train_models: mode not implemented in this pipeline")
    return {"status": "noop"}


async def evaluate_models():
    """Evaluate trained models on held-out data."""
    logger.info("evaluate_models: mode not implemented in this pipeline")
    return {"status": "noop"}


async def full_pipeline():
    """Run the full ML pipeline: collect → train → evaluate → predict."""
    logger.info("full_pipeline: running full pipeline")
    await collect_data()
    await train_models()
    await evaluate_models()
    logger.info("full_pipeline: complete")
    return {"status": "complete"}


async def main():
    mode = "full"
    ticker = "SPY"

    # Parse args
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--mode" and i + 1 < len(sys.argv[1:]):
            mode = sys.argv[i + 2]
        elif arg == "--ticker" and i + 1 < len(sys.argv[1:]):
            ticker = sys.argv[i + 2]

    if mode == "collect":
        await collect_data()
    elif mode == "train":
        await train_models()
    elif mode == "predict":
        from ml_price_prediction import predict_price_direction
        result = await predict_price_direction(ticker)
        logger.info(json.dumps(result, indent=2))
    elif mode == "evaluate":
        await evaluate_models()
    elif mode == "full":
        await full_pipeline()
    else:
        logger.info(f"Unknown mode: {mode}")
        logger.info("Available modes: collect, train, predict, evaluate, full")


if __name__ == "__main__":
    asyncio.run(main())
