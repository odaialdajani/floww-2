"""
backend/services/ml/registry.py

Model registry service for the Confluence Decoder ML pipeline.

Manages the full model lifecycle (shadow -> active -> retired) with:
- Metadata storage in MongoDB collection 'ml_models'
- Promotion gate: shadow -> active only if quality criteria are met
- Inference: load active model, compute features, return prediction
- Drift monitoring: PSI per feature over rolling 24h vs training distribution
- Prediction logging to 'ml_predictions' collection
"""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from . import DegenerateModelError

log = logging.getLogger("ml.registry")

load_dotenv(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
COLLECTION_MODELS = "ml_models"
COLLECTION_PREDICTIONS = "ml_predictions"
COLLECTION_FEATURES = "ml_features"

# Default model artifact directory (repo-root/models/)
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _get_db() -> Any:
    """Return a motor async database handle."""
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


# ────────────────────────────────────────────────────────────────────────────
# PSI (Population Stability Index)
# ────────────────────────────────────────────────────────────────────────────


def compute_psi(
    expected: np.ndarray,
    actual: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute PSI between two distributions.

    Uses quantile-based bins from the expected (training) distribution.
    Returns 0.0 for degenerate inputs (constant arrays, empty, etc.).
    """
    expected = expected[~np.isnan(expected)]
    actual = actual[~np.isnan(actual)]

    if len(expected) < n_bins * 2 or len(actual) < 2:
        return 0.0

    # Build bins from expected distribution quantiles
    quantiles = np.linspace(0, 1, n_bins + 1)
    bins = np.unique(np.quantile(expected, quantiles))
    if len(bins) < 3:
        return 0.0  # constant or near-constant

    expected_counts, _ = np.histogram(expected, bins=bins)
    actual_counts, _ = np.histogram(actual, bins=bins)

    # Normalize to proportions
    expected_prop = expected_counts.astype(float) / max(expected_counts.sum(), 1)
    actual_prop = actual_counts.astype(float) / max(actual_counts.sum(), 1)

    # PSI formula: sum((actual - expected) * ln(actual / expected))
    psi = 0.0
    for a, e in zip(actual_prop, expected_prop):
        if a < 1e-10 or e < 1e-10:
            continue
        psi += (a - e) * math.log(a / e)

    return float(psi)


# ────────────────────────────────────────────────────────────────────────────
# Model Registry
# ────────────────────────────────────────────────────────────────────────────


class ModelRegistry:
    """Manages ML model lifecycle in MongoDB.

    Usage:
        registry = ModelRegistry(db)
        await registry.register_model(...)
        await registry.promote_model(model_id)
        prediction = await registry.predict(ticker)
        drift = await registry.compute_drift(ticker)
    """

    def __init__(self, db: Any) -> None:
        self.db = db
        self.models_col = db[COLLECTION_MODELS]
        self.predictions_col = db[COLLECTION_PREDICTIONS]
        self.features_col = db[COLLECTION_FEATURES]
        # In-memory cache: ticker -> (model, scaler, meta)
        self._cache: Dict[str, Tuple[Any, Any, Dict]] = {}

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def register_model(
        self,
        model_id: str,
        ticker: str,
        feature_version: str,
        training_window: str,
        metrics_summary: Dict[str, Any],
        artifact_path: str,
        training_feature_dist: Optional[Dict[str, List[float]]] = None,
        status: str = "shadow",
    ) -> Dict[str, Any]:
        """Register a new model in the registry.

        Args:
            model_id: Unique identifier (e.g. "SPY_direction_v2.0")
            ticker: Ticker symbol
            feature_version: Feature version string
            training_window: Description of training window
            metrics_summary: Dict with keys like accuracy, sharpe, beats_baselines, etc.
            artifact_path: Filesystem path to .joblib model artifact
            training_feature_dist: Per-feature training distribution for drift monitoring
            status: Initial status (default: shadow)
        """
        doc = {
            "model_id": model_id,
            "ticker": ticker.upper(),
            "feature_version": feature_version,
            "training_window": training_window,
            "metrics_summary": metrics_summary,
            "artifact_path": artifact_path,
            "training_feature_dist": training_feature_dist or {},
            "status": status,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "promoted_at": None,
            "retired_at": None,
        }

        await self.models_col.update_one(
            {"model_id": model_id},
            {"$set": doc},
            upsert=True,
        )
        log.info(f"Registered model {model_id} ({ticker}) status={status}")
        return doc

    async def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get a single model document by model_id."""
        return await self.models_col.find_one({"model_id": model_id}, {"_id": 0})

    async def list_models(
        self,
        ticker: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List models, optionally filtered by ticker and/or status."""
        query: Dict[str, Any] = {}
        if ticker:
            query["ticker"] = ticker.upper()
        if status:
            query["status"] = status

        cursor = self.models_col.find(query, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(length=1000)

    async def get_active_model(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get the currently active model for a ticker."""
        return await self.models_col.find_one(
            {"ticker": ticker.upper(), "status": "active"},
            {"_id": 0},
        )

    # ── Lifecycle / Promotion Gate ────────────────────────────────────────

    async def promote_model(self, model_id: str) -> Dict[str, Any]:
        """Promote a shadow model to active.

        Promotion gate criteria (all must hold):
            1. beats_baselines == True
            2. holdout_sharpe > prior_active.holdout_sharpe
            3. calibration_error < 0.05

        If no prior active model exists, criterion 2 is skipped (auto-pass).

        Returns:
            Dict with keys: success (bool), reason (str), model_id
        """
        model = await self.get_model(model_id)
        if not model:
            return {"success": False, "reason": f"model {model_id} not found", "model_id": model_id}

        if model["status"] != "shadow":
            return {
                "success": False,
                "reason": f"model is {model['status']}, expected shadow",
                "model_id": model_id,
            }

        metrics = model.get("metrics_summary", {})

        # Gate 1: beats_baselines
        if not metrics.get("beats_baselines", False):
            return {
                "success": False,
                "reason": "beats_baselines is False",
                "model_id": model_id,
            }

        # Gate 2: holdout_sharpe > prior_active.holdout_sharpe
        ticker = model["ticker"]
        prior_active = await self.models_col.find_one(
            {"ticker": ticker, "status": "active"},
            {"_id": 0},
        )
        if prior_active:
            prior_sharpe = prior_active.get("metrics_summary", {}).get("holdout_sharpe", 0.0)
            candidate_sharpe = metrics.get("holdout_sharpe", 0.0)
            if candidate_sharpe <= prior_sharpe:
                return {
                    "success": False,
                    "reason": (
                        f"holdout_sharpe {candidate_sharpe:.4f} <= "
                        f"prior active {prior_sharpe:.4f}"
                    ),
                    "model_id": model_id,
                }

        # Gate 3: calibration_error < 0.05
        cal_error = metrics.get("calibration_error", 1.0)  # default fail-closed
        if cal_error >= 0.05:
            return {
                "success": False,
                "reason": f"calibration_error {cal_error:.4f} >= 0.05",
                "model_id": model_id,
            }

        # All gates passed — promote
        now = _now_iso()

        # Retire prior active
        if prior_active:
            await self.models_col.update_one(
                {"model_id": prior_active["model_id"]},
                {"$set": {"status": "retired", "retired_at": now, "updated_at": now}},
            )
            # Invalidate cache for this ticker
            self._cache.pop(ticker, None)
            log.info(f"Retired prior active model {prior_active['model_id']}")

        # Promote candidate
        await self.models_col.update_one(
            {"model_id": model_id},
            {"$set": {"status": "active", "promoted_at": now, "updated_at": now}},
        )
        log.info(f"Promoted model {model_id} to active for {ticker}")

        return {"success": True, "reason": "promoted", "model_id": model_id}

    async def retire_model(self, model_id: str) -> Dict[str, Any]:
        """Retire a model (active or shadow)."""
        model = await self.get_model(model_id)
        if not model:
            return {"success": False, "reason": f"model {model_id} not found"}

        now = _now_iso()
        await self.models_col.update_one(
            {"model_id": model_id},
            {"$set": {"status": "retired", "retired_at": now, "updated_at": now}},
        )
        ticker = model["ticker"]
        self._cache.pop(ticker, None)
        log.info(f"Retired model {model_id}")
        return {"success": True, "reason": "retired", "model_id": model_id}

    # ── Inference ─────────────────────────────────────────────────────────

    async def _load_active_artifact(
        self, ticker: str
    ) -> Tuple[Any, Any, Dict[str, Any]]:
        """Load the active model + scaler for a ticker (with in-memory cache).

        Returns (model, scaler, model_doc).
        Raises DegenerateModelError if no active model or artifact missing.
        """
        ticker = ticker.upper()

        if ticker in self._cache:
            return self._cache[ticker]

        model_doc = await self.get_active_model(ticker)
        if not model_doc:
            raise DegenerateModelError(f"No active model for {ticker}")

        artifact_path = model_doc.get("artifact_path", "")
        scaler_path = artifact_path.replace(".joblib", "_scaler.joblib")
        _meta_path = artifact_path.replace(".joblib", "_meta.json")

        if not os.path.exists(artifact_path):
            raise DegenerateModelError(
                f"Model artifact not found: {artifact_path}"
            )

        model = joblib.load(artifact_path)

        scaler = None
        if os.path.exists(scaler_path):
            scaler = joblib.load(scaler_path)

        self._cache[ticker] = (model, scaler, model_doc)
        log.debug(f"Loaded active model for {ticker}: {model_doc['model_id']}")
        return model, scaler, model_doc

    async def predict(self, ticker: str) -> Dict[str, Any]:
        """Run inference using the active model for a ticker.

        Loads the active model, computes features from the latest data,
        returns prediction, and logs to ml_predictions.
        """
        ticker = ticker.upper()
        model, scaler, model_doc = await self._load_active_artifact(ticker)

        # Compute features from latest data
        features_df = await self._compute_latest_features(ticker, model_doc["feature_version"])
        if features_df is None or features_df.empty:
            raise DegenerateModelError(f"Could not compute features for {ticker}")

        # Extract feature matrix in the order the model expects
        feature_names = model_doc.get("metrics_summary", {}).get(
            "feature_names", list(features_df.columns)
        )
        # Only use columns that exist
        available = [f for f in feature_names if f in features_df.columns]
        if not available:
            raise DegenerateModelError(
                f"No expected features found for {ticker}. "
                f"Expected: {feature_names}, Available: {list(features_df.columns)}"
            )

        X = features_df[available].iloc[-1:].values.astype(float)
        if scaler is not None:
            X = scaler.transform(X)

        prediction = model.predict(X)[0]
        probability = None
        if hasattr(model, "predict_proba"):
            probability = model.predict_proba(X)[0].tolist()

        result = {
            "ticker": ticker,
            "prediction": int(prediction),
            "probability": probability,
            "model_id": model_doc["model_id"],
            "feature_version": model_doc["feature_version"],
            "features_used": available,
            "ts": _now_iso(),
        }

        # Log prediction
        await self.predictions_col.insert_one({
            "ticker": ticker,
            "ts": _now_dt(),
            "prediction": int(prediction),
            "probability": probability,
            "model_id": model_doc["model_id"],
            "feature_version": model_doc["feature_version"],
            "realized_outcome": None,
        })

        return result

    async def _compute_latest_features(
        self, ticker: str, feature_version: str
    ) -> Optional[pd.DataFrame]:
        """Fetch the latest computed features for a ticker from ml_features."""
        cursor = self.features_col.find(
            {"ticker": ticker, "feature_version": feature_version}
        ).sort("date", -1)
        rows = await cursor.to_list(length=100)
        if not rows:
            return None
        df = pd.DataFrame(rows)
        if "_id" in df.columns:
            df.drop(columns=["_id"], inplace=True)
        return df

    # ── Drift Monitoring ──────────────────────────────────────────────────

    async def compute_drift(self, ticker: str) -> Dict[str, Any]:
        """Compute PSI drift report for a ticker's active model.

        Compares the rolling 24h feature distribution against the
        training distribution stored in the model document.
        """
        ticker = ticker.upper()
        model_doc = await self.get_active_model(ticker)
        if not model_doc:
            return {
                "ticker": ticker,
                "status": "no_active_model",
                "features": {},
            }

        training_dist: Dict[str, List[float]] = model_doc.get(
            "training_feature_dist", {}
        )
        if not training_dist:
            return {
                "ticker": ticker,
                "model_id": model_doc["model_id"],
                "status": "no_training_dist",
                "features": {},
            }

        # Fetch last 24h of features
        cutoff = _now_dt() - timedelta(hours=24)
        cursor = self.features_col.find(
            {
                "ticker": ticker,
                "feature_version": model_doc["feature_version"],
                "date": {"$gte": cutoff.isoformat()},
            }
        ).sort("date", 1)
        recent_rows = await cursor.to_list(length=10000)

        if not recent_rows:
            return {
                "ticker": ticker,
                "model_id": model_doc["model_id"],
                "status": "no_recent_data",
                "features": {},
            }

        recent_df = pd.DataFrame(recent_rows)
        if "_id" in recent_df.columns:
            recent_df.drop(columns=["_id"], inplace=True)

        # Compute PSI per feature
        feature_psi: Dict[str, float] = {}
        drift_alerts: List[str] = []
        PSI_THRESHOLD = 0.2  # standard threshold for significant drift

        for feat_name, train_vals in training_dist.items():
            if feat_name not in recent_df.columns:
                continue
            train_arr = np.array(train_vals, dtype=float)
            recent_arr = recent_df[feat_name].dropna().values.astype(float)
            if len(recent_arr) < 10:
                continue
            psi = compute_psi(train_arr, recent_arr)
            feature_psi[feat_name] = round(psi, 6)
            if psi >= PSI_THRESHOLD:
                drift_alerts.append(feat_name)

        status = "ok" if not drift_alerts else "drift_detected"
        return {
            "ticker": ticker,
            "model_id": model_doc["model_id"],
            "status": status,
            "n_recent_samples": len(recent_df),
            "psi_threshold": PSI_THRESHOLD,
            "features": feature_psi,
            "drift_alerts": drift_alerts,
            "computed_at": _now_iso(),
        }

    # ── Prediction outcome backfill ───────────────────────────────────────

    async def update_realized_outcome(
        self, ticker: str, ts: datetime, outcome: int
    ) -> None:
        """Backfill the realized_outcome for a prediction."""
        await self.predictions_col.update_one(
            {"ticker": ticker.upper(), "ts": ts},
            {"$set": {"realized_outcome": outcome}},
        )


# ────────────────────────────────────────────────────────────────────────────
# Module-level singleton helper
# ────────────────────────────────────────────────────────────────────────────

_registry_instance: Optional[ModelRegistry] = None


