"""Universe scan + leaderboard routes: shape, cache, budget-honest."""
from __future__ import annotations
import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.flowseeker import router

def _app():
    app = FastAPI()
    app.include_router(router)
    return app

def _seed_board(monkeypatch):
    import routes.flowseeker as F
    F._UNIVERSE_SCAN_CACHE.update({"ts": 0.0, "payload": None})
    F._UNIVERSE_CURSOR = 0
    import services.universe_scan as U
    async def fake_batch(tickers, **kw):
        rows = [{"ticker": t, "snapshot_id": "s-" + t, "asof": "a",
                 "opportunity": {"opportunity_score": 9.0 if t == "BBB" else 1.0,
                 "direction": "BEAR" if t == "BBB" else "NEUTRAL",
                 "trade_type": "x", "invalidation": "i %s" % t},
                 "conviction": {"conviction": 10}} for t in tickers]
        return {"rows": rows, "skipped": [], "coverage": {"requested": len(tickers), "scanned": len(tickers), "skipped": 0}}
    monkeypatch.setattr(U, "scan_batch", fake_batch)
    async def fake_movers(limit=80):
        return {"results": []}
    import services.movers as M
    monkeypatch.setattr(M, "get_movers", fake_movers)
    import services.flow_alerts as FA
    monkeypatch.setattr(FA, "read_alert_feed", lambda *a, **k: [])
    import services.regime_opportunity as RO
    monkeypatch.setattr(RO, "compute", lambda inputs: {"opportunity_score": 5.0, "opportunity_tier": "WATCH", "direction": "NEUTRAL", "trade_type": "no_trade", "invalidation": "i", "components": {}, "warnings": []})
    import services.conviction_rank as CR
    monkeypatch.setattr(CR, "rank_one", lambda t, **k: {"ticker": t, "conviction": 10.0, "tier": "LOW", "direction": "NEUTRAL", "trade_type": "no_trade", "invalidation": "i", "snapshot_id": "s", "asof": "a", "evidence": {}})

def test_universe_scan_leaderboard_and_cache(monkeypatch):
    _seed_board(monkeypatch)
    c = TestClient(_app())
    r1 = c.get("/api/flowseeker/universe/scan?limit=3&refresh=true")
    assert r1.status_code == 200, r1.text[:300]
    b1 = r1.json()
    assert "leaderboard" in b1 and "prefilter" in b1 and b1["cache"] == "miss"
    assert all("invalidation" in row for row in b1["leaderboard"])
    r2 = c.get("/api/flowseeker/universe/scan?limit=3")
    assert r2.json()["cache"] == "hit"
    r3 = c.get("/api/flowseeker/universe/leaderboard?limit=3")
    assert r3.status_code == 200 and isinstance(r3.json()["leaderboard"], list)
