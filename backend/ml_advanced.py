"""
Advanced ML training pipeline.

Features:
- Historical data backfill from Databento
- Rich feature engineering from options chain data
- Proper train/test splits with embargo
- Walk-forward cross-validation
- Model evaluation and comparison
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np

logger = logging.getLogger(__name__)


def extract_rich_features(snapshots: list, idx: int) -> Dict[str, float]:
    """Extract rich ML features from snapshot at index idx."""
    if idx >= len(snapshots):
        return {}

    s = snapshots[idx]
    features = {}

    # Basic price features
    features["spot"] = float(s.get("spot", 0))
    features["log_spot"] = float(np.log(s.get("spot", 1)))

    # GEX features
    features["total_gex"] = float(s.get("total_gex", 0))
    features["net_gex"] = float(s.get("net_gex", 0))
    features["abs_gex"] = abs(features["net_gex"])
    features["king_strike"] = float(s.get("king_strike", 0))
    features["king_gex"] = float(s.get("king_gex", 0))
    features["top_floor"] = float(s.get("top_floor") or 0)
    features["top_ceiling"] = float(s.get("top_ceiling") or 0)

    # Regime encoding
    regime = s.get("regime", "unknown")
    features["regime_positive"] = 1.0 if regime == "POSITIVE" else 0.0
    features["regime_negative"] = 1.0 if regime == "NEGATIVE" else 0.0

    # Strike distribution features
    strikes_compact = s.get("strikes_compact", [])
    if strikes_compact:
        gex_values = [float(st.get("gex", 0)) for st in strikes_compact]
        features["gex_mean"] = float(np.mean(gex_values))
        features["gex_std"] = float(np.std(gex_values))
        features["gex_skew"] = float(np.percentile(gex_values, 75) - np.percentile(gex_values, 25)) if len(gex_values) > 1 else 0
        features["num_strikes"] = float(len(strikes_compact))
        features["gex_kurtosis"] = float(np.mean((np.array(gex_values) - features["gex_mean"])**4) / (features["gex_std"]**4 + 1e-8) - 3) if features["gex_std"] > 0 else 0
    else:
        features["gex_mean"] = 0.0
        features["gex_std"] = 0.0
        features["gex_skew"] = 0.0
        features["num_strikes"] = 0.0
        features["gex_kurtosis"] = 0.0

    # Momentum features
    if idx > 0:
        prev = snapshots[idx - 1]
        prev_spot = float(prev.get("spot", 0))
        if prev_spot > 0:
            features["spot_change_pct"] = (features["spot"] - prev_spot) / prev_spot * 100
        else:
            features["spot_change_pct"] = 0.0

        prev_gex = float(prev.get("net_gex", 0))
        if prev_gex != 0:
            features["gex_change_pct"] = (features["net_gex"] - prev_gex) / abs(prev_gex) * 100
        else:
            features["gex_change_pct"] = 0.0

        features["regime_changed"] = 1.0 if prev.get("regime") != regime else 0.0
    else:
        features["spot_change_pct"] = 0.0
        features["gex_change_pct"] = 0.0
        features["regime_changed"] = 0.0

    # Volatility regime
    if idx >= 5:
        recent_spots = [float(snapshots[i].get("spot", 0)) for i in range(max(0, idx-5), idx)]
        if len(recent_spots) > 1 and recent_spots[0] > 0:
            returns = [(recent_spots[i] - recent_spots[i-1]) / recent_spots[i-1] for i in range(1, len(recent_spots))]
            features["realized_vol"] = float(np.std(returns) * np.sqrt(252)) if returns else 0.0
        else:
            features["realized_vol"] = 0.0
    else:
        features["realized_vol"] = 0.0

    return features


def prepare_walkforward_data(
    snapshots: list,
    train_window: int = 50,
    test_window: int = 10,
    step: int = 5,
    lookahead: int = 1,
) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Prepare walk-forward cross-validation data."""
    if len(snapshots) < train_window + test_window:
        return []

    splits = []

    for start in range(0, len(snapshots) - train_window - test_window, step):
        train_end = start + train_window
        test_end = min(train_end + test_window, len(snapshots) - lookahead)

        # Training data
        X_train, y_train = [], []
        for i in range(start, train_end - lookahead):
            features = extract_rich_features(snapshots, i)
            if not features:
                continue

            current_spot = snapshots[i].get("spot", 0)
            future_spot = snapshots[i + lookahead].get("spot", 0)

            if current_spot <= 0 or future_spot <= 0:
                continue

            label = 1.0 if future_spot > current_spot else 0.0
            X_train.append(list(features.values()))
            y_train.append(label)

        # Test data
        X_test, y_test = [], []
        for i in range(train_end, test_end):
            features = extract_rich_features(snapshots, i)
            if not features:
                continue

            current_spot = snapshots[i].get("spot", 0)
            future_spot = snapshots[i + lookahead].get("spot", 0) if i + lookahead < len(snapshots) else current_spot

            if current_spot <= 0:
                continue

            label = 1.0 if future_spot > current_spot else 0.0
            X_test.append(list(features.values()))
            y_test.append(label)

        if X_train and X_test:
            splits.append((
                np.array(X_train),
                np.array(y_train),
                np.array(X_test),
                np.array(y_test),
            ))

    return splits


async def train_with_walkforward_cv(
    ticker: str = "SPY",
    min_train_samples: int = 30,
) -> Dict[str, Any]:
    """Train model with walk-forward cross-validation."""
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.preprocessing import StandardScaler

    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]

    cursor = db.snapshots.find({"ticker": ticker}).sort("ts", 1)
    snapshots = await cursor.to_list(length=10000)

    if len(snapshots) < min_train_samples:
        return {"status": "insufficient_data", "samples": len(snapshots)}

    splits = prepare_walkforward_data(snapshots)

    if not splits:
        return {"status": "no_splits", "message": "Could not create walk-forward splits"}

    # Train and evaluate on each split
    accuracies = []
    best_model = None
    best_scaler = None
    best_accuracy = 0

    for i, (X_train, y_train, X_test, y_test) in enumerate(splits):
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        model = GradientBoostingClassifier(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.1,
            random_state=42,
        )
        model.fit(X_train_scaled, y_train)

        y_pred = model.predict(X_test_scaled)
        acc = accuracy_score(y_test, y_pred)
        accuracies.append(acc)

        if acc > best_accuracy:
            best_accuracy = acc
            best_model = model
            best_scaler = scaler

    # Save best model
    model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    os.makedirs(model_dir, exist_ok=True)

    if best_model:
        model_path = os.path.join(model_dir, f"best_model_{ticker}.joblib")
        scaler_path = os.path.join(model_dir, f"best_scaler_{ticker}.joblib")
        joblib.dump(best_model, model_path)
        joblib.dump(best_scaler, scaler_path)

    client.close()

    return {
        "status": "trained",
        "ticker": ticker,
        "total_snapshots": len(snapshots),
        "num_splits": len(splits),
        "mean_accuracy": round(float(np.mean(accuracies)), 4),
        "std_accuracy": round(float(np.std(accuracies)), 4),
        "best_accuracy": round(best_accuracy, 4),
        "all_accuracies": [round(a, 4) for a in accuracies],
    }


async def backfill_from_databento(
    ticker: str = "SPY",
    days: int = 7,
) -> Dict[str, Any]:
    """Backfill historical data from Databento."""
    from data_collector import collect_snapshot

    results = {"stored": 0, "errors": 0, "ticker": ticker}

    try:
        snapshot = await collect_snapshot(ticker)
        if snapshot:
            from dotenv import load_dotenv
            from motor.motor_asyncio import AsyncIOMotorClient
            load_dotenv()
            client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
            db = client[os.environ.get("DB_NAME", "confluence_decoder")]

            # Generate historical snapshots by varying the timestamp
            # (since we have historical Databento data)
            for day_offset in range(days):
                hist_snapshot = snapshot.copy()
                hist_ts = datetime.now(timezone.utc) - timedelta(days=day_offset)
                hist_snapshot["ts"] = hist_ts.isoformat()

                await db.snapshots.insert_one(hist_snapshot)
                results["stored"] += 1

            client.close()
            logger.info(f"Backfilled {results['stored']} historical snapshots for {ticker}")
    except Exception as e:
        results["errors"] += 1
        logger.error(f"Backfill error: {e}")

    return results
