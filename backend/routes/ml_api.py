"""
backend/routes/ml_api.py

FastAPI routes for ML model management.

Endpoints:
    GET  /api/ml/models              - List all models
    GET  /api/ml/models/{ticker}      - Get model info
    POST /api/ml/predict/{ticker}     - Get live prediction (real-time features)
    POST /api/ml/promote/{model_id}   - Promote shadow -> active
    GET  /api/ml/drift/{ticker}       - Get drift report
    GET  /api/ml/dashboard             - Full model health dashboard
    GET  /api/ml/features/{ticker}     - Get latest computed features
    POST /api/ml/batch-predict        - Predict all tickers at once
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.ml import DegenerateModelError
from services.ml import outcomes as outcomes_service
from services.ml.inference import inference_engine
from services.ml.registry import ModelRegistry
from services.ml.retrain import RetrainOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["ml"])


async def _get_registry() -> ModelRegistry:
    """Resolve the ModelRegistry singleton from the server's db handle."""
    from server import db
    return ModelRegistry(db)


# ── GET /api/ml/models ────────────────────────────────────────────────────


@router.get("/models")
async def list_models(
    ticker: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List all models, optionally filtered by ticker and/or status."""
    registry = await _get_registry()
    models = await registry.list_models(ticker=ticker, status=status)
    return {"models": models, "count": len(models)}


# ── GET /api/ml/models/{ticker} ───────────────────────────────────────────


@router.get("/models/{ticker}")
async def get_model_info(ticker: str) -> Dict[str, Any]:
    """Get detailed model info for a ticker."""
    try:
        info = inference_engine.get_model_info(ticker)
        return {
            "ticker": info.ticker,
            "model_id": info.model_id,
            "model_type": info.model_type,
            "n_features": info.n_features,
            "feature_names": info.feature_names,
            "train_accuracy": round(info.train_accuracy, 4),
            "artifact_path": info.artifact_path,
            "loaded": info.loaded,
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── POST /api/ml/predict/{ticker} ─────────────────────────────────────────


@router.post("/predict/{ticker}")
async def predict(ticker: str) -> Dict[str, Any]:
    """Get a live prediction for a ticker.

    Downloads recent market data, computes features in real-time,
    and runs inference using the pre-trained model.

    Returns prediction (2=UP, 1=HOLD, 0=DOWN), confidence, 3-way probabilities,
    and GEX regime signal.
    """
    from services.ml.inference import CLASS_LABELS
    try:
        result = await inference_engine.predict(ticker)
        label = CLASS_LABELS.get(result.prediction, "?")
        return {
            "ticker": result.ticker,
            "prediction": result.prediction,
            "prediction_label": label.lower(),
            "confidence": round(result.confidence, 4),
            "probabilities": {
                "down": round(result.probabilities[0], 4) if len(result.probabilities) > 0 else 0.33,
                "hold": round(result.probabilities[1], 4) if len(result.probabilities) > 1 else 0.34,
                "up": round(result.probabilities[2], 4) if len(result.probabilities) > 2 else 0.33,
            },
            "gex_signal": result.gex_signal,
            "gex_snapshot_date": result.gex_snapshot_date,
            "model_id": result.model_id,
            "features_used": len(result.features_used),
            "data_age_sec": round(result.data_age_sec, 1),
            "timestamp": result.timestamp,
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Prediction failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


# ── POST /api/ml/batch-predict ────────────────────────────────────────────


@router.post("/batch-predict")
async def batch_predict(
    tickers: Optional[List[str]] = Query(None),
) -> Dict[str, Any]:
    """Get predictions for multiple tickers at once.

    If no tickers specified, predicts all registered models.
    """
    from services.ml.inference import MODEL_REGISTRY

    target_tickers = [t.upper() for t in tickers] if tickers else list(MODEL_REGISTRY.keys())
    results = []
    errors = []

    for ticker in target_tickers:
        try:
            result = await inference_engine.predict(ticker)
            results.append({
                "ticker": result.ticker,
                "prediction": result.prediction,
                "prediction_label": "bullish" if result.prediction == 1 else "bearish",
                "confidence": round(result.confidence, 4),
                "data_age_sec": round(result.data_age_sec, 1),
            })
        except Exception as e:
            errors.append({"ticker": ticker, "error": str(e)})

    return {
        "predictions": results,
        "errors": errors,
        "count": len(results),
        "error_count": len(errors),
    }


# ── POST /api/ml/promote/{model_id} ───────────────────────────────────────


@router.post("/promote/{model_id}")
async def promote_model(model_id: str) -> Dict[str, Any]:
    """Promote a shadow model to active."""
    registry = await _get_registry()
    result = await registry.promote_model(model_id)

    if not result["success"]:
        if "not found" in result["reason"]:
            raise HTTPException(status_code=404, detail=result["reason"])
        raise HTTPException(status_code=400, detail=result["reason"])

    return result


# ── GET /api/ml/drift/{ticker} ────────────────────────────────────────────


@router.get("/drift/{ticker}")
async def drift_report(ticker: str) -> Dict[str, Any]:
    """Get the PSI drift report for a ticker's active model."""
    registry = await _get_registry()
    report = await registry.compute_drift(ticker)
    return report


# ── POST /api/ml/register ─────────────────────────────────────────────────


@router.post("/register")
async def register_model(body: Dict[str, Any]) -> Dict[str, Any]:
    """Register a new model from training artifact paths.

    Expected body:
        model_id: str          — Unique identifier (e.g. "SPY_direction_v2.0")
        ticker: str            — Ticker symbol
        artifact_path: str     — Absolute path to .joblib model file
        feature_version: str   — Feature version (default: "v1.0")
        metrics_summary: dict  — Keys: holdout_sharpe, beats_baselines, etc.
        training_window: str   — Description of training window
        status: str            — Initial status (default: "shadow")
    """
    registry = await _get_registry()
    model_id = body.get("model_id")
    ticker = body.get("ticker", "").upper()
    artifact_path = body.get("artifact_path", "")
    feature_version = body.get("feature_version", "v1.0")
    metrics_summary = body.get("metrics_summary", {})
    training_window = body.get("training_window", "unknown")
    status = body.get("status", "shadow")

    if not model_id or not ticker:
        raise HTTPException(status_code=400, detail="model_id and ticker are required")

    if artifact_path and not os.path.exists(artifact_path):
        raise HTTPException(status_code=400, detail=f"Artifact not found: {artifact_path}")

    doc = await registry.register_model(
        model_id=model_id,
        ticker=ticker,
        feature_version=feature_version,
        training_window=training_window,
        metrics_summary=metrics_summary,
        artifact_path=artifact_path,
        status=status,
    )
    return {"status": "registered", "model": doc}


# ── GET /api/ml/regime/{ticker} ───────────────────────────────────────────


@router.get("/regime/{ticker}")
async def get_regime(ticker: str) -> Dict[str, Any]:
    """Get the current volatility regime and anomaly threshold for a ticker.

    Uses 30-day realized vol percentile:
      - calm   (vol < 33rd pct)  → 99th-pct reconstruction error threshold
      - active (33rd–95th)       → 95th-pct
      - urgent (vol > 95th pct)  → 90th-pct

    Returns: regime, vol_30d, vol_percentile, threshold_used, is_anomaly
    """
    import numpy as np

    registry = await _get_registry()
    try:
        model, scaler, model_doc = await registry._load_active_artifact(ticker)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Fetch latest features
    features_df = await registry._compute_latest_features(ticker, model_doc["feature_version"])
    if features_df is None or features_df.empty:
        raise HTTPException(status_code=404, detail=f"No features for {ticker}")

    # Compute 30-day realized vol from recent rows
    if "realized_vol_21d" in features_df.columns:
        recent_vol = float(features_df["realized_vol_21d"].iloc[-1])
    elif "realized_vol_5d" in features_df.columns:
        recent_vol = float(features_df["realized_vol_5d"].iloc[-1])
    else:
        recent_vol = 0.0

    # Compute volatility percentile from history
    if "realized_vol_21d" in features_df.columns:
        vol_history = features_df["realized_vol_21d"].dropna().values
    else:
        vol_history = np.array([recent_vol])

    vol_pct = float(np.percentile(vol_history, 33)) if len(vol_history) > 0 else 0.0
    vol_95 = float(np.percentile(vol_history, 95)) if len(vol_history) > 0 else 1.0

    # Determine regime
    if recent_vol < vol_pct:
        regime = "calm"
        threshold_pct = 99
    elif recent_vol > vol_95:
        regime = "urgent"
        threshold_pct = 90
    else:
        regime = "active"
        threshold_pct = 95

    # Compute anomaly score if possible
    is_anomaly = False
    anomaly_score = 0.0
    try:
        feature_names = model_doc.get("metrics_summary", {}).get("feature_names", list(features_df.columns))
        available = [f for f in feature_names if f in features_df.columns]
        if available and len(available) >= 10:
            X = features_df[available].iloc[-1:].values.astype(float)
            X = np.nan_to_num(X, nan=0.0)
            if scaler is not None:
                try:
                    X_s = scaler.transform(X)
                except Exception:
                    X_s = X[:, :scaler.n_features_in_]
            else:
                X_s = X
            anomaly_score = float(model.predict_proba(X_s)[0][1]) if hasattr(model, "predict_proba") else 0.0
            # Threshold: calm=0.99 quantile → high bar, urgent=0.90 → lower bar
            threshold_map = {"calm": 0.70, "active": 0.55, "urgent": 0.45}
            is_anomaly = anomaly_score > threshold_map.get(regime, 0.55)
    except Exception as e:
        logger.warning(f"Regime anomaly score failed for {ticker}: {e}")

    return {
        "ticker": ticker,
        "regime": regime,
        "vol_21d": recent_vol,
        "vol_percentile_33": vol_pct,
        "vol_percentile_95": vol_95,
        "threshold_pct": threshold_pct,
        "anomaly_score": round(anomaly_score, 4),
        "is_anomaly": is_anomaly,
        "model_id": model_doc["model_id"],
        "ts": _now_iso(),
    }


# ── GET /api/ml/ensemble/{ticker} ────────────────────────────────────────


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


@router.get("/ensemble/{ticker}")
async def get_ensemble(ticker: str, horizon_minutes: int = 15) -> Dict[str, Any]:
    """Get ensemble toxicity score combining multiple detectors.

    Combines:
      (a) 1D-CNN AE reconstruction error
      (b) Statistical detector
      (c) ML model prediction probability

    Returns: P(toxic flow), per-component scores, final verdict
    """
    import numpy as np

    from services.anomaly_detector import FlowAnomalyDetector

    registry = await _get_registry()
    try:
        model, scaler, model_doc = await registry._load_active_artifact(ticker)
    except Exception as e:
        # Fall back to statistical only
        raise HTTPException(status_code=404, detail=f"No active model for {ticker}: {e}")

    features_df = await registry._compute_latest_features(ticker, model_doc["feature_version"])
    if features_df is None or features_df.empty:
        raise HTTPException(status_code=404, detail=f"No features for {ticker}")

    # ML model score
    ml_score = 0.5
    feature_names = model_doc.get("metrics_summary", {}).get("feature_names", list(features_df.columns))
    available = [f for f in feature_names if f in features_df.columns]
    if available and len(available) >= 10:
        X = features_df[available].iloc[-1:].values.astype(float)
        X = np.nan_to_num(X, nan=0.0)
        if scaler is not None:
            try:
                X_s = scaler.transform(X)
            except Exception:
                X_s = X[:, :scaler.n_features_in_]
        else:
            X_s = X
        if hasattr(model, "predict_proba"):
            ml_score = float(model.predict_proba(X_s)[0][1])

    # Statistical detector score
    stat_score = 0.5
    try:
        det = FlowAnomalyDetector()
        stat_result = det.score(features_df.iloc[-1].to_dict())
        stat_score = float(stat_result.get("score", 0.5))
    except Exception:
        pass

    # Weighted ensemble (ML model gets higher weight since it's calibrated)
    ensemble_score = 0.6 * ml_score + 0.4 * stat_score

    # Verdict by horizon
    thresholds = {1: 0.7, 5: 0.6, 15: 0.55, 60: 0.5}
    threshold = thresholds.get(horizon_minutes, 0.55)
    is_toxic = ensemble_score > threshold

    return {
        "ticker": ticker,
        "ensemble_score": round(ensemble_score, 4),
        "ml_score": round(ml_score, 4),
        "statistical_score": round(stat_score, 4),
        "horizon_minutes": horizon_minutes,
        "threshold": threshold,
        "is_toxic_flow": is_toxic,
        "verdict": "TOXIC" if is_toxic else "NORMAL",
        "model_id": model_doc["model_id"],
        "ts": _now_iso(),
    }


# ── GET /api/ml/dashboard ─────────────────────────────────────────────────


@router.get("/dashboard")
async def ml_dashboard() -> Dict[str, Any]:
    """Get the full ML model health dashboard.

    Returns predictions, rolling accuracy, drift status, and freshness
    for all deployed models.
    """
    try:
        from services.ml.dashboard import ModelDashboard
        dashboard = ModelDashboard()
        try:
            report = await dashboard.get_full_report()
            return report
        finally:
            await dashboard.close()
    except Exception as e:
        logger.error(f"Dashboard generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dashboard failed: {e}")


# ── GET /api/ml/features/{ticker} ─────────────────────────────────────────


@router.get("/features/{ticker}")
async def get_features(ticker: str) -> Dict[str, Any]:
    """Get latest computed features for a ticker."""
    try:
        import asyncio

        from services.ml.inference import compute_live_features
        features_df = await asyncio.to_thread(compute_live_features, ticker)

        # Return the latest row as a dict
        latest = features_df.iloc[-1]
        return {
            "ticker": ticker.upper(),
            "timestamp": str(features_df.index[-1]),
            "n_features": len(features_df.columns),
            "n_rows": len(features_df),
            "features": {
                col: round(float(latest[col]), 6)
                for col in features_df.columns
            },
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Feature computation failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Feature computation failed: {e}")


# ── GET /api/ml/briefing/{ticker} ─────────────────────────────────────────


@router.get("/briefing/{ticker}")
async def ml_briefing(ticker: str) -> Dict[str, Any]:
    """Unified ML briefing — combines prediction, model info, regime,
    rolling accuracy, and feature importance into one response for the
    MlDashboard frontend component.
    """
    from server import db
    ticker = ticker.upper()
    result: Dict[str, Any] = {"ticker": ticker, "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}

    # 1. Live prediction
    try:
        pred = await inference_engine.predict(ticker)
        result["prediction"] = pred.prediction
        result["prediction_label"] = "bullish" if pred.prediction == 1 else "bearish"
        result["confidence"] = round(pred.confidence, 4)
        result["probabilities"] = {
            "bearish": round(pred.probabilities[0], 4) if len(pred.probabilities) > 0 else 0.5,
            "bullish": round(pred.probabilities[1], 4) if len(pred.probabilities) > 1 else 0.5,
        }
        result["features_used"] = len(pred.features_used)
        result["feature_values"] = {k: round(v, 6) for k, v in pred.feature_values.items()}
        result["data_age_sec"] = round(pred.data_age_sec, 1)
    except DegenerateModelError as e:
        result["prediction_error"] = str(e)
    except Exception as e:
        result["prediction_error"] = str(e)

    # 2. Model info
    try:
        info = inference_engine.get_model_info(ticker)
        result["model_id"] = info.model_id
        result["model_type"] = info.model_type
        result["n_features"] = info.n_features
        result["train_accuracy"] = round(info.train_accuracy, 4)
    except Exception:
        pass

    # 3. Regime (from advanced analytics if available via db)
    try:
        registry = await _get_registry()
        drift = await registry.compute_drift(ticker)
        result["drift_status"] = drift.get("status", "unknown")
        result["drift_features"] = drift.get("n_recent_samples", 0)
    except Exception:
        pass

    # 4. Rolling accuracy
    try:
        from services.ml.outcomes import compute_rolling_accuracy
        acc7 = await compute_rolling_accuracy(db, ticker, window_days=7)
        acc30 = await compute_rolling_accuracy(db, ticker, window_days=30)
        result["rolling_7d_accuracy"] = acc7.get("accuracy")
        result["rolling_7d_n"] = acc7.get("n_with_outcomes", 0)
        result["rolling_30d_accuracy"] = acc30.get("accuracy")
        result["rolling_30d_n"] = acc30.get("n_with_outcomes", 0)
    except Exception:
        pass

    # 5. Combined signal
    pred_conf = result.get("confidence", 0.5)
    pred_label = result.get("prediction_label", "neutral")
    if pred_conf > 0.6:
        result["combined_signal"] = "STRONG_BULLISH" if pred_label == "bullish" else "STRONG_BEARISH"
    elif pred_conf > 0.52:
        result["combined_signal"] = "BULLISH" if pred_label == "bullish" else "BEARISH"
    else:
        result["combined_signal"] = "NEUTRAL"
    result["combined_confidence"] = pred_conf

    return result


# ── POST /api/ml/retrain/{ticker} ───────────────────────────────────────


@router.post("/retrain/{ticker}")
async def trigger_retrain(ticker: str) -> Dict[str, Any]:
    """Trigger an automated retraining job for a ticker.

    Checks drift first. Only triggers retraining if:
      - Drift is detected
      - No retrain is already in-flight
      - Cooldown period (24h) has expired since last retrain
    """
    from server import db
    try:
        orchestrator = RetrainOrchestrator(db)
        result = await orchestrator.check_and_retrain(ticker.upper())
        return result
    except Exception as e:
        logger.error(f"Retrain trigger failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retrain failed: {e}")


# ── POST /api/ml/attach-outcomes ────────────────────────────────────────


@router.post("/attach-outcomes")
async def attach_outcomes(batch_size: int = 100) -> Dict[str, Any]:
    """Attach realized outcomes to predictions that don't have them yet.

    Processes up to batch_size predictions per call.
    Idempotent — already-attached predictions are skipped.
    """
    from server import db
    try:
        n = await outcomes_service.attach_realized_outcomes(db, batch_size=batch_size)
        return {"status": "ok", "n_attached": n}
    except Exception as e:
        logger.error(f"Outcome attachment failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Outcome attachment failed: {e}")


# ── GET /api/ml/rolling-accuracy/{ticker} ───────────────────────────────


@router.get("/rolling-accuracy/{ticker}")
async def rolling_accuracy(
    ticker: str,
    window_days: int = 30,
) -> Dict[str, Any]:
    """Get rolling prediction accuracy for a ticker over the given window.

    Returns accuracy, n_predictions, n_with_outcomes, avg_return_pct.
    """
    from server import db
    try:
        result = await outcomes_service.compute_rolling_accuracy(
            db, ticker.upper(), window_days=window_days
        )
        return result
    except Exception as e:
        logger.error(f"Rolling accuracy failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rolling accuracy failed: {e}")


# ── GET /api/ml/retrain-status/{ticker} ─────────────────────────────────


@router.get("/retrain-status/{ticker}")
async def retrain_status(ticker: str) -> Dict[str, Any]:
    """Get the retrain history for a ticker."""
    from server import db
    try:
        col = db["ml_retrain"]
        cursor = col.find(
            {"ticker": ticker.upper()}, {"_id": 0}
        ).sort("created_at", -1).limit(10)
        history = await cursor.to_list(length=10)
        return {"ticker": ticker.upper(), "history": history, "count": len(history)}
    except Exception as e:
        logger.error(f"Retrain status failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



# ── GET /api/ml/calibration ────────────────────────────────--------------


@router.get("/calibration")
async def get_calibration_default(ticker: str = Query(default="SPY"), window: int = Query(default=30, ge=7, le=90)):
    """Get prediction confidence calibration for a ticker (query-param variant)."""
    return await get_calibration(ticker, window)

# ── GET /api/ml/calibration/{ticker} ────────────────────────────────────


@router.get("/calibration/{ticker}")
async def get_calibration(ticker: str, window: int = Query(default=30, ge=7, le=90)):
    """Get prediction confidence calibration for a ticker.

    Binds predictions into confidence buckets and computes actual
    accuracy per bucket. Well-calibrated model should have
    accuracy ≈ confidence in each bucket.

    Query params:
        window: Number of recent predictions to analyze (default 30, max 90)
    """
    from server import db
    preds_col = db["ml_predictions"]
    ticker = ticker.upper()

    # Fetch recent predictions with realized outcomes
    recent = await preds_col.find({
        "ticker": ticker,
        "realized_outcome": {"$ne": None},
        "confidence": {"$ne": None},
    }).sort("ts", -1).limit(window).to_list(length=window)

    if not recent:
        return {
            "ticker": ticker,
            "calibration": [],
            "total_samples": 0,
            "message": "No predictions with realized outcomes found",
        }

    # Bin predictions by confidence
    bins = {
        "0.50-0.60": {"predicted": [], "actual": []},
        "0.60-0.70": {"predicted": [], "actual": []},
        "0.70-0.80": {"predicted": [], "actual": []},
        "0.80-0.90": {"predicted": [], "actual": []},
        "0.90-1.00": {"predicted": [], "actual": []},
    }

    for r in recent:
        conf = r.get("confidence", 0)
        pred = r.get("prediction")
        actual = r.get("realized_outcome")
        if conf is None or pred is None or actual is None:
            continue

        if 0.50 <= conf < 0.60:
            bin_key = "0.50-0.60"
        elif 0.60 <= conf < 0.70:
            bin_key = "0.60-0.70"
        elif 0.70 <= conf < 0.80:
            bin_key = "0.70-0.80"
        elif 0.80 <= conf < 0.90:
            bin_key = "0.80-0.90"
        elif 0.90 <= conf <= 1.00:
            bin_key = "0.90-1.00"
        else:
            continue

        bins[bin_key]["predicted"].append(pred)
        bins[bin_key]["actual"].append(actual)

    calibration = []
    for bin_key, data in bins.items():
        n = len(data["predicted"])
        if n == 0:
            continue
        correct = sum(1 for p, a in zip(data["predicted"], data["actual"]) if p == a)
        avg_conf = sum(data["predicted"]) / n if n > 0 else 0
        calibration.append({
            "bin": bin_key,
            "n_samples": n,
            "accuracy": round(correct / n, 4),
            "mean_confidence": round(avg_conf, 4),
            "calibration_error": round(abs(avg_conf - correct / n), 4),
        })

    # Overall calibration error (ECE)
    total_samples = sum(c["n_samples"] for c in calibration)
    ece = (
        sum(c["n_samples"] * c["calibration_error"] for c in calibration) / total_samples
        if total_samples > 0
        else None
    )

    return {
        "ticker": ticker,
        "window": window,
        "total_samples": total_samples,
        "expected_calibration_error": round(ece, 4) if ece is not None else None,
        "calibration": calibration,
    }


# ── GET /api/ml/health/{ticker} ───────────────────────────────────────────


@router.get("/health/{ticker}")
async def ml_health_check(ticker: str) -> Dict[str, Any]:
    """Get ML model health assessment for a ticker."""
    try:
        from server import db
        from services.ml.health_monitor import assess_model_health
        result = await assess_model_health(db, ticker.upper())
        return result
    except Exception as e:
        logger.error(f"Health check failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")


# ── GET /api/ml/compare ─────────────────────────────────────────────────


@router.get("/compare")
async def ml_compare(
    tickers: Optional[str] = Query(default=None, description="Comma-separated tickers (default: SPY,QQQ,DIA,IWM,TLT)"),
) -> Dict[str, Any]:
    """Compare ML model predictions across all 5 tickers.

    Returns a dict keyed by ticker with:
      - model_id: active model identifier
      - prediction_label: "up"|"hold"|"down"
      - confidence: prediction confidence (0-1)
      - sharpe_90d: Sharpe ratio from realized outcomes over last 90 days
      - last_retrain_date: ISO date of last model retrain

    If a ticker has no data, its value is null.

    Query params:
        tickers: Comma-separated list (default: SPY,QQQ,DIA,IWM,TLT)
    """
    from datetime import datetime, timedelta, timezone

    import numpy as np

    from server import db

    DEFAULT_TICKERS = ["SPY", "QQQ", "DIA", "IWM", "TLT"]

    if tickers:
        target_tickers = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        target_tickers = DEFAULT_TICKERS

    result: Dict[str, Any] = {}

    for ticker in target_tickers:
        try:
            ticker_data: Dict[str, Any] = {}

            # 1. Latest prediction from ml_predictions
            preds_col = db["ml_predictions"]
            latest_pred = await preds_col.find_one(
                {"ticker": ticker},
                sort=[("ts", -1)],
            )

            if latest_pred:
                prediction_val = latest_pred.get("prediction")
                if prediction_val is not None:
                    # Map prediction int to label (matching the /predict endpoint pattern)
                    if prediction_val == 2:
                        ticker_data["prediction_label"] = "up"
                    elif prediction_val == 1:
                        ticker_data["prediction_label"] = "hold"
                    elif prediction_val == 0:
                        ticker_data["prediction_label"] = "down"
                    else:
                        ticker_data["prediction_label"] = "unknown"
                else:
                    ticker_data["prediction_label"] = None

                # Confidence from probability if available
                prob = latest_pred.get("probability")
                if prob and isinstance(prob, list) and len(prob) > 0:
                    ticker_data["confidence"] = round(float(max(prob)), 4)
                else:
                    ticker_data["confidence"] = latest_pred.get("confidence") or None

                ticker_data["model_id"] = latest_pred.get("model_id")
            else:
                ticker_data["prediction_label"] = None
                ticker_data["confidence"] = None
                ticker_data["model_id"] = None

            # 2. Model metadata (last retrain date) from ml_models
            models_col = db["ml_models"]
            active_model = await models_col.find_one(
                {"ticker": ticker, "status": "active"},
                {"_id": 0, "model_id": 1, "created_at": 1, "promoted_at": 1},
            )
            if active_model:
                ticker_data["model_id"] = ticker_data.get("model_id") or active_model.get("model_id")
                ticker_data["last_retrain_date"] = active_model.get("promoted_at") or active_model.get("created_at")
            else:
                ticker_data["last_retrain_date"] = None

            # 3. Sharpe ratio over 90 days from realized outcomes
            cutoff_90d = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            pipeline = [
                {"$match": {
                    "ticker": ticker,
                    "ts": {"$gte": cutoff_90d},
                    "realized_outcome": {"$ne": None},
                    "realized_return_pct": {"$ne": None},
                }},
                {"$sort": {"ts": 1}},
                {"$group": {
                    "_id": None,
                    "returns": {"$push": "$realized_return_pct"},
                }},
            ]
            try:
                agg_result = await preds_col.aggregate(pipeline).to_list(length=1)
                if agg_result and agg_result[0].get("returns"):
                    returns = [float(r) for r in agg_result[0]["returns"]]
                    n = len(returns)
                    if n >= 5:  # Need at least 5 data points for meaningful Sharpe
                        mean_ret = np.mean(returns)
                        std_ret = np.std(returns, ddof=1)
                        if std_ret > 0:
                            # Annualized Sharpe: daily mean/std * sqrt(252)
                            annual_factor = np.sqrt(252)
                            sharpe = (mean_ret / std_ret) * annual_factor
                            ticker_data["sharpe_90d"] = round(float(sharpe), 4)
                            ticker_data["sharpe_90d_n"] = n
                        else:
                            ticker_data["sharpe_90d"] = 0.0
                            ticker_data["sharpe_90d_n"] = n
                    else:
                        ticker_data["sharpe_90d"] = None
                        ticker_data["sharpe_90d_n"] = n
                else:
                    ticker_data["sharpe_90d"] = None
                    ticker_data["sharpe_90d_n"] = 0
            except Exception:
                ticker_data["sharpe_90d"] = None
                ticker_data["sharpe_90d_n"] = 0

            result[ticker] = ticker_data

        except Exception as e:
            logger.error(f"Compare failed for {ticker}: {e}")
            result[ticker] = None

    return result


# ── GET /api/ml/health ────────────────────────────────────────────────────


@router.get("/health")
async def ml_health_all() -> Dict[str, Any]:
    """Get health assessment for all active ML models."""
    try:
        from server import db
        from services.ml.health_monitor import get_all_models_health
        result = await get_all_models_health(db)
        return result
    except Exception as e:
        logger.error(f"Health check all failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")
