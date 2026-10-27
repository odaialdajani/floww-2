"""Focused regression — paper-trading route input validation (paper-recovery B6).

``/api/paper-trading/submit|execute|estimate-cost`` forwarded unchecked body
fields into the engine: negative/zero/non-integer quantities were ACCEPTED,
non-numeric quantities and zero-bid/ask markets crashed with 5xx
(ZeroDivisionError/TypeError) instead of 4xx. RED on base 56f218ed; GREEN
after route-level validation. Success shapes are unchanged (compatibility-
preserving); every refusal is HTTP 400 with the same reason-first style the
router already uses for engine rejections.

The router is exercised on an isolated FastAPI app with a fresh in-memory
PaperTradingEngine per test — no server import, no Mongo, no network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from routes.paper_trading import router, set_paper_engine  # noqa: E402
from services.paper_trading import PaperTradingEngine  # noqa: E402


def _client(engine=None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    set_paper_engine(engine or PaperTradingEngine(initial_capital=100_000))
    return TestClient(app)


def _valid_market(bid=100.0, ask=100.1):
    return {"symbol": "SPY", "bid": bid, "ask": ask, "last": (bid + ask) / 2,
            "bid_size": 100, "ask_size": 100, "volume": 1_000_000, "volatility": 0.2}


def _submit(client, **body):
    payload = {"symbol": "SPY", "side": "buy", "quantity": 1}
    payload.update(body)
    return client.post("/api/paper-trading/submit", json=payload)


class TestSubmitValidation:
    def test_negative_quantity_refused(self):
        r = _submit(_client(), quantity=-5)
        assert r.status_code == 400, r.text

    def test_zero_quantity_refused(self):
        r = _submit(_client(), quantity=0)
        assert r.status_code == 400, r.text

    def test_non_integer_quantity_refused(self):
        r = _submit(_client(), quantity="abc")
        assert r.status_code == 400, r.text

    def test_fractional_quantity_refused(self):
        r = _submit(_client(), quantity=1.5)
        assert r.status_code == 400, r.text

    def test_integral_float_quantity_accepted_for_compatibility(self):
        r = _submit(_client(), quantity=2.0)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "accepted"

    def test_unknown_side_refused(self):
        r = _submit(_client(), side="hold")
        assert r.status_code == 400, r.text

    def test_empty_symbol_refused(self):
        r = _submit(_client(), symbol="")
        assert r.status_code == 400, r.text

    def test_valid_submit_still_accepted(self):
        r = _submit(_client())
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "accepted"


class TestExecuteValidation:
    def test_empty_order_id_refused_not_500(self):
        r = _client().post("/api/paper-trading/execute",
                           json={"order_id": "", "market": _valid_market()})
        assert r.status_code == 400, r.text

    def test_unknown_order_id_refused_not_500(self):
        r = _client().post("/api/paper-trading/execute",
                           json={"order_id": "PAPER-999999", "market": _valid_market()})
        assert r.status_code == 400, r.text

    def test_zero_bid_ask_market_refused_not_500(self):
        client = _client()
        order_id = _submit(client).json()["order_id"]
        r = client.post("/api/paper-trading/execute",
                        json={"order_id": order_id, "market": _valid_market(0, 0)})
        assert r.status_code == 400, r.text

    def test_nonfinite_market_refused(self):
        # httpx2 refuses to JSON-encode inf client-side, but the wire form
        # json.loads accepts (exponent overflow 1e999 -> inf) must still be
        # refused by the route, never reach the engine as a 5xx.
        client = _client()
        order_id = _submit(client).json()["order_id"]
        body = json.dumps({"order_id": order_id,
                           "market": {**_valid_market(), "ask": 1e999}})
        r = client.post("/api/paper-trading/execute", content=body,
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 400, r.text

    def test_valid_execute_still_fills(self):
        client = _client()
        order_id = _submit(client).json()["order_id"]
        r = client.post("/api/paper-trading/execute",
                        json={"order_id": order_id, "market": _valid_market()})
        assert r.status_code == 200, r.text
        assert r.json()["filled_qty"] == 1

    def test_duplicate_execute_refused_not_500(self):
        client = _client()
        order_id = _submit(client).json()["order_id"]
        first = client.post("/api/paper-trading/execute",
                            json={"order_id": order_id, "market": _valid_market()})
        assert first.status_code == 200
        again = client.post("/api/paper-trading/execute",
                            json={"order_id": order_id, "market": _valid_market()})
        assert again.status_code == 400, again.text


class TestEstimateCostValidation:
    def test_zero_market_refused(self):
        r = _client().post("/api/paper-trading/estimate-cost",
                           json={"symbol": "SPY", "side": "buy", "quantity": 1,
                                 "market": _valid_market(0, 0)})
        assert r.status_code == 400, r.text

    def test_negative_quantity_refused(self):
        r = _client().post("/api/paper-trading/estimate-cost",
                           json={"symbol": "SPY", "side": "buy", "quantity": -1,
                                 "market": _valid_market()})
        assert r.status_code == 400, r.text

    def test_valid_estimate_still_returns(self):
        r = _client().post("/api/paper-trading/estimate-cost",
                           json={"symbol": "SPY", "side": "buy", "quantity": 1,
                                 "market": _valid_market()})
        assert r.status_code == 200, r.text


class TestStatusEndpointsUntouched:
    def test_status_route_shape_unchanged(self):
        r = _client().get("/api/paper-trading/status")
        assert r.status_code == 200
        assert "cash" in r.json()
