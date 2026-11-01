"""
Route-level honesty tests for ``GET /api/exposure_profile/{ticker}``.

The route used to catch every exception (including the provider's own
``HTTPException(503, ...)``) and answer 200 with ``spot: 0.0`` /
``current_total_exposure: 0.0`` / ``profile: []``. That renders an
unavailable provider as a measured zero exposure profile. These tests pin
the honest contract:

  * a provider ``HTTPException`` propagates unchanged (503);
  * any other fetch/compute failure becomes a 503, never a zero payload;
  * the successful response shape is unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server import app  # noqa: E402

_PROVIDER_DETAIL = "Public-only market data: legacy Yahoo chain study unavailable"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _synth_chain() -> dict:
    """Minimal BS-priced chain the exposure-profile service accepts."""
    from bs_greeks import bs_call_price, bs_put_price

    spot = 100.0
    T = 30.0 / 365.0
    contracts = []
    for strike in (95.0, 100.0, 105.0):
        for kind, pricer in (("call", bs_call_price), ("put", bs_put_price)):
            mid = float(pricer(spot, strike, T, 0.20, r=0.05))
            contracts.append({
                "strike": strike,
                "type": kind,
                "oi": 100.0,
                "bid": mid,
                "ask": mid,
                "lastPrice": mid,
                "impliedVolatility": 0.20,
                "expiry": "30DTE",
            })
    return {"spot": spot, "contracts": contracts}


def test_provider_http_exception_propagates_as_503(client, monkeypatch):
    """The public-only policy refusal must not become 200-with-zeros."""

    def _refuse(ticker, max_expiries=4):
        raise HTTPException(503, _PROVIDER_DETAIL)

    monkeypatch.setattr("server.fetch_spot_and_chains", _refuse)

    response = client.get("/api/exposure_profile/SPY")

    assert response.status_code == 503, response.text
    # server.py's HTTPException handler exposes exc.detail as "error".
    assert response.json()["error"] == _PROVIDER_DETAIL
    # No fabricated zero payload alongside the honest status.
    assert "profile" not in response.json()
    assert "spot" not in response.json()


def test_unexpected_fetch_exception_returns_503_not_zero_profile(client, monkeypatch):
    """A non-HTTP provider failure is also unavailable, not an empty profile."""

    def _boom(ticker, max_expiries=4):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr("server.fetch_spot_and_chains", _boom)

    response = client.get("/api/exposure_profile/SPY")

    assert response.status_code == 503, response.text
    detail = response.json()["error"].lower()
    assert "unavailable" in detail
    assert "profile" not in response.json()
    assert "current_total_exposure" not in response.json()


def test_success_path_shape_is_unchanged(client, monkeypatch):
    """The happy-path payload keeps its documented keys and values."""

    monkeypatch.setattr(
        "server.fetch_spot_and_chains",
        lambda ticker, max_expiries=4: _synth_chain(),
    )

    response = client.get("/api/exposure_profile/SPY?shifts=-2,0,2")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticker"] == "SPY"
    assert body["spot"] == pytest.approx(100.0)
    assert body["shifts_pct"] == [-2.0, 0.0, 2.0]
    assert len(body["profile"]) == 3
    assert isinstance(body["current_total_exposure"], float)
    assert body["method"] == "bs_reprice_then_dollar_gex"
