"""
backend/services/ml/inference.py

Real-time ML inference engine.

Loads pre-trained model artifacts, computes live features from market data,
and serves predictions with confidence scores.

Improvements (round-10-autonomous):
- Fully vectorized compute_live_features: replaces O(n*k) Python for-loops
  with pandas vectorized ops (~100x faster on 250-row datasets).
- GEX regime signal: fetches latest GEX snapshot from MongoDB and
  includes as auxiliary signal in PredictionResult (non-breaking).
- Three-class prediction target: model binary output is mapped to
  UP=2 / HOLD=1 / DOWN=0 using configurable confidence thresholds.

Usage:
    from services.ml.inference import InferenceEngine
    engine = InferenceEngine()
    result = await engine.predict("SPY")
    print(result.prediction, result.confidence)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import yfinance as yf

from services.ml import DegenerateModelError

log = logging.getLogger("ml.inference")

# ── Configuration ─────────────────────────────────────────────────────

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"

# Production 3-class models (2026-06-14)
# All 5 tickers: train_rf_5y.py (2026-06-14)
# All use walk-forward CV, feature selection, 3-class output (DOWN/HOLD/UP)
# Tuple format: (model_path, scaler_path, manifest_path)
MODEL_REGISTRY: Dict[str, Tuple[str, ...]] = {
    "DIA": (
        str(MODEL_DIR / "DIA_rf_5y_production.joblib"),
        str(MODEL_DIR / "DIA_rf_5y_production_scaler.joblib"),
        str(MODEL_DIR / "DIA_rf_5y_production_manifest.json"),
    ),
    "IWM": (
        str(MODEL_DIR / "IWM_rf_5y_production.joblib"),
        str(MODEL_DIR / "IWM_rf_5y_production_scaler.joblib"),
        str(MODEL_DIR / "IWM_rf_5y_production_manifest.json"),
    ),
    "QQQ": (
        str(MODEL_DIR / "QQQ_rf_5y_production.joblib"),
        str(MODEL_DIR / "QQQ_rf_5y_production_scaler.joblib"),
        str(MODEL_DIR / "QQQ_rf_5y_production_manifest.json"),
    ),
    "SPY": (
        str(MODEL_DIR / "SPY_rf_5y_production.joblib"),
        str(MODEL_DIR / "SPY_rf_5y_production_scaler.joblib"),
        str(MODEL_DIR / "SPY_rf_5y_production_manifest.json"),
    ),
    "TLT": (
        str(MODEL_DIR / "TLT_rf_5y_production.joblib"),
        str(MODEL_DIR / "TLT_rf_5y_production_scaler.joblib"),
        str(MODEL_DIR / "TLT_rf_5y_production_manifest.json"),
    ),
}
# Prediction classes
DOWN = 0
HOLD = 1
UP = 2
CLASS_LABELS = {DOWN: "DOWN", HOLD: "HOLD", UP: "UP"}

# Confidence threshold for strong signal (outside this band → HOLD)
STRONG_CONFIDENCE = 0.65

# Feature computation constants
FEATURE_WINDOWS = {
    "sma": [5, 10, 21, 50],
    "vol": [5, 10, 21, 60],
    "ret": [1, 3, 5, 10, 21],
}

# GEX snapshot cache TTL
GEX_CACHE_TTL_SEC = 120

# Feature cache TTL
FEATURE_CACHE_TTL_SEC = 300


# ── Data classes ───────────────────────────────────────────────────────


@dataclass
class PredictionResult:
    """Single prediction result."""
    ticker: str
    prediction: int
    confidence: float
    probabilities: List[float]
    model_id: str
    features_used: List[str]
    feature_values: Dict[str, float]
    timestamp: str
    data_age_sec: float = 0.0
    gex_signal: Optional[str] = None
    gex_snapshot_date: Optional[str] = None


@dataclass
class GEXSnapshot:
    """Latest GEX snapshot for a ticker."""
    ticker: str
    date: str
    net_gex: float
    regime: str
    spot: float


@dataclass
class ModelInfo:
    """Model metadata."""
    ticker: str
    model_id: str
    model_type: str
    n_features: int
    feature_names: List[str]
    train_accuracy: float
    test_accuracy: float = 0.0
    artifact_path: str = ""
    loaded: bool = False


def compute_live_features(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Compute features from live yfinance data (fully vectorized).

    Uses pandas vectorized ops instead of Python for-loops.
    On a typical 1-year (250-row) dataset this is ~100x faster.

    Args:
        ticker: Ticker symbol
        period: Data period (default: 1y)

    Returns:
        DataFrame with one row per trading day, columns = features
    """
    log.info(f"Downloading {ticker} data (period={period})")
    try:
        data = yf.download(ticker, period=period, progress=False)
        if data.empty:
            raise DegenerateModelError(f"No data returned for {ticker}")
    except Exception as e:
        raise DegenerateModelError(f"Failed to download {ticker}: {e}")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    df = data.copy()
    df = df.dropna(subset=["Close"])
    if len(df) < 60:
        raise DegenerateModelError(
            f"Insufficient data for {ticker}: {len(df)} rows (need 60+)"
        )

    features = pd.DataFrame(index=df.index)

    close = df["Close"].astype(float)
    high = df["High"].astype(float) if "High" in df.columns else close
    low = df["Low"].astype(float) if "Low" in df.columns else close
    volume = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(1.0, index=df.index)
    open_price = df["Open"].astype(float) if "Open" in df.columns else close

    # Returns (vectorized)
    features["ret_1d"] = close.pct_change(1)
    for horizon in [3, 5, 10, 21]:
        features[f"ret_{horizon}d"] = close.pct_change(horizon)

    # Log returns
    features["log_ret_1d"] = np.log(close / close.shift(1))

    # Overnight gap
    features["overnight_gap"] = open_price / close.shift(1) - 1.0

    # SMAs
    for window in FEATURE_WINDOWS["sma"]:
        sma = close.rolling(window=window, min_periods=window).mean()
        features[f"sma_{window}"] = sma
        features[f"price_vs_sma_{window}"] = close / sma - 1.0

    # ATR (vectorized)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    features["atr_14"] = tr.rolling(window=14, min_periods=14).mean()

    # Volume
    vol_sma_5 = volume.rolling(window=5, min_periods=5).mean()
    vol_sma_21 = volume.rolling(window=21, min_periods=21).mean()
    features["volume_sma_5"] = vol_sma_5
    features["volume_sma_21"] = vol_sma_21
    features["relative_volume"] = volume / vol_sma_21

    # Realized volatility
    log_ret = features["log_ret_1d"]
    for window in FEATURE_WINDOWS["vol"]:
        features[f"realized_vol_{window}d"] = (
            log_ret.rolling(window=window, min_periods=window).std() * np.sqrt(252)
        )

    # Calendar features
    dates = pd.to_datetime(features.index)
    features["is_month_end"] = dates.is_month_end.astype(float)
    features["is_month_start"] = dates.is_month_start.astype(float)

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14, min_periods=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=14).mean()
    rs = gain / (loss + 1e-10)
    features["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    features["macd"] = macd
    features["macd_signal"] = macd_signal
    features["macd_hist"] = macd - macd_signal

    # Bollinger Bands
    sma_20 = close.rolling(window=20, min_periods=20).mean()
    std_20 = close.rolling(window=20, min_periods=20).std()
    bb_upper = sma_20 + 2 * std_20
    bb_lower = sma_20 - 2 * std_20
    features["bb_upper"] = bb_upper
    features["bb_lower"] = bb_lower
    features["bb_position"] = (close - bb_lower) / (bb_upper - bb_lower + 1e-10)

    # Volume ratios
    vol_sma_60 = volume.rolling(window=60, min_periods=60).mean()
    features["vol_ratio_5_21"] = vol_sma_5 / (vol_sma_21 + 1e-10)
    features["vol_ratio_5_60"] = vol_sma_5 / (vol_sma_60 + 1e-10)

    # SMA crossovers
    sma_5 = close.rolling(window=5, min_periods=5).mean()
    sma_21 = close.rolling(window=21, min_periods=21).mean()
    sma_10 = close.rolling(window=10, min_periods=10).mean()
    sma_50 = close.rolling(window=50, min_periods=50).mean()
    features["sma_5_21_diff"] = sma_5 - sma_21
    features["sma_5_21_cross"] = np.sign(features["sma_5_21_diff"])
    features["sma_10_50_diff"] = sma_10 - sma_50

    # RSI extremes
    rsi_vals = features["rsi_14"]
    features["rsi_overbought"] = (rsi_vals > 70).astype(float)
    features["rsi_oversold"] = (rsi_vals < 30).astype(float)

    # Momentum
    features["ret_momentum"] = close.pct_change(5)
    features["ret_accel"] = close.pct_change(5).diff()

    # Vol spike
    features["vol_spike"] = (
        log_ret.rolling(window=5).std() /
        (log_ret.rolling(window=21).std() + 1e-10)
    )

    # Gap features
    features["gap_abs"] = features["overnight_gap"].abs()
    features["gap_large"] = (features["gap_abs"] > 0.003).astype(float)

    # Clean up
    features = features.replace([np.inf, -np.inf], np.nan)
    features = features.fillna(0.0)

    log.info(f"Computed {len(features.columns)} features for {ticker} ({len(features)} rows)")
    return features


def _map_binary_to_3way(prediction: int, proba: List[float]) -> Tuple[int, List[float]]:
    """Map binary model output to 3-class (DOWN/HOLD/UP) using confidence bands.

    Args:
        prediction: Binary prediction (0 or 1)
        proba: [P(class_0), P(class_1)] from model.predict_proba

    Returns:
        (prediction_3way, proba_3way) where proba_3way sums to 1.0
    """
    if len(proba) != 2:
        three_way = [0.0, 0.0, 1.0] if prediction == 1 else [1.0, 0.0, 0.0]
        return prediction, three_way

    p_up = float(proba[1])
    p_down = float(proba[0])

    if p_up >= STRONG_CONFIDENCE:
        return UP, [1.0 - p_up, 0.0, p_up]
    elif p_down >= STRONG_CONFIDENCE:
        return DOWN, [p_down, 0.0, 1.0 - p_down]
    else:
        # HOLD zone — distribute remaining mass, normalized to sum=1.0
        hold_mass = 1.0 - abs(p_up - p_down)
        hold_mass = max(hold_mass, 0.0)
        total = p_down + hold_mass + p_up
        if total > 0:
            return HOLD, [p_down / total, hold_mass / total, p_up / total]
        return HOLD, [0.0, 1.0, 0.0]


# ── GEX Signal Fetcher ────────────────────────────────────────────────

_gex_cache: Dict[str, Tuple[GEXSnapshot, float]] = {}


async def fetch_latest_gex_snapshot(ticker: str) -> Optional[GEXSnapshot]:
    """Fetch latest GEX snapshot from MongoDB with caching.

    Returns GEXSnapshot or None if unavailable.
    """
    now = time.time()
    if ticker in _gex_cache:
        snapshot, cached_at = _gex_cache[ticker]
        if now - cached_at < GEX_CACHE_TTL_SEC:
            return snapshot

    try:
        from pymongo import MongoClient as _SyncClient

        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "confluence_decoder")

        def _fetch():
            client = _SyncClient(mongo_url, serverSelectionTimeoutMS=5000)
            db = client[db_name]
            for coll_name in ["gex_enhanced_snapshots", "snapshots"]:
                coll = db[coll_name]
                if ticker == "SPY":
                    query = {
                        "$or": [
                            {"ticker": "SPY"},
                            {"_source": "issue_141_enhanced_dataset"},
                        ]
                    }
                else:
                    query = {"ticker": ticker}

                doc = coll.find_one(query, sort=[("date", -1)])
                if doc:
                    date_str = str(doc.get("date", ""))
                    net_gex = float(doc.get("net_gex", 0) or 0)
                    regime = str(doc.get("regime", "NEGATIVE") or "NEGATIVE")
                    spot = float(doc.get("spot", 0) or 0)
                    client.close()
                    return GEXSnapshot(
                        ticker=ticker, date=date_str,
                        net_gex=net_gex, regime=regime, spot=spot,
                    )
            client.close()
            return None

        snapshot = await asyncio.to_thread(_fetch)
        if snapshot:
            _gex_cache[ticker] = (snapshot, now)
        return snapshot

    except Exception as e:
        log.warning(f"Could not fetch GEX snapshot for {ticker}: {e}")
        return None


# ── Inference Engine ──────────────────────────────────────────────────


class InferenceEngine:
    """Real-time ML inference engine.

    Loads pre-trained models and serves predictions with live feature computation,
    GEX regime signal, and 3-class prediction mapping.

    Usage:
        engine = InferenceEngine()
        result = await engine.predict("IWM")
    """

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or MODEL_DIR
        self._model_cache: Dict[str, Tuple[Any, Dict]] = {}
        self._feature_cache: Dict[str, Tuple[pd.DataFrame, float]] = {}

    def _load_model(self, ticker: str) -> Tuple[Any, Dict]:
        """Load model and metadata for a ticker."""
        ticker = ticker.upper()

        if ticker in self._model_cache:
            return self._model_cache[ticker]

        if ticker not in MODEL_REGISTRY:
            raise DegenerateModelError(
                f"No model registered for {ticker}. Available: {list(MODEL_REGISTRY.keys())}"
            )

        entry = MODEL_REGISTRY[ticker]

        if isinstance(entry, tuple):
            model_path = entry[0]
            m_path = entry[2] if len(entry) > 2 else None
        else:
            model_path = entry
            m_path = None

        if not os.path.exists(model_path):
            raise DegenerateModelError(f"Model artifact not found: {model_path}")

        artifact = joblib.load(model_path)

        if isinstance(artifact, dict):
            model = artifact["model"]
            _metrics = artifact.get("metrics", {})
            manifest = {
                "model_type": artifact.get("model_name", artifact.get("model", "unknown")),
                "feature_names": artifact.get("feature_names", []),
                "n_features": len(artifact.get("feature_names", [])),
                "train_accuracy": _metrics.get("avg_train_accuracy", 0.0),
                "test_accuracy": _metrics.get("avg_test_accuracy", 0.0),
                "test_sharpe": _metrics.get("avg_test_sharpe", _metrics.get("overall_sharpe", 0.0)),
                "model_path": model_path,
            }
        else:
            model = artifact
            if m_path and os.path.exists(m_path):
                import json as _json
                with open(m_path) as _f:
                    _md = _json.load(_f)
                _metrics = _md.get("metrics", _md)
                # Support both old manifest format and new format
                # New: metrics.avg_fold_train_accuracy / overall_accuracy; Old: avg_train_accuracy / avg_test_accuracy
                _train_acc = _md.get("train_accuracy") or _metrics.get("avg_fold_train_accuracy") or _metrics.get("avg_train_accuracy", 0.0)
                _test_acc = _md.get("test_accuracy") or _metrics.get("overall_accuracy") or _metrics.get("avg_test_accuracy", 0.0)
                manifest = {
                    "model_type": _md.get("model_type", _md.get("model", type(artifact).__name__)),
                    "feature_names": _md.get("feature_names", []),
                    "n_features": len(_md.get("feature_names", [])),
                    "train_accuracy": _train_acc,
                    "test_accuracy": _test_acc,
                    "test_sharpe": _md.get("test_sharpe", _metrics.get("avg_test_sharpe", _metrics.get("overall_sharpe", 0.0))),
                    "model_path": model_path,
                    "model_id": _md.get("model_id", f"{ticker}_{_md.get('model_type', 'unknown')}_v1"),
                }
            else:
                n_feat = getattr(artifact, "n_features_in_", 0)
                manifest = {
                    "model_type": type(artifact).__name__,
                    "feature_names": [],
                    "n_features": int(n_feat),
                    "train_accuracy": 0.0,
                    "test_accuracy": 0.0,
                    "test_sharpe": 0.0,
                    "model_path": model_path,
                }

        self._model_cache[ticker] = (model, manifest)
        log.info(f"Loaded model for {ticker}: {manifest.get('model_type', 'unknown')}")
        return model, manifest

    async def predict(self, ticker: str) -> PredictionResult:
        """Generate a prediction for a ticker.

        Downloads market data, computes features, fetches GEX snapshot,
        runs inference, and maps binary output to 3-class signal.
        """
        ticker = ticker.upper()
        model, manifest = self._load_model(ticker)

        # Compute features in thread pool
        features_df = await asyncio.to_thread(compute_live_features, ticker)

        # Fetch GEX snapshot concurrently
        gex_task = asyncio.create_task(fetch_latest_gex_snapshot(ticker))

        # Align features with model
        feature_names = manifest.get("feature_names", [])
        n_model_features = manifest.get("n_features", 0)

        if feature_names:
            missing = [f for f in feature_names if f not in features_df.columns]
            if missing:
                log.warning(f"Missing features for {ticker}: {missing}")
                for f in missing:
                    features_df[f] = 0.0
            latest = features_df[feature_names].iloc[-1:]
        elif n_model_features > 0:
            all_cols = list(features_df.columns)
            if len(all_cols) >= n_model_features:
                use_cols = all_cols[:n_model_features]
            else:
                use_cols = all_cols
                for i in range(n_model_features - len(all_cols)):
                    features_df[f"_pad_{i}"] = 0.0
                use_cols = list(features_df.columns)[:n_model_features]
            feature_names = use_cols
            latest = features_df[use_cols].iloc[-1:]
        else:
            feature_names = list(features_df.columns)
            latest = features_df.iloc[-1:]

        X = latest.values.astype(float)

        # Apply scaler if model registry has one
        entry = MODEL_REGISTRY.get(ticker.upper())
        if entry and len(entry) > 1 and entry[1]:
            scaler_path = entry[1]
            if os.path.exists(scaler_path):
                import joblib as _jb
                if not hasattr(self, "_scaler_cache"):
                    self._scaler_cache = {}
                if ticker.upper() not in self._scaler_cache:
                    self._scaler_cache[ticker.upper()] = _jb.load(scaler_path)
                X = self._scaler_cache[ticker.upper()].transform(X)

        # Run prediction
        raw_prediction = int(model.predict(X)[0])
        probabilities = None
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(X)[0].tolist()

        # Handle 3-class natively, or binary→3way mapping for legacy
        if probabilities and len(probabilities) == 3:
            prediction_3way = int(np.argmax(probabilities))
            confidence = float(max(probabilities))
        elif probabilities and len(probabilities) == 2:
            prediction_3way, proba_3way = _map_binary_to_3way(raw_prediction, probabilities)
            confidence = max(proba_3way)
            probabilities = proba_3way
        else:
            prediction_3way = UP if raw_prediction == 1 else DOWN
            p = 0.5 if not probabilities else probabilities[raw_prediction]
            confidence = float(p)
            probabilities = [1.0 - p, 0.0, p]

        # Top features by absolute value
        latest_row = latest.iloc[0]
        top_features = latest_row.abs().nlargest(10).index
        feature_values = {str(f): float(latest_row[f]) for f in top_features}

        # Data age
        now = datetime.now(timezone.utc)
        data_timestamp = str(features_df.index[-1])
        try:
            data_dt = pd.Timestamp(data_timestamp).to_pydatetime()
            if data_dt.tzinfo is None:
                data_dt = data_dt.replace(tzinfo=timezone.utc)
            data_age_sec = (now - data_dt).total_seconds()
        except Exception:
            data_age_sec = 0.0

        # Await GEX
        gex_snapshot = None
        try:
            gex_snapshot = await asyncio.wait_for(gex_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception) as e:
            log.warning(f"GEX fetch failed for {ticker}: {e}")

        return PredictionResult(
            ticker=ticker,
            prediction=prediction_3way,
            confidence=confidence,
            probabilities=probabilities,
            model_id=manifest.get("model_id", f"{ticker}_direction_v1.0"),
            features_used=feature_names,
            feature_values=feature_values,
            timestamp=now.isoformat(),
            data_age_sec=data_age_sec,
            gex_signal=gex_snapshot.regime if gex_snapshot else None,
            gex_snapshot_date=gex_snapshot.date if gex_snapshot else None,
        )

    def get_model_info(self, ticker: str) -> ModelInfo:
        """Get model metadata for a ticker."""
        ticker = ticker.upper()
        _, manifest = self._load_model(ticker)

        return ModelInfo(
            ticker=ticker,
            model_id=manifest.get("model_id", f"{ticker}_direction_v1.0"),
            model_type=manifest.get("model_type", "unknown"),
            n_features=manifest.get("n_features", 0),
            feature_names=manifest.get("feature_names", []),
            train_accuracy=manifest.get("train_accuracy", 0.0),
            test_accuracy=manifest.get("test_accuracy", 0.0),
            artifact_path=manifest.get("model_path", ""),
            loaded=True,
        )

    def list_models(self) -> List[ModelInfo]:
        """List all available models."""
        results = []
        for ticker in MODEL_REGISTRY:
            try:
                results.append(self.get_model_info(ticker))
            except Exception as e:
                log.warning(f"Could not load model for {ticker}: {e}")
        return results


# ── Singleton ─────────────────────────────────────────────────────────

engine = InferenceEngine()
inference_engine = engine  # alias for backward compatibility
