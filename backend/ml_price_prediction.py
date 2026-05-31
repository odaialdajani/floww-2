"""
ML Model Training for Price Direction Prediction.

Predicts next-day price direction (up/down) based on:
- GEX regime features
- Options flow signals
- Technical indicators
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

import numpy as np

logger = logging.getLogger(__name__)


def extract_features(snapshots: list, idx: int) -> Dict[str, float]:
    """Extract features from a snapshot at index idx."""
    if idx >= len(snapshots):
        return {}

    s = snapshots[idx]
    features = {}

    # GEX features
    features["spot"] = float(s.get("spot", 0))
    features["total_gex"] = float(s.get("total_gex", 0))
    features["net_gex"] = float(s.get("net_gex", 0))
    features["king_strike"] = float(s.get("king_strike", 0))
    features["king_gex"] = float(s.get("king_gex", 0))
    features["top_floor"] = float(s.get("top_floor") or 0)
    features["top_ceiling"] = float(s.get("top_ceiling") or 0)

    # Regime encoding
    regime = s.get("regime", "unknown")
    features["regime_positive"] = 1.0 if regime == "POSITIVE" else 0.0
    features["regime_negative"] = 1.0 if regime == "NEGATIVE" else 0.0

    # Strike distribution
    strikes_compact = s.get("strikes_compact", [])
    if strikes_compact:
        gex_values = [float(st.get("gex", 0)) for st in strikes_compact]
        features["gex_mean"] = float(np.mean(gex_values))
        features["gex_std"] = float(np.std(gex_values))
        features["num_strikes"] = float(len(strikes_compact))
    else:
        features["gex_mean"] = 0.0
        features["gex_std"] = 0.0
        features["num_strikes"] = 0.0

    # Momentum features (if we have previous snapshots)
    if idx > 0:
        prev = snapshots[idx - 1]
        prev_spot = float(prev.get("spot", 0))
        if prev_spot > 0:
            features["spot_change_pct"] = (features["spot"] - prev_spot) / prev_spot * 100
        else:
            features["spot_change_pct"] = 0.0

        prev_gex = float(prev.get("total_gex", 0))
        if prev_gex != 0:
            features["gex_change_pct"] = (features["total_gex"] - prev_gex) / abs(prev_gex) * 100
        else:
            features["gex_change_pct"] = 0.0
    else:
        features["spot_change_pct"] = 0.0
        features["gex_change_pct"] = 0.0

    return features


async def train_price_direction_model(
    ticker: str = "SPY",
    min_samples: int = 20,
) -> Dict[str, Any]:
    """Train a price direction prediction model."""
    import joblib
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.preprocessing import StandardScaler

    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]

    # Get all snapshots for this ticker
    cursor = db.snapshots.find({"ticker": ticker}).sort("ts", 1)
    snapshots = await cursor.to_list(length=10000)

    if len(snapshots) < min_samples:
        return {
            "status": "insufficient_data",
            "samples": len(snapshots),
            "required": min_samples,
        }

    # Get price data for labels

    # Build training data
    X = []
    y = []

    for i in range(len(snapshots) - 1):
        features = extract_features(snapshots, i)
        if not features:
            continue

        # Label: did price go up in the next snapshot?
        current_spot = snapshots[i].get("spot", 0)
        next_spot = snapshots[i + 1].get("spot", 0)

        if current_spot <= 0 or next_spot <= 0:
            continue

        label = 1.0 if next_spot > current_spot else 0.0

        feature_vector = list(features.values())
        X.append(feature_vector)
        y.append(label)

    if len(X) < min_samples:
        return {
            "status": "insufficient_training_data",
            "samples": len(X),
            "required": min_samples,
        }

    X = np.array(X)
    y = np.array(y)

    # Check class balance
    unique, counts = np.unique(y, return_counts=True)
    class_dist = dict(zip(unique.tolist(), counts.tolist()))

    if len(unique) < 2:
        return {
            "status": "single_class",
            "message": f"Only one class found: {class_dist}",
        }

    # Split train/test
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model
    model = GradientBoostingClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        random_state=42,
    )
    model.fit(X_train_scaled, y_train)

    # Evaluate
    y_pred = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred)

    # Feature importance
    feature_names = list(extract_features(snapshots, 0).keys())
    importance_list = model.feature_importances_.tolist()
    importance = {feature_names[i]: importance_list[i] for i in range(min(len(feature_names), len(importance_list)))}
    importance = dict(sorted(importance.items(), key=lambda x: abs(x[1]), reverse=True))

    # Save model
    model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    os.makedirs(model_dir, exist_ok=True)

    model_path = os.path.join(model_dir, f"price_model_{ticker}.joblib")
    scaler_path = os.path.join(model_dir, f"price_scaler_{ticker}.joblib")

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    client.close()

    result = {
        "status": "trained",
        "ticker": ticker,
        "total_snapshots": len(snapshots),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "accuracy": round(accuracy, 4),
        "class_distribution": class_dist,
        "top_features": dict(list(importance.items())[:5]),
        "model_path": model_path,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"Price model trained for {ticker}: accuracy={accuracy:.4f}")
    return result


async def predict_price_direction(
    ticker: str = "SPY",
) -> Dict[str, Any]:
    """Predict price direction using trained model."""
    import joblib

    model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    model_path = os.path.join(model_dir, f"{ticker}_direction_v1.0.joblib")
    scaler_path = os.path.join(model_dir, f"{ticker}_scaler_v1.0.joblib")

    if not os.path.exists(model_path):
        return {"status": "no_model", "message": f"No trained model for {ticker}"}

    assert "_quarantine" not in str(model_path), f"refused to load quarantined model: {model_path}"
    model = joblib.load(model_path)
    assert "_quarantine" not in str(scaler_path), f"refused to load quarantined scaler: {scaler_path}"
    scaler = joblib.load(scaler_path)

    # Get latest snapshot
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient
    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]

    cursor = db.snapshots.find({"ticker": ticker}).sort("ts", -1).limit(2)
    latest = await cursor.to_list(length=2)
    client.close()

    if len(latest) < 1:
        return {"status": "no_data", "message": f"No snapshots for {ticker}"}

    # Extract features
    snapshots = list(reversed(latest))  # Oldest first
    features = extract_features(snapshots, len(snapshots) - 1)

    feature_vector = np.array([list(features.values())])
    feature_scaled = scaler.transform(feature_vector)

    prediction = model.predict(feature_scaled)[0]
    probability = model.predict_proba(feature_scaled)[0]

    return {
        "status": "ok",
        "ticker": ticker,
        "prediction": "UP" if prediction == 1.0 else "DOWN",
        "confidence": round(float(max(probability)), 4),
        "probabilities": {
            "down": round(float(probability[0]), 4),
            "up": round(float(probability[1]), 4),
        },
        "current_spot": features.get("spot", 0),
        "regime": "POSITIVE" if features.get("regime_positive", 0) == 1.0 else "NEGATIVE",
    }
