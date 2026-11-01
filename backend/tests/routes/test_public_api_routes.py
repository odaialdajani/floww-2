from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)

# conftest sets API_SECRET_KEY=test-secret-key; account reads must present it.
AUTH = {"X-API-Key": "test-secret-key"}


def test_public_portfolio_raw_refuses_without_key() -> None:
    """Reproduced 2026-11-01: the raw account view was readable unauthenticated."""
    response = client.get("/api/public/portfolio/raw")
    assert response.status_code == 401


def test_public_portfolio_raw_refuses_wrong_key() -> None:
    response = client.get("/api/public/portfolio/raw", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_public_portfolio_raw_refuses_when_auth_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    response = client.get("/api/public/portfolio/raw", headers=AUTH)
    assert response.status_code == 503


@dataclass
class PositionFixture:
    symbol: str
    quantity: float


@dataclass
class OrderFixture:
    order_id: str
    status: str


@dataclass
class PortfolioFixture:
    cash: float
    positions: list[PositionFixture]
    orders: list[OrderFixture]


def test_public_portfolio_serializes_nested_dataclasses() -> None:
    account = MagicMock(account_id="acct-1")
    portfolio = PortfolioFixture(
        cash=1000.0,
        positions=[PositionFixture(symbol="SPY", quantity=2.0)],
        orders=[OrderFixture(order_id="order-1", status="OPEN")],
    )
    broker = MagicMock()
    broker.get_trading_account.return_value = account
    broker.get_portfolio = AsyncMock(return_value=portfolio)

    with patch("routes.public_api._get_broker", new=AsyncMock(return_value=broker)):
        response = client.get("/api/public/portfolio/raw", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["account_id"] == "acct-1"
    assert body["data_source"] == "public_api"
    assert body["portfolio"]["cash"] == 1000.0
    assert body["portfolio"]["positions"] == [{"symbol": "SPY", "quantity": 2.0}]
    assert body["portfolio"]["orders"] == [{"order_id": "order-1", "status": "OPEN"}]


def test_public_portfolio_returns_502_without_broker() -> None:
    with patch("routes.public_api._get_broker", new=AsyncMock(return_value=None)):
        response = client.get("/api/public/portfolio/raw", headers=AUTH)

    assert response.status_code == 502


def test_public_portfolio_returns_502_without_trading_account() -> None:
    broker = MagicMock()
    broker.get_trading_account.return_value = None

    with patch("routes.public_api._get_broker", new=AsyncMock(return_value=broker)):
        response = client.get("/api/public/portfolio/raw", headers=AUTH)

    assert response.status_code == 502


def test_public_portfolio_returns_502_on_upstream_error() -> None:
    account = MagicMock(account_id="acct-1")
    broker = MagicMock()
    broker.get_trading_account.return_value = account
    broker.get_portfolio = AsyncMock(side_effect=RuntimeError("upstream unavailable"))

    with patch("routes.public_api._get_broker", new=AsyncMock(return_value=broker)):
        response = client.get("/api/public/portfolio/raw", headers=AUTH)

    assert response.status_code == 502
