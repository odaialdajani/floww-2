"""T2 /api/tickers/all: paged full universe + cache (TDD: 404 on main)."""
import pytest

from routes.market_data import list_all_tickers


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    import server as server_mod
    monkeypatch.setattr(server_mod, "_TICKER_CACHE", None)
    monkeypatch.setattr(server_mod, "_TICKER_CACHE_TS", None)


def _fake_client(symbols, calls):
    class FakeClient:
        def symbols_us_equities(self):
            calls["n"] += 1
            return list(symbols)
    return FakeClient


def test_pagination_math(monkeypatch):
    import services.finnhub_client as fc_mod
    calls = {"n": 0}
    syms = [f"S{i:05d}" for i in range(2500)]
    monkeypatch.setattr(fc_mod, "FinnhubClient", lambda: _fake_client(syms, calls)())

    import asyncio
    p1 = asyncio.run(list_all_tickers(limit=1000, page=1, refresh=False))
    assert p1["total"] == 2500
    assert len(p1["tickers"]) == 1000
    assert p1["tickers"][0] == "S00000"
    assert p1["has_more"] is True
    p3 = asyncio.run(list_all_tickers(limit=1000, page=3, refresh=False))
    assert len(p3["tickers"]) == 500
    assert p3["has_more"] is False
    assert calls["n"] == 1, "pages 1+3 share one cached fetch"


def test_refresh_bypasses_cache(monkeypatch):
    import services.finnhub_client as fc_mod
    calls = {"n": 0}
    monkeypatch.setattr(
        fc_mod, "FinnhubClient",
        lambda: _fake_client(["A", "B"], calls)())
    import asyncio
    asyncio.run(list_all_tickers(limit=1000, page=1, refresh=False))
    asyncio.run(list_all_tickers(limit=1000, page=1, refresh=True))
    assert calls["n"] == 2


def test_no_key_returns_empty(monkeypatch):
    import services.finnhub_client as fc_mod

    class NoKey:
        def symbols_us_equities(self):
            return None

    monkeypatch.setattr(fc_mod, "FinnhubClient", NoKey)
    import asyncio
    out = asyncio.run(list_all_tickers(limit=1000, page=1, refresh=False))
    assert out["tickers"] == [] and out["total"] == 0
    assert out["has_more"] is False


def test_symbols_us_equities_unit(monkeypatch):
    from services.finnhub_client import FinnhubClient

    class Raw:
        def symbol_list(self):
            return [{"symbol": "b"}, {"symbol": "A "}, {"symbol": "a"},
                    {"symbol": ""}, {"symbol": "C"}]

    c = FinnhubClient.__new__(FinnhubClient)
    c._client = Raw()
    assert c.symbols_us_equities() == ["A", "B", "C"]

    c2 = FinnhubClient.__new__(FinnhubClient)
    c2._client = None
    assert c2.symbols_us_equities() is None
