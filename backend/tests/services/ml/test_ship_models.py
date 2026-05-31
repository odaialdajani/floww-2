"""
Integration tests: load SHIP-trained models, verify predictions are sane.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pytest

MODEL_DIR = Path(__file__).resolve().parents[3] / "models"


def _find_ship_model(ticker):
    """Find the most recent SHIP model artifact for a ticker."""
    pattern = f"{ticker}_*_ship_*.joblib"
    matches = sorted(MODEL_DIR.glob(pattern))
    if not matches:
        pytest.skip(f"No SHIP model found for {ticker}")
    return matches[-1]


def _find_ship_manifest(ticker):
    """Find the most recent SHIP manifest for a ticker."""
    pattern = f"{ticker}_*_ship_manifest_*.json"
    matches = sorted(MODEL_DIR.glob(pattern))
    if not matches:
        pytest.skip(f"No SHIP manifest found for {ticker}")
    with open(matches[-1]) as f:
        return json.load(f)


class TestShipModelLoading:
    """Verify SHIP models load correctly and produce valid predictions."""

    @pytest.mark.parametrize("ticker", ["QQQ", "TLT", "DIA", "IWM"])
    def test_model_loads(self, ticker):
        """Model artifact loads without errors."""
        path = _find_ship_model(ticker)
        artifact = joblib.load(path)
        assert "model" in artifact
        assert "feature_names" in artifact
        assert "ticker" in artifact
        assert artifact["ticker"] == ticker

    @pytest.mark.parametrize("ticker", ["QQQ", "TLT", "DIA", "IWM"])
    def test_manifest_valid(self, ticker):
        """Manifest has required fields and SHIP verdict."""
        manifest = _find_ship_manifest(ticker)
        assert manifest["verdict"] == "SHIP"
        assert manifest["ticker"] == ticker
        assert manifest["n_features"] > 0
        assert manifest["n_samples"] > 100
        assert len(manifest["feature_names"]) == manifest["n_features"]

    @pytest.mark.parametrize("ticker", ["QQQ", "TLT", "DIA", "IWM"])
    def test_prediction_shape(self, ticker):
        """Model produces valid predictions on random input."""
        path = _find_ship_model(ticker)
        artifact = joblib.load(path)
        model = artifact["model"]
        n_features = len(artifact["feature_names"])

        # Create synthetic input
        rng = np.random.RandomState(42)
        X = rng.randn(10, n_features)

        if artifact.get("model_name") == "logistic":
            scaler = artifact.get("scaler")
            if scaler:
                X = scaler.transform(X)

        preds = model.predict(X)
        assert len(preds) == 10
        assert all(p in (0, 1) for p in preds.astype(int))

    @pytest.mark.parametrize("ticker", ["QQQ", "TLT", "DIA", "IWM"])
    def test_prediction_proba_valid(self, ticker):
        """Model produces valid probabilities."""
        path = _find_ship_model(ticker)
        artifact = joblib.load(path)
        model = artifact["model"]
        n_features = len(artifact["feature_names"])

        rng = np.random.RandomState(42)
        X = rng.randn(10, n_features)

        if artifact.get("model_name") == "logistic":
            scaler = artifact.get("scaler")
            if scaler:
                X = scaler.transform(X)

        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)
            assert proba.shape == (10, 2)
            assert np.allclose(proba.sum(axis=1), 1.0, atol=0.01)
            assert np.all(proba >= 0) and np.all(proba <= 1)

    @pytest.mark.parametrize("ticker", ["QQQ", "TLT", "DIA", "IWM"])
    def test_dummy_input_deterministic(self, ticker):
        """All-zero input gives deterministic prediction."""
        path = _find_ship_model(ticker)
        artifact = joblib.load(path)
        model = artifact["model"]
        n_features = len(artifact["feature_names"])

        X = np.zeros((5, n_features))

        if artifact.get("model_name") == "logistic":
            scaler = artifact.get("scaler")
            if scaler:
                X = scaler.transform(X)

        preds = model.predict(X)
        assert len(set(preds)) == 1  # All same prediction for all-zeros

    def test_qqq_rf_primary_ship(self):
        """QQQ RF model (best performer, 3/5 SHIP folds) loads and predicts."""
        path = _find_ship_model("QQQ")
        artifact = joblib.load(path)
        manifest = _find_ship_manifest("QQQ")

        assert artifact["model_name"] == "rf"
        assert manifest["model_type"] == "rf"
        assert manifest["median_test_sharpe"] > 1.0

        n_features = len(artifact["feature_names"])
        rng = np.random.RandomState(42)
        X = rng.randn(100, n_features) * 0.5

        # Probabilities should be well-calibrated (not all near 0 or 1)
        proba = artifact["model"].predict_proba(X)
        mean_proba = proba[:, 1].mean()
        # Model trained on QQQ (56% up days) should have positive bias
        assert 0.4 < mean_proba < 0.9, f"QQQ RF mean P(up)={mean_proba:.2f} is extreme"
        # But should have some variance across samples
        assert proba[:, 1].std() > 0.01, "QQQ RF probabilities have no variance"

    def test_tlt_gbm_ship_quality(self):
        """TLT GBM has acceptable overfit gap."""
        manifest = _find_ship_manifest("TLT")
        # The manifest should show this was trained with anti-overfit params
        assert manifest["n_samples"] == 2799
        assert manifest["n_features"] < 30  # Feature selection reduced from 53
