"""Candle intervals travel unchanged through the read-only price-history route."""
import sys
from types import SimpleNamespace

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.price_history import router
from services.connection_guard import connection_lock
from services.heatmap_history import ensure_tables


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
        return [{"t": "2026-10-06T14:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101}]

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


def test_explicit_half_hour_candles_do_not_silently_use_five_minutes(history_client):
    client, calls = history_client
    response = client.get("/api/heatseeker/price-history/SPY", params={"days": 5, "interval_minutes": 30})
    assert response.status_code == 200
    assert calls == [("SPY", {"period": "WEEK", "aggregation": "THIRTY_MINUTES", "sessions": "regular"})]
    assert response.json()["bar_seconds"] == 1800


@pytest.mark.parametrize(("minutes", "aggregation"), [(1, "ONE_MINUTE"), (5, "FIVE_MINUTES"), (15, "FIFTEEN_MINUTES"), (30, "THIRTY_MINUTES"), (60, "ONE_HOUR")])
def test_selected_interval_preserves_owning_price_candle_times(history_client, minutes, aggregation):
    client, calls = history_client
    response = client.get("/api/heatseeker/price-history/SPY", params={"days": 20, "interval_minutes": minutes})
    assert response.status_code == 200
    assert calls[0][1]["aggregation"] == aggregation
    assert response.json()["bar_seconds"] == minutes * 60
    assert response.json()["frames"][0]["time"] == "2026-10-06T14:00:00+00:00"
    assert response.json()["frames"][0]["nodes"] == []


@pytest.mark.parametrize("minutes", [0, 2, 31, 61, "invalid"])
def test_unsupported_intervals_cannot_start_a_provider_read(history_client, minutes):
    client, calls = history_client
    assert client.get("/api/heatseeker/price-history/SPY", params={"interval_minutes": minutes}).status_code == 422
    assert calls == []


def test_older_callers_keep_their_existing_default(history_client):
    client, calls = history_client
    response = client.get("/api/heatseeker/price-history/SPY", params={"days": 5})
    assert response.status_code == 200
    assert calls[0][1]["aggregation"] == "FIVE_MINUTES"


def test_selected_window_keeps_only_requested_trading_sessions(history_client, monkeypatch):
    client, _ = history_client

    async def long_history(ticker, **kwargs):
        return [{"t": f"2026-10-{day:02}T14:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101} for day in (1, 2, 5, 6)]

    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval", long_history)
    response = client.get("/api/heatseeker/price-history/SPY", params={"days": 1, "interval_minutes": 30})
    assert response.status_code == 200
    assert [frame["time"][:10] for frame in response.json()["frames"]] == ["2026-10-06"]
    assert response.json()["price_sessions_returned"] == 1
