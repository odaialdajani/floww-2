"""
ML Training Pipeline for Confluence Decoder.

Trains models on historical GEX data to predict:
- Regime changes (positive → negative gamma)
- Price movement direction
- Volatility expansion/contraction

Uses scikit-learn and optionally PyTorch (via unsloth for fine-tuning).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def extract_features_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, float]:
    """Extract ML features from a GEX snapshot."""
    features = {}

    # Basic features
    features["spot"] = float(snapshot.get("spot", 0))
    features["total_gex"] = float(snapshot.get("total_gex", 0))
    features["net_gex"] = float(snapshot.get("net_gex", 0))

    # King strike features
    king = snapshot.get("king", {})
    features["king_strike"] = float(king.get("strike", 0)) if king else 0
    features["king_gex"] = float(king.get("gex", 0)) if king else 0

    # Floor/ceiling features
    floors = snapshot.get("floors", [])
    ceilings = snapshot.get("ceilings", [])
    features["top_floor_strike"] = float(floors[0].get("strike", 0)) if floors else 0
    features["top_floor_gex"] = float(floors[0].get("gex", 0)) if floors else 0
    features["top_ceiling_strike"] = float(ceilings[0].get("strike", 0)) if ceilings else 0
    features["top_ceiling_gex"] = float(ceilings[0].get("gex", 0)) if ceilings else 0

    # Strike distribution features
    strikes_compact = snapshot.get("strikes_compact", [])
    if strikes_compact:
        gex_values = [float(s.get("gex", 0)) for s in strikes_compact]
        features["gex_mean"] = np.mean(gex_values)
        features["gex_std"] = np.std(gex_values)
        features["gex_skew"] = float(np.percentile(gex_values, 75) - np.percentile(gex_values, 25))
        features["num_strikes"] = len(strikes_compact)
    else:
        features["gex_mean"] = 0
        features["gex_std"] = 0
        features["gex_skew"] = 0
        features["num_strikes"] = 0

    # Regime encoding
    regime = snapshot.get("regime", "unknown")
    features["regime_positive"] = 1.0 if regime == "POSITIVE" else 0.0
    features["regime_negative"] = 1.0 if regime == "NEGATIVE" else 0.0

    return features


def prepare_training_data(
    snapshots: List[Dict[str, Any]],
    lookahead: int = 1,
) -> Tuple[np.ndarray, np.ndarray]:
    """Prepare training data from snapshots.
    
    Features: current GEX state
    Labels: regime change (1 if regime flipped, 0 otherwise)
    """
    if len(snapshots) < 2:
        return np.array([]), np.array([])

    # Sort by timestamp
    sorted_snaps = sorted(snapshots, key=lambda s: s.get("ts", ""))

    X = []
    y = []

    for i in range(len(sorted_snaps) - lookahead):
        current = sorted_snaps[i]
        future = sorted_snaps[i + lookahead]

        features = extract_features_from_snapshot(current)
        feature_vector = list(features.values())

        # Label: did regime change?
        current_regime = current.get("regime", "unknown")
        future_regime = future.get("regime", "unknown")
        label = 1.0 if current_regime != future_regime else 0.0

        X.append(feature_vector)
        y.append(label)

    return np.array(X), np.array(y)


async def train_regime_prediction_model(
    ticker: str = "SPY",
    min_samples: int = 10,
) -> Dict[str, Any]:
    """Train a regime prediction model on historical GEX data."""
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient

    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]

    # Fetch snapshots
    cursor = db.snapshots.find({"ticker": ticker}).sort("ts", 1)
    snapshots = await cursor.to_list(length=10000)

    if len(snapshots) < min_samples:
        return {
            "status": "insufficient_data",
            "samples": len(snapshots),
            "required": min_samples,
        }

    # Prepare data
    X, y = prepare_training_data(snapshots)

    if len(X) == 0:
        return {"status": "error", "message": "No training data generated"}

    # Split train/test
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Train model
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        random_state=42,
    )
    model.fit(X_train_scaled, y_train)

    # Evaluate
    y_pred = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred)

    # Feature importance
    feature_names = list(extract_features_from_snapshot(snapshots[0]).keys())
    importance = dict(zip(feature_names, model.feature_importances_.tolist()))
    importance = dict(sorted(importance.items(), key=lambda x: abs(x[1]), reverse=True))

    # Save model
    import joblib
    model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    os.makedirs(model_dir, exist_ok=True)

    model_path = os.path.join(model_dir, f"regime_model_{ticker}.joblib")
    scaler_path = os.path.join(model_dir, f"regime_scaler_{ticker}.joblib")

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    client.close()

    result = {
        "status": "trained",
        "ticker": ticker,
        "samples": len(snapshots),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "accuracy": round(accuracy, 4),
        "feature_importance": importance,
        "model_path": model_path,
        "scaler_path": scaler_path,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"Model trained: accuracy={accuracy:.4f}, samples={len(snapshots)}")
    return result


async def predict_regime(
    ticker: str = "SPY",
    current_features: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Predict regime using trained model."""
    import joblib

    model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    model_path = os.path.join(model_dir, f"regime_model_{ticker}.joblib")
    scaler_path = os.path.join(model_dir, f"regime_scaler_{ticker}.joblib")

    if not os.path.exists(model_path):
        return {"status": "no_model", "message": f"No trained model for {ticker}"}

    assert "_quarantine" not in str(model_path), f"refused to load quarantined model: {model_path}"
    model = joblib.load(model_path)
    assert "_quarantine" not in str(scaler_path), f"refused to load quarantined scaler: {scaler_path}"
    scaler = joblib.load(scaler_path)

    if current_features is None:
        # Fetch latest snapshot
        from dotenv import load_dotenv
        from motor.motor_asyncio import AsyncIOMotorClient
        load_dotenv()
        client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
        db = client[os.environ.get("DB_NAME", "confluence_decoder")]
        latest = await db.snapshots.find_one({"ticker": ticker}, sort=[("ts", -1)])
        client.close()

        if not latest:
            return {"status": "no_data", "message": f"No snapshots for {ticker}"}

        current_features = extract_features_from_snapshot(latest)

    feature_vector = np.array([list(current_features.values())])
    feature_scaled = scaler.transform(feature_vector)

    prediction = model.predict(feature_scaled)[0]
    probability = model.predict_proba(feature_scaled)[0]

    return {
        "status": "ok",
        "ticker": ticker,
        "prediction": "REGIME_CHANGE" if prediction == 1.0 else "STABLE",
        "confidence": round(float(max(probability)), 4),
        "probabilities": {
            "stable": round(float(probability[0]), 4),
            "regime_change": round(float(probability[1]), 4),
        },
        "features_used": list(current_features.keys()),
    }
