"""Next listed is a server selection, never a client date or 0DTE substitute."""
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import server
from services import cvserver_client, duckdb_engine
from services.agent.display_map import map_cache_key
from tests.offline_network import deny_external_network  # noqa: F401


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        # UTC is already Saturday; New York is still Friday.
        return datetime(2026, 10, 3, 1, tzinfo=UTC).astimezone(tz)


@pytest.fixture
def source(monkeypatch):
    rows = [dict(strike=100.0, expiry=e, type="call", gamma=.1, delta=.5,
                 oi=100, volume=10, iv=.25, T=7/365, multiplier=100)
            for e in ("2026-10-01", "2026-10-02", "2026-10-05", "2026-10-09")]
    raw = dict(ticker="SPY", spot=100.0, contracts=rows,
               expiries=[c["expiry"] for c in rows], data_source="r13_fixture")
    monkeypatch.setattr(server, "datetime", Clock)
    monkeypatch.setattr(server, "fetch_spot_and_chains_merged", AsyncMock(side_effect=lambda *a, **kw: deepcopy(raw)))
    monkeypatch.setattr(server, "save_snapshot", AsyncMock())
    monkeypatch.setattr(server, "velocity_and_rolling", AsyncMock(return_value={}))
    monkeypatch.setattr(server, "calc_realized_volatility", lambda *a: None)
    monkeypatch.setattr(server, "calc_iv_rank_percentile", lambda *a: {})
    monkeypatch.setattr(cvserver_client, "CVSERVER_API_KEY", "")
    monkeypatch.setattr(duckdb_engine.db, "_conn", None)
    server._BUILD_HEATMAP_CACHE.clear()
    yield raw
    server._BUILD_HEATMAP_CACHE.clear()


@pytest.mark.asyncio
async def test_next_listed_uses_exchange_date_and_one_actual_expiry(source):
    out = await server._build_heatmap_impl("SPY", with_taps=False, expiry_scope="next")
    assert out["expiries_used"] == ["2026-10-02"]
    assert out["grid"]["expiries"] == ["2026-10-02"]
    assert out["grid"]["grid"]["2026-10-02"]["100"] == 100000
    assert out["map_query"]["expiryScope"] == "next"
    assert out["map_query"]["sessionDate"] == "2026-10-02"
    assert out["scope_selection"]["selected_expiries"] == out["expiries_used"]
    assert map_cache_key("SPY", out["map_query"]) in server._BUILD_HEATMAP_CACHE
    assert len(source["contracts"]) == 4


@pytest.mark.asyncio
async def test_next_listed_empty_scope_is_unavailable_not_a_future_or_zero_fill(source):
    source["contracts"][:] = [source["contracts"][0]]
    out = await server._build_heatmap_impl("SPY", with_taps=False, expiry_scope="next")
    assert out["status"] == "unavailable"
    assert out["reason"] == "NO_LISTED_EXPIRY_IN_BOUND"
    assert out["strikes"] == [] and out["expiries_used"] == []
    assert out["grid"]["grid"] == {}
    assert out["metrics"]["gex_net_v1"] is None
    assert out["snapshotId"]


@pytest.mark.asyncio
async def test_weekend_next_listed_does_not_change_zero_dte(source):
    source["contracts"][:] = source["contracts"][2:]
    nxt = await server._build_heatmap_impl("SPY", with_taps=False, expiry_scope="next")
    zero = await server._build_heatmap_impl("SPY", with_taps=False, dte=0)
    assert nxt["expiries_used"] == ["2026-10-05"]
    assert zero["expiries_used"] == []
    assert zero["map_query"].get("expiryScope") is None
    assert map_cache_key("SPY", nxt["map_query"]) != map_cache_key("SPY", zero["map_query"])


@pytest.mark.asyncio
async def test_next_listed_identity_distinguishes_loaded_even_when_cells_match(source):
    from services.heatmap_snapshot import snapshot_id_for
    nxt = await server._build_heatmap_impl("SPY", with_taps=False, expiry_scope="next")
    other = deepcopy(nxt)
    other["map_query"].pop("expiryScope")
    other["map_query"].pop("sessionDate")
    other.pop("scope_selection")
    assert snapshot_id_for(nxt) != snapshot_id_for(other)


def test_mounted_route_owns_scope_and_rejects_conflicting_dte(source):
    client = TestClient(server.app)  # deliberately no lifespan
    out = client.get("/api/heatmap/SPY?expiry_scope=next&taps=false")
    assert out.status_code == 200
    assert out.json()["expiries_used"] == ["2026-10-02"]
    conflict = client.get("/api/heatmap/SPY?expiry_scope=next&dte=0")
    assert conflict.status_code == 422
