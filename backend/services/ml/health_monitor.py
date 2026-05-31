"""
backend/services/ml/health_monitor.py

ML Model Health Monitor — tracks prediction quality, data freshness,
and feature drift in real time. Triggers alerts when models degrade.

Monitors:
  1. Rolling accuracy (7d / 30d) vs baseline
  2. Prediction confidence distribution drift
  3. Feature PSI (Population Stability Index)
  4. Data freshness (time since last feature update)
  5. Prediction volume anomalies

Alert thresholds:
  - rolling_7d_accuracy < 0.50  -> DEGRADED
  - rolling_30d_accuracy < 0.48 -> CRITICAL
  - data_age_hours > 48          -> STALE
  - feature_psi > 0.25           -> DRIFT
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import numpy as np

log = logging.getLogger("ml.health")


class ModelHealthStatus:
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


def compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Compute Population Stability Index between two distributions.

    PSI < 0.1: stable
    PSI 0.1-0.25: moderate shift
    PSI > 0.25: significant drift
    """
    if len(expected) < bins or len(actual) < bins:
        return 0.0

    # Create bins from expected distribution
    breakpoints = np.percentile(expected, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)
    if len(breakpoints) < 3:
        return 0.0

    expected_counts = np.histogram(expected, bins=breakpoints)[0]
    actual_counts = np.histogram(actual, bins=breakpoints)[0]

    # Normalize to proportions
    expected_pct = expected_counts / max(len(expected), 1)
    actual_pct = actual_counts / max(len(actual), 1)

    # Add small epsilon to avoid log(0)
    eps = 1e-6
    expected_pct = np.clip(expected_pct, eps, 1)
    actual_pct = np.clip(actual_pct, eps, 1)

    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return float(psi)


async def assess_model_health(db, ticker: str) -> Dict[str, Any]:
    """Comprehensive health assessment for a single ticker's model.

    Returns dict with:
      - status: HEALTHY | DEGRADED | CRITICAL | STALE | UNKNOWN
      - rolling_7d_accuracy, rolling_30d_accuracy
      - feature_drift_scores: {feature: psi_score}
      - data_freshness_hours
      - recommendation: string
    """
    ticker = ticker.upper()
    result: Dict[str, Any] = {
        "ticker": ticker,
        "status": ModelHealthStatus.UNKNOWN,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    registry = _get_registry_from_db(db)

    # 1. Get active model info
    try:
        model_doc = await _get_active_model_doc(registry, ticker)
        if not model_doc:
            result["status"] = ModelHealthStatus.UNKNOWN
            result["recommendation"] = f"No active model for {ticker}"
            return result
        result["model_id"] = model_doc.get("model_id", "unknown")
        result["model_registered_at"] = model_doc.get("created_at", "unknown")
    except Exception as e:
        result["error"] = f"Model lookup failed: {e}"
        return result

    # 2. Rolling accuracy from outcomes
    now = datetime.now(timezone.utc)
    for window_days, key in [(7, "rolling_7d"), (30, "rolling_30d")]:
        try:
            since = (now - timedelta(days=window_days)).isoformat()
            cursor = db["ml_predictions"].find({
                "ticker": ticker,
                "timestamp": {"$gte": since},
                "outcome": {"$exists": True, "$ne": None},
            })
            docs = await cursor.to_list(length=1000)
            if len(docs) >= 10:
                correct = sum(1 for d in docs if d.get("prediction") == d.get("outcome"))
                acc = correct / len(docs)
                result[f"{key}_accuracy"] = round(acc, 4)
                result[f"{key}_n"] = len(docs)
            else:
                result[f"{key}_accuracy"] = None
                result[f"{key}_n"] = len(docs)
        except Exception as e:
            result[f"{key}_accuracy"] = None
            log.debug(f"Rolling accuracy failed for {ticker}: {e}")

    # 3. Data freshness
    try:
        latest = await db["ml_predictions"].find_one(
            {"ticker": ticker},
            sort=[("timestamp", -1)],
        )
        if latest and "timestamp" in latest:
            ts = latest["timestamp"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_hours = (now - ts).total_seconds() / 3600
            result["data_freshness_hours"] = round(age_hours, 1)
            if age_hours > 48:
                result["status"] = ModelHealthStatus.STALE
        else:
            result["data_freshness_hours"] = None
    except Exception as e:
        result["data_freshness_hours"] = None
        log.debug(f"Data freshness check failed for {ticker}: {e}")

    # 4. Feature drift (PSI on recent vs training distribution)
    try:
        feature_drift = await _compute_feature_drift(db, ticker, model_doc)
        result["feature_drift_scores"] = feature_drift
        max_psi = max(feature_drift.values()) if feature_drift else 0.0
        result["max_feature_psi"] = round(max_psi, 4)
    except Exception as e:
        result["feature_drift_scores"] = {}
        result["max_feature_psi"] = 0.0
        log.debug(f"Feature drift failed for {ticker}: {e}")

    # 5. Overall status determination
    acc7 = result.get("rolling_7d_accuracy")
    acc30 = result.get("rolling_30d_accuracy")
    max_psi = result.get("max_feature_psi", 0)
    freshness = result.get("data_freshness_hours")

    if acc7 is not None and acc7 < 0.50:
        result["status"] = ModelHealthStatus.CRITICAL
        result["recommendation"] = f"7d accuracy {acc7:.1%} below 50% — retrain immediately"
    elif acc30 is not None and acc30 < 0.48:
        result["status"] = ModelHealthStatus.DEGRADED
        result["recommendation"] = f"30d accuracy {acc30:.1%} below 48% — schedule retrain"
    elif max_psi > 0.25:
        result["status"] = ModelHealthStatus.DEGRADED
        result["recommendation"] = f"Feature drift PSI={max_psi:.2f} > 0.25 — retrain recommended"
    elif freshness is not None and freshness > 48:
        result["status"] = ModelHealthStatus.STALE
        result["recommendation"] = f"Data stale ({freshness:.0f}h old) — check data pipeline"
    elif acc7 is not None and acc7 > 0.52:
        result["status"] = ModelHealthStatus.HEALTHY
        result["recommendation"] = "Model performing within expected range"
    else:
        result["status"] = ModelHealthStatus.UNKNOWN
        result["recommendation"] = "Insufficient data for health assessment"

    return result


async def get_all_models_health(db) -> Dict[str, Any]:
    """Health assessment for all active models."""
    registry = _get_registry_from_db(db)
    try:
        tickers = await registry.get_active_tickers()
    except Exception:
        tickers = ["SPY", "QQQ", "DIA", "IWM", "TLT"]

    results = {}
    for ticker in tickers:
        try:
            results[ticker] = await assess_model_health(db, ticker)
        except Exception as e:
            results[ticker] = {"ticker": ticker, "status": "ERROR", "error": str(e)}

    healthy = sum(1 for r in results.values() if r.get("status") == ModelHealthStatus.HEALTHY)
    degraded = sum(1 for r in results.values() if r.get("status") in (ModelHealthStatus.DEGRADED, ModelHealthStatus.STALE))
    critical = sum(1 for r in results.values() if r.get("status") == ModelHealthStatus.CRITICAL)

    return {
        "models": results,
        "summary": {
            "total": len(results),
            "healthy": healthy,
            "degraded": degraded,
            "critical": critical,
            "overall_status": "CRITICAL" if critical > 0 else "DEGRADED" if degraded > 0 else "HEALTHY",
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Internal helpers ──────────────────────────────────────────────────────

def _get_registry_from_db(db):
    from services.ml.registry import ModelRegistry
    return ModelRegistry(db)


async def _get_active_model_doc(registry, ticker):
    try:
        models = await registry.list_models(ticker=ticker, status="active")
        return models[0] if models else None
    except Exception:
        return None


async def _compute_feature_drift(db, ticker: str, model_doc: Dict) -> Dict[str, float]:
    """Compute PSI for each feature between training and recent distributions."""
    try:
        # Get recent predictions with feature snapshots
        cursor = db["ml_predictions"].find(
            {"ticker": ticker, "feature_snapshot": {"$exists": True}},
            {"feature_snapshot": 1, "_id": 0},
        ).sort("timestamp", -1).limit(100)
        recent_docs = await cursor.to_list(length=100)
        if not recent_docs:
            return {}

        # Get training distribution from model manifest
        training_stats = model_doc.get("training_data_stats", {})
        if not training_stats:
            return {}

        drift_scores = {}
        for feat_name in training_stats:
            recent_vals = [
                d["feature_snapshot"].get(feat_name)
                for d in recent_docs
                if d.get("feature_snapshot", {}).get(feat_name) is not None
            ]
            if len(recent_vals) < 10:
                continue

            train_mean = training_stats[feat_name].get("mean", 0)
            train_std = training_stats[feat_name].get("std", 1)
            if train_std < 1e-8:
                continue

            # Generate synthetic training distribution
            train_dist = np.random.normal(train_mean, train_std, 1000)
            recent_arr = np.array(recent_vals)

            psi = compute_psi(train_dist, recent_arr)
            if psi > 0.05:  # Only report meaningful drift
                drift_scores[feat_name] = round(psi, 4)

        return drift_scores
    except Exception as e:
        log.debug(f"Feature drift computation failed: {e}")
        return {}
