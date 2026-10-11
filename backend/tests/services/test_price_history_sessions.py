"""Session coverage: regular vs all-sessions bars (24/5 lane).

RED first: route has no sessions param (all-sessions reads impossible),
frames drop the provider session label. Provider monkeypatched.
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
        return [{"t": "2026-10-06T14:00:00Z", "o": 100, "h": 102, "l": 99,
                 "c": 101, "v": 5000, "session": kwargs.get("sessions", "regular")}]

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


def test_all_sessions_reaches_provider_and_frames_carry_labels(history_client):
    client, calls = history_client
    resp = client.get("/api/heatseeker/price-history/SPY",
                      params={"days": 5, "sessions": "all"})
    assert resp.status_code == 200, resp.text
    assert calls == [("SPY", {"period": "WEEK", "aggregation": "FIVE_MINUTES",
                              "sessions": "all"})]
    frames = resp.json()["frames"]
    assert frames and all("session" in f for f in frames)
    assert frames[0]["session"] == "all"


def test_regular_default_keeps_labels(history_client):
    client, calls = history_client
    resp = client.get("/api/heatseeker/price-history/SPY", params={"days": 5})
    assert resp.status_code == 200, resp.text
    assert calls[0][1]["sessions"] == "regular"
    assert resp.json()["frames"][0]["session"] == "regular"


def test_unknown_sessions_refused(history_client):
    client, _ = history_client
    assert client.get("/api/heatseeker/price-history/SPY",
                      params={"days": 5, "sessions": "overnight"}).status_code == 422
