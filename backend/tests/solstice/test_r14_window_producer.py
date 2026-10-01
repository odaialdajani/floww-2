"""Actual producer/recorder/admission path, providers blocked and no lifespan."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import duckdb
import pytest

import server
from services import cvserver_client, duckdb_engine
from services.agent.display_map import display_facts
from services.heatmap_history import record_snapshot, replay_snapshot
from services.solstice_replay import recorded_display
from tests.agent.test_exact_contract_admission import contract
from tests.offline_network import deny_external_network  # noqa: F401


async def produce(conn, *, volume=110, baseline=True, source_clock=True, query_conflict=False):
    now = datetime.now(UTC)
    expiry = (now.date() + timedelta(days=2)).isoformat()
    query = dict(expiries=4, mode="day", dte=None, scalp=False, withTaps=False, maxStrikes=200)
    row = contract(expiry=expiry, volume=volume, T=2/365, iv=.25, theta=-.02, vega=.1, received_at=(now-timedelta(seconds=2)).isoformat(),
                   bid_timestamp=(now-timedelta(seconds=5)).isoformat(), ask_timestamp=(now-timedelta(seconds=5)).isoformat())
    source = dict(ticker="SPY", spot=100, expiries=[expiry], contracts=[row], data_source="r14_fixture",
                  event_time=(now-timedelta(seconds=5)).isoformat() if source_clock else None,
                  fetched_at=(now-timedelta(seconds=2)).isoformat(), received_at=(now-timedelta(seconds=2)).isoformat())
    if baseline:
        previous = dict(ticker="SPY", spot=100, data_source="r14_fixture", formula_version="gex.v2", exposure_basis="OI",
                        asof=(now-timedelta(seconds=50)).isoformat(), event_time=(now-timedelta(seconds=60)).isoformat(),
                        fetched_at=(now-timedelta(seconds=55)).isoformat(), map_query={**query, "maxStrikes":80} if query_conflict else query,
                        contracts=[{**deepcopy(row),"volume":100}], grid={"strikes":[100],"expiries":[expiry],"grid":{expiry:{"100":10000}}})
        assert record_snapshot(conn, previous, "SPY:day:None:False", "prior") == "prior"
    server._BUILD_HEATMAP_CACHE.clear()
    with patch.object(cvserver_client,"CVSERVER_API_KEY",""), patch.object(duckdb_engine.db,"_conn",conn), \
         patch.object(server,"fetch_spot_and_chains_merged",AsyncMock(return_value=source)), \
         patch.object(server,"velocity_and_rolling",AsyncMock(return_value={"history":[]})), \
         patch.object(server,"save_snapshot",AsyncMock(return_value=None)), \
         patch.object(server,"calc_realized_volatility",return_value=None), \
         patch.object(server,"calc_iv_rank_percentile",return_value={"iv_rank":None,"status":"unavailable"}):
        result = await server._build_heatmap_impl("SPY",with_taps=False)
        tasks = [t for t in server._background_tasks if t.get_loop() is asyncio.get_running_loop()]
        if tasks:
            await asyncio.gather(*tasks)
    server._BUILD_HEATMAP_CACHE.clear()
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("volume,expected",[(110,500),(100,0)])
async def test_actual_producer_binds_window_to_source_interval_and_owning_record(volume,expected):
    with duckdb.connect(":memory:") as conn:
        payload = await produce(conn,volume=volume)
        section = payload["metrics"]["grids"]["window"]
        assert section["grid"][payload["expiries_used"][0]]["100"] == expected
        assert section["comparison"]["current"]["available_at"] == payload["asof"]
        assert section["interval"]["end"] == payload["event_time"]
        raw = recorded_display(replay_snapshot(conn,payload["snapshotId"]),"SPY",payload["snapshotId"])
        raw["window_baseline"] = recorded_display(replay_snapshot(conn,"prior"),"SPY","prior")
        screen = dict(contextVersion=2,page="heatseeker",ticker="SPY",metric="gex",overlayMetric="window",displayMode="live",
                      activePane="gex",snapshotId=payload["snapshotId"],windowBaselineId="prior",mapQuery=payload["map_query"],
                      mapVersion=payload["asof"],provider=payload["data_source"],formula="gex.v2",mapStrikes=[100],
                      mapExpiries=payload["expiries_used"],selectedStrike=100,selectedExpiry=payload["expiries_used"][0])
        facts,gaps = display_facts(raw,screen,"SPY",datetime.now(UTC))
        assert {f["metric"]:f["value"] for f in facts}["Selected display cell"] == expected, gaps


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs,reason",[({"baseline":False},"NO_BASELINE"),({"source_clock":False},"IDENTITY_UNDECLARED"),
                                         ({"query_conflict":True},"SCOPE_MISMATCH"),({"volume":99},"VOLUME_REBASE")])
async def test_actual_producer_refusal_is_explicit_not_zero_or_session_volume(kwargs,reason):
    with duckdb.connect(":memory:") as conn:
        if not kwargs.get("baseline",True):
            from services.heatmap_history import ensure_tables
            ensure_tables(conn)
        payload = await produce(conn,**kwargs)
        assert payload["metrics"]["window_dadgex_v1"] is None
        assert payload["metrics"]["grids"]["window"]["reason"] == reason
