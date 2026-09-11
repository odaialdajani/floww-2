"""
Regression tests for route-ordering reachability.

Phase 1 fixed catch-all shadowing where literal routes like /status and /align
were declared AFTER /{ticker}, making them unreachable. These tests ensure the
ordering fix holds and the literal routes respond (200 or 404/503, NOT 422
from treating "status"/"align" as ticker params).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestRouteOrderingAlerts:
    """/api/alerts/status must be reachable above /api/alerts/{ticker}."""

    def test_status_route_reachable(self, client):
        """GET /api/alerts/status returns 200/401/404/503, NOT 422.

        422 means "status" was parsed as a {ticker} catch-all param —
        the exact shadowing bug Phase 1 fixed. This test catches regressions
        by rejecting 422.
        """
        r = client.get("/api/alerts/status")
        # 200 = ok, 401 = no auth, 404 = not found, 503 = service unavailable
        assert r.status_code not in (422,), (
            f"Got 422 — /status is shadowed by /{{ticker}} catch-all: {r.text[:200]}"
        )
        assert r.status_code in (200, 401, 404, 503), (
            f"Unexpected status {r.status_code}: {r.text[:200]}"
        )

    def test_ticker_route_still_works(self, client):
        """GET /api/alerts/SPY should still work (catch-all not broken)."""
        r = client.get("/api/alerts/SPY")
        assert r.status_code in (200, 401, 404, 422, 503)


class TestRouteOrderingDataProviders:
    """/api/data/status must be reachable above /api/data/{ticker}."""

    def test_status_route_reachable(self, client):
        """GET /api/data/status returns 200/401/404/503, NOT 422.

        422 means "status" was parsed as a {ticker} catch-all param —
        the exact shadowing bug Phase 1 fixed.
        """
        r = client.get("/api/data/status")
        assert r.status_code not in (422,), (
            f"Got 422 — /status is shadowed by /{{ticker}} catch-all: {r.text[:200]}"
        )
        assert r.status_code in (200, 401, 404, 503), (
            f"Unexpected status {r.status_code}: {r.text[:200]}"
        )


class TestRouteOrderingTrinity:
    """/api/trinity/align must be reachable above /api/trinity/{ticker}."""

    def test_align_route_reachable(self, client, monkeypatch):
        """The literal route computes all three markets, never ticker ALIGN."""
        from routes import trinity

        spots = {"SPY": 500.0, "QQQ": 450.0, "^SPX": 5000.0}

        async def market_chain(ticker, expiries):
            spot = spots[ticker]
            return {
                "spot": spot,
                "contracts": [
                    {"strike": spot * 0.99, "type": "put", "oi": 100,
                     "iv": 0.2, "T": 30 / 365},
                    {"strike": spot * 1.01, "type": "call", "oi": 100,
                     "iv": 0.2, "T": 30 / 365},
                ],
            }

        fetch_chain = AsyncMock(side_effect=market_chain)
        monkeypatch.setattr(trinity, "_fetch_chain", fetch_chain)
        r = client.get("/api/trinity/align")
        assert r.status_code == 200, r.text[:200]
        assert fetch_chain.await_args_list == [call("SPY", 4), call("QQQ", 4), call("^SPX", 4)]
        result = r.json()
        for key, spot in zip(("spy", "qqq", "spx"), spots.values(), strict=True):
            levels = result[f"{key}_flip_levels"]
            assert len(levels) == 1
            assert spot * 0.99 < levels[0] < spot * 1.01
        assert result["score"] > 0
        assert result["aligned_levels"]
