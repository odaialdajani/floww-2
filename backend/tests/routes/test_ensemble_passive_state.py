"""Polling state must not initialize prediction engines or import Torch."""
import builtins
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from routes import ensemble


@pytest.fixture(autouse=True)
def passive_registry(monkeypatch):
    monkeypatch.setattr(ensemble, "_ensembles", {})
    original = builtins.__import__

    def no_model_import(name, *args, **kwargs):
        if name == "services.ml_ensemble":
            raise AssertionError("a status read tried to load the prediction engine")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_model_import)


@pytest.mark.asyncio
async def test_cold_status_is_unknown_without_initializing_models():
    result = await ensemble.get_ensemble_state("spy")
    assert result["ticker"] == "SPY"
    assert result["type"] == "toxicity_ensemble"
    assert result["horizons"] == [1, 5, 15, 60]
    assert result["initialized"] is False
    assert result["status"] == "uninitialized"
    assert result["ensemble_probabilities"] == {}
    assert ensemble._ensembles == {}


@pytest.mark.asyncio
async def test_existing_status_preserves_values_without_loading_another_model():
    state = {"status": "active", "ensemble_probabilities": {"p_toxic_1min": 0.0, "p_toxic_5min": None}}
    read = Mock(return_value=state)
    existing = SimpleNamespace(get_state=read)
    ensemble._ensembles["SPY"] = existing
    result = await ensemble.get_ensemble_state("SPY")
    assert result["initialized"] is True
    assert result["ensemble_probabilities"] == state["ensemble_probabilities"]
    assert ensemble._ensembles["SPY"] is existing
    read.assert_called_once_with()
