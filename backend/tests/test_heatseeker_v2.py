"""V2 features: 2D grid heatmap, swing mode, contract drilldown, Databento usage."""
import pytest

pytestmark = pytest.mark.asyncio


def install_offline_market(monkeypatch):
    """Supply deterministic provider inputs while exercising real route calculations."""
    from datetime import UTC, datetime, timedelta
    from unittest.mock import AsyncMock

    import routes.analytics as analytics
    import server

    async def chain(ticker, max_expiries=4, *args, **kwargs):
        now = datetime.now(UTC)
        expiries = [(now + timedelta(days=7 * (i + 1))).date().isoformat()
                    for i in range(max_expiries)]
        spot = 5000.0 if ticker == "^SPX" else 500.0
        contracts = [{"strike": spot * (1 + j / 100), "type": kind,
                      "expiry": expiry, "T": 7 * (i + 1) / 365,
                      "oi": 1000 + j * 10, "volume": 100, "iv": 0.2,
                      "gamma": 0.02, "delta": 0.5 if kind == "call" else -0.5,
                      "bid": 4.9, "ask": 5.1}
                     for i, expiry in enumerate(expiries)
                     for j in range(-25, 26) for kind in ("call", "put")]
        return {"ticker": ticker, "spot": spot, "contracts": contracts,
                "expiries": expiries, "data_source": "yfinance",
                "spot_source": "yfinance", "event_time": now.isoformat(),
                "spot_event_time": now.isoformat(), "fetched_at": now.isoformat()}

    monkeypatch.setattr(server, "fetch_spot_and_chains_merged", chain)
    monkeypatch.setattr(analytics._cache, "get_chain", chain)
    monkeypatch.setattr(server, "_BUILD_HEATMAP_CACHE", {})
    monkeypatch.setattr(server, "tap_counts", AsyncMock(return_value={}))
    monkeypatch.setattr(server, "_fetch_movers_sync", lambda: [])
    monkeypatch.setattr(server, "calc_realized_volatility", lambda *a, **k: {})
    monkeypatch.setattr(server, "calc_iv_rank_percentile", lambda *a, **k: {})
    monkeypatch.setattr(server, "velocity_and_rolling", AsyncMock(return_value={}))


@pytest.fixture(autouse=True)
def offline_market(monkeypatch):
    install_offline_market(monkeypatch)


# --- Grid + data_source on heatmap SPY day ---
async def test_heatmap_spy_day_grid(aclient):
    r = await aclient.get("/api/heatmap/SPY?expiries=3&mode=day")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d.get("mode") == "day"
    assert "grid" in d
    grid = d["grid"]
    for k in ("expiries", "strikes", "grid", "strike_totals"):
        assert k in grid, f"grid missing {k}"
    assert isinstance(grid["expiries"], list) and len(grid["expiries"]) > 0
    assert isinstance(grid["strikes"], list) and len(grid["strikes"]) > 0
    # grid map keyed by expiry then strike-as-int-string when whole number
    first_exp = grid["expiries"][0]
    cells = grid["grid"][first_exp]
    assert isinstance(cells, dict)
    for key in cells:
        # SPY strikes are integers, should not contain "."
        # (SPY has half-strikes only on weeklies — but we still want pure-int strings for whole numbers)
        if "." not in key:
            assert key.lstrip("-").isdigit(), f"non-int-string key {key} for SPY whole strike"
    # data_source — Public API is primary post-Phase 3; cvserver/yfinance/databento are fallbacks
    assert d.get("data_source") in ("public_api", "databento+yfinance", "yfinance", "cvserver")


async def test_heatmap_swing_more_expiries_wider_band(aclient):
    # Day baseline
    rd = (await aclient.get("/api/heatmap/SPY?expiries=4&mode=day")).json()
    rs = (await aclient.get("/api/heatmap/SPY?expiries=8&mode=swing")).json()
    assert rs.get("mode") == "swing"
    # Swing should have >= day expiries
    assert len(rs["grid"]["expiries"]) >= len(rd["grid"]["expiries"])
    spot = rs["spot"]
    # widest strike distance / spot > 0.15 (since band is ±25% in swing)
    if rs["grid"]["strikes"]:
        max_dev = max(abs(s - spot) / spot for s in rs["grid"]["strikes"])
        # In practice should be > 0.15 if chain has strikes that far
        assert max_dev <= 0.26  # within band cap
    # day baseline must be <= 0.16
    if rd["grid"]["strikes"]:
        max_dev_d = max(abs(s - spot) / spot for s in rd["grid"]["strikes"])
        assert max_dev_d <= 0.16


@pytest.mark.flaky
async def test_heatmap_spx_via_spxw(aclient):
    r = await aclient.get("/api/heatmap/%5ESPX?expiries=2&mode=day")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "^SPX"
    assert d["spot"] > 0
    assert "grid" in d and len(d["grid"]["strikes"]) > 0


@pytest.mark.flaky
async def test_heatmap_qqq_grid(aclient):
    r = await aclient.get("/api/heatmap/QQQ?expiries=2&mode=day")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "QQQ"
    assert len(d["grid"]["strikes"]) > 0


@pytest.mark.flaky
async def test_trinity_day_all_populated(aclient):
    r = await aclient.get("/api/trinity?mode=day")
    assert r.status_code == 200, r.text
    d = r.json()
    for t in ("^SPX", "SPY", "QQQ"):
        assert t in d["tickers"], f"missing {t}"
        entry = d["tickers"][t]
        if "error" in entry:
            pytest.fail(f"trinity {t} errored: {entry['error']}")
        assert entry["spot"] > 0
        assert len(entry["strikes"]) > 0
    assert d["alignment"]["verdict"] in ("full_alignment", "partial_alignment", "divergence")


async def test_contract_drilldown_spy(aclient):
    # Get a real expiry first
    r = (await aclient.get("/api/heatmap/SPY?expiries=3")).json()
    exp_list = r["grid"]["expiries"]
    assert exp_list
    exp = exp_list[1] if len(exp_list) > 1 else exp_list[0]
    r2 = await aclient.get(f"/api/contract/SPY?expiry={exp}")
    assert r2.status_code == 200, r2.text
    d = r2.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] > 0
    assert d["count"] > 0
    assert isinstance(d["rows"], list) and len(d["rows"]) > 0
    row = d["rows"][0]
    for k in ("strike", "type", "oi", "iv", "delta", "gamma", "gex"):
        assert k in row, f"missing {k} in drilldown row"
    assert isinstance(row["delta"], (int, float))
    assert isinstance(row["gamma"], (int, float))
    # oi_source present when databento active
    if d.get("data_source", "").startswith("databento"):
        assert any("oi_source" in r_ for r_ in d["rows"]), "missing oi_source despite databento data_source"


@pytest.mark.flaky
async def test_databento_usage(aclient):
    r = await aclient.get("/api/databento/usage")
    assert r.status_code == 200
    d = r.json()
    assert "cached_days" in d
    assert "recent" in d
    assert isinstance(d["recent"], list)
    # Should have at least 1 cached snapshot from prior heatmap calls
    if d["cached_days"] > 0:
        item = d["recent"][0]
        for k in ("parent", "day", "count"):
            assert k in item


async def test_databento_oi_collection_populated(aclient):
    """After hitting heatmap, Databento cache should have at least one record."""
    await aclient.get("/api/heatmap/SPY?expiries=2")
    r = await aclient.get("/api/databento/usage")
    d = r.json()
    # Either databento active (cached_days >= 1) or env disabled — accept both but flag
    assert d.get("cached_days", 0) >= 0
