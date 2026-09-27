"""Route-level proof the #4/#5 overlay is actually mounted.

The pure service tests pin the math; this pins the wiring — that a real
HTTP call reaches the confluence scorer and the flow read, and that the
degraded path stays honest instead of 500ing.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import heatseeker as H


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(H.router)
    return app


def _contract(strike: float, is_call: bool, gamma: float = 0.02,
              oi: float = 100.0, vol: float = 100.0) -> dict:
    return {
        "strike": strike,
        "type": "call" if is_call else "put",
        "gamma": gamma,
        "oi": oi,
        "total_volume": vol,
    }


@pytest.fixture
def _stub_chain(monkeypatch):
    async def fake_fetch(ticker, expiries):
        return {
            "spot": 500.0,
            "contracts": [
                _contract(500.0, True, vol=900.0),
                _contract(500.0, False, vol=100.0),
                _contract(495.0, False, vol=800.0),
                _contract(495.0, True, vol=50.0),
            ],
        }

    monkeypatch.setattr(H, "_fetch_chain", fake_fetch)


def test_node_confluence_route_returns_rows(_stub_chain):
    c = TestClient(_app())
    r = c.get("/api/heatseeker/node-confluence?ticker=SPY&expiries=1&include_flow=false")

    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["ticker"] == "SPY"
    assert body["spot"] == 500.0
    assert body["rows"], "must return per-strike rows"
    assert body["strikes_considered"] >= 1
    # Ranks by |GEX| desc.
    abs_gex = [abs(row["gex"]) for row in body["rows"]]
    assert abs_gex == sorted(abs_gex, reverse=True)


def test_node_confluence_route_carries_honest_dimension_status(_stub_chain):
    c = TestClient(_app())
    body = c.get("/api/heatseeker/node-confluence?ticker=SPY&expiries=1&include_flow=false").json()

    dims = body["rows"][0]["confluence"]["dimensions"]
    assert dims["structure"]["inputs_status"] == "context_only", (
        "gamma magnitude is unsigned context, not a direction"
    )
    for dim in ("ml", "vol", "time_delta"):
        assert dims[dim]["inputs_status"] == "missing", (
            f"{dim} has no per-strike input and must be reported missing"
        )
        assert dims[dim]["contribution"] == 0.0


def test_node_confluence_route_flags_flow_disabled_honestly(_stub_chain):
    c = TestClient(_app())
    body = c.get("/api/heatseeker/node-confluence?ticker=SPY&expiries=1&include_flow=false").json()
    assert body["flow_status"] == "disabled", "a disabled input is not a pass"


def test_node_confluence_route_404s_on_empty_chain(monkeypatch):
    async def empty(ticker, expiries):
        return {"spot": 0, "contracts": []}

    monkeypatch.setattr(H, "_fetch_chain", empty)
    c = TestClient(_app())
    r = c.get("/api/heatseeker/node-confluence?ticker=XXX&expiries=1")
    assert r.status_code == 404, "no data is a 404, not a fabricated empty board"


def test_node_confluence_route_degrades_instead_of_500(monkeypatch):
    async def boom(ticker, expiries):
        raise RuntimeError("chain fetch exploded")

    monkeypatch.setattr(H, "_fetch_chain", boom)
    c = TestClient(_app())
    r = c.get("/api/heatseeker/node-confluence?ticker=SPY&expiries=1")
    assert r.status_code == 200, "the panel must self-recover, not error out"
    body = r.json()
    assert body["status"] == "degraded"
    assert body["rows"] == []
    assert "exploded" in body["error"]


def test_route_is_registered():
    """The endpoint must be discoverable, not just importable."""
    paths = {getattr(r, "path", "") for r in H.router.routes}
    assert "/api/heatseeker/node-confluence" in paths, (
        f"routes seen: {sorted(p for p in paths if 'node' in p)}"
    )
