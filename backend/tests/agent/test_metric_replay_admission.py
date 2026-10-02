"""Recorded metric admission never calculates new Greeks or substitutes live."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import duckdb
import pytest

import server
from services.agent.display_map import display_facts
from services.agent.reads import ResearchReads
from services.heatmap_history import record_snapshot, replay_snapshot
from services.solstice_replay import recorded_display
from tests.agent.test_display_map import NOW
from tests.agent.test_window_admission import frames, values
from tests.offline_network import deny_external_network  # noqa: F401

UNITS = {"vex":"USD delta-notional/+1 vol pt", "charm":"dollar_charm_1pct_per_year"}
IDS = {"vex":"vex_net_1volpt", "charm":"charm_net_1pct_year_v1"}


def recording(metric, value=0):
    _,raw = frames()
    raw["grid"].update({metric+"_grid":{"2026-09-18":{"100":value}}})
    meta = dict(exposure_basis="VEX_1VOLPT" if metric=="vex" else "CHARM",weight_basis="OI",unit=UNITS[metric],
                formula_version="gex.v2",model="local-bs-vanna.v1" if metric=="vex" else "local-bs-charm.v1",
                metric_id=IDS[metric],status="ok",reason=None,quarantined=0,invalid_type=0,
                                **{"missing_vanna_inputs" if metric=="vex" else "missing_charm_inputs":0},record_version="metric-record.v1",data_source=raw["data_source"],
                map_query=raw["map_query"],event_time=raw["event_time"],fetched_at=raw["fetched_at"],available_at=raw["asof"],
                scope={"strikes":raw["grid"]["strikes"],"expiries":raw["grid"]["expiries"]})
    raw["grid"][metric+"_meta"] = meta
    with duckdb.connect(":memory:") as conn:
        assert record_snapshot(conn,raw,"fixture","snap1") == "snap1"
        return recorded_display(replay_snapshot(conn,"snap1"),"SPY","snap1")


def selection(raw,metric):
    return dict(contextVersion=2,page="heatseeker",ticker="SPY",snapshotId="snap1",displayMode="replay",metric=metric,
                overlayMetric="raw",activePane=metric,mapQuery=raw["map_query"],mapVersion=raw["asof"],provider=raw["data_source"],
                formula="gex.v2",mapStrikes=[100],mapExpiries=["2026-09-18"],selectedStrike=100,selectedExpiry="2026-09-18")


@pytest.mark.parametrize("metric",["vex","charm"])
@pytest.mark.parametrize("value",[0,-123.5])
def test_projection_and_facts_preserve_recorded_signed_zero_and_metric_specific_units(metric,value):
    raw = recording(metric,value)
    assert raw["grid"][metric+"_grid"]["2026-09-18"]["100"] == value
    facts,gaps = display_facts(raw,selection(raw,metric),"SPY",NOW)
    cell = next(f for f in facts if f["metric"] == "Selected display cell")
    assert cell["value"] == value and cell["unit"] == UNITS[metric]
    assert values(facts)["Displayed signed profile"] == [value]
    assert values(facts)["Recorded metric convention"] == IDS[metric]
    assert any("recorded" in g.lower() for g in gaps)


@pytest.mark.parametrize("metric",["vex","charm"])
@pytest.mark.parametrize("field,value,reason",[("unit","other","CONVENTION_CONFLICT"),("model","live-recomputed","CONVENTION_CONFLICT"),
    ("formula_version","other","CONVENTION_CONFLICT"),("data_source","other","PROVENANCE_CONFLICT"),
    ("map_query",{},"SCOPE_CONFLICT"),("event_time",None,"SOURCE_CLOCK_INVALID"),("record_version",None,"ENVELOPE_INCOMPLETE"),
    ("available_at",(NOW+timedelta(seconds=1)).isoformat(),"SOURCE_CLOCK_INVALID")])
def test_incomplete_conflicting_old_metric_records_refuse_all_facts(metric,field,value,reason):
    raw = recording(metric,1)
    raw["grid"][metric+"_meta"][field] = value
    facts,gaps = display_facts(raw,selection(raw,metric),"SPY",NOW)
    assert not facts and any(reason in g for g in gaps)


@pytest.mark.parametrize("metric",["vex","charm"])
def test_missing_cell_remains_unknown_and_partial_coverage_preserves_valid_recorded_cell(metric):
    raw = recording(metric,12)
    raw["grid"][metric+"_meta"].update(status="partial",quarantined=1)
    facts,gaps = display_facts(raw,selection(raw,metric),"SPY",NOW)
    assert values(facts)["Selected display cell"] == 12
    assert any("partial" in g.lower() for g in gaps)
    raw["grid"][metric+"_grid"]["2026-09-18"]["100"] = None
    facts,gaps = display_facts(raw,selection(raw,metric),"SPY",NOW)
    assert "Selected display cell" not in values(facts)
    assert values(facts)["Displayed signed profile"] == [None]  # explicit unknown, never zero
    assert gaps


@pytest.mark.parametrize("metric",["vex","charm"])
def test_unknown_recorded_metric_population_quality_is_not_invented_complete(metric):
    raw = recording(metric,7)
    raw["grid"][metric+"_meta"].pop("quarantined")
    facts,gaps = display_facts(raw,selection(raw,metric),"SPY",NOW)
    assert not facts and any("COVERAGE_UNDECLARED" in g for g in gaps)


@pytest.mark.asyncio
@pytest.mark.parametrize("metric",["vex","charm"])
async def test_metric_reads_only_the_selected_record_no_live_recomputation(metric):
    raw = recording(metric,7)
    records = Mock(return_value=deepcopy(raw))
    forbidden = Mock(side_effect=AssertionError("Replay accessed live data"))
    reads = ResearchReads(forbidden,forbidden,forbidden,read_recorded_map=records)
    out = await reads.snapshot("SPY","all",screen=selection(raw,metric),now=NOW)
    assert values(out["facts"])["Selected display cell"] == 7
    forbidden.assert_not_called()
    records.assert_called_once_with("SPY","snap1")


def test_actual_display_producer_declares_registered_vex_and_charm_conventions():
    _,raw = frames()
    raw["contracts"][0].update(iv=.25,T=.02)
    _,_,_,grid = server._display_surfaces(100,raw["contracts"],"SPY",scalp=False)
    for metric in ("vex","charm"):
        meta = grid[metric+"_meta"]
        assert meta["unit"] == UNITS[metric]
        assert meta["formula_version"] == "gex.v2"
        assert meta["metric_id"] == IDS[metric]
