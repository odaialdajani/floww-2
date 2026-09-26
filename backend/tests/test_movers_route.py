"""Route tests for /api/movers v2 (R7-01).

Ranked completed-session percent through the actual route with the provider
boundary mocked (market_bars.get_daily_bars). No network.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture
def client():
    return TestClient(app)


def _bars_for(symbol, drift):
    """10 ET days of bars with a fixed per-day drift (fraction)."""
    from datetime import UTC, datetime, timedelta
    rows = []
    base = 100.0
    for back in range(10, 0, -1):
        day = (datetime.now(UTC) - timedelta(days=back)).strftime("%Y-%m-%d")
        c = base * (1.0 + drift) ** (10 - back)
        rows.append({"t": f"{day}T12:00:00-04:00", "o": c, "h": c * 1.01,
                     "l": c * 0.99, "c": c, "v": 1000})
    return rows


async def _fake_daily(sym, days=10):
    # Serve real universe tickers (route uses POPULAR_UNIVERSE); the rest miss.
    table = {"AAPL": 0.004, "MSFT": -0.009, "GOOGL": 0.0}
    if sym not in table:
        return None
    return _bars_for(sym, table[sym])


def test_movers_v2_contract_ranked_and_limited(client):
    """Results carry change_pct (+legacy aliases), sorted by |pct|, limited."""
    with patch("services.market_bars.get_daily_bars", new=_fake_daily):
        r = client.get("/api/movers?limit=2")
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["schema_version"] == "movers.v2"
    assert body["mode"] == "previous_completed_session"
    assert body["session_date"] and body["prior_session_date"]
    assert body["universe_id"] == "tracked-options.v1"
    assert body["price_basis"] == "vendor-close-as-returned-unadjusted"
    assert body["coverage"]["requested"] >= 3
    assert "asof" in body
    got = body["results"]
    assert len(got) == 2
    assert [x["ticker"] for x in got] == ["MSFT", "AAPL"]
    for x in got:
        assert x["pct"] == x["change"] == x["change_pct"]
        assert x["close"] > 0 and x["previous_close"] > 0
    assert abs(got[0]["change_pct"]) >= abs(got[1]["change_pct"])


def test_movers_route_not_double_prefixed(client):
    """/api/api/movers must NOT exist (historical double-prefix bug)."""
    r = client.get("/api/api/movers?limit=3")
    assert r.status_code == 404
