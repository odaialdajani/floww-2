"""Public-only policy: the source labels must be honest.

Three claims are pinned here.

1. The core chain fails closed to legacy sources. In Public-only mode the
   Public API is the only market-data source; when it cannot answer, the
   request fails with a 503 instead of quietly serving cvserver, yfinance or
   Databento data.

2. The provider status names the role of every provider. Public.com is the
   primary source; the legacy providers are emergency fallbacks that the
   core chain does not use while Public-only mode is on. A status that
   lists them as enabled without saying so is a claim the status cannot
   make: a reader would conclude they are live sources.

3. The optional TradingVolatility enrichment is a separate, non-Public path.
   It rides along in the regime response, so it has to name its own source;
   a reader must not take it for Public.com data.

Everything here is offline: no key, no network, no orders.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. The core chain fails closed to legacy sources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_core_chain_refuses_legacy_sources_in_public_only_mode(monkeypatch):
    """When Public cannot answer, the request fails - it never falls back."""
    from fastapi import HTTPException

    import server

    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    monkeypatch.setenv("PUBLIC_API_KEY", "test-key")

    async def _public_unavailable(*args, **kwargs):
        raise RuntimeError("public unavailable")

    monkeypatch.setattr(
        "services.public_api_adapter.fetch_chain_from_public_api", _public_unavailable)

    cvserver_called = []

    async def _cvserver(*args, **kwargs):
        cvserver_called.append(True)
        return {"contracts": [{"strike": 100.0}], "spot": 100.0}

    monkeypatch.setattr(
        "services.cvserver_client.fetch_chain_from_cvserver", _cvserver)

    with pytest.raises(HTTPException) as caught:
        await server.fetch_spot_and_chains_merged("SPY", max_expiries=1)

    assert caught.value.status_code == 503, caught.value
    assert "disabled" in str(caught.value.detail).lower(), caught.value.detail
    assert not cvserver_called, (
        "the core chain fell back to a legacy source in Public-only mode")


@pytest.mark.asyncio
async def test_the_core_chain_still_uses_legacy_sources_outside_public_only_mode(monkeypatch):
    """Outside Public-only mode the legacy fallback chain still works."""
    import server

    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.setenv("PUBLIC_API_KEY", "test-key")

    async def _public_unavailable(*args, **kwargs):
        raise RuntimeError("public unavailable")

    monkeypatch.setattr(
        "services.public_api_adapter.fetch_chain_from_public_api", _public_unavailable)

    async def _cvserver(*args, **kwargs):
        return {"contracts": [{"strike": 100.0}], "spot": 100.0}

    monkeypatch.setattr(
        "services.cvserver_client.fetch_chain_from_cvserver", _cvserver)

    result = await server.fetch_spot_and_chains_merged("SPY", max_expiries=1)
    assert result["contracts"], result
    assert result["spot"] == 100.0, result


# ---------------------------------------------------------------------------
# 2. The provider status names every provider's role
# ---------------------------------------------------------------------------


def _provider_status() -> dict:
    response = client.get("/api/data/status")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_provider_status_names_the_primary_source(monkeypatch):
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    body = _provider_status()
    providers = body["providers"]

    assert providers["public_api"]["role"] == "primary", providers["public_api"]
    assert providers["public_api"]["in_use"] is True, providers["public_api"]


def test_the_provider_status_marks_the_legacy_providers_as_fallbacks(monkeypatch):
    """A legacy provider is never advertised as a live source."""
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    body = _provider_status()
    providers = body["providers"]

    for name in ("finnhub", "polygon", "yfinance"):
        assert providers[name]["role"] == "emergency_fallback", providers[name]
        assert providers[name]["in_use"] is False, (
            f"{name} is advertised as in use while Public-only mode disables "
            "the legacy sources for the core chain")


def test_the_provider_status_states_the_active_policy(monkeypatch):
    """The labels only mean something next to the policy they describe."""
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    body = _provider_status()

    assert body["policy"]["market_data_provider"] == "public", body["policy"]
    assert body["policy"]["legacy_sources"] == "disabled", body["policy"]


def test_the_legacy_fallbacks_are_in_use_outside_public_only_mode(monkeypatch):
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    body = _provider_status()
    providers = body["providers"]

    assert body["policy"]["market_data_provider"] != "public", body["policy"]
    assert body["policy"]["legacy_sources"] == "enabled", body["policy"]
    assert providers["yfinance"]["in_use"] is True, providers["yfinance"]


def test_a_retired_provider_stays_retired_and_disabled(monkeypatch):
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    body = _provider_status()
    providers = body["providers"]

    assert providers["alphavantage"]["enabled"] is False, providers["alphavantage"]
    assert providers["alphavantage"]["role"] == "retired", providers["alphavantage"]
    assert providers["alphavantage"]["in_use"] is False, providers["alphavantage"]
    assert "alphavantage" in body["retired"], body["retired"]


@pytest.mark.asyncio
async def test_the_legacy_spot_fallback_is_off_in_public_only_mode(monkeypatch):
    """The label "not in use" has to be true of the code, not only of the text.

    The status says the legacy sources are not serving market data under the
    Public-only policy. If the legacy spot fallback still ran, that label
    would be a lie a reader could not detect.
    """
    from data_providers import DataAggregator

    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")

    async def _public_unavailable(ticker):
        return None

    monkeypatch.setattr("services.public_api_adapter.fetch_spot_from_public_api",
                        _public_unavailable)

    finnhub_called: list[str] = []

    class _FakeFinnhub:
        enabled = True

        async def get_quote(self, ticker):
            finnhub_called.append(ticker)
            return {"price": 123.0, "source": "finnhub"}

    agg = DataAggregator()
    agg.finnhub = _FakeFinnhub()
    spot = await agg.get_spot_price("SPY")

    assert spot is None, (
        "a legacy source served a market price while the policy disabled "
        "the legacy sources")
    assert not finnhub_called, finnhub_called


@pytest.mark.asyncio
async def test_the_legacy_spot_fallback_still_works_outside_public_only_mode(monkeypatch):
    """Outside the Public-only policy the emergency fallback still answers."""
    from data_providers import DataAggregator

    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)

    async def _public_unavailable(ticker):
        return None

    monkeypatch.setattr("services.public_api_adapter.fetch_spot_from_public_api",
                        _public_unavailable)

    class _FakeFinnhub:
        enabled = True

        async def get_quote(self, ticker):
            return {"price": 123.0, "source": "finnhub"}

    agg = DataAggregator()
    agg.finnhub = _FakeFinnhub()
    spot = await agg.get_spot_price("SPY")

    assert spot == {"price": 123.0, "source": "finnhub"}, spot


# ---------------------------------------------------------------------------
# 3. The TradingVolatility enrichment names its own, non-Public source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_trading_volatility_enrichment_is_labelled_as_non_public(monkeypatch):
    """The enrichment rides in the regime response: it must name its source."""
    import routes.flowseeker as flowseeker

    monkeypatch.setattr(flowseeker, "_fetch_tv_signal",
                        AsyncMock(return_value={"score": 0.7, "signal": "bullish"}))

    async def _heatmap(*args, **kwargs):
        return {
            "gamma_flip": {"regime": "positive_gamma", "spot": 100.0,
                           "flip": 95.0, "dist_to_flip": 5.0, "total_gex": 1000.0},
            "market_regime": {"regime": "calm", "atm_iv": 0.2},
            "data_source": "public_api",
        }

    monkeypatch.setattr("server.build_heatmap", _heatmap)

    response = client.get("/api/flowseeker/regime/SPY")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body.get("tv_signal"), body
    assert body.get("tv_signal_source") == "tradingvolatility.net", body
    assert body.get("tv_signal_is_public_data") is False, (
        "a non-Public enrichment was presented as Public data")
    assert body.get("tv_signal_mode") in ("demo", "licensed"), body


@pytest.mark.asyncio
async def test_the_regime_response_says_which_source_the_structure_came_from(monkeypatch):
    """The GEX structure is Public-derived; the response should say so."""
    import routes.flowseeker as flowseeker

    monkeypatch.setattr(flowseeker, "_fetch_tv_signal", AsyncMock(return_value=None))

    async def _heatmap(*args, **kwargs):
        return {
            "gamma_flip": {"regime": "positive_gamma", "spot": 100.0,
                           "flip": 95.0, "dist_to_flip": 5.0, "total_gex": 1000.0},
            "market_regime": {"regime": "calm", "atm_iv": 0.2},
            "data_source": "public_api",
        }

    monkeypatch.setattr("server.build_heatmap", _heatmap)

    response = client.get("/api/flowseeker/regime/SPY")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body.get("structure_source") == "public_option_chain", body
    assert body.get("tv_signal") is None, body


@pytest.mark.asyncio
async def test_the_structure_label_follows_the_chain_that_was_actually_used(monkeypatch):
    """A legacy chain must not be labelled as a Public option chain."""
    import routes.flowseeker as flowseeker

    monkeypatch.setattr(flowseeker, "_fetch_tv_signal", AsyncMock(return_value=None))

    async def _heatmap(*args, **kwargs):
        return {
            "gamma_flip": {"regime": "positive_gamma", "spot": 100.0,
                           "flip": 95.0, "dist_to_flip": 5.0, "total_gex": 1000.0},
            "market_regime": {"regime": "calm", "atm_iv": 0.2},
            "data_source": "cvserver",
        }

    monkeypatch.setattr("server.build_heatmap", _heatmap)

    response = client.get("/api/flowseeker/regime/SPY")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body.get("structure_source") == "cvserver_option_chain", body
