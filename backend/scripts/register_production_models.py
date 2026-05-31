#!/usr/bin/env python3
"""
scripts/register_production_models.py

Register existing trained model artifacts into the MongoDB model registry.
Run from backend/ directory:
  cd backend && python -m scripts.register_production_models --dry-run
  cd backend && python -m scripts.register_production_models --register --promote IWM TLT
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import logging

from motor.motor_asyncio import AsyncIOMotorClient

from services.ml.registry import ModelRegistry

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = REPO_ROOT / "models"

# Map of ticker -> model spec
MODEL_SPECS = {
    "IWM": {
        "model_id": "IWM_direction_v1.0_gbm",
        "artifact_path": str(MODELS_DIR / "IWM_gbm_production.joblib"),
        "metrics": {
            "holdout_sharpe": 1.397,
            "beats_baselines": True,
            "calibration_error": 0.03,
            "train_accuracy": 0.9979,
            "n_train_samples": 2799,
            "n_features": 44,
            "target": "target_directional_move",
            "model_type": "gbm",
            "feature_names": [],  # Will be loaded from manifest
        },
    },
    "TLT": {
        "model_id": "TLT_direction_v1.0_gbm_deep",
        "artifact_path": str(MODELS_DIR / "TLT_gbm_deep_production.joblib"),
        "metrics": {
            "holdout_sharpe": 1.365,
            "beats_baselines": True,
            "calibration_error": 0.03,
            "train_accuracy": 0.9982,
            "n_train_samples": 2799,
            "n_features": 44,
            "target": "target_directional_move",
            "model_type": "gbm_deep",
            "feature_names": [],
        },
    },
    "QQQ": {
        "model_id": "QQQ_direction_v1.0",
        "artifact_path": str(MODELS_DIR / "QQQ_direction_v1.0.joblib"),
        "metrics": {
            "holdout_sharpe": 1.867,
            "beats_baselines": False,
            "calibration_error": 0.04,
            "train_accuracy": 0.998,
            "n_train_samples": 2799,
            "n_features": 44,
            "target": "target_directional_move",
            "model_type": "gbm_deep",
            "feature_names": [],
        },
    },
    "DIA": {
        "model_id": "DIA_direction_v1.0",
        "artifact_path": str(MODELS_DIR / "DIA_direction_v1.0.joblib"),
        "metrics": {
            "holdout_sharpe": 1.224,
            "beats_baselines": False,
            "calibration_error": 0.04,
            "train_accuracy": 0.997,
            "n_train_samples": 2799,
            "n_features": 44,
            "target": "target_directional_move",
            "model_type": "gbm_deep",
            "feature_names": [],
        },
    },
}


async def register_all(dry_run: bool = True, promote: list = None):
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "confluence_decoder")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    registry = ModelRegistry(db)

    promote = promote or []
    results = []

    for ticker, spec in MODEL_SPECS.items():
        metrics = dict(spec["metrics"])
        manifest = load_manifest_for_ticker(ticker)

        # Enrich from manifest
        if manifest:
            metrics["train_accuracy"] = manifest.get("train_accuracy", metrics["train_accuracy"])
            metrics["n_features"] = manifest.get("n_features", metrics["n_features"])
            metrics["feature_names"] = manifest.get("feature_names", [])

        training_window = f"2024-01-01 to 2024-12-30 ({metrics['n_train_samples']} samples)"

        logger.info(f"\n{'='*60}")
        logger.info(f"  Ticker: {ticker}")
        logger.info(f"  Model ID: {spec['model_id']}")
        logger.info(f"  Sharpe: {metrics['holdout_sharpe']}")
        logger.info(f"  Beats baselines: {metrics['beats_baselines']}")

        if not os.path.exists(spec["artifact_path"]):
            logger.info("  SKIP: Artifact not found")
            results.append((ticker, "skip", "artifact missing"))
            continue

        if dry_run:
            logger.info("  DRY RUN — would register as shadow")
            results.append((ticker, "dry_run", "ok"))
            continue

        doc = await registry.register_model(
            model_id=spec["model_id"],
            ticker=ticker,
            feature_version="v1.0",
            training_window=training_window,
            metrics_summary=metrics,
            artifact_path=spec["artifact_path"],
            status="shadow",
        )
        logger.info(f"  Registered: {doc['model_id']} status=shadow")
        results.append((ticker, "registered", spec["model_id"]))

        if ticker in promote and metrics.get("beats_baselines"):
            result = await registry.promote_model(spec["model_id"])
            logger.info(f"  Promote: {result}")
            results.append((ticker, "promoted" if result["success"] else "promote_failed", result.get("reason", "")))
        elif ticker in promote:
            logger.info("  PROMOTE SKIP: beats_baselines=False")
            results.append((ticker, "promote_skip", "beats_baselines=False"))

    logger.info(f"\n{'='*60}")
    logger.info("Summary:")
    for ticker, action, detail in results:
        logger.info(f"  {ticker}: {action} ({detail})")

    client.close()


def load_manifest_for_ticker(ticker: str) -> dict:
    manifest_path = MODELS_DIR / f"{ticker}_gbm_production_manifest.json"
    if not manifest_path.exists():
        manifest_path = MODELS_DIR / f"{ticker}_gbm_deep_production_manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register production ML models")
    parser.add_argument("--register", action="store_true", help="Actually register (default: dry-run)")
    parser.add_argument("--promote", nargs="*", default=[], help="Tickers to promote (e.g., --promote IWM TLT)")
    args = parser.parse_args()

    asyncio.run(register_all(dry_run=not args.register, promote=args.promote))
