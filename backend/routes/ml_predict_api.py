"""
backend/routes/ml_predict_api.py

Real-time ML prediction endpoint using live data.

GET /api/ml/predict/{ticker}
  → Fetches live options chain + price history
  → Computes GEX/OI/IV + technical features
  → Runs trained model inference
  → Returns prediction with confidence + feature breakdown

GET /api/ml/ensemble
  → Runs inference on all registered models (SPY, QQQ, TLT, IWM)
  → Returns combined signal with per-ticker breakdown

POST /api/ml/train
  → Triggers async model retraining on latest data
  → Returns training job status
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["ml-predict"])


# ── Prediction cache ─────────────────────────────────────────────────────
_pred_cache: Dict[str, Dict] = {}
_pred_cache_ttl_sec = 60  # Cache predictions for 60 seconds


def _get_cached_prediction(ticker: str) -> Optional[Dict]:
    """Get cached prediction if fresh enough."""
    import time
    entry = _pred_cache.get(ticker.upper())
    if entry and (time.time() - entry["ts"]) < _pred_cache_ttl_sec:
        return entry["data"]
    return None


def _set_cached_prediction(ticker: str, data: Dict):
    """Cache a prediction result."""
    import time
    _pred_cache[ticker.upper()] = {"ts": time.time(), "data": data}



@router.get("/predict/{ticker}")
async def predict_direction(
    ticker: str,
    model_type: str = Query(default="gbm", description="Model type: gbm, logistic, ensemble"),
):
    """Predict SPY direction using live data + trained model.

    Fetches the current options chain, computes GEX/OI/IV features,
    combines with technical indicators, and runs the trained model.

    Response:
    {
        "ticker": "SPY",
        "prediction": "UP" | "DOWN",
        "confidence": 0.65,
        "probabilities": {"down": 0.35, "up": 0.65},
        "spot": 528.50,
        "model_id": "SPY_gbm_v1.0",
        "features": {
            "chain_available": true,
            "net_gex": 1.2e9,
            "gex_regime": "positive",
            "king_distance_pct": -0.01,
            "rsi_14": 62.3,
            ...
        },
        "chain_meta": {...},
        "computed_at": "2026-05-23T..."
    }
    """
    ticker = ticker.upper()

    # 1. Compute features from live data
    from services.ml_realtime_features import compute_features_async
    feature_data = await compute_features_async(ticker)
    if feature_data is None:
        raise HTTPException(503, f"Could not compute features for {ticker}")

    features = feature_data["features"]
    feature_names = feature_data["feature_names"]

    # 2. Load model
    model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
    model_path = os.path.join(model_dir, f"price_model_{ticker}.joblib")
    scaler_path = os.path.join(model_dir, f"price_scaler_{ticker}.joblib")
    meta_path = os.path.join(model_dir, f"meta_{ticker}.json")

    import joblib
    if not os.path.exists(model_path):
        raise HTTPException(404, f"No trained model for {ticker}. Run training first.")

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path) if os.path.exists(scaler_path) else None

    # 3. Build feature vector in model-expected order
    # Load meta to get the exact feature names the model was trained with
    model_feature_names = feature_names  # default
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        model_feature_names = meta.get("feature_names", feature_names)

    # Build vector, using 0.0 for any missing features
    import numpy as np
    X = np.array([[features.get(name, 0.0) for name in model_feature_names]])

    if scaler is not None:
        X = scaler.transform(X)

    # 4. Predict
    prediction = int(model.predict(X)[0])
    probability = model.predict_proba(X)[0].tolist() if hasattr(model, "predict_proba") else [0.5, 0.5]

    # 5. Build response
    result = {
        "ticker": ticker,
        "prediction": "UP" if prediction == 1 else "DOWN",
        "confidence": round(float(max(probability)), 4),
        "probabilities": {
            "down": round(float(probability[0]), 4),
            "up": round(float(probability[1]), 4),
        },
        "spot": feature_data["spot"],
        "model_type": model_type,
        "chain_available": feature_data["chain_available"],
        "chain_meta": feature_data.get("chain_meta"),
        "top_features": _get_top_features(model, model_feature_names),
        "computed_at": feature_data["computed_at"],
    }

    logger.info(
        f"Prediction for {ticker}: {result['prediction']} "
        f"(confidence={result['confidence']:.3f}, "
        f"chain={'yes' if feature_data['chain_available'] else 'no'})"
    )

    return result


def _get_top_features(model, feature_names: List[str], top_n: int = 10) -> Dict[str, float]:
    """Get top N feature importances from the model."""
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        pairs = list(zip(feature_names, importances))
        pairs.sort(key=lambda x: abs(x[1]), reverse=True)
        return {name: round(float(imp), 6) for name, imp in pairs[:top_n]}
    return {}


@router.get("/ensemble")
async def ensemble_prediction(
    tickers: str = Query(default="SPY,QQQ,TLT,IWM", description="Comma-separated tickers"),
    min_confidence: float = Query(default=0.55, ge=0.5, le=0.95),
):
    """Run inference on all registered models and return combined signal.

    Combines predictions from SPY, QQQ, TLT, IWM into a single ensemble signal.
    Each ticker is weighted by its model confidence.

    Response:
    {
        "ensemble_signal": "BULLISH" | "BEARISH" | "MIXED",
        "ensemble_confidence": 0.72,
        "n_models": 4,
        "n_bullish": 3,
        "n_bearish": 1,
        "tickers": {
            "SPY": {"prediction": "UP", "confidence": 0.68, "probabilities": {...}},
            "QQQ": {"prediction": "UP", "confidence": 0.71, "probabilities": {...}},
            ...
        },
        "computed_at": "2026-05-24T..."
    }
    """
    from services.ml import DegenerateModelError
    from services.ml.inference import MODEL_REGISTRY, inference_engine

    ticker_list = [t.strip().upper() for t in tickers.split(",")]
    results = {}
    errors = []

    for ticker in ticker_list:
        if ticker not in MODEL_REGISTRY:
            errors.append(f"{ticker}: not registered")
            continue
        try:
            pred = await inference_engine.predict(ticker)
            results[ticker] = {
                "prediction": "UP" if pred.prediction == 1 else "DOWN",
                "confidence": round(pred.confidence, 4),
                "probabilities": {
                    "down": round(pred.probabilities[0], 4),
                    "up": round(pred.probabilities[1], 4),
                },
                "model_id": pred.model_id,
                "data_age_sec": round(pred.data_age_sec, 1),
            }
        except DegenerateModelError as e:
            errors.append(f"{ticker}: {e}")
        except Exception as e:
            errors.append(f"{ticker}: {type(e).__name__}: {e}")

    # Compute ensemble signal
    n_models = len(results)
    n_bullish = sum(1 for r in results.values() if r["prediction"] == "UP")
    n_bearish = n_models - n_bullish

    if n_models == 0:
        ensemble_signal = "NO_DATA"
        ensemble_confidence = 0.0
    elif n_bullish > n_bearish:
        ensemble_signal = "BULLISH"
        # Average confidence of bullish models
        bullish_confs = [r["confidence"] for r in results.values() if r["prediction"] == "UP"]
        ensemble_confidence = sum(bullish_confs) / len(bullish_confs) if bullish_confs else 0.5
    elif n_bearish > n_bullish:
        ensemble_signal = "BEARISH"
        bearish_confs = [r["confidence"] for r in results.values() if r["prediction"] == "DOWN"]
        ensemble_confidence = sum(bearish_confs) / len(bearish_confs) if bearish_confs else 0.5
    else:
        ensemble_signal = "MIXED"
        ensemble_confidence = 0.5

    from datetime import datetime, timezone
    return {
        "ensemble_signal": ensemble_signal,
        "ensemble_confidence": round(ensemble_confidence, 4),
        "n_models": n_models,
        "n_bullish": n_bullish,
        "n_bearish": n_bearish,
        "tickers": results,
        "errors": errors if errors else None,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/train")
async def trigger_training(
    ticker: str = Query(default="SPY"),
    days: int = Query(default=126, ge=30, le=500),
    n_splits: int = Query(default=5, ge=2, le=10),
):
    """Trigger model retraining on latest data.

    Runs asynchronously — returns immediately with a job ID.
    """
    import uuid
    job_id = str(uuid.uuid4())[:8]

    # Run training in background (deferred import to avoid circular dep)
    from server import _background_tasks, _logged_task
    _t = asyncio.create_task(
        _logged_task(
            _run_training_job(job_id, ticker, days, n_splits),
            f"train:{ticker}:{job_id}",
        )
    )
    _background_tasks.add(_t)
    _t.add_done_callback(_background_tasks.discard)

    return {
        "status": "started",
        "job_id": job_id,
        "ticker": ticker.upper(),
        "days": days,
        "n_splits": n_splits,
    }


async def _run_training_job(job_id: str, ticker: str, days: int, n_splits: int):
    """Background training job."""
    logger.info(f"Training job {job_id}: starting for {ticker}")
    try:
        from datetime import datetime

        from scripts.train_spy_ml import (
            build_dataset,
            fetch_options_chain_on_date,
            fetch_spot_history,
            save_model,
            train_walk_forward,
        )

        price_df = fetch_spot_history(ticker, days)
        live_chain = None
        try:
            live_chain = fetch_options_chain_on_date(ticker, datetime.now())
        except Exception as e:
            logger.warning(f"Training job {job_id}: failed to fetch live chain for {ticker}: {e}")

        X, y, feature_names, timestamps = build_dataset(price_df, live_chain, days_back=days)
        result, model, scaler, final_features = train_walk_forward(
            X, y, feature_names, timestamps, n_splits=n_splits, ticker=ticker,
        )

        if result.get("status") == "trained":
            model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
            save_model(model, scaler, final_features, result, model_dir, ticker)
            logger.info(f"Training job {job_id}: complete. Sharpe={result.get('model_sharpe')}")
        else:
            logger.warning(f"Training job {job_id}: failed - {result}")

    except Exception as e:
        logger.error(f"Training job {job_id}: error - {e}")


@router.get("/model-info/{ticker}")
async def model_info(ticker: str):
    """Get information about the trained model for a ticker."""
    ticker = ticker.upper()
    model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
    meta_path = os.path.join(model_dir, f"meta_{ticker}.json")

    import joblib
    model_path = os.path.join(model_dir, f"price_model_{ticker}.joblib")

    if not os.path.exists(meta_path):
        raise HTTPException(404, f"No model info for {ticker}")

    with open(meta_path) as f:
        meta = json.load(f)

    model = joblib.load(model_path)

    return {
        "ticker": ticker,
        "model_type": type(model).__name__,
        "n_features": len(meta.get("feature_names", [])),
        "feature_names": meta.get("feature_names", []),
        "top_features": meta.get("top_features", {}),
        "metrics": meta.get("metrics", {}),
        "trained_at": meta.get("trained_at"),
        "model_size_mb": round(os.path.getsize(model_path) / 1024 / 1024, 2),
    }
