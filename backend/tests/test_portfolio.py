"""Tests for portfolio, Schwab, live policy, and position sizing endpoints."""
import pytest

pytestmark = pytest.mark.asyncio


# ============ Portfolio Tests ============

async def test_portfolio_add_position(aclient):
    """Add a position to a portfolio."""
    pos = {
        "symbol": "SPY",
        "option_type": "call",
        "strike": 500.0,
        "expiry": "2026-06-15",
        "quantity": 2,
        "entry_price": 5.50,
        "entry_iv": 0.15,
        "underlying_price": 530.0,
    }
    r = await aclient.post("/api/portfolio/test/position", json=pos)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "added"
    assert d["positions"] >= 1


async def test_portfolio_get(aclient):
    """Get portfolio summary."""
    r = await aclient.get("/api/portfolio/test?spot=530&iv=0.15")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "test"
    assert d["positions"] >= 1
    assert "greeks" in d
    assert "pnl" in d
    g = d["greeks"]
    for k in ("delta", "gamma", "vega", "theta"):
        assert k in g, f"missing greek {k}"


async def test_portfolio_scenario(aclient):
    """Run scenario analysis."""
    r = await aclient.get("/api/portfolio/test/scenario?spot=530&iv=0.15")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "scenarios" in d
    assert len(d["scenarios"]) > 0
    # Should have spot and vol scenarios
    spot_scenarios = [s for s in d["scenarios"] if s["type"] == "spot"]
    vol_scenarios = [s for s in d["scenarios"] if s["type"] == "vol"]
    assert len(spot_scenarios) > 0
    assert len(vol_scenarios) > 0


async def test_portfolio_hedge(aclient):
    """Calculate Greek-neutral hedge."""
    hedge_opts = [
        {"strike": 500, "expiry": "2026-06-15", "type": "call", "iv": 0.15},
        {"strike": 495, "expiry": "2026-06-15", "type": "put", "iv": 0.15},
    ]
    r = await aclient.post("/api/portfolio/test/hedge", json={
        "spot": 530, "iv": 0.15, "hedge_options": hedge_opts,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    if "error" not in d:
        assert "hedge_positions" in d
        assert "stock_hedge" in d
        assert "resulting_greeks" in d


async def test_portfolio_remove_position(aclient):
    """Remove a position."""
    r = await aclient.delete("/api/portfolio/test/position/0")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "removed"


async def test_portfolio_not_found(aclient):
    """404 for nonexistent portfolio."""
    r = await aclient.get("/api/portfolio/nonexistent_xyz?spot=530&iv=0.15")
    assert r.status_code == 404


# ============ Position Sizing Tests ============

async def test_position_size(aclient):
    """Calculate position size."""
    r = await aclient.post(
        "/api/position-size?account_size=100000&risk_per_trade_pct=0.02&spot=530&gex_level=1000000",
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["recommended_contracts"] >= 1
    assert d["position_value"] > 0
    assert d["risk_per_trade"] == 2000.0  # 2% of 100k


# ============ Live Policy Tests ============

async def test_live_policy_get(aclient):
    """Get current live policy."""
    r = await aclient.get("/api/live/policy")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "paid_tickers" in d
    assert "live_window_et" in d


async def test_live_policy_update(aclient):
    """Update live policy."""
    r = await aclient.post("/api/live/policy", json={
        "paid_tickers": ["SPY"],
        "window_start": "09:00",
        "window_stop": "10:30",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert "SPY" in d["paid_tickers"]


# ============ Schwab Tests (RETIRED 2026-09-03 — public-api-only) ============

async def test_schwab_auth_url_deleted(aclient):
    """Schwab deleted 2026-09-06 — /api/schwab/* is 404, not 410."""
    r = await aclient.get("/api/schwab/auth-url")
    assert r.status_code == 404


# ============ History Tests ============

async def test_history_endpoint(aclient):
    """Get snapshot history."""
    # First trigger a snapshot by hitting heatmap
    await aclient.get("/api/heatmap/SPY?expiries=2")
    r = await aclient.get("/api/history/SPY?limit=5")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "snapshots" in d
    assert isinstance(d["snapshots"], list)


# ============ Patterns Glossary Tests ============

async def test_patterns_glossary(aclient):
    """Get patterns glossary."""
    r = await aclient.get("/api/patterns/glossary")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "King Node" in d or "king" in str(d).lower()
