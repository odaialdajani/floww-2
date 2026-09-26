"""Full provider catalog pagination remains independent of custom scan lists."""
from unittest.mock import AsyncMock

import pytest

from routes.market_data import list_all_tickers
from services import market_catalog


@pytest.mark.asyncio
async def test_pagination_retains_every_provider_ticker(monkeypatch):
    data = {"instruments": [{"symbol": f"S{i:05d}"} for i in range(13135)],
            "total": 13135, "source": "public-instruments", "complete_exchange_catalog": False,
            "complete_provider_catalog": True, "stale": False}
    monkeypatch.setattr(market_catalog, "get_catalog", AsyncMock(return_value=data))
    first = await list_all_tickers(limit=5000, page=1, refresh=False)
    last = await list_all_tickers(limit=5000, page=3, refresh=False)
    assert first["total"] == 13135 and len(first["tickers"]) == 5000 and first["has_more"]
    assert len(last["tickers"]) == 3135 and not last["has_more"]
    assert last["tickers"][-1] == "S13134"
    assert first["source"] == "public-instruments" and not first["complete_exchange_catalog"]


@pytest.mark.asyncio
async def test_custom_scan_list_does_not_restrict_full_browse(monkeypatch):
    monkeypatch.setenv("FLOWW_PUBLIC_UNIVERSE", "SPY")
    data = {"instruments": [{"symbol": "AAPL"}, {"symbol": "SPY"}], "total": 2}
    monkeypatch.setattr(market_catalog, "get_catalog", AsyncMock(return_value=data))
    result = await list_all_tickers(limit=1000, page=1, refresh=False)
    assert result["tickers"] == ["AAPL", "SPY"]


@pytest.mark.asyncio
async def test_refresh_and_stale_flags_remain_truthful(monkeypatch):
    load = AsyncMock(return_value={"instruments": [], "total": 0,
                                  "stale": True, "complete_provider_catalog": False})
    monkeypatch.setattr(market_catalog, "get_catalog", load)
    result = await list_all_tickers(limit=1000, page=1, refresh=True)
    load.assert_awaited_once_with(refresh=True)
    assert result["tickers"] == [] and not result["has_more"]
    assert result["stale"] and not result["complete_provider_catalog"]


def test_symbols_us_equities_unit(monkeypatch):
    from services.finnhub_client import FinnhubClient

    class Raw:
        def stock_symbols(self, exchange):
            assert exchange == "US"
            return [{"symbol": "b"}, {"symbol": "A "}, {"symbol": "a"},
                    {"symbol": ""}, {"symbol": "C"}]

    c = FinnhubClient.__new__(FinnhubClient)
    c._client = Raw()
    assert c.symbols_us_equities() == ["A", "B", "C"]

    c2 = FinnhubClient.__new__(FinnhubClient)
    c2._client = None
    assert c2.symbols_us_equities() is None
