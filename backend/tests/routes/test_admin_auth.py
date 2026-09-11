"""
backend/tests/routes/test_admin_auth.py

Verify that all 5 admin trading routes require authentication.
Each route is tested for:
  - 401 without API key
  - 200 with valid API key
"""
import os

import pytest
from fastapi.testclient import TestClient

# Set a test API key before importing server
os.environ["API_SECRET_KEY"] = "test-secret-key"

from server import app

client = TestClient(app)

ROUTES_GET = [
    "/api/admin/trading/status",
    "/api/admin/trading/circuit-breaker/log",
]

ROUTES_POST = [
    "/api/admin/trading/circuit-breaker/reset",
    "/api/admin/trading/circuit-breaker/trip",
    "/api/admin/trading/transition",
]

ALL_ROUTES = ROUTES_GET + ROUTES_POST


class TestAdminRoutesRequireAuth:
    """All admin trading routes must return 401 without a valid API key."""

    @pytest.mark.parametrize("path", ALL_ROUTES)
    def test_no_key_returns_401(self, path):
        r = client.get(path) if path in ROUTES_GET else client.post(path, json={})
        assert r.status_code == 401, f"{path} should be 401 without key, got {r.status_code}"

    @pytest.mark.parametrize("path", ALL_ROUTES)
    def test_valid_key_returns_200(self, path):
        headers = {"X-API-Key": "test-secret-key"}
        r = client.get(path, headers=headers) if path in ROUTES_GET else client.post(path, json={}, headers=headers)
        assert r.status_code == 200, f"{path} should be 200 with valid key, got {r.status_code}"

    @pytest.mark.parametrize("path", ALL_ROUTES)
    def test_wrong_key_returns_401(self, path):
        headers = {"X-API-Key": "wrong-key"}
        r = client.get(path, headers=headers) if path in ROUTES_GET else client.post(path, json={}, headers=headers)
        assert r.status_code == 401, f"{path} should be 401 with wrong key, got {r.status_code}"


class TestAuthErrorCarriesCorsHeaders:
    """A 401 from auth_middleware must carry Access-Control-Allow-Origin, else a
    cross-origin browser sees an opaque CORS failure instead of the real 401 —
    the same reason the rate-limit middleware and the exception handlers echo it.
    """

    def test_401_on_mutating_route_has_cors_header(self):
        r = client.post(
            "/api/admin/trading/circuit-breaker/reset",
            json={},
            headers={"X-API-Key": "wrong-key", "Origin": "http://localhost:3000"},
        )
        assert r.status_code == 401
        header_keys = {k.lower() for k in r.headers}
        assert "access-control-allow-origin" in header_keys, (
            "auth 401 lacks Access-Control-Allow-Origin — a cross-origin browser "
            "sees an opaque CORS error instead of the 401"
        )
