"""
Tests for GET /api/backtest/report/{ticker} (ROADMAP Phase 6.2 remainder).

Contract:
- GET before any POST /run → {"status": "not_found", ...}
- POST /run then GET → identical report payload (status ok, same ticker).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("API_SECRET_KEY", "test-secret-key")
    return TestClient(app, headers={"X-API-Key": "test-secret-key"})


def _payload(ticker: str) -> dict:
    bars, snaps = [], []
    price = 500.0
    for i in range(40):
        price += 1.0 if i % 2 == 0 else -0.5
        bars.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": price, "high": price + 1, "low": price - 1,
            "close": price, "volume": 1_000_000,
        })
        snaps.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "net_gex": 1e9 if i % 2 == 0 else -1e9,
            "net_gex_zscore_60d": -1.5 if i % 2 == 0 else 1.5,
            "spot": price,
        })
    return {"ticker": ticker, "snapshots": snaps, "bars": bars}


def test_report_not_found_before_run(client: TestClient):
    resp = client.get("/api/backtest/report/ZZNOTRUN")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "not_found"
    assert body["ticker"] == "ZZNOTRUN"


def test_run_stores_report_retrievable(client: TestClient):
    run = client.post("/api/backtest/run", json=_payload("ZZRPT"))
    assert run.status_code == 200
    assert run.json()["status"] == "ok"

    rep = client.get("/api/backtest/report/ZZRPT")
    assert rep.status_code == 200
    body = rep.json()
    assert body["status"] == "ok"
    assert body["result"]["ticker"] == "ZZRPT"
    assert body == run.json()


def test_report_ticker_case_insensitive(client: TestClient):
    client.post("/api/backtest/run", json=_payload("zzcase"))
    rep = client.get("/api/backtest/report/ZZCASE")
    assert rep.status_code == 200
    assert rep.json()["status"] == "ok"
