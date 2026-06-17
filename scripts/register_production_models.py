#!/usr/bin/env python3
"""
scripts/register_production_models.py

Register existing trained model artifacts into the MongoDB model registry.
Reads manifest JSON files and calls ModelRegistry.register_model().

Usage:
  python scripts/register_production_models.py --dry-run
  python scripts/register_production_models.py --register
  python scripts/register_production_models.py --register --promote IWM
"""
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / "backend" / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
from services.ml.registry import ModelRegistry  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parent
MODELS_DIR = REPO_ROOT / "models"
REPORTS_DIR = REPO_ROOT / "reports"

# Map of ticker -> manifest file + model artifact paths
MODEL_SPECS: Dict[str, Dict[str, Any]] = {
    "IWM": {
        "manifest": MODELS_DIR / "IWM_gbm_production_manifest.json",
        "model_id": "IWM_direction_v1.0_gbm",
        "artifact_path": str(MODELS_DIR / "IWM_gbm_production.joblib"),
        "scaler_path": str(MODELS_DIR / "IWM_gbm_production_scaler.joblib"),
    },
    "TLT": {
        "manifest": MODELS_DIR / "TLT_gbm_deep_production_manifest.json",
        "model_id": "TLT_direction_v1.0_gbm_deep",
        "artifact_path": str(MODELS_DIR / "TLT_gbm_deep_production.joblib"),
        "scaler_path": str(MODELS_DIR / "TLT_gbm_deep_production_scaler.joblib"),
    },
    "QQQ": {
        "manifest": None,  # No manifest, construct from known info
        "model_id": "QQQ_direction_v1.0",
        "artifact_path": str(MODELS_DIR / "QQQ_direction_v1.0.joblib"),
        "scaler_path": str(MODELS_DIR / "QQQ_scaler_v1.0.joblib"),
    },
    "DIA": {
        "manifest": None,
        "model_id": "DIA_direction_v1.0",
        "artifact_path": str(MODELS_DIR / "DIA_direction_v1.0.joblib"),
        "scaler_path": str(MODELS_DIR / "DIA_scaler_v1.0.joblib"),
    },
}


def load_manifest(path: Optional[Path]) -> Dict[str, Any]:
    if path and path.exists():
        with open(path) as f:
            return json.load(f)  # type: ignore[no-any-return]
    return {}


def build_metrics_summary(ticker: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Build metrics_summary for the registry from manifest + known results."""
    # Known results from ML_RESULTS_SUMMARY.md
    known = {
        "IWM": {
            "holdout_sharpe": 1.397,
            "beats_baselines": True,
            "calibration_error": 0.03,
            "train_accuracy": 0.9979,
            "n_train_samples": 2799,
            "n_features": 44,
            "target": "target_directional_move",
            "model_type": "gbm",
        },
        "TLT": {
            "holdout_sharpe": 1.365,
            "beats_baselines": True,
            "calibration_error": 0.03,
            "train_accuracy": 0.9982,
            "n_train_samples": 2799,
            "n_features": 44,
            "target": "target_directional_move",
            "model_type": "gbm_deep",
        },
        "QQQ": {
            "holdout_sharpe": 1.867,
            "beats_baselines": False,  # REJECT: majority baseline 2.359
            "calibration_error": 0.04,
            "train_accuracy": 0.998,
            "n_train_samples": 2799,
            "n_features": 44,
            "target": "target_directional_move",
            "model_type": "gbm_deep",
        },
        "DIA": {
            "holdout_sharpe": 1.224,
            "beats_baselines": False,  # REJECT: majority baseline 1.636
            "calibration_error": 0.04,
            "train_accuracy": 0.997,
            "n_train_samples": 2799,
            "n_features": 44,
            "target": "target_directional_move",
            "model_type": "gbm_deep",
        },
    }
    base = known.get(ticker, {})
    # Override with manifest values if available
    if manifest:
        base["train_accuracy"] = manifest.get("train_accuracy", base.get("train_accuracy", 0))
        base["n_features"] = manifest.get("n_features", base.get("n_features", 0))
        base["feature_names"] = manifest.get("feature_names", [])
    return base


async def register_all(dry_run: bool = True, promote: Optional[List[str]] = None) -> None:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "confluence_decoder")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    registry = ModelRegistry(db)

    promote = promote or []
    results = []

    for ticker, spec in MODEL_SPECS.items():
        manifest = load_manifest(spec.get("manifest"))
        metrics = build_metrics_summary(ticker, manifest)
        feature_version = manifest.get("feature_version", "v1.0") if manifest else "v1.0"
        feature_names = manifest.get("feature_names", []) if manifest else []
        training_window = f"2024-01-01 to 2024-12-30 ({metrics.get('n_train_samples', '?')} samples)"

        print(f"\n{'='*60}")
        print(f"  Ticker: {ticker}")
        print(f"  Model ID: {spec['model_id']}")
        print(f"  Artifact: {spec['artifact_path']}")
        print(f"  Sharpe: {metrics.get('holdout_sharpe', 'N/A')}")
        print(f"  Beats baselines: {metrics.get('beats_baselines', 'N/A')}")
        print(f"  Status: {'SHIP' if metrics.get('beats_baselines') else 'REJECT'}")

        if not os.path.exists(spec["artifact_path"]):
            print(f"  SKIP: Artifact not found at {spec['artifact_path']}")
            results.append((ticker, "skip", "artifact missing"))
            continue

        if dry_run:
            print(f"  DRY RUN — would register as shadow")
            results.append((ticker, "dry_run", "would register"))
            continue

        # Register
        doc = await registry.register_model(
            model_id=spec["model_id"],
            ticker=ticker,
            feature_version=feature_version,
            training_window=training_window,
            metrics_summary={**metrics, "feature_names": feature_names},
            artifact_path=spec["artifact_path"],
            status="shadow",
        )
        print(f"  Registered: {doc['model_id']} status=shadow")
        results.append((ticker, "registered", spec["model_id"]))

        # Promote if requested and passes gate
        if ticker in promote:
            if not metrics.get("beats_baselines", False):
                print(f"  PROMOTE SKIP: beats_baselines=False, would fail gate")
                results.append((ticker, "promote_skip", "beats_baselines=False"))
            else:
                result = await registry.promote_model(spec["model_id"])
                print(f"  Promote result: {result}")
                results.append((ticker, "promoted" if result["success"] else "promote_failed", result.get("reason", "")))

    print(f"\n{'='*60}")
    print("Summary:")
    for ticker, action, detail in results:
        print(f"  {ticker}: {action} ({detail})")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register production ML models")
    parser.add_argument("--register", action="store_true", help="Actually register (default: dry-run)")
    parser.add_argument("--promote", nargs="*", default=[], help="Tickers to promote after registration (e.g., --promote IWM TLT)")
    args = parser.parse_args()

    import asyncio
    asyncio.run(register_all(dry_run=not args.register, promote=args.promote))
