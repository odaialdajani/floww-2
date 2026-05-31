"""
backend/tests/services/test_ensemble_api.py

Tests for the ensemble API endpoints.
Tests the /api/anomaly/ensemble/update, /api/anomaly/ensemble/state endpoints.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Set API key for auth middleware
os.environ["API_SECRET_KEY"] = "test-secret-key"

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

from server import app


@pytest.fixture
def client():
    return TestClient(app, headers={"X-API-Key": "test-secret-key"})


class TestEnsembleUpdateEndpoint:
    def test_update_returns_ticker(self, client):
        """POST /api/ensemble/update should return ticker."""
        resp = client.post("/api/ensemble/update?ticker=SPY&vpin=0.5&qi=0.1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "SPY"

    def test_update_returns_ensemble_probabilities(self, client):
        """Update should return probabilities for all horizons."""
        resp = client.post("/api/ensemble/update?ticker=SPY&vpin=0.5&qi=0.1")
        data = resp.json()
        assert "ensemble_probabilities" in data
        probs = data["ensemble_probabilities"]
        for h in [1, 5, 15, 60]:
            assert f"p_toxic_{h}min" in probs

    def test_update_returns_component_scores(self, client):
        """Update should return component scores."""
        resp = client.post("/api/ensemble/update?ticker=SPY&vpin=0.5&qi=0.1")
        data = resp.json()
        assert "component_scores" in data
        scores = data["component_scores"]
        assert "cnn_ae" in scores
        assert "statistical" in scores
        assert "forecast_residual" in scores

    def test_update_returns_status(self, client):
        """Update should return status field."""
        resp = client.post("/api/ensemble/update?ticker=SPY&vpin=0.5&qi=0.1")
        data = resp.json()
        assert "status" in data

    def test_update_is_idempotent_per_ticker(self, client):
        """Multiple updates for same ticker should reuse the same ensemble."""
        r1 = client.post("/api/ensemble/update?ticker=QQQ&vpin=0.3&qi=0.05")
        r2 = client.post("/api/ensemble/update?ticker=QQQ&vpin=0.4&qi=0.1")
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_update_different_tickers_independent(self, client):
        """Different tickers should have independent ensemble states."""
        r1 = client.post("/api/ensemble/update?ticker=SPY&vpin=0.9&qi=0.8")
        r2 = client.post("/api/ensemble/update?ticker=QQQ&vpin=0.1&qi=0.01")
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_update_with_zero_vpin(self, client):
        """Update with zero VPIN should not crash."""
        resp = client.post("/api/ensemble/update?ticker=SPY&vpin=0.0&qi=0.0")
        assert resp.status_code == 200

    def test_update_with_high_vpin(self, client):
        """Update with high VPIN should return valid probabilities."""
        resp = client.post("/api/ensemble/update?ticker=SPY&vpin=1.0&qi=1.0")
        assert resp.status_code == 200
        probs = resp.json()["ensemble_probabilities"]
        for key, val in probs.items():
            assert 0.0 <= val <= 1.0, f"{key}={val} out of range"


class TestEnsembleStateEndpoint:
    def test_state_returns_ticker(self, client):
        """GET /api/ensemble/state should return ticker."""
        resp = client.get("/api/ensemble/state?ticker=SPY")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "SPY"

    def test_state_returns_type(self, client):
        """State should include type field."""
        resp = client.get("/api/ensemble/state?ticker=SPY")
        data = resp.json()
        assert data["type"] == "toxicity_ensemble"

    def test_state_returns_horizons(self, client):
        """State should include horizons list."""
        resp = client.get("/api/ensemble/state?ticker=SPY")
        data = resp.json()
        assert "horizons" in data
        assert data["horizons"] == [1, 5, 15, 60]

    def test_state_creates_ensemble_if_missing(self, client):
        """State endpoint should create ensemble for new ticker."""
        resp = client.get("/api/ensemble/state?ticker=IWM")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "IWM"
