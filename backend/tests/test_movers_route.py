"""
Regression test for the /api/movers route.

Bug: the @api.get decorator was registered with the path "/api/movers" while
the APIRouter was already mounted under prefix="/api", so the combined route
was "/api/api/movers". Every call to /api/movers returned 404.

Run with:
    cd backend && .venv/bin/python -m pytest tests/test_movers_route.py -v
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture
def client():
    return TestClient(app)


def _fake_movers():
    """Static fixture so the test doesn't depend on yfinance / network."""
    return [
        {"ticker": "SPY",  "open": 500.0, "close": 510.0, "pct": 2.00,
         "volume": 1.0e8, "high": 511.0, "low": 499.0, "prev_close": 500.0},
        {"ticker": "QQQ",  "open": 400.0, "close": 392.0, "pct": -2.00,
         "volume": 5.0e7, "high": 401.0, "low": 391.0, "prev_close": 400.0},
        {"ticker": "NVDA", "open": 120.0, "close": 122.4, "pct": 2.00,
         "volume": 2.0e8, "high": 123.0, "low": 119.5, "prev_close": 120.0},
    ]


def test_movers_route_is_reachable_at_api_movers(client):
    """GET /api/analytics/movers must return 200 (moved under analytics prefix)."""
    with patch("server._fetch_movers_sync", side_effect=_fake_movers):
        # bypass the 60s in-memory cache by stamping it stale
        import server as srv
        srv._movers_cache["ts"] = 0
        srv._movers_cache["data"] = []

        r = client.get("/api/analytics/movers?limit=3")

    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
    body = r.json()
    assert "results" in body
    assert "asof" in body
    assert isinstance(body["results"], list)
    assert len(body["results"]) <= 3


def test_movers_route_not_double_prefixed(client):
    """The pre-fix bug exposed the route at /api/api/movers — that path must NOT exist."""
    r = client.get("/api/api/movers?limit=3")
    assert r.status_code == 404, (
        f"/api/api/movers should be 404 (double-prefix bug); got {r.status_code}"
    )
