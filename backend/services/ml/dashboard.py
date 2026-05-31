"""
backend/services/ml/dashboard.py

ML Model Dashboard — health, performance, and drift monitoring.

Provides a unified view of all deployed models:
- Current predictions with confidence
- Rolling accuracy over 7d / 30d windows
- Feature drift (PSI) alerts
- Model freshness (data age, last retrain)
- Prediction latency

Usage:
    from services.ml.dashboard import ModelDashboard
    dash = ModelDashboard()
    report = await dash.get_full_report()
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from services.ml.inference import MODEL_REGISTRY, InferenceEngine
from services.ml.registry import ModelRegistry

log = logging.getLogger("ml.dashboard")

load_dotenv(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"


class ModelDashboard:
    """ML model health dashboard.

    Aggregates predictions, drift, accuracy, and freshness into
    a single monitoring view.
    """

    def __init__(self):
        self.inference = InferenceEngine()
        self._client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        self._db = self._client[DB_NAME]
        self.registry = ModelRegistry(self._db)

    async def get_model_health(self, ticker: str) -> ModelHealth:
        """Get health status for a single model."""
        ticker = ticker.upper()
        prediction = None
        confidence = None
        data_age = None
        pred_ts = None
        status = "healthy"

        # Try to run a live prediction
        try:
            result = await self.inference.predict(ticker)
            prediction = result.prediction
            confidence = result.confidence
            data_age = result.data_age_sec
            pred_ts = result.timestamp
        except Exception as e:
            log.warning(f"Prediction failed for {ticker}: {e}")
            status = "error"

        # Get drift report
        drift_status = "ok"
        drift_alerts = []
        try:
            drift = await self.registry.compute_drift(ticker)
            drift_status = drift.get("status", "unknown")
            if drift_status == "drift_detected":
                status = "drift"
                drift_alerts = [
                    f for f, psi in drift.get("features", {}).items()
                    if psi >= 0.2
                ]
        except Exception as e:
            log.debug(f"Drift check failed for {ticker}: {e}")

        # Get rolling accuracy from prediction log
        rolling_7d = None
        rolling_30d = None
        total_preds = 0
        try:
            preds_col = self._db["ml_predictions"]
            now = datetime.now(timezone.utc)

            # Last 7 days
            cutoff_7d = (now - timedelta(days=7)).isoformat()
            recent = await preds_col.find({
                "ticker": ticker,
                "ts": {"$gte": cutoff_7d},
                "realized_outcome": {"$ne": None},
            }).to_list(length=1000)

            if recent:
                correct = sum(
                    1 for r in recent if r.get("prediction") == r.get("realized_outcome")
                )
                rolling_7d = correct / len(recent)

            # Last 30 days
            cutoff_30d = (now - timedelta(days=30)).isoformat()
            month = await preds_col.find({
                "ticker": ticker,
                "ts": {"$gte": cutoff_30d},
                "realized_outcome": {"$ne": None},
            }).to_list(length=5000)

            if month:
                correct = sum(
                    1 for r in month if r.get("prediction") == r.get("realized_outcome")
                )
                rolling_30d = correct / len(month)

            # Total predictions
            total_preds = await preds_col.count_documents({"ticker": ticker})

            # Last prediction timestamp
            last = await preds_col.find_one(
                {"ticker": ticker},
                sort=[("ts", -1)],
            )
            if last:
                raw_ts = last.get("ts", pred_ts)
                if isinstance(raw_ts, datetime):
                    pred_ts = raw_ts.isoformat()
                else:
                    pred_ts = raw_ts

        except Exception as e:
            log.debug(f"Accuracy check failed for {ticker}: {e}")

        # Check staleness
        if data_age and data_age > 3600:  # > 1 hour
            if status == "healthy":
                status = "stale"

        # Get model info
        try:
            model_info = self.inference.get_model_info(ticker)
            model_id = model_info.model_id
            model_type = model_info.model_type
            train_acc = model_info.train_accuracy
            n_feat = model_info.n_features
        except Exception:
            model_id = f"{ticker}_unknown"
            model_type = "unknown"
            train_acc = 0.0
            n_feat = 0

        return ModelHealth(
            ticker=ticker,
            model_id=model_id,
            model_type=model_type,
            status=status,
            loaded=ticker in self.inference._model_cache,
            prediction=prediction,
            confidence=confidence,
            data_age_sec=data_age,
            rolling_7d_accuracy=round(rolling_7d, 4) if rolling_7d is not None else None,
            rolling_30d_accuracy=round(rolling_30d, 4) if rolling_30d is not None else None,
            total_predictions=total_preds,
            drift_status=drift_status,
            drift_alerts=drift_alerts[:5],  # cap at 5
            last_prediction_ts=pred_ts,
            train_accuracy=train_acc,
            n_features=n_feat,
        )

    async def get_full_report(self) -> Dict[str, Any]:
        """Get the full dashboard report for all models."""
        models = []
        for ticker in MODEL_REGISTRY:
            try:
                health = await self.get_model_health(ticker)
                models.append(health)
            except Exception as e:
                log.error(f"Failed to get health for {ticker}: {e}")
                models.append(ModelHealth(
                    ticker=ticker,
                    model_id=f"{ticker}_error",
                    model_type="unknown",
                    status="error",
                    loaded=False,
                    prediction=None,
                    confidence=None,
                    data_age_sec=None,
                    rolling_7d_accuracy=None,
                    rolling_30d_accuracy=None,
                    total_predictions=0,
                    drift_status="unknown",
                    drift_alerts=[],
                    last_prediction_ts=None,
                    train_accuracy=0.0,
                    n_features=0,
                ))

        now = datetime.now(timezone.utc)
        healthy = sum(1 for m in models if m.status == "healthy")
        drift = sum(1 for m in models if m.status == "drift")
        errors = sum(1 for m in models if m.status == "error")

        avg_conf = np.mean([
            m.confidence for m in models if m.confidence is not None
        ]) if any(m.confidence is not None for m in models) else 0.0

        avg_age = np.mean([
            m.data_age_sec for m in models if m.data_age_sec is not None
        ]) if any(m.data_age_sec is not None for m in models) else 0.0

        return {
            "timestamp": now.isoformat(),
            "models": [
                {
                    "ticker": m.ticker,
                    "model_id": m.model_id,
                    "model_type": m.model_type,
                    "status": m.status,
                    "loaded": m.loaded,
                    "prediction": m.prediction,
                    "confidence": round(m.confidence, 4) if m.confidence else None,
                    "data_age_sec": round(m.data_age_sec, 1) if m.data_age_sec else None,
                    "rolling_7d_accuracy": m.rolling_7d_accuracy,
                    "rolling_30d_accuracy": m.rolling_30d_accuracy,
                    "total_predictions": m.total_predictions,
                    "drift_status": m.drift_status,
                    "drift_alerts": m.drift_alerts,
                    "last_prediction_ts": m.last_prediction_ts,
                    "train_accuracy": round(m.train_accuracy, 4),
                    "n_features": m.n_features,
                }
                for m in models
            ],
            "summary": {
                "total_models": len(models),
                "healthy": healthy,
                "drift": drift,
                "error": errors,
                "avg_confidence": round(float(avg_conf), 4),
                "avg_data_age_sec": round(float(avg_age), 1),
            },
        }

    async def close(self):
        self._client.close()


class ModelHealth:
    """Health status for a single model."""
    ticker: str
    model_id: str
    model_type: str
    status: str  # "healthy", "stale", "drift", "error"
    loaded: bool
    prediction: Optional[int]
    confidence: Optional[float]
    data_age_sec: Optional[float]
    rolling_7d_accuracy: Optional[float]
    rolling_30d_accuracy: Optional[float]
    total_predictions: int
    drift_status: str
    drift_alerts: List[str]
    last_prediction_ts: Optional[str]
    train_accuracy: float
    n_features: int


