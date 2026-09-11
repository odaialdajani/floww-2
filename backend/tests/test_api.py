"""Local route contracts using controlled market inputs and storage boundaries.

Real route calculations run without provider calls or starting server lifespan.
These checks do not certify live-provider acceptance.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Make ``server`` importable when pytest is invoked from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app  # noqa: E402
from tests.test_heatseeker_v2 import install_offline_market  # noqa: E402


@pytest.fixture(autouse=True)
def offline_routes(monkeypatch):
    from unittest.mock import AsyncMock

    import server

    install_offline_market(monkeypatch)
    monkeypatch.setattr(server, "save_snapshot", AsyncMock())
    monkeypatch.setattr(server, "velocity_and_rolling", AsyncMock(return_value={
        "velocity_score": 0, "rolling_floor": "stable",
        "rolling_ceiling": "stable", "history": [],
    }))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("API_SECRET_KEY", "test-secret-key")
    return TestClient(app, headers={"X-API-Key": "test-secret-key"})


def _fake_chain() -> dict[str, Any]:
    """
    Static option-chain fixture wide enough to drive every chain-consuming
    endpoint (heatmap, advanced, chain, regime, gamma-flip, gex-timeframes,
    uoa). Shape mirrors what ``fetch_spot_and_chains_merged`` returns.
    """
    spot = 500.0
    expiries = ["2026-05-22", "2026-05-29"]
    # Time-to-expiry in years; the production fetcher always populates this
    # field and the downstream BS Greek calls do c["T"] (not .get).
    t_by_expiry = {"2026-05-22": 3 / 365.0, "2026-05-29": 10 / 365.0}
    contracts: list[dict[str, Any]] = []
    for exp in expiries:
        for k in (485.0, 490.0, 495.0, 500.0, 505.0, 510.0, 515.0):
            for typ in ("call", "put"):
                contracts.append({
                    "strike": k,
                    "type": typ,
                    "expiry": exp,
                    "T": t_by_expiry[exp],
                    "oi": 1500,
                    "open_interest": 1500,
                    "volume": 250,
                    "iv": 0.18,
                    "gamma": 0.04,
                    "delta": 0.5 if typ == "call" else -0.5,
                    "vega": 0.1,
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
    """Patch the chain fetcher in server.py so chain-dependent routes work."""
    fake = _fake_chain()
    async_mock = AsyncMock(return_value=fake)
    with patch("server.fetch_spot_and_chains_merged", async_mock):
        yield fake


# ---------------------------------------------------------------------------
# Light routes — no external I/O, run unconditionally
# ---------------------------------------------------------------------------

def test_root(client):
    r = client.get("/api/")
    assert r.status_code == 200
    d = r.json()
    assert d["app"] == "confluence-decoder"


def test_tickers(client):
    r = client.get("/api/tickers")
    assert r.status_code == 200
    d = r.json()
    assert "trinity" in d
    assert "SPY" in d["trinity"]


def test_404_handling(client):
    r = client.get("/api/nonexistent")
    assert r.status_code == 404


def test_validation_error(client):
    r = client.get("/api/heatmap/SPY?mode=invalid")
    assert r.status_code == 422


def test_alert_types_in_response(client):
    """All registered alert types must surface in /alerts/types."""
    r = client.get("/api/alerts/types")
    assert r.status_code == 200
    d = r.json()
    alert_types = [a["type"] for a in d.get("alert_types", [])]
    expected_types = [
        "GAMMA_FLIP", "GAMMA_SQUEEZE", "MOMENTUM_EXTREME",
        "WALL_BREACH", "GEX_MAGNITUDE_SHIFT", "GAMMA_FLIP_PROXIMITY",
        "PIN_RISK", "CHARM_PINNING", "VANNA_REGIME_CHANGE",
        "UNUSUAL_PC_OI_RATIO", "MAX_PAIN_MAGNET",
    ]
    for expected in expected_types:
        assert expected in alert_types, f"Missing alert type: {expected}"


def test_alerts_crud(client):
    """In-memory alert store: create / list / delete round-trip."""
    # Create
    r = client.post("/api/alerts", json={
        "ticker": "SPY",
        "alert_type": "gex_cross",
        "threshold": 1000000,
        "direction": "above",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    alert_id = d.get("rule", {}).get("id") or d.get("id")
    assert alert_id

    # List
    r = client.get("/api/alerts")
    assert r.status_code == 200
    d = r.json()
    alerts = d.get("rules", d) if isinstance(d, dict) else d
    assert isinstance(alerts, list)

    # Delete
    r = client.delete(f"/api/alerts/{alert_id}")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Health uses controlled storage, key-presence and connection-count inputs.
# ---------------------------------------------------------------------------

def test_health(client, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    monkeypatch.setenv("PUBLIC_API_KEY", "test-key")
    monkeypatch.setattr("routes.health.duckdb_engine", MagicMock())
    monkeypatch.setattr("routes.health.ws_manager", SimpleNamespace(_all={}))
    monkeypatch.setattr("routes.health.av_circuit", SimpleNamespace(state=SimpleNamespace(value="closed"), failure_count=0, success_count=0))
    monkeypatch.setattr("routes.health._institutional_section", lambda feed: {"feed": feed})
    r = client.get("/api/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "healthy"
    assert set(d["checks"]) == {"duckdb", "public_api", "alpha_vantage", "websocket", "circuit_breaker"}
    assert d["checks"]["public_api"] == {"status": "healthy", "key_configured": True}
    assert d["checks"]["alpha_vantage"]["deprecated"] is True
    assert d["checks"]["websocket"]["active_connections"] == 0


# ---------------------------------------------------------------------------
# Chain-dependent routes exercise real calculations from offline inputs.
# ---------------------------------------------------------------------------

def test_heatmap_spy(client):
    r = client.get("/api/heatmap/SPY?expiries=4")
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "SPY"
    assert "strikes" in d
    assert "nodes" in d
    assert "market_regime" in d
    assert "implied_pdf" in d
    assert len(d["strikes"]) > 0


def test_heatmap_modes(client):
    for mode in ["day", "swing", "scalp"]:
        r = client.get(f"/api/heatmap/SPY?expiries=2&mode={mode}")
        assert r.status_code == 200, f"Mode {mode} failed"
        d = r.json()
        assert d["mode"] == mode


def test_heatmap_dte_filter(client):
    r = client.get("/api/heatmap/SPY?expiries=4&dte=2")
    assert r.status_code == 200
    d = r.json()
    # Controlled contracts begin seven days out; two days must not widen.
    assert d["strikes"] == []
    assert d["grid"] == {}
    assert d["expiries_used"] == []
    within_week = client.get("/api/heatmap/SPY?expiries=4&dte=8")
    assert within_week.status_code == 200
    assert within_week.json()["strikes"]
    assert len(within_week.json()["grid"]["expiries"]) == 1


def test_chain_spy(client, patched_chain):
    r = client.get("/api/chain/SPY?min_oi=100")
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d
    assert "count" in d
    assert d["count"] > 0
    row = d["rows"][0]
    assert "type" in row
    assert "strike" in row
    assert "iv" in row
    assert "gex" in row


def test_chain_filter_expiry(client, patched_chain):
    r = client.get("/api/chain/SPY?min_oi=100")
    assert r.status_code == 200
    d = r.json()
    if d["count"] > 0 and d.get("expiries"):
        first_exp = d["expiries"][0]
        r2 = client.get(f"/api/chain/SPY?min_oi=100&expiry={first_exp}")
        assert r2.status_code == 200


def test_advanced_spy(client, patched_chain):
    r = client.get("/api/advanced/SPY?expiries=4")
    assert r.status_code == 200
    d = r.json()
    assert "implied_pdf" in d
    assert "regime" in d
    assert "hedge_impulse" in d
    assert "pressure_cloud" in d
    assert "charm_integral" in d


def test_regime_spy(client, patched_chain):
    r = client.get("/api/regime/SPY")
    if r.status_code == 404:
        r = client.get("/api/advanced/SPY?expiries=4")
        d = r.json()
        assert "regime" in d
    else:
        d = r.json()
        assert "regime" in d
        assert "atm_iv" in d
        assert "skew" in d


def test_implied_pdf_spy(client, patched_chain):
    r = client.get("/api/implied-pdf/SPY")
    if r.status_code == 404:
        r = client.get("/api/advanced/SPY?expiries=4")
        d = r.json()
        assert "implied_pdf" in d
    else:
        d = r.json()
        assert "strike_probabilities" in d
        assert "most_likely_price" in d
        assert "expected_move" in d


def test_hedge_impulse_spy(client, patched_chain):
    r = client.get("/api/hedge-impulse/SPY")
    if r.status_code == 404:
        r = client.get("/api/advanced/SPY?expiries=4")
        d = r.json()
        assert "hedge_impulse" in d
    else:
        d = r.json()
        assert "curve" in d
        assert "regime" in d
        assert "impulse_at_spot" in d


def test_pressure_cloud_spy(client, patched_chain):
    r = client.get("/api/pressure-cloud/SPY")
    if r.status_code == 404:
        r = client.get("/api/advanced/SPY?expiries=4")
        d = r.json()
        assert "pressure_cloud" in d
    else:
        d = r.json()
        assert "stability_zones" in d
        assert "acceleration_zones" in d


def test_charm_integral_spy(client, patched_chain):
    r = client.get("/api/charm-integral/SPY")
    if r.status_code == 404:
        r = client.get("/api/advanced/SPY?expiries=4")
        d = r.json()
        assert "charm_integral" in d
    else:
        d = r.json()
        assert "total_charm_to_close" in d
        assert "direction" in d
        assert "buckets" in d


@pytest.fixture
def patched_analytics_chain():
    """Feed a full fixture chain into the analytics cache router so the
    compute-heavy endpoints (vanna/charm) exercise the real Greek path
    instead of 404-ing on an empty test cache."""
    fake = _fake_chain()
    with patch("routes.analytics._cache.get_chain", AsyncMock(return_value=fake)):
        yield fake


def test_vanna_exposure_spy(client, patched_analytics_chain):
    """Regression: vanna-exposure must COMPUTE, not return a degraded
    'computation_error'. The endpoint previously passed spot as a 1-D numpy
    array into the scalar-S ``bs_vanna_vec`` njit function, which triggered
    'No implementation of function log() for array(float64, 1d)' in Numba's
    nopython pipeline. With a valid chain the response must carry real vanna.
    """
    r = client.get("/api/vanna-exposure/SPY?expiries=4")
    assert r.status_code == 200
    d = r.json()
    assert not d.get("degraded"), f"vanna-exposure degraded: {d.get('detail')}"
    assert "strikes" in d and isinstance(d["strikes"], list)
    assert "vanna" in d and isinstance(d["vanna"], list)


def test_gex_timeframes_spy(client, patched_chain):
    r = client.get("/api/gex-timeframes/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "timeframes" in d
    tf = d["timeframes"]
    for key in ["0DTE", "1DTE", "weekly", "monthly", "all"]:
        assert key in tf, f"Missing timeframe {key}"


def test_uoa_spy(client, patched_chain):
    r = client.get("/api/uoa/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "unusual" in d
    if d["unusual"]:
        row = d["unusual"][0]
        assert "type" in row
        assert "strike" in row
        # services/uoa.py rows carry "reasons" (list of trigger strings),
        # not the older "signals" key.
        assert "reasons" in row


def test_gamma_flip_endpoint(client, patched_chain):
    r = client.get("/api/gamma-flip/SPY?expiries=2")
    assert r.status_code == 200
    d = r.json()
    assert "gamma_flip" in d
    assert "call_wall" in d
    assert "put_wall" in d
    assert "regime" in d
    assert d["regime"] in ("positive_gamma", "negative_gamma", "unknown")


def test_daily_checklist_endpoint(client):
    r = client.get("/api/daily-checklist/SPY?expiries=2")
    assert r.status_code == 200
    d = r.json()
    assert "regime" in d
    assert "key_levels" in d
    assert "strategy" in d
    assert "risk_management" in d
    assert "hedging_flow" in d
    assert "recommended_strategies" in d["strategy"]


def test_trinity(client):
    r = client.get("/api/trinity")
    assert r.status_code == 200
    d = r.json()
    assert set(d["tickers"]) == {"^SPX", "SPY", "QQQ"}
    for ticker, result in d["tickers"].items():
        assert "error" not in result
        assert result["ticker"] == ticker
        assert result["spot"] == (5000.0 if ticker == "^SPX" else 500.0)
        assert result["strikes"]


def test_spot_spy(client):
    r = client.get("/api/spot/SPY")
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] == 500.0
    assert d["data_source"] == "yfinance"
    assert d["status"] == "ok"
    assert d["ts"] is not None


def test_multiple_tickers(client):
    for ticker in ["SPY", "QQQ", "IWM", "AAPL", "NVDA"]:
        r = client.get(f"/api/heatmap/{ticker}?expiries=2")
        assert r.status_code == 200, f"Ticker {ticker} failed: {r.status_code}"
        d = r.json()
        assert d["ticker"].replace("^", "") == ticker.replace("^", "")


# ---------------------------------------------------------------------------
# Memory routes — depend on Chroma + a long-lived embedder. Mock the
# memory_integration entry points so the routes stay green in CI.
# ---------------------------------------------------------------------------

def test_memory_trade_endpoint(client):
    with patch("server.remember_trade", new_callable=AsyncMock, return_value="trade-1"):
        r = client.post("/api/memory/trade", json={
            "ticker": "SPY",
            "trade_type": "call",
            "entry_price": 450.0,
            "exit_price": 455.0,
            "pnl": 5.0,
            "notes": "Test trade",
        })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "ok"


def test_memory_gex_endpoint(client):
    with patch("server.remember_gex_observation", new_callable=AsyncMock, return_value="gex-1"):
        r = client.post("/api/memory/gex", json={
            "ticker": "SPY",
            "observation": "GEX regime changed from positive to negative",
            "metadata": {"regime": "NEGATIVE", "gamma_flip": 450.0},
        })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "ok"


def test_memory_recall_endpoint(client):
    with patch("server.recall_trading_context", new_callable=AsyncMock, return_value=[]):
        r = client.get("/api/memory/recall/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "results" in d


def test_memory_summary_endpoint(client):
    with patch("server.get_trading_summary", new_callable=AsyncMock, return_value="no data yet"):
        r = client.get("/api/memory/summary/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "summary" in d
