"""Count scope is applied to listed expiry dates, not calendar-day substitutes."""
from unittest.mock import AsyncMock

import pytest

import server
from services import cvserver_client


@pytest.mark.asyncio
async def test_sparse_enrichment_does_not_expand_requested_expiry_population(monkeypatch):
    first, second = "2031-01-17", "2031-01-24"
    rows = [{"strike": s, "expiry": e, "type": "call", "oi": 100, "volume": 10,
             "gamma": .1, "delta": .5, "iv": .25, "T": 30/365, "multiplier": 100}
            for e in [second, first] for s in range(80, 121)]
    fetch = AsyncMock(return_value={"ticker": "SCOPEFX", "spot": 100,
                                   "contracts": rows, "expiries": [second, first], "data_source": "public_api"})
    monkeypatch.setattr(server, "fetch_spot_and_chains_merged", fetch)
    monkeypatch.setattr(cvserver_client, "CVSERVER_API_KEY", "")
    monkeypatch.setattr(server, "save_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(server, "calc_realized_volatility", lambda *_args: None)
    monkeypatch.setattr(server, "calc_iv_rank_percentile", lambda *_args: {"iv_rank": None, "status": "unavailable"})
    monkeypatch.setattr(server, "velocity_and_rolling", AsyncMock(return_value={"history": []}))
    server._BUILD_HEATMAP_CACHE.clear()
    out = await server._build_heatmap_impl("SCOPEFX", max_expiries=1, with_taps=False)
    assert out["expiries_used"] == [first]
    assert out["grid"]["expiries"] == [first]
    for name in ("delta", "activity", "session_delta_volume"):
        assert out["metrics"]["grids"][name]["expiries"] == [first]
    assert out["map_query"]["expiries"] == 1
