"""Passive anomaly reads must not allocate per-ticker model state."""
import builtins

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import anomaly


@pytest.fixture(autouse=True)
def empty_registries(monkeypatch):
    monkeypatch.setattr(anomaly, "_detectors", {})
    monkeypatch.setattr(anomaly, "_ensembles", {})
    original_import = builtins.__import__

    def reject_model_import(name, *args, **kwargs):
        if name in {"services.anomaly_detector", "services.ml_ensemble"}:
            raise AssertionError(f"passive read tried to import {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_model_import)


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["UNTRACKED_XYZ", "ODD-123"])
@pytest.mark.parametrize("route", ["state", "status"])
async def test_detector_gets_report_no_data_without_allocating_models(ticker, route):
    if route == "state":
        result = await anomaly.get_anomaly_state(ticker)
    else:
        result = await anomaly.get_detector_status(ticker)

    assert result["ticker"] == ticker.upper()
    assert result["status"] == "no_data"
    assert result["reason"] == "detector_not_initialized"
    assert set(result) == {
        "model_type",
        "seq_len",
        "latent_dim",
        "buffer_fill",
        "n_errors",
        "trained",
        "ticker",
        "threshold_sigma",
        "status",
        "reason",
    }
    assert result["model_type"] is None
    assert result["seq_len"] == 50
    assert result["latent_dim"] == 8
    assert result["buffer_fill"] == 0.0
    assert result["n_errors"] == 0
    assert result["trained"] is False
    assert result["threshold_sigma"] == 2.5
    assert anomaly._detectors == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["prediction", "state"])
async def test_ensemble_gets_report_cold_state_without_allocating_models(route):
    ticker = "UNTRACKED_XYZ"
    if route == "prediction":
        result = await anomaly.get_ensemble_prediction(ticker=ticker, horizon_minutes=15)
        assert result["horizon_minutes"] == 15
    else:
        result = await anomaly.get_ensemble_state(ticker=ticker)

    assert result["ticker"] == ticker
    assert result["type"] == "toxicity_ensemble"
    assert result["initialized"] is False
    assert result["status"] == "uninitialized"
    assert result["reason"] == "NO_OBSERVATIONS_IN_THIS_PROCESS"
    assert result["ensemble_probabilities"] == {}
    assert result["component_scores"] == {}
    assert set(result) == {
        "ticker",
        "type",
        "seq_len",
        "device",
        "forecaster_loaded",
        "horizons",
        "n_score_history",
        "initialized",
        "status",
        "reason",
        "ensemble_probabilities",
        "component_scores",
    } | ({"horizon_minutes"} if route == "prediction" else set())
    assert result["seq_len"] == 50
    assert result["device"] == "cpu"
    assert result["forecaster_loaded"] is False
    assert result["horizons"] == [1, 5, 15, 60]
    assert result["n_score_history"] == 0
    assert anomaly._ensembles == {}


@pytest.mark.parametrize(
    "path,expected_extra_key",
    [
        ("/api/anomaly/UNTRACKED_HTTP", None),
        ("/api/anomaly/UNTRACKED_HTTP/status", None),
        ("/api/anomaly/ensemble?ticker=UNTRACKED_HTTP", "horizon_minutes"),
        ("/api/anomaly/ensemble/state?ticker=UNTRACKED_HTTP", None),
    ],
)
def test_cold_get_routes_serialize_legacy_state_fields(path, expected_extra_key):
    app = FastAPI()
    app.include_router(anomaly.router)

    response = TestClient(app).get(path)

    assert response.status_code == 200
    data = response.json()
    if path.endswith("/status") or path == "/api/anomaly/UNTRACKED_HTTP":
        assert data["model_type"] is None
        assert data["buffer_fill"] == 0.0
        assert data["status"] == "no_data"
        assert data["reason"] == "detector_not_initialized"
    else:
        assert data["seq_len"] == 50
        assert data["device"] == "cpu"
        assert data["horizons"] == [1, 5, 15, 60]
        assert data["ensemble_probabilities"] == {}
        assert data["status"] == "uninitialized"
    assert ("horizon_minutes" in data) is (expected_extra_key is not None)
    assert anomaly._detectors == {}
    assert anomaly._ensembles == {}
