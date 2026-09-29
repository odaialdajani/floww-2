from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


CHAIN = {
    "ticker": "SPY",
    "spot": 500.0,
    "expiries": ["2026-09-18", "2026-10-16"],
    "contracts": [
        {"expiry": "2026-09-18", "type": "call", "strike": 500.0},
        {"expiry": "2026-10-16", "type": "put", "strike": 490.0},
    ],
    "data_source": "public_api",
}


def test_public_chain_filters_requested_expiration() -> None:
    with patch(
        "routes.public_api.fetch_chain_from_public_api",
        new=AsyncMock(return_value=CHAIN.copy()),
    ):
        response = client.get("/api/public/chain/SPY?expiration=2026-09-18")

    assert response.status_code == 200
    body = response.json()
    assert body["expiries"] == ["2026-09-18"]
    assert body["n_contracts"] == 1
    assert body["contracts"][0]["expiry"] == "2026-09-18"


def test_public_chain_rejects_invalid_expiration_count() -> None:
    response = client.get("/api/public/chain/SPY?expirations=0")
    assert response.status_code == 422


def test_public_chain_returns_502_when_provider_unavailable() -> None:
    with patch(
        "routes.public_api.fetch_chain_from_public_api",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/public/chain/SPY")

    assert response.status_code == 502


def _chain_with(contracts):
    return {
        "ticker": "SPY", "spot": 500.0, "expiries": ["2026-09-18"],
        "contracts": contracts, "data_source": "public_api",
    }


def test_public_chain_rows_carry_canonical_basis_fields() -> None:
    fw = _chain_with([
        {"expiry": "2026-09-18", "type": "call", "strike": 500.0,
         "oi": 100, "gamma": 0.05},
    ])
    with patch("routes.public_api.fetch_chain_from_public_api",
               new=AsyncMock(return_value=fw)):
        body = client.get("/api/public/chain/SPY").json()
    row = body["contracts"][0]
    # Canonical S2 unit .05*100*500^2*.01 = 12,500; x OI 100 = 1,250,000.
    assert row["gex"] == 1_250_000.0
    assert row["gex_basis"] == "OI"
    assert row["gex_reason"] is None
    assert row["gex_formula_version"] == "gex.v2"


def test_public_chain_quarantines_adjusted_contracts() -> None:
    fw = _chain_with([
        {"expiry": "2026-09-18", "type": "call", "strike": 500.0,
         "oi": 100, "gamma": 0.05, "adjusted": True},
    ])
    with patch("routes.public_api.fetch_chain_from_public_api",
               new=AsyncMock(return_value=fw)):
        body = client.get("/api/public/chain/SPY").json()
    row = body["contracts"][0]
    assert row["gex"] is None
    assert row["gex_basis"] == "OI_UNKNOWN"


def test_public_chain_honours_explicit_multiplier() -> None:
    fw = _chain_with([
        {"expiry": "2026-09-18", "type": "call", "strike": 500.0,
         "oi": 100, "gamma": 0.05, "multiplier": 1000},
    ])
    with patch("routes.public_api.fetch_chain_from_public_api",
               new=AsyncMock(return_value=fw)):
        body = client.get("/api/public/chain/SPY").json()
    assert body["contracts"][0]["gex"] == 12_500_000.0


def test_public_chain_gamma_less_row_is_unknown_not_zero() -> None:
    fw = _chain_with([
        {"expiry": "2026-09-18", "type": "call", "strike": 500.0, "oi": 100},
    ])
    with patch("routes.public_api.fetch_chain_from_public_api",
               new=AsyncMock(return_value=fw)):
        body = client.get("/api/public/chain/SPY").json()
    row = body["contracts"][0]
    assert row["gex"] is None
    assert row["gex_basis"] == "OI_UNKNOWN"
    assert row["gex_reason"] == "GAMMA_MISSING"
