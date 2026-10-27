"""Focused ASGI regression: the literal /data-quality/history must win over /data-quality/{ticker}.

Root reproduced (2026-10-26): GET /api/data-quality/history returned
{"ticker":"HISTORY","status":"INSUFFICIENT_DATA",...} because the parameter route is
registered before the literal route inside routes/data_quality_api.py. FastAPI matches
routes in registration order, so the literal handler never runs and the word "history"
is treated as a ticker (triggering provider lookups for a non-existent symbol).

This test pins BOTH directions:
- the literal handler answers /data-quality/history (per-process history shape: the
  "history"/"metrics" keys; NO "ticker" field; no provider lookup for a symbol named
  "history");
- an ordinary ticker still routes to the parameter handler.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.data_quality_api import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_literal_history_route_wins_over_parameter_route() -> None:
    resp = _client().get("/api/data-quality/history")
    assert resp.status_code == 200
    body = resp.json()
    # The literal handler's shape: per-process history + metrics, never a "ticker" field.
    assert "ticker" not in body, (
        "the literal /data-quality/history route was captured by /data-quality/{ticker} "
        f"(got the ticker-shaped body {body})"
    )
    assert "history" in body and "metrics" in body


def test_ordinary_ticker_still_routes_to_parameter_handler() -> None:
    resp = _client().get("/api/data-quality/SPY")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ticker") == "SPY", f"the parameter route must keep serving tickers, got {body}"
