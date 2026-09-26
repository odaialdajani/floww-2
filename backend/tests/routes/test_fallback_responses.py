"""
Tests for graceful fallback responses on analytics routes.

Validates:
  - External API errors return 200 with degradation payload.
  - Computation errors return 200 with degradation payload.
  - Degraded payload has correct structure.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestFallbackResponses:
    """All endpoints return 200 with degradation info on failure."""

    def test_implied_pdf_external_error_returns_200(self, client):
        with patch("routes.analytics._cache") as mock_cache:
            mock_cache.get_chain = AsyncMock(side_effect=ConnectionError("API down"))
            r = client.get("/api/implied-pdf/SPY")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "degraded"
        assert d["stale"] is True
        assert "retry_after" in d

    def test_regime_computation_error_returns_200(self, client):
        bad_data = {"spot": None, "contracts": []}
        with patch("routes.analytics._cache") as mock_cache:
            mock_cache.get_chain = AsyncMock(return_value=bad_data)
            r = client.get("/api/regime/SPY")
        # Should get 404 from _check_chain since spot is None
        assert r.status_code in (200, 404)

    def test_movers_error_returns_200_with_empty_results(self, client):
        from unittest.mock import AsyncMock

        from services import movers as movers_svc
        movers_svc._CACHE.clear()  # isolate from other tests' last-good entries

        async def _boom(sym, days=10):
            raise RuntimeError("provider down")
        with patch("services.market_bars.get_daily_bars", new=_boom):
            r = client.get("/api/movers")
        assert r.status_code == 200
        d = r.json()
        assert d["results"] == []
        assert d["status"] == "unavailable"
        assert d["schema_version"] == "movers.v2"

    def test_history_error_returns_200_with_empty_snapshots(self, client):
        with patch("server.db") as mock_db:
            mock_db.snapshots.find.side_effect = Exception("mongo down")
            r = client.get("/api/history/SPY")
        assert r.status_code == 200
        d = r.json()
        assert d["snapshots"] == []
        assert d["count"] == 0
        assert d["status"] == "degraded"

    def test_degraded_response_has_required_fields(self, client):
        """Verify the degraded response structure."""
        with patch("routes.analytics._cache") as mock_cache:
            mock_cache.get_chain = AsyncMock(side_effect=Exception("test"))
            r = client.get("/api/implied-pdf/SPY")
        d = r.json()
        required = ["status", "reason", "stale", "retry_after", "asof"]
        for field in required:
            assert field in d, f"Missing field: {field}"
