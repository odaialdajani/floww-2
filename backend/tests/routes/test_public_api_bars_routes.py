"""Route tests for the Public.com STOCK data feed.

Covers the new ``GET /api/public/bars/{ticker}`` endpoint and the enriched
``GET /api/public/quotes/{ticker}`` response. The pre-existing quote keys
(``ok`` / ``ticker`` / ``spot`` / ``data_source``) are pinned here so the
enrichment cannot silently change their names or meanings — frontend/src/lib/
publicApi.js consumes this endpoint.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server import app
from tests.offline_network import deny_external_network  # noqa: F401

client = TestClient(app)


BARS = [
    {"date": "2026-09-02T20:00:00Z", "open": 500.0, "high": 505.0,
     "low": 499.0, "close": 503.5, "volume": 1000},
    {"date": "2026-09-03T20:00:00Z", "open": 503.5, "high": 508.0,
     "low": 502.0, "close": 507.25, "volume": 2000},
]

QUOTE = {
    "ticker": "SPY",
    "spot": 500.0,
    "last": 500.5,
    "bid": 499.0,
    "ask": 501.0,
    "bid_size": 300,
    "ask_size": 400,
    "volume": 12345,
    "previous_close": 498.0,
    "change": 2.5,
    "percent_change": 0.5,
    "timestamp": "2026-09-03T20:00:00Z",
    "data_source": "public_api",
}


# ---------------------------------------------------------------------------
# GET /api/public/bars/{ticker}
# ---------------------------------------------------------------------------


def test_public_bars_returns_ohlcv_rows() -> None:
    with patch(
        "routes.public_api.fetch_bars_from_public_api",
        new=AsyncMock(return_value=list(BARS)),
    ):
        response = client.get("/api/public/bars/spy?timeframe=1Day&limit=100")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ticker"] == "SPY"
    assert body["timeframe"] == "1Day"
    assert body["count"] == 2
    assert body["data_source"] == "public_api"
    assert set(body["bars"][0]) == {"date", "open", "high", "low", "close", "volume"}


def test_public_bars_forwards_timeframe_and_limit() -> None:
    fetch = AsyncMock(return_value=list(BARS))
    with patch("routes.public_api.fetch_bars_from_public_api", new=fetch):
        response = client.get("/api/public/bars/SPY?timeframe=5Min&limit=25")

    assert response.status_code == 200
    assert fetch.await_args.kwargs["timeframe"] == "5Min"
    assert fetch.await_args.kwargs["limit"] == 25


def test_public_bars_returns_502_when_provider_unavailable() -> None:
    with patch(
        "routes.public_api.fetch_bars_from_public_api",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/public/bars/SPY")

    assert response.status_code == 502


def test_public_bars_rejects_unsupported_timeframe() -> None:
    fetch = AsyncMock(return_value=list(BARS))
    with patch("routes.public_api.fetch_bars_from_public_api", new=fetch):
        response = client.get("/api/public/bars/SPY?timeframe=3Fortnights")

    assert response.status_code == 400
    fetch.assert_not_awaited()


def test_public_bars_rejects_invalid_limit() -> None:
    response = client.get("/api/public/bars/SPY?limit=0")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/public/quotes/{ticker} — enriched, backwards compatible
# ---------------------------------------------------------------------------


def test_public_quotes_keeps_existing_keys() -> None:
    with patch(
        "routes.public_api.fetch_quotes_from_public_api",
        new=AsyncMock(return_value={"SPY": dict(QUOTE)}),
    ):
        response = client.get("/api/public/quotes/spy")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ticker"] == "SPY"
    assert body["spot"] == 500.0
    assert body["data_source"] == "public_api"


def test_public_quotes_adds_bid_ask_and_sizes() -> None:
    with patch(
        "routes.public_api.fetch_quotes_from_public_api",
        new=AsyncMock(return_value={"SPY": dict(QUOTE)}),
    ):
        response = client.get("/api/public/quotes/SPY")

    body = response.json()
    assert body["bid"] == 499.0
    assert body["ask"] == 501.0
    assert body["bid_size"] == 300
    assert body["ask_size"] == 400
    assert body["last"] == 500.5


def test_public_quotes_returns_502_when_provider_unavailable() -> None:
    with patch(
        "routes.public_api.fetch_quotes_from_public_api",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/public/quotes/SPY")

    assert response.status_code == 502


def test_public_quotes_returns_502_when_symbol_missing_from_batch() -> None:
    with patch(
        "routes.public_api.fetch_quotes_from_public_api",
        new=AsyncMock(return_value={"QQQ": dict(QUOTE), "IWM": dict(QUOTE)}),
    ):
        response = client.get("/api/public/quotes/SPY")

    assert response.status_code == 502


def test_public_quotes_resolves_caret_prefixed_symbol() -> None:
    """``^SPX`` normalises to ``SPX`` before the adapter lookup."""
    with patch(
        "routes.public_api.fetch_quotes_from_public_api",
        new=AsyncMock(return_value={"SPX": dict(QUOTE, ticker="SPX", spot=6000.0)}),
    ):
        response = client.get("/api/public/quotes/%5Espx")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "^SPX"
    assert body["spot"] == 6000.0


# ---------------------------------------------------------------------------
# Safety — this router is DATA ONLY
# ---------------------------------------------------------------------------


def test_public_router_exposes_no_order_endpoint() -> None:
    from routes.public_api import router

    # The market-data router has its own boundary. The app also mounts the
    # separately protected brokerage router, tested by test_public_brokerage_gate.
    paths = {
        route.path
        for route in router.routes
        if getattr(route, "path", "").startswith("/api/public")
    }
    assert "/api/public/bars/{ticker}" in paths
    for path in paths:
        assert "order" not in path, f"{path} must not exist on the data router"
