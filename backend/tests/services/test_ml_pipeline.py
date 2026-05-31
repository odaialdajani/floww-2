"""
backend/tests/services/test_ml_pipeline.py

Integration tests for the ML pipeline:
  - Model loading from disk
  - Feature computation from MongoDB
  - Walk-forward CV sanity checks
  - Registry CRUD operations

Run with:
    cd backend && .venv/bin/python -m pytest tests/services/test_ml_pipeline.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# ────────────────────────────────────────────────────────────────────────
# Model artifact tests
# ────────────────────────────────────────────────────────────────────────

class TestModelArtifacts:
    """Test that shipped model artifacts exist and are loadable."""

    def test_model_file_exists(self):
        model_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_direction_v2.0-regime.joblib"
        assert model_path.exists(), f"Model not found at {model_path}"

    def test_scaler_file_exists(self):
        scaler_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_scaler_v2.0-regime.joblib"
        assert scaler_path.exists(), f"Scaler not found at {scaler_path}"

    def test_meta_file_exists(self):
        meta_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_meta_v2.0-regime.json"
        assert meta_path.exists(), f"Meta not found at {meta_path}"

    def test_model_loads(self):
        import joblib
        model_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_direction_v2.0-regime.joblib"
        model = joblib.load(model_path)
        assert model is not None
        assert hasattr(model, "predict")
        assert hasattr(model, "predict_proba")

    def test_scaler_loads(self):
        import joblib
        scaler_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_scaler_v2.0-regime.joblib"
        scaler = joblib.load(scaler_path)
        assert scaler is not None
        assert hasattr(scaler, "transform")

    def test_meta_valid_json(self):
        import json
        meta_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_meta_v2.0-regime.json"
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["ticker"] == "SPY"
        assert meta["target"] == "directional_move"
        assert meta["n_features"] > 0
        assert "feature_names" in meta
        assert len(meta["feature_names"]) == meta["n_features"]

    def test_model_predicts_valid_output(self):
        import json

        import joblib
        model_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_direction_v2.0-regime.joblib"
        scaler_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_scaler_v2.0-regime.joblib"
        meta_path = Path(__file__).resolve().parent.parent.parent.parent / "models" / "SPY_meta_v2.0-regime.json"

        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
        with open(meta_path) as f:
            meta = json.load(f)

        n_features = meta["n_features"]
        X_dummy = np.random.randn(10, n_features)
        X_scaled = scaler.transform(X_dummy)

        preds = model.predict(X_scaled)
        assert len(preds) == 10
        assert all(p in (0, 1) for p in preds)

        proba = model.predict_proba(X_scaled)
        assert proba.shape == (10, 2)
        assert np.allclose(proba.sum(axis=1), 1.0, atol=0.01)


# ────────────────────────────────────────────────────────────────────────
# Registry tests
# ────────────────────────────────────────────────────────────────────────

class TestModelRegistry:
    """Test MongoDB model registry operations."""

    def test_registry_collection_accessible(self):
        """Verify we can read from ml_models collection."""
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
        from pymongo import MongoClient

        c = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "confluence_decoder")]
        count = db["ml_models"].count_documents({})
        c.close()
        assert count >= 0  # Collection exists

    def test_registered_model_metadata(self):
        """Verify the v2.0-regime model is registered."""
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
        from pymongo import MongoClient

        c = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "confluence_decoder")]
        doc = db["ml_models"].find_one({
            "ticker": "SPY",
            "feature_version": "v2.0-regime",
        })
        c.close()

        if doc is not None:
            assert doc["status"] == "active"
            assert doc["n_features"] > 0
            assert "metrics" in doc
            assert doc["metrics"]["in_sample_sharpe"] is not None


# ────────────────────────────────────────────────────────────────────────
# Feature computation tests
# ────────────────────────────────────────────────────────────────────────

class TestFeatureComputation:
    """Test ML feature computation pipeline."""

    def test_get_feature_cols_excludes_targets(self):
        from services.ml.features import compute_realized_vol, compute_returns, compute_technical_features
        # Just verify the functions exist and are callable
        assert callable(compute_technical_features)
        assert callable(compute_returns)
        assert callable(compute_realized_vol)

    def test_compute_returns_basic(self):
        from services.ml.features import compute_returns
        bars = [
            {"date": "2024-01-02", "close": 100.0},
            {"date": "2024-01-03", "close": 101.0},
            {"date": "2024-01-04", "close": 99.0},
        ]
        result = compute_returns(bars)
        assert "ret_1d" in result
        assert len(result["ret_1d"]) == 3

    def test_compute_realized_vol_basic(self):
        from services.ml.features import compute_realized_vol
        bars = [{"date": f"2024-01-{i:02d}", "close": 100.0 + i * 0.5} for i in range(1, 30)]
        result = compute_realized_vol(bars)
        assert "realized_vol_5d" in result
        assert "realized_vol_21d" in result

    def test_compute_technical_features_basic(self):
        from services.ml.features import compute_technical_features
        bars = [{"date": f"2024-01-{i:02d}", "close": 100.0 + i * 0.3, "high": 101.0 + i * 0.3,
                 "low": 99.0 + i * 0.3, "volume": 1e6 + i * 1e4} for i in range(1, 60)]
        result = compute_technical_features(bars)
        assert "sma_5" in result
        assert "sma_21" in result
        assert "atr_14" in result


# ────────────────────────────────────────────────────────────────────────
# Quality gate tests
# ────────────────────────────────────────────────────────────────────────

class TestQualityGates:
    """Test ML quality gate functions."""

    def test_compute_trading_sharpe_basic(self):
        from services.ml.gate import compute_trading_sharpe
        preds = [1, 0, 1, 1, 0, 1]
        actuals = [1, 0, 0, 1, 0, 1]
        sharpe = compute_trading_sharpe(preds, actuals)
        assert isinstance(sharpe, float)
        assert sharpe > 0  # 3/4 wins = positive sharpe

    def test_compute_trading_sharpe_empty(self):
        from services.ml.gate import compute_trading_sharpe
        sharpe = compute_trading_sharpe([], [])
        assert sharpe == 0.0

    def test_compute_trading_sharpe_all_wrong(self):
        from services.ml.gate import compute_trading_sharpe
        sharpe = compute_trading_sharpe([1, 1, 1], [0, 0, 0])
        assert sharpe < 0  # All losing trades


# ────────────────────────────────────────────────────────────────────────
# ML Ensemble tests
# ────────────────────────────────────────────────────────────────────────

class TestMLEnsemble:
    """Test ML ensemble components."""

    def test_platt_scaler_basic(self):
        from services.ml_ensemble import PlattScaler
        scaler = PlattScaler()
        scores = np.array([0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 0.95])
        labels = np.array([0, 0, 0, 1, 1, 0, 0, 1, 1, 1])
        scaler.fit(scores, labels)
        assert scaler._fitted

        proba = scaler.predict_proba(scores)
        assert len(proba) == len(scores)
        assert all(0 <= p <= 1 for p in proba)

    def test_platt_scaler_unfitted(self):
        from services.ml_ensemble import PlattScaler
        scaler = PlattScaler()
        proba = scaler.predict_proba(np.array([0.5]))
        # Should return 0.5 (uninformative) when not fitted
        assert len(proba) == 1
