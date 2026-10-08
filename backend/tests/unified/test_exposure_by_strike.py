"""C17: admitted per-strike exposure series (OpenCode takeover).

Failed-first note: every pin below reads `n_measured` / `partial` keys the
baseline `project_triad_from_chain` never emitted (KeyError on baseline) —
RED by construction there, GREEN here. No new metric: subtotals aggregate
admitted per-row canonical gex; counts are bookkeeping.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.triad_projection import (  # noqa: E402
    FORMULA_VERSION,
    TRIAD_PROJECTION_VERSION,
    exposure_by_strike,
)

EXP = "2026-09-30"


def row(strike, kind, oi, gamma, expiry=EXP):
    return {"osi": f"X{strike}{kind}", "expiry": expiry, "type": kind,
            "strike": strike, "oi": oi, "gamma": gamma, "delta": 0.5,
            "volume": 10}


def payload(contracts, spot=450.0):
    return {"ticker": "SPY", "spot": spot, "contracts": contracts,
            "data_source": "synthetic-test"}


def by_strike(doc):
    return {r["strike"]: r for r in doc["strikes"]}


def test_partial_strike_marks_counts_not_completeness():
    doc = exposure_by_strike(payload([
        row(780, "call", 1000, 0.011),
        {**row(780, "put", 1000, 0.009), "oi": None},  # unknown sibling
    ]))
    rec = by_strike(doc)[780]
    assert rec["partial"] is True
    assert rec["n_measured"] == 1 and rec["n_total"] == 2
    assert doc["coverage"]["partial_strikes"] == 1


def test_all_unknown_strike_is_null_never_zero():
    doc = exposure_by_strike(payload([
        {**row(785, "call", 1000, 0.011), "oi": None},
        {**row(785, "put", 1000, 0.009), "gamma": None},
    ]))
    rec = by_strike(doc)[785]
    assert rec["gex"] is None and rec["partial"] is False
    assert rec["n_measured"] == 0 and rec["n_total"] == 2
    assert doc["coverage"]["unknown_strikes"] == 1


def test_measured_zero_stays_zero_and_complete():
    doc = exposure_by_strike(payload([
        row(790, "call", 0, 0.011),
        row(790, "put", 0, 0.009),
    ]))
    rec = by_strike(doc)[790]
    assert rec["gex"] == 0.0 and rec["partial"] is False
    assert rec["n_measured"] == 2


def test_fractional_strikes_stay_distinct_and_versioned():
    doc = exposure_by_strike(payload([
        row(100.25, "call", 1000, 0.011),
        row(100.75, "call", 1000, 0.011),
    ]))
    assert set(by_strike(doc)) == {100.25, 100.75}
    assert doc["series_version"] == TRIAD_PROJECTION_VERSION
    assert doc["formula_version"] == FORMULA_VERSION
    assert doc["coverage"]["rows_measured"] == doc["coverage"]["rows_total"] == 2


def test_empty_and_missing_contracts_degrade_honestly():
    assert exposure_by_strike({"ticker": "SPY", "spot": 450.0, "contracts": []})["strikes"] == []
    assert exposure_by_strike(None)["strikes"] == []


def test_endpoint_serves_the_series_without_order_surfaces(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routes.public_api as api

    async def fake_fetch(ticker, max_expiries=4):
        return {"ticker": ticker, "spot": 450.0, "data_source": "synthetic-test",
                "contracts": [
                    {"osi": "A", "expiry": EXP, "type": "call", "strike": 780,
                     "oi": 1000, "gamma": 0.011, "delta": 0.5, "volume": 10},
                    {"osi": "B", "expiry": EXP, "type": "put", "strike": 780,
                     "oi": None, "gamma": 0.009, "delta": -0.4, "volume": 10},
                ]}

    monkeypatch.setattr(api, "fetch_chain_from_public_api", fake_fetch)
    app = FastAPI()
    app.include_router(api.router)  # router already carries /api/public
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/public/chain/SPY/exposure-by-strike")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["series_version"] == TRIAD_PROJECTION_VERSION
    rec = {r["strike"]: r for r in body["strikes"]}[780]
    assert rec["partial"] is True and rec["n_measured"] == 1
    assert set(body) >= {"ok", "series_version", "formula_version", "ticker",
                         "spot", "strikes", "coverage", "data_source", "stale"}
    assert not any("order" in getattr(route, "path", "") or "broker" in getattr(route, "path", "")
                   for route in app.routes)
