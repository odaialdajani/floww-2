"""
Provider-outage honesty tests for the analytics chain routes.

``FetchCoordinator`` turns a fetcher exception into a structured
``status == "error"`` payload. The analytics routes used to see only
"no spot / no contracts" and raise ``404 No options data`` — reporting a
provider outage as an empty options universe. These tests pin the split:

  * provider error payload -> 503 (retryable, not a coverage claim);
  * genuinely empty non-error chain -> 404 (empty universe is real);
  * the pre-existing degraded pass-through (429/503) still works.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_public_budget():
    """Each test starts with a full fetch budget so degradation is caused
    by the patched provider, never by leftover budget state."""
    from services.public_budget import budget

    budget.reset()
    yield
    budget.reset()


def test_fetcher_exception_is_503_not_404(client, monkeypatch):
    """A raising provider is an outage, not 'no options data for TICKER'."""

    async def _boom(ticker, expiries=4):
        raise ConnectionError("provider down")

    monkeypatch.setattr("server.fetch_spot_and_chains_merged", _boom)

    response = client.get("/api/contract/HONESTY")

    assert response.status_code == 503, response.text
    detail = response.json()["error"].lower()
    assert "provider unavailable" in detail
    assert "no options data" not in detail


def test_empty_non_error_chain_still_returns_404(client, monkeypatch):
    """A real fetch that found no contracts keeps the 404 contract."""

    async def _empty(ticker, expiries=4):
        return {"ticker": ticker, "spot": 100.0, "contracts": []}

    monkeypatch.setattr("server.fetch_spot_and_chains_merged", _empty)

    response = client.get("/api/contract/HONESTY_EMPTY")

    assert response.status_code == 404, response.text
    assert "No options data" in response.json()["error"]


def test_degraded_budget_payload_still_passes_through(client, monkeypatch):
    """The explicit degraded branch is unchanged: 429 for budget exhaustion."""
    from services.fetch_coordinator import degraded_response

    payload = degraded_response("budget_exhausted", "bucket empty", retry_after=7)
    monkeypatch.setattr(
        "routes.analytics._cache.get_chain",
        AsyncMock(return_value=payload),
    )

    response = client.get("/api/contract/DEGRADED")

    assert response.status_code == 429, response.text
    assert response.json()["reason"] == "budget_exhausted"
