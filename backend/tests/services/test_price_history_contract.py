"""M3 contract premium path: per-contract OHLCV via Public OSI bars.

RED first: route has no contract_symbol param (422/ignored). Provider
functions monkeypatched — no network, no real spend.
"""
import sys
from types import SimpleNamespace

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.price_history import router
from services.connection_guard import connection_lock
from services.heatmap_history import ensure_tables

UNDERLYING = [{"t": "2026-10-06T14:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101, "v": 5000}]
CONTRACT = [
    {"t": "2026-10-06T14:00:00Z", "o": 5.0, "h": 5.4, "l": 4.8, "c": 5.2, "v": 120},
    {"t": "2026-10-06T14:30:00Z", "o": 5.2, "h": 5.6, "l": 5.0, "c": 5.5, "v": 90},
]


@pytest.fixture
def history_client(monkeypatch):
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    calls = []

    def query(sql, args):
        with connection_lock(conn):
            result = conn.execute(sql, args)
            names = [column[0] for column in result.description]
            return [dict(zip(names, row, strict=True)) for row in result.fetchall()]

    async def bars(ticker, **kwargs):
        calls.append((ticker, kwargs))
        if kwargs.get("instrument_type") == "OPTION":
            return list(CONTRACT)
        return list(UNDERLYING)

    class Budget:
        async def acquire(self, host):
            assert host == "api.public.com"

        def release(self):
            pass

    monkeypatch.setitem(sys.modules, "services.duckdb_engine", SimpleNamespace(db=SimpleNamespace(conn=conn, query_strict=query)))
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval", bars)
    monkeypatch.setattr("services.public_budget.budget", Budget())
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client, calls
    conn.close()


def test_contract_bars_ride_along_with_own_premium_axis(history_client):
    client, calls = history_client
    resp = client.get("/api/heatseeker/price-history/SPY",
                      params={"days": 5, "interval_minutes": 30,
                              "contract_symbol": "SPY261017C00650000"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contract_status"] == "available"
    assert body["contract_symbol"] == "SPY261017C00650000"
    assert [b["c"] for b in body["contract_bars"]] == [5.2, 5.5]
    # Underlying candles keep their own dollars — no mixing.
    assert body["frames"][0]["close"] == 101
    option_calls = [c for c in calls if c[1].get("instrument_type") == "OPTION"]
    assert len(option_calls) == 1
    assert option_calls[0][0] == "SPY261017C00650000"


def test_missing_contract_bars_stay_explicitly_unavailable(history_client, monkeypatch):
    async def no_contract(ticker, **kwargs):
        if kwargs.get("instrument_type") == "OPTION":
            return None
        return list(UNDERLYING)
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval", no_contract)
    client, _ = history_client
    resp = client.get("/api/heatseeker/price-history/SPY",
                      params={"days": 5, "contract_symbol": "SPY261017C00650000"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contract_status"] == "unavailable"
    assert body["contract_bars"] == []
    assert body["price_status"] == "available"


def test_no_contract_param_means_not_requested(history_client):
    client, calls = history_client
    resp = client.get("/api/heatseeker/price-history/SPY", params={"days": 5})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contract_status"] == "not_requested"
    assert body["contract_bars"] == []
    assert all(c[1].get("instrument_type") != "OPTION" for c in calls)


@pytest.mark.parametrize("bad", ["x" * 33, "SPY C500!!!", ""])
def test_bad_contract_symbol_is_refused_before_any_provider_read(history_client, bad):
    client, calls = history_client
    before = len(calls)
    assert client.get("/api/heatseeker/price-history/SPY",
                      params={"days": 5, "contract_symbol": bad}).status_code == 422
    assert len(calls) == before
