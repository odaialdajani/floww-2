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
    """Bars covering the two completed sessions the service actually asks for.

    The previous version walked back 10 *calendar* days from now and stopped at
    yesterday. services.movers.get_movers reads the last two COMPLETED exchange
    sessions, and on any weekday the most recent one is today -- so the fixture
    could never cover it and the route correctly returned 0 rows with
    coverage {requested: 75, valid: 0, excluded: 75}.

    That made this test pass on weekends and fail every weekday, so CI went red
    intermittently depending on the day it ran.

    Now the dates come from the service's own session pair, so the fixture is
    correct on any calendar day. The drift is applied across the emitted bars
    in order, so the expected ranking is unchanged.
    """
    from datetime import UTC, datetime, timedelta

    from services.movers import completed_session_pair

    last, prior = completed_session_pair()
    last_d = datetime.strptime(last, "%Y-%m-%d")
    prior_d = datetime.strptime(prior, "%Y-%m-%d")

    # last session plus a few sessions before it, so the pair is always present.
    sessions = [last_d - timedelta(days=i) for i in range(0, 6)]
    sessions.append(prior_d)

    rows = []
    base = 100.0
    n = len(sessions)
    for i, day in enumerate(sessions):
        c = base * (1.0 + drift) ** (n - 1 - i)
        rows.append({"t": f"{day.strftime('%Y-%m-%d')}T12:00:00-04:00",
                     "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000})
    return rows


async def _fake_daily(sym, days=10, *, budget_wait_s=0):
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
