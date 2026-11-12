#!/usr/bin/env python3
"""tests/services/ml/test_outcome_tracking.py — ML outcome tracking tests."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def isolated_forecast(monkeypatch):
    """Exercise real persistence independently of vendor/model availability."""
    from services.ml.inference import PredictionResult, inference_engine

    async def forecast(ticker):
        return PredictionResult(
            ticker=ticker, prediction=2, confidence=0.75,
            probabilities=[0.1, 0.15, 0.75], model_id="fixture-only",
            features_used=["ret_1d"], feature_values={"ret_1d": 0.0125},
            timestamp="2026-11-06T14:30:00+00:00", gex_signal=None,
        )

    monkeypatch.setattr(inference_engine, "predict", forecast)


@pytest.mark.asyncio
async def test_record_prediction(aclient):
    """Test recording a prediction."""
    resp = await aclient.post("/api/ml/outcome/record?ticker=SPY")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["ticker"] == "SPY"
    assert "prediction" in data
    assert "confidence" in data
    assert "outcome_date" in data
    saved = (await aclient.get("/api/ml/outcome/recent?ticker=SPY&limit=1")).json()["predictions"][0]
    assert saved["model_id"] == "fixture-only"
    assert saved["prediction"] == 2
    assert saved["probabilities"] == {"down": 0.1, "hold": 0.15, "up": 0.75}
    assert saved["feature_snapshot"] == {"ret_1d": 0.0125}


@pytest.mark.asyncio
async def test_failed_forecast_does_not_record_a_prediction(aclient, monkeypatch):
    import server
    from services.ml.inference import inference_engine

    before = await server.db.ml_predictions.count_documents({})

    async def unavailable(ticker):
        raise RuntimeError("fixture provider unavailable")

    monkeypatch.setattr(inference_engine, "predict", unavailable)
    response = await aclient.post("/api/ml/outcome/record?ticker=SPY")
    assert response.status_code == 503
    assert await server.db.ml_predictions.count_documents({}) == before


@pytest.mark.asyncio
async def test_batch_record(aclient):
    """Test batch recording for all tickers."""
    resp = await aclient.post("/api/ml/outcome/batch-record")
    assert resp.status_code == 200
    data = resp.json()
    assert data["recorded"] > 0


@pytest.mark.asyncio
async def test_accuracy_empty(aclient):
    """Test accuracy endpoint with no outcomes yet."""
    resp = await aclient.get("/api/ml/outcome/accuracy")
    assert resp.status_code == 200
    data = resp.json()
    # Should return message about no outcomes or empty stats
    assert "message" in data or "total_predictions" in data


@pytest.mark.asyncio
async def test_recent_predictions(aclient):
    """Test getting recent predictions."""
    # Record one first
    await aclient.post("/api/ml/outcome/record?ticker=SPY")
    resp = await aclient.get("/api/ml/outcome/recent?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1


@pytest.mark.asyncio
async def test_compute_outcomes(aclient):
    """Test outcome computation endpoint."""
    resp = await aclient.post("/api/ml/outcome/compute")
    assert resp.status_code == 200
    data = resp.json()
    assert "updated" in data


@pytest.mark.asyncio
async def test_record_all_tickers(aclient):
    """Test recording predictions for all 5 tickers."""
    resp = await aclient.post("/api/ml/outcome/batch-record?tickers=SPY&tickers=QQQ&tickers=DIA&tickers=IWM&tickers=TLT")
    assert resp.status_code == 200
    data = resp.json()
    assert data["recorded"] == 5
    assert len(data["errors"]) == 0
