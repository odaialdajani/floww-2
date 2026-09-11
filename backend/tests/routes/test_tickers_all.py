"""Configured-universe pagination, without the retired provider client."""
import pytest

from routes.market_data import list_all_tickers


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    import server
    monkeypatch.setattr(server, "_TICKER_CACHE", None)
    monkeypatch.setattr(server, "_TICKER_CACHE_TS", None)
    monkeypatch.delenv("FLOWW_PUBLIC_UNIVERSE", raising=False)

@pytest.mark.asyncio
async def test_pagination_retains_every_configured_ticker(monkeypatch):
    monkeypatch.setenv("FLOWW_PUBLIC_UNIVERSE", ",".join(f"S{i:05d}" for i in range(2500)))
    first = await list_all_tickers(limit=1000, page=1, refresh=False)
    last = await list_all_tickers(limit=1000, page=3, refresh=False)
    assert first["total"] == 2500 and len(first["tickers"]) == 1000 and first["has_more"]
    assert len(last["tickers"]) == 500 and not last["has_more"]
    assert first["source"] == "configured-universe" and not first["complete_exchange_catalog"]

@pytest.mark.asyncio
async def test_featured_refresh_and_cache(monkeypatch):
    import server
    monkeypatch.setattr(server, "POPULAR_UNIVERSE", ["B", "A"])
    first = await list_all_tickers(limit=1000, page=1, refresh=False)
    monkeypatch.setattr(server, "POPULAR_UNIVERSE", ["C"])
    cached = await list_all_tickers(limit=1000, page=1, refresh=False)
    refreshed = await list_all_tickers(limit=1000, page=1, refresh=True)
    assert first["tickers"] == cached["tickers"] == ["A", "B"]
    assert refreshed["tickers"] == ["C"] and not refreshed["cached"]
    assert refreshed["source"] == "featured-universe" and not refreshed["complete_exchange_catalog"]

@pytest.mark.asyncio
async def test_empty_featured_list_is_honest(monkeypatch):
    import server
    monkeypatch.setattr(server, "POPULAR_UNIVERSE", [])
    result = await list_all_tickers(limit=1000, page=1, refresh=False)
    assert result["tickers"] == [] and result["total"] == 0 and not result["has_more"]

@pytest.mark.asyncio
async def test_configured_symbols_are_deduplicated_and_changes_visible(monkeypatch):
    monkeypatch.setenv("FLOWW_PUBLIC_UNIVERSE", " spy,QQQ, SPY,, ")
    result = await list_all_tickers(limit=1000, page=1, refresh=False)
    assert result["tickers"] == ["QQQ", "SPY"]
    assert not result["cached"] and result["cached_age_s"] is None
    monkeypatch.setenv("FLOWW_PUBLIC_UNIVERSE", "IBM")
    assert (await list_all_tickers(limit=1000, page=1, refresh=False))["tickers"] == ["IBM"]
