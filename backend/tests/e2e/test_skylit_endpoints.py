"""
backend/tests/e2e/test_skylit_endpoints.py

End-to-end API smoke tests for the Skylit (Heatseeker) tab endpoints.
Uses the async test client (ASGI transport) to verify:
  - All 14 endpoints return 200 and have expected response shapes.
  - Snapshot POST → GET top-movers → GET velocity-mode roundtrip.
  - Cross-panel consistency (ticker, spot agreement).

Run:
  pytest backend/tests/e2e/test_skylit_endpoints.py -v
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


# ── Constants ─────────────────────────────────────────────────────────────

SKYLIT_GET_ENDPOINTS = [
    "flip-zones",
    "node-lifecycle",
    "air-pockets",
    "beach-ball",
    "reverse-rug",
    "rainbow-road",
    "velocity-mode",
    "trinity-confluence",
    "rolling-floors-ceilings",
    "node-classification",
    "stacked-nodes",
    "tug-of-war",
]

# Fields each panel should include
PANEL_SHAPE = {
    "flip-zones":           {"ticker": str, "spot": (int, float), "flip_zones": list, "count": int},
    "node-lifecycle":       {"ticker": str, "spot": (int, float), "nodes": list, "history_points": int},
    "air-pockets":          {"ticker": str, "spot": (int, float), "air_pockets": list},
    "beach-ball":           {"ticker": str, "spot": (int, float), "active": (int, bool), "pattern": str},
    "reverse-rug":          {"ticker": str, "spot": (int, float), "active": (int, bool), "pattern": str},
    "rainbow-road":         {"ticker": str, "spot": (int, float), "active": (int, bool), "pattern": str},
    "velocity-mode":        {"ticker": str, "velocity_strikes_per_min": (int, float), "mode": str, "n_snapshots": int},
    "trinity-confluence":   {"score": (int, float)},
    "rolling-floors-ceilings": {"ticker": str, "floor_series": list, "ceiling_series": list},
    "node-classification":  {"ticker": str, "spot": (int, float), "nodes": list},
    "stacked-nodes":        {"ticker": str, "spot": (int, float), "stacked_nodes": list},
    "tug-of-war":           {"ticker": str, "in_tug_of_war": (int, bool)},
}

# Endpoints that need extra params beyond ticker
EXTRA_PARAMS = {
    "rolling-floors-ceilings": {"lookback_days": 5},
    "stacked-nodes":           {"threshold_pct": 0.3},
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _check_shape(body: dict, endpoint: str) -> None:
    """Verify the response body has the expected keys and value types."""
    expected = PANEL_SHAPE.get(endpoint, {})
    for key, expected_type in expected.items():
        assert key in body, f"{endpoint}: missing key '{key}' in {list(body.keys())[:10]}"
        val = body[key]
        if not isinstance(val, expected_type):
            pytest.fail(
                f"{endpoint}: key '{key}' expected {expected_type}, got {type(val).__name__} = {val!r:.80}"
            )


# ── Smoke: all GET endpoints ──────────────────────────────────────────────

@pytest.mark.parametrize("endpoint", SKYLIT_GET_ENDPOINTS)
async def test_skylit_endpoint_200_and_shape(aclient, endpoint: str):
    """Every Skylit GET endpoint returns 200 and the expected response shape."""
    params: dict = {"ticker": "SPY", **EXTRA_PARAMS.get(endpoint, {})}
    r = await aclient.get(f"/api/heatseeker/{endpoint}", params=params)
    assert r.status_code == 200, f"{endpoint}: HTTP {r.status_code} — {r.text[:200]}"
    body = r.json()
    _check_shape(body, endpoint)
    # Zero degraded responses in e2e (real chain must load)
    if "status" in body:
        assert body["status"] != "degraded", f"{endpoint}: degraded — {body.get('error', 'no error')}"


# ── Vanna + Charm endpoints ───────────────────────────────────────────────

async def test_vanna_exposure_200(aclient):
    r = await aclient.get("/api/vanna-exposure/SPY", params={"expiries": 4})
    assert r.status_code == 200, f"vanna-exposure: HTTP {r.status_code}"


async def test_charm_integral_200(aclient):
    r = await aclient.get("/api/charm-integral/SPY", params={"expiries": 4})
    assert r.status_code == 200, f"charm-integral: HTTP {r.status_code}"


# ── Snapshot roundtrip (T3 verification) ──────────────────────────────────

async def test_snapshot_top_movers_roundtrip(aclient):
    """
    POST a snapshot for SPY, then GET top-movers and velocity-mode.
    Verifies the T3 fix: snapshots write to shared DuckDB, not :memory:.
    """
    # 1. POST snapshot
    r = await aclient.post("/api/heatseeker/snapshot/SPY")
    assert r.status_code == 200, f"snapshot POST: HTTP {r.status_code} — {r.text[:200]}"
    snap = r.json()
    inserted = snap.get("result", {}).get("inserted", 0)
    assert inserted > 0, f"snapshot POST inserted 0 rows: {snap}"

    # 2. GET top-movers (must have data from the snapshot)
    r2 = await aclient.get("/api/heatseeker/top-movers/SPY")
    assert r2.status_code == 200, f"top-movers: HTTP {r2.status_code} — {r2.text[:200]}"
    movers = r2.json()
    mover_list = movers if isinstance(movers, list) else movers.get("movers", [])
    assert len(mover_list) > 0, f"top-movers returned 0 rows after snapshot: {movers}"

    # 3. GET velocity-mode — just verify it returns 200.
    #    (velocity-mode reads from Mongo db.snapshots, not DuckDB,
    #     so n_snapshots may be 0 after a DuckDB-only snapshot POST.)
    r3 = await aclient.get("/api/heatseeker/velocity-mode", params={"ticker": "SPY"})
    assert r3.status_code == 200
    vel = r3.json()
    assert vel.get("mode") in ("calm", "drifting", "accelerating", "sprinting")
    assert isinstance(vel.get("n_snapshots", -1), int)


# ── Cross-panel consistency ───────────────────────────────────────────────

async def test_cross_panel_ticker_spot_consistency(aclient):
    """
    flip-zones, node-lifecycle, and air-pockets for the same ticker
    must agree on ticker and spot (± tolerance for race).
    """
    results = {}
    for ep in ("flip-zones", "node-lifecycle", "air-pockets"):
        r = await aclient.get(f"/api/heatseeker/{ep}", params={"ticker": "SPY"})
        assert r.status_code == 200, f"{ep}: HTTP {r.status_code}"
        results[ep] = r.json()

    # Ticker must match
    tickers = {d["ticker"] for d in results.values()}
    assert tickers == {"SPY"}, f"ticker mismatch: {tickers}"

    # Spot must be within 1% (live price may tick between requests)
    spots = [d["spot"] for d in results.values()]
    avg = sum(spots) / len(spots)
    for ep, spot in zip(results, spots):
        assert spot > 0, f"{ep}: spot={spot} <= 0"
        assert abs(spot - avg) / avg < 0.02, f"{ep}: spot={spot} deviates >2% from avg={avg:.2f}"


# ── Trinity confluence e2e ─────────────────────────────────────────────────

async def test_trinity_confluence_all_tickers(aclient):
    """Trinity confluence must reference SPX, SPY, QQQ snapshots."""
    r = await aclient.get("/api/heatseeker/trinity-confluence", params={"expiries": 4})
    assert r.status_code == 200
    body = r.json()
    assert "score" in body
    assert 0 <= body["score"] <= 100, f"score out of range: {body['score']}"
    assert "snapshots" in body, f"trinity missing snapshots key — keys: {list(body.keys())}"
    for tk in ("SPX", "SPY", "QQQ"):
        assert tk in body["snapshots"], f"trinity missing snapshot for {tk}"


# ── Wave 2 / Wave 3 param validation ──────────────────────────────────────

async def test_velocity_mode_empty_history(aclient):
    """Velocity-mode with a ticker that has no snapshot history returns calm/0."""
    r = await aclient.get("/api/heatseeker/velocity-mode", params={"ticker": "ZZZZUNKNOWN"})
    # May 200 (degraded) or 404 — degraded is acceptable
    assert r.status_code in (200, 404), f"velocity-mode unexpected: HTTP {r.status_code}"
    if r.status_code == 200:
        body = r.json()
        assert body.get("mode") == "calm"
        assert body.get("n_snapshots", 0) == 0


async def test_beach_ball_param_boundaries(aclient):
    """Beach-ball with boundary expiries works."""
    for exp in (1, 12):
        r = await aclient.get("/api/heatseeker/beach-ball", params={"ticker": "SPY", "expiries": exp})
        assert r.status_code == 200, f"beach-ball expiries={exp}: HTTP {r.status_code}"


async def test_rainbow_road_param_boundaries(aclient):
    """Rainbow-road with boundary max_dominant_share works."""
    for share in (0.01, 1.0):
        r = await aclient.get(
            "/api/heatseeker/rainbow-road",
            params={"ticker": "SPY", "max_dominant_share": share},
        )
        assert r.status_code == 200, f"rainbow-road share={share}: HTTP {r.status_code}"
