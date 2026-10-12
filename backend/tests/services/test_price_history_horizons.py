"""Long horizons: daily bars up to ten years (PUBLIC_MAXIMIZATION P1).

RED first: days is capped at 20 (422 beyond). Provider monkeypatched.
Snapshots only cover recent days — old frames keep honest nulls; this
suite pins the period/aggregation brackets and the compat floor.

Round 6 (2026-10-11, Hermes re-audit): the TEN_YEARS period label is
REJECTED by Public.com's live gateway (400 on /historicdata/EQUITY/SPY/
TEN_YEARS/ONE_DAY); FIVE_YEARS is the longest period the provider
serves (1255 daily bars). The 10-year UI option must therefore request
FIVE_YEARS — the provider-verified maximum — never a label Public 400s
on. Yamato's original test mocked the provider so the bad label passed.
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
        return [{"t": "2026-10-06T14:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101, "v": 5000}]

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


@pytest.mark.parametrize(("days", "period"), [(60, "QUARTER"), (260, "YEAR"), (2600, "FIVE_YEARS")])
def test_long_horizons_fetch_daily_brackets(history_client, days, period):
    client, calls = history_client
    resp = client.get("/api/heatseeker/price-history/SPY", params={"days": days})
    assert resp.status_code == 200, resp.text
    assert calls == [("SPY", {"period": period, "aggregation": "ONE_DAY", "sessions": "regular"})]
    assert resp.json()["bar_seconds"] == 86400
    assert resp.json()["frames"][0]["duration_seconds"] == 86400


def test_ten_year_option_never_requests_rejected_period(history_client):
    """The 10-year picker option must map to a period Public's gateway
    actually serves. TEN_YEARS 400s live; FIVE_YEARS is the max."""
    client, calls = history_client
    resp = client.get("/api/heatseeker/price-history/SPY", params={"days": 2600})
    assert resp.status_code == 200, resp.text
    requested = calls[0][1]["period"]
    assert requested in {"FIVE_YEARS", "YEAR"}, (
        f"period {requested!r} is not served by api.public.com historicdata; "
        "TEN_YEARS returns HTTP 400 from the live gateway"
    )


def test_short_horizons_unchanged(history_client):
    client, calls = history_client
    assert client.get("/api/heatseeker/price-history/SPY", params={"days": 5}).status_code == 200
    assert calls == [("SPY", {"period": "WEEK", "aggregation": "FIVE_MINUTES", "sessions": "regular"})]


@pytest.mark.parametrize("bad", [0, 2601, -5])
def test_out_of_range_days_refused(history_client, bad):
    client, _ = history_client
    assert client.get("/api/heatseeker/price-history/SPY", params={"days": bad}).status_code == 422
