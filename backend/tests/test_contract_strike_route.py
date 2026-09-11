"""
backend/tests/test_contract_strike_route.py — SOFI degraded ticket fix.

TrinityView calls GET /api/contract/{ticker}/{strike}/{expiry} to enrich a
strike selection with live bid/ask/last + greeks. Only
GET /api/contract/{ticker} existed, so enrichment 404'd and QuickTradePanel
rendered the SOFI screenshot state: IV —, Delta —, OI —, Est $—, Max —,
Notional $0.

Contract:
- routes.analytics exposes contracts_for_strike_expiry() pure helper
- router has GET /contract/{ticker}/{strike}/{expiry}
- helper maps chain rows -> frontend shape:
  {type, strike, expiry, iv, delta, bid, ask, last, open_interest, oi,
   volume, osi=None} ; midpoint -> last fallback
- strike match is float-tolerant (22 vs 22.0), expiry exact string match
- missing strike/expiry -> [] (never raise)
"""
from __future__ import annotations


def test_route_exists():
    from routes.analytics import router

    paths = sorted(
        getattr(r, "path", "") for r in router.routes if hasattr(r, "path")
    )
    assert "/contract/{ticker}/{strike}/{expiry}" in paths


def test_helper_maps_frontend_shape():
    from routes.analytics import contracts_for_strike_expiry

    rows = [
        {"type": "call", "strike": 22.0, "expiry": "2026-09-18",
         "iv": 0.55, "delta": 0.28, "bid": 0.45, "ask": 0.55,
         "midpoint": 0.50, "oi": 1200, "volume": 88},
        {"type": "put", "strike": 22.0, "expiry": "2026-09-18",
         "iv": 0.60, "delta": -0.30, "bid": 1.20, "ask": 1.40,
         "midpoint": 0.0, "oi": 3400, "volume": 12},
        {"type": "call", "strike": 20.0, "expiry": "2026-09-18",
         "iv": 0.50, "delta": 0.40, "bid": 1.0, "ask": 1.1,
         "midpoint": 1.05, "oi": 10, "volume": 1},
    ]
    out = contracts_for_strike_expiry(rows, 22, "2026-09-18")
    assert len(out) == 2
    call = next(c for c in out if c["type"] == "call")
    put = next(c for c in out if c["type"] == "put")
    # midpoint -> last fallback
    assert call["last"] == 0.50
    # midpoint 0 -> mid of bid/ask
    assert put["last"] == __import__("pytest").approx(1.30)
    # frontend reads open_interest, backend stores oi — ship both
    assert call["open_interest"] == 1200
    assert call["oi"] == 1200
    assert call["bid"] == 0.45 and call["ask"] == 0.55
    assert call["iv"] == 0.55 and call["delta"] == 0.28
    assert "osi" in call


def test_helper_miss_returns_empty():
    from routes.analytics import contracts_for_strike_expiry

    rows = [{"type": "call", "strike": 22.0, "expiry": "2026-09-18"}]
    assert contracts_for_strike_expiry(rows, 999, "2026-09-18") == []
    assert contracts_for_strike_expiry(rows, 22, "2030-01-01") == []
    assert contracts_for_strike_expiry([], 22, "2026-09-18") == []
