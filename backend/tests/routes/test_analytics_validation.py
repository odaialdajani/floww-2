"""
Tests for FastAPI query param validation on Heatseeker routes.

Validates:
  - Out-of-range params return 422 with clear error messages.
  - Default params return 200.
  - Boundary values are accepted.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from server import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _mock_chain():
    return {
        "ticker": "SPY",
        "spot": 500.0,
        "expiries": ["2026-05-22"],
        "contracts": [
            {"strike": 500.0, "type": "call", "expiry": "2026-05-22",
             "T": 3 / 365.0, "oi": 1000, "gamma": 0.04, "iv": 0.20},
            {"strike": 500.0, "type": "put", "expiry": "2026-05-22",
             "T": 3 / 365.0, "oi": 1000, "gamma": 0.04, "iv": 0.20},
        ],
    }


class TestFlipZonesValidation:
    """window_pct and min_gap_pct bounds."""

    def test_default_params_return_200(self, client):
        with patch("routes.heatseeker._fetch_chain", AsyncMock(return_value=_mock_chain())):
            r = client.get("/api/heatseeker/flip-zones?ticker=SPY")
        assert r.status_code == 200, r.text

    def test_window_pct_too_large_returns_422(self, client):
        r = client.get("/api/heatseeker/flip-zones?ticker=SPY&window_pct=2.0")
        assert r.status_code == 422
        detail = r.json().get("detail", [])
        assert any("window_pct" in str(d) for d in detail)

    def test_window_pct_too_small_returns_422(self, client):
        r = client.get("/api/heatseeker/flip-zones?ticker=SPY&window_pct=0.001")
        assert r.status_code == 422

    def test_min_gap_pct_too_large_returns_422(self, client):
        r = client.get("/api/heatseeker/flip-zones?ticker=SPY&min_gap_pct=0.5")
        assert r.status_code == 422

    def test_boundary_values_accepted(self, client):
        with patch("routes.heatseeker._fetch_chain", AsyncMock(return_value=_mock_chain())):
            r = client.get("/api/heatseeker/flip-zones?ticker=SPY&window_pct=0.01&min_gap_pct=0.005")
        assert r.status_code == 200, r.text

    def test_upper_boundary_accepted(self, client):
        with patch("routes.heatseeker._fetch_chain", AsyncMock(return_value=_mock_chain())):
            r = client.get("/api/heatseeker/flip-zones?ticker=SPY&window_pct=0.50&min_gap_pct=0.20")
        assert r.status_code == 200, r.text


class TestAirPocketsValidation:
    """min_gap_pct bounds."""

    def test_default_params_return_200(self, client):
        with patch("routes.heatseeker._fetch_chain", AsyncMock(return_value=_mock_chain())):
            r = client.get("/api/heatseeker/air-pockets?ticker=SPY")
        assert r.status_code == 200, r.text

    def test_min_gap_pct_too_small_returns_422(self, client):
        r = client.get("/api/heatseeker/air-pockets?ticker=SPY&min_gap_pct=0.001")
        assert r.status_code == 422

    def test_min_gap_pct_too_large_returns_422(self, client):
        r = client.get("/api/heatseeker/air-pockets?ticker=SPY&min_gap_pct=0.5")
        assert r.status_code == 422


class TestNodeLifecycleValidation:
    """lookback_mins bounds."""

    def test_default_params_return_200(self, client):
        with patch("routes.heatseeker._fetch_chain", AsyncMock(return_value=_mock_chain())):
            with patch("routes.heatseeker._fetch_history", AsyncMock(return_value=[])):
                r = client.get("/api/heatseeker/node-lifecycle?ticker=SPY")
        assert r.status_code == 200, r.text

    def test_lookback_too_small_returns_422(self, client):
        r = client.get("/api/heatseeker/node-lifecycle?ticker=SPY&lookback_mins=1")
        assert r.status_code == 422

    def test_lookback_too_large_returns_422(self, client):
        r = client.get("/api/heatseeker/node-lifecycle?ticker=SPY&lookback_mins=9999")
        assert r.status_code == 422
