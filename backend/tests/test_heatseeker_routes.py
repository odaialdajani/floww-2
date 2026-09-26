"""
Route-level integration tests for the Wave 1 + Wave 2 Heatseeker surface.

Each route is exercised through FastAPI's in-process ``TestClient`` so the
suite runs in CI with no live backend. External I/O (chain fetcher, Mongo
history, trinity snapshots) is mocked via the helpers exported by
``routes.heatseeker`` — the route code's local ``from server import ...``
imports stay untouched, but the helper that owns the fetch is overridden.

Covers the 8 Wave 1 + Wave 2 routes:
    /api/heatseeker/flip-zones
    /api/heatseeker/node-lifecycle
    /api/heatseeker/air-pockets
    /api/heatseeker/beach-ball
    /api/heatseeker/reverse-rug
    /api/heatseeker/rainbow-road
    /api/heatseeker/velocity-mode
    /api/heatseeker/trinity-confluence
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Make ``server`` importable when pytest is invoked from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _chain_fixture() -> dict[str, Any]:
    """
    Static option chain with enough strikes + both call/put sides so the
    GEX-per-strike aggregator returns a non-trivial map. Calls dominate
    above spot, puts dominate below — gives a real King Node and a
    plausible flip zone within the default ±5% window.
    """
    spot = 500.0
    expiries = ["2026-05-22", "2026-05-29"]
    t_by_expiry = {"2026-05-22": 3 / 365.0, "2026-05-29": 10 / 365.0}
    contracts: list[dict[str, Any]] = []
    for exp in expiries:
        for strike in (485.0, 490.0, 495.0, 500.0, 505.0, 510.0, 515.0):
            for typ in ("call", "put"):
                # Concentrate OI at 510 (call wall) and 490 (put wall) so the
                # GEX map yields a clear King Node + opposite-sign neighbours.
                base_oi = 2000
                if typ == "call" and strike == 510.0 or typ == "put" and strike == 490.0:
                    base_oi = 8000
                contracts.append({
                    "strike": strike,
                    "type": typ,
                    "expiry": exp,
                    "T": t_by_expiry[exp],
                    "oi": base_oi,
                    "open_interest": base_oi,
                    "volume": 250,
                    "iv": 0.20,
                    "gamma": 0.04,
                    "delta": 0.5 if typ == "call" else -0.5,
                    "vega": 0.10,
                    "theta": -0.02,
                    "charm": 0.001,
                    "vanna": 0.002,
                    "bid": 1.0,
                    "ask": 1.1,
                    "last": 1.05,
                })
    return {
        "ticker": "SPY",
        "spot": spot,
        "expiries": expiries,
        "contracts": contracts,
        "data_source": "fixture",
    }


@pytest.fixture
def patched_chain():
    """
    Replace ``routes.heatseeker._fetch_chain`` with an async stub that
    returns the static fixture. Yields the underlying chain dict for the
    test to reference.
    """
    fake = _chain_fixture()
    async_mock = AsyncMock(return_value=fake)
    with patch("routes.heatseeker._fetch_chain", async_mock):
        yield fake


# ---------------------------------------------------------------------------
# Regression: gamma enrichment (Skylit GEX panels rendered empty)
# ---------------------------------------------------------------------------

def test_fetch_chain_enriches_missing_gamma():
    """Production chains from ``fetch_spot_and_chains_merged`` carry no
    ``gamma`` field, so ``_gex_per_strike`` skipped every contract and all
    Skylit GEX panels rendered empty. ``routes.heatseeker._ensure_gamma``
    must compute Black-Scholes gamma from spot/strike/T/iv; contracts that
    already include gamma are left untouched.
    """
    from routes.heatseeker import _ensure_gamma
    from services.heatseeker import _gex_per_strike

    chain = _chain_fixture()
    for c in chain["contracts"]:
        c.pop("gamma", None)
    # Baseline documents the bug: with no gamma field the GEX map is empty.
    assert _gex_per_strike(chain["spot"], chain["contracts"]) == {}
    # Fix: enrichment computes a positive gamma -> non-empty GEX map.
    enriched = _ensure_gamma(chain)
    assert all(float(c.get("gamma", 0)) > 0 for c in enriched["contracts"])
    gex = _gex_per_strike(enriched["spot"], enriched["contracts"])
    assert gex, "GEX map still empty after _ensure_gamma enrichment"


# ---------------------------------------------------------------------------
# Wave 1 routes
# ---------------------------------------------------------------------------

def test_flip_zones_route(client, patched_chain):
    r = client.get("/api/heatseeker/flip-zones?ticker=SPY")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] == 500.0
    assert "flip_zones" in d
    assert "window_low" in d
    assert "window_high" in d
    assert "count" in d
    assert isinstance(d["flip_zones"], list)
    assert d["count"] == len(d["flip_zones"])


def test_flip_zones_404_on_empty(client):
    """When the chain fetcher returns no contracts, the route 404s."""
    empty_chain = {"ticker": "ZZZ", "spot": None, "expiries": [], "contracts": []}
    with patch("routes.heatseeker._fetch_chain", AsyncMock(return_value=empty_chain)):
        r = client.get("/api/heatseeker/flip-zones?ticker=ZZZ")
    assert r.status_code == 404


def test_param_percents_never_422(client, patched_chain):
    """Panels historically send percents (window_pct=5, min_gap_pct=1) where the
    backend wants fractions. These must normalize + clamp, NEVER 422 (a 422
    blanks the panel). Root fix for the recurring Skylit-tab errors.
    """
    assert client.get("/api/heatseeker/flip-zones?ticker=SPY&window_pct=5").status_code == 200
    assert client.get("/api/heatseeker/flip-zones?ticker=SPY&window_pct=500").status_code == 200
    assert client.get("/api/heatseeker/air-pockets?ticker=SPY&min_gap_pct=1").status_code == 200


def test_node_lifecycle_route(client, patched_chain):
    """
    /node-lifecycle reads a 24h history via ``_fetch_history``. Mock it with
    a small list of spot taps so the lifecycle classifier exercises both
    'fresh' and 'tested' branches.
    """
    history = [
        {"timestamp": "2026-05-18T13:00:00Z", "spot": 499.5},
        {"timestamp": "2026-05-18T13:15:00Z", "spot": 510.2},  # near 510 wall
        {"timestamp": "2026-05-18T13:30:00Z", "spot": 489.9},  # near 490 wall
    ]
    with patch(
        "routes.heatseeker._fetch_history",
        AsyncMock(return_value=history),
    ):
        r = client.get("/api/heatseeker/node-lifecycle?ticker=SPY")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] == 500.0
    assert d["history_points"] == 3
    assert "nodes" in d
    assert isinstance(d["nodes"], list)
    if d["nodes"]:
        node = d["nodes"][0]
        for k in ("strike", "net_gex", "state", "tap_probability"):
            assert k in node, f"missing node field {k}"
        assert node["state"] in ("fresh", "tested", "delivered", "decaying")


def test_air_pockets_route(client, patched_chain):
    r = client.get("/api/heatseeker/air-pockets?ticker=SPY")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] == 500.0
    assert "air_pockets" in d
    assert isinstance(d["air_pockets"], list)


# ---------------------------------------------------------------------------
# Wave 2 routes
# ---------------------------------------------------------------------------

def test_beach_ball_route(client, patched_chain):
    r = client.get("/api/heatseeker/beach-ball?ticker=SPY")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] == 500.0
    assert d["pattern"] == "beach_ball"
    for k in ("active", "king_node", "spot_distance_pct", "direction", "confidence"):
        assert k in d, f"missing beach-ball field {k}"
    assert d["direction"] in ("above", "below", "at")


def test_reverse_rug_route(client, patched_chain):
    r = client.get("/api/heatseeker/reverse-rug?ticker=SPY")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["pattern"] == "reverse_rug"
    for k in ("active", "floor_strike", "floor_gex", "ceiling_strike", "ceiling_gex"):
        assert k in d, f"missing reverse-rug field {k}"


def test_rainbow_road_route(client, patched_chain):
    r = client.get("/api/heatseeker/rainbow-road?ticker=SPY")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["pattern"] == "rainbow_road"
    for k in ("active", "top_strike_share", "n_strikes_significant"):
        assert k in d, f"missing rainbow-road field {k}"


def test_velocity_mode_route(client):
    """
    /velocity-mode pulls king-node history from Mongo via
    ``_fetch_king_node_history``. Mock it with two well-separated rows so
    the mode classifier yields a deterministic 'calm' result.
    """
    king_history = [
        {"timestamp": "2026-05-18T13:00:00Z", "king_node_strike": 500.0, "spot": 499.8},
        {"timestamp": "2026-05-18T13:10:00Z", "king_node_strike": 500.0, "spot": 500.4},
    ]
    with patch(
        "routes.heatseeker._fetch_king_node_history",
        AsyncMock(return_value=king_history),
    ):
        r = client.get("/api/heatseeker/velocity-mode?ticker=SPY")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert "velocity_strikes_per_min" in d
    assert "mode" in d
    assert d["mode"] in ("calm", "active", "urgent")
    assert d["n_snapshots"] == 2


def test_velocity_mode_empty_history(client):
    """F09 (corrected): Mongo unavailable / empty history → unknown (never calm)."""
    with patch(
        "routes.heatseeker._fetch_king_node_history",
        AsyncMock(return_value=[]),
    ):
        r = client.get("/api/heatseeker/velocity-mode?ticker=SPY")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "unknown"
    assert d["n_snapshots"] == 0
    assert d["velocity_strikes_per_min"] is None


def test_trinity_confluence_route(client):
    """
    /trinity-confluence fans out three ``_trinity_snapshot`` calls. Patch
    that helper with a deterministic aligned-positive snapshot so the
    verdict is predictable.
    """
    snap = {
        "gex_regime": "positive",
        "spot": 500.0,
        "gamma_flip": 495.0,
        "trend_direction": "up",
    }
    with patch(
        "routes.heatseeker._trinity_snapshot",
        AsyncMock(return_value=snap),
    ):
        r = client.get("/api/heatseeker/trinity-confluence")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "snapshots" in d
    for k in ("SPX", "SPY", "QQQ"):
        assert k in d["snapshots"]
    assert "score" in d
    assert "verdict" in d
    assert d["verdict"] in ("high_confluence", "partial", "divergence")
    # All three snapshots identical + non-missing → full alignment.
    assert d["score"] == 100
    assert d["verdict"] == "high_confluence"


def test_trinity_confluence_all_missing(client):
    """
    If every per-ticker snapshot is genuinely missing (None across the board),
    none of the three dimensions align → score is 0 / divergence.

    NOTE: ``calc_trinity_confluence`` treats the literal string ``"missing"``
    in ``trend_direction`` as a valid (non-None) aligned value when all three
    inputs match — which is why ``_trinity_snapshot``'s fallback dict uses
    ``"missing"`` for ``trend_direction`` but None for the numeric fields.
    Here we pass None across the board so the test exercises a true
    divergence path rather than the string-match quirk.
    """
    missing = {
        "gex_regime": None,
        "spot": None,
        "gamma_flip": None,
        "trend_direction": None,
    }
    with patch(
        "routes.heatseeker._trinity_snapshot",
        AsyncMock(return_value=missing),
    ):
        r = client.get("/api/heatseeker/trinity-confluence")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["score"] == 0
    assert d["verdict"] == "divergence"


# ---------------------------------------------------------------------------
# TASK 3 — Regression: field-name mismatch between writer and reader
# ---------------------------------------------------------------------------

def test_velocity_mode_reads_writer_field():
    """save_snapshot writes 'king_strike'; the velocity-mode read path must
    read the SAME field, or n_snapshots is always 0."""
    import inspect
    import re

    import routes.heatseeker as hr
    import server

    write_src = inspect.getsource(server.save_snapshot)
    read_src = inspect.getsource(hr._fetch_king_node_history)
    written = set(re.findall(r'"(king[_a-z]*)"', write_src))
    read = set(re.findall(r'"(king[_a-z]*)"', read_src))
    assert written & read, \
        f"writer fields {written} and reader fields {read} do not overlap"


# ---------------------------------------------------------------------------
# TASK 3 — Regression: snapshot POST writes to shared DB (not :memory:)
# ---------------------------------------------------------------------------

def test_snapshot_top_movers_roundtrip(client):
    """POST a snapshot → GET top-movers → assert ≥1 row from the shared DB."""
    # fetch_spot_and_chains_merged is imported locally inside the POST handler,
    # so patch it on server where it lives.
    headers = {"X-API-Key": "test-secret-key"}
    with patch(
        "server.fetch_spot_and_chains_merged",
        AsyncMock(return_value=_chain_fixture()),
    ):
        # POST a snapshot
        r = client.post("/api/heatseeker/snapshot/SPY", headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "ok", d
        assert d["result"]["inserted"] > 0, d

        # GET top-movers — should return rows from the shared DB
        r2 = client.get("/api/heatseeker/top-movers/SPY?top_n=5")
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["ticker"] == "SPY"
        assert d2["n_contracts"] >= 1, \
            f"top-movers should have ≥1 row after snapshot, got {d2['n_contracts']}"
        assert len(d2["movers"]) >= 1
        # Verify mover shape
        m = d2["movers"][0]
        for k in ("ticker", "expiry", "strike", "type", "oi", "iv"):
            assert k in m, f"missing mover field {k}"
