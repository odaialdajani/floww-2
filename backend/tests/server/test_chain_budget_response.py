"""The actual chain HTTP route retains Public admission refusal without I/O."""
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import server
from services import public_api_adapter as adapter
from services import public_budget
from tests.offline_network import deny_external_network  # noqa: F401


@pytest.fixture
def no_provider_io(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_KEY", "offline-fixture-only")
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    monkeypatch.setattr(adapter, "BROKER", None)
    monkeypatch.setattr(adapter, "_CHAIN_CACHE", {})
    monkeypatch.setattr(adapter, "_CHAIN_LOCKS", {})
    broker = AsyncMock(side_effect=AssertionError("Public broker initialization forbidden"))
    public = AsyncMock(side_effect=AssertionError("Public provider call forbidden"))
    cvserver = AsyncMock(side_effect=AssertionError("alternate provider forbidden"))
    legacy = Mock(side_effect=AssertionError("legacy provider forbidden"))
    monkeypatch.setattr(adapter, "_get_broker", broker)
    monkeypatch.setattr(adapter, "_fetch_chain_live", public)
    monkeypatch.setattr("services.cvserver_client.fetch_chain_from_cvserver", cvserver)
    monkeypatch.setattr(server, "fetch_spot_and_chains", legacy)
    yield cvserver
    broker.assert_not_awaited()
    public.assert_not_awaited()
    legacy.assert_not_called()


@pytest.mark.parametrize("reason,retry_after", [
    ("inflight_cap", 5), ("token_bucket", 7), ("host_cooldown", 19),
])
def test_chain_budget_refusal_keeps_typed_retry_on_wire(
    monkeypatch, no_provider_io, reason, retry_after,
):
    admission = AsyncMock(side_effect=public_budget.BudgetExhausted(retry_after, reason))
    monkeypatch.setattr(public_budget, "wait_for_read_admission", admission)

    response = TestClient(server.app).get("/api/chain/SPY?expiries=8")

    assert response.status_code == 503, response.text
    body = response.json()
    error = body["error"]
    assert isinstance(error, dict), body
    assert error["status"] == "degraded"
    assert error["reason"] == error["error_type"] == "budget_exhausted"
    assert error["budget_reason"] == reason
    assert error["retry_after"] == retry_after
    assert error["detail"] == f"Public-path budget exhausted (retry in {retry_after}s)"
    assert error["data"] is None and error["contracts"] == [] and error["spot"] is None
    assert body["status_code"] == 503 and body["path"] == "/api/chain/SPY"
    assert response.headers["Retry-After"] == str(retry_after)
    assert response.headers["Access-Control-Allow-Origin"]
    admission.assert_awaited_once()
    no_provider_io.assert_not_awaited()


def test_legacy_budget_refusal_retains_cvserver_fallback(monkeypatch, no_provider_io):
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "legacy")
    admission = AsyncMock(side_effect=public_budget.BudgetExhausted(5, "inflight_cap"))
    monkeypatch.setattr(public_budget, "wait_for_read_admission", admission)
    no_provider_io.side_effect = None
    no_provider_io.return_value = {
        "ticker": "SPY", "spot": 500.0, "expiries": ["2099-01-16"],
        "contracts": [{"expiry": "2099-01-16", "strike": 500.0, "type": "call",
                       "oi": 10, "gamma": 0.01, "delta": 0.5, "iv": 0.2}],
        "data_source": "cvserver",
    }

    response = TestClient(server.app).get("/api/chain/SPY?expiries=8")

    assert response.status_code == 200, response.text
    assert response.json()["data_source"] == "cvserver"
    assert "Retry-After" not in response.headers
    admission.assert_awaited_once()
    no_provider_io.assert_awaited_once_with("SPY", max_expiries=8)


def test_generic_chain_unavailable_does_not_invent_budget_retry(monkeypatch, no_provider_io):
    monkeypatch.setattr(adapter, "fetch_chain_from_public_api", AsyncMock(return_value=None))

    response = TestClient(server.app).get("/api/chain/SPY?expiries=8")

    assert response.status_code == 503
    assert response.json()["error"] == "Public market data is unavailable; alternate sources are disabled"
    assert "Retry-After" not in response.headers
    no_provider_io.assert_not_awaited()


def test_successful_chain_keeps_success_and_opts_into_budget_errors(monkeypatch, no_provider_io):
    chain = {"ticker": "SPY", "spot": 500.0, "expiries": ["2099-01-16"],
             "contracts": [{"expiry": "2099-01-16", "strike": 500.0, "type": "call",
                            "oi": 10, "gamma": 0.01, "delta": 0.5, "iv": 0.2}],
             "data_source": "public_api"}
    fetch = AsyncMock(return_value=chain)
    monkeypatch.setattr(adapter, "fetch_chain_from_public_api", fetch)

    response = TestClient(server.app).get("/api/chain/SPY?expiries=8")

    assert response.status_code == 200, response.text
    assert "Retry-After" not in response.headers
    fetch.assert_awaited_once_with("SPY", max_expiries=8, raise_budget_exhausted=True)
    no_provider_io.assert_not_awaited()
