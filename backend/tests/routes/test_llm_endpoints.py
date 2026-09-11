"""Strict local route success, unavailable-service and invalid-input checks."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from server import app

TRADE = {"ticker": "SPY", "spot": 570.0, "regime": "positive", "net_gex": 1.2e9,
         "prediction": "bullish", "confidence": 0.65}
GENERATE = {"prompt": "A short market briefing", "system_prompt": "You are a market analyst.",
            "max_tokens": 64}


@pytest.fixture
def model_boundary(monkeypatch):
    module = ModuleType("services.llm")
    module.analyze_trade_with_llm = AsyncMock(return_value={"analysis": "saved trade explanation"})
    service = Mock()
    service.generate.return_value = {"text": "saved briefing"}
    service.available_providers = ["test-provider"]
    service.provider = "test-provider"
    service.is_configured = True
    module.get_llm_service = Mock(return_value=service)
    monkeypatch.setitem(sys.modules, "services.llm", module)
    return module, service


@pytest.fixture
def client(monkeypatch, model_boundary):
    monkeypatch.setenv("API_SECRET_KEY", "test-secret-key")
    return TestClient(app, headers={"X-API-Key": "test-secret-key"})


def test_llm_providers_returns_exact_configured_state(client, model_boundary):
    response = client.get("/api/llm/providers")
    assert response.status_code == 200
    assert response.json() == {"providers": ["test-provider"], "current": "test-provider", "configured": True}
    model_boundary[0].get_llm_service.assert_called_once_with()


def test_llm_analyze_trade_forwards_exact_args(client, model_boundary):
    response = client.post("/api/llm/analyze-trade", json=TRADE)
    assert response.status_code == 200
    assert response.json() == {"analysis": "saved trade explanation"}
    model_boundary[0].analyze_trade_with_llm.assert_awaited_once_with(**TRADE)


def test_llm_generate_forwards_exact_args(client, model_boundary):
    response = client.post("/api/llm/generate", json=GENERATE)
    assert response.status_code == 200
    assert response.json() == {"text": "saved briefing"}
    model_boundary[0].get_llm_service.assert_called_once_with()
    model_boundary[1].generate.assert_called_once_with(**GENERATE)


@pytest.mark.parametrize("route,payload", [("analyze-trade", TRADE), ("generate", GENERATE)])
def test_missing_service_import_is_clean_503(client, monkeypatch, model_boundary, route, payload):
    monkeypatch.setitem(sys.modules, "services.llm", None)
    response = client.post("/api/llm/" + route, json=payload)
    assert response.status_code == 503
    assert response.json() == {"error": "LLM service not configured",
                               "status_code": 503, "path": "/api/llm/" + route}
    model_boundary[0].analyze_trade_with_llm.assert_not_awaited()
    model_boundary[1].generate.assert_not_called()


@pytest.mark.parametrize("route,payload", [("analyze-trade", {"ticker": "SPY", "spot": "bad"}),
                                           ("generate", {"max_tokens": 64})])
def test_invalid_input_never_calls_model(client, model_boundary, route, payload):
    response = client.post("/api/llm/" + route, json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    model_boundary[0].analyze_trade_with_llm.assert_not_awaited()
    model_boundary[0].get_llm_service.assert_not_called()
    model_boundary[1].generate.assert_not_called()


def test_generation_rejected_by_service_is_clean_400(client, model_boundary):
    model_boundary[1].generate.side_effect = ValueError("provider not configured")
    response = client.post("/api/llm/generate", json=GENERATE)
    assert response.status_code == 400
    assert response.json() == {"error": "provider not configured",
                               "status_code": 400, "path": "/api/llm/generate"}
    model_boundary[1].generate.assert_called_once_with(**GENERATE)
