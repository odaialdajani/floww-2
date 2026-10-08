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


def test_unknown_side_is_counted_as_missing_at_its_strike():
    doc = exposure_by_strike(payload([row(780, "call", 1000, 0.011),
                                      row(780, "unknown", 1000, 0.011)]))
    rec = by_strike(doc)[780]
    assert (rec["n_measured"], rec["n_total"], rec["partial"]) == (1, 2, True)
    assert rec["gex_basis"] == "OI_PARTIAL"
    assert doc["coverage"]["dropped_unknown_side"] == 1


def test_quarantined_zero_does_not_become_measured_zero():
    doc = exposure_by_strike(payload([{**row(780, "call", 0, None), "adjusted": True}]))
    rec = by_strike(doc)[780]
    assert rec["gex"] is None and rec["n_measured"] == 0
    assert rec["unknown_reasons"] == {"CONTRACT_QUARANTINED": 1}


def test_source_clocks_and_failed_expiry_coverage_survive_projection():
    source = {**payload([row(780, "call", 1000, 0.011)]),
              "event_time": None, "fetched_at": "2026-10-07T14:01:00Z",
              "spot_event_time": "2026-10-07T14:00:00Z", "spot_fetched_at": "2026-10-07T14:00:02Z",
              "received_at": "2026-10-07T14:01:01Z", "cache_age_s": 12.5,
              "skipped": [{"expiry": "2026-10-08", "reason": "UPSTREAM_FAILED"}],
              "expiries_attempted": [EXP, "2026-10-08"], "attempt_cap": 4}
    doc = exposure_by_strike(source)
    for key in ("event_time", "fetched_at", "spot_event_time", "spot_fetched_at", "received_at", "cache_age_s"):
        assert key in doc and doc[key] == source[key]
    assert doc["source_coverage"]["skipped"] == source["skipped"]
    assert doc["coverage"]["returned"] == 1


def test_paired_consumer_fixture_matches_canonical_producer():
    import json

    fixture = json.loads((BACKEND.parent / "frontend/src/test-fixtures/triad-exposure.paired.json").read_text())
    assert exposure_by_strike(fixture["input"]) == fixture["expected"]


def test_chain_carries_series_from_same_raw_snapshot_before_row_filtering(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routes.public_api as api

    source = {**payload([row(780, "call", 1000, 0.011), row(780, "unknown", 1000, 0.011)]),
              "fetched_at": "2026-10-07T14:00:00Z", "expiries": [EXP]}
    calls = []

    async def fake_fetch(ticker, max_expiries=4):
        calls.append(ticker)
        return source

    monkeypatch.setattr(api, "fetch_chain_from_public_api", fake_fetch)
    app = FastAPI()
    app.include_router(api.router)
    body = TestClient(app).get(f"/api/public/chain/SPY?expiration={EXP}").json()
    assert calls == ["SPY"]
    series = body["exposure_by_strike"]
    assert series["fetched_at"] == body["fetched_at"] == source["fetched_at"]
    assert by_strike(series)[780]["n_total"] == 2
    assert by_strike(series)[780]["partial"] is True


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
