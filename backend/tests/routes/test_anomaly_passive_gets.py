"""Passive anomaly reads must not allocate per-ticker model state."""
import builtins

import pytest

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
    assert anomaly._ensembles == {}
