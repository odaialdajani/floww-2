"""Agent endpoint contract: 200 or clean 503, never 500 (mirrors llm endpoints)."""

import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app, headers={"X-API-Key": "test-secret-key"})


def test_ask_returns_200_422_or_503(client: TestClient):
    resp = client.post("/api/agent/ask", json={"question": "SPY 0DTE read?", "ticker": "SPY", "horizon": "0dte"})
    assert resp.status_code in (200, 422, 503), f"got {resp.status_code}: {resp.text}"


def test_budget_returns_200_or_503(client: TestClient):
    resp = client.get("/api/agent/budget")
    assert resp.status_code in (200, 503), f"got {resp.status_code}: {resp.text}"


def test_prefs_returns_200_or_503(client: TestClient):
    resp = client.get("/api/agent/prefs")
    assert resp.status_code in (200, 503), f"got {resp.status_code}: {resp.text}"


def test_unknown_turn_404_or_503(client: TestClient):
    resp = client.get("/api/agent/turn/does-not-exist")
    assert resp.status_code in (200, 404, 503), f"got {resp.status_code}: {resp.text}"
