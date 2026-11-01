"""
Dashboard auth-middleware denial-path tests.

The middleware used ``JSONResponse(status_code=..., detail=...)``, but
Starlette's ``JSONResponse`` has no ``detail`` keyword — so both denial
branches raised ``TypeError`` (500) instead of sending 503/401. These tests
execute the real middleware through the app's test client with
``ENVIRONMENT=production`` and the session token configured/absent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_missing_dash_session_token_returns_503(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DASH_SESSION_TOKEN", raising=False)

    response = client.get("/dashboard/")

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": "Dashboard auth not configured"}


def test_wrong_dash_session_token_returns_401(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DASH_SESSION_TOKEN", "expected-token")

    response = client.get("/dashboard/?token=wrong-token")

    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "Unauthorized"}
