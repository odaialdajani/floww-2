"""Comparable stored-window admission, including zero and typed exclusions."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import duckdb
import pytest

from services import solstice_window
from services.agent.contracts import request_spec
from services.agent.display_map import display_facts
from services.agent.reads import ResearchReads
from services.heatmap_history import record_snapshot, replay_snapshot
from services.solstice_metric_contract import build_surface_coverage, window_grid_section
from services.solstice_replay import recorded_display
from tests.agent.test_display_map import NOW, _v2_raw, _v2_screen
from tests.agent.test_exact_contract_admission import contract
from tests.offline_network import deny_external_network  # noqa: F401


def frames():
    current = _v2_raw()
    current.update(contracts=[contract(volume=110,received_at=(NOW-timedelta(seconds=2)).isoformat())], exposure_basis="OI", fetched_at=(NOW-timedelta(seconds=2)).isoformat(),
                   event_time=(NOW-timedelta(seconds=5)).isoformat(), source_received_at=NOW.isoformat(), expiries_used=["2026-09-18"])
    current["metrics"]["walls"] = [{"wall_id":"w1","low":99,"high":101,"gross":12,"net":3}]
    previous = deepcopy(current)
    previous.update(asof=(NOW-timedelta(seconds=50)).isoformat(), event_time=(NOW-timedelta(seconds=60)).isoformat(),
                    fetched_at=(NOW-timedelta(seconds=55)).isoformat(), source_received_at=(NOW-timedelta(seconds=55)).isoformat(),
                    contracts=[contract(volume=100,received_at=(NOW-timedelta(seconds=55)).isoformat(),
                                        bid_timestamp=(NOW-timedelta(seconds=90)).isoformat(),ask_timestamp=(NOW-timedelta(seconds=80)).isoformat())])
    return previous, current


def selection():
    return _v2_screen(overlayMetric="window", selectedWall="w1", selectedStrike=100,
                      selectedExpiry="2026-09-18", windowBaselineId="prior", mapStrikes=[100])


def pair(previous=None, current=None):
    p, c = frames()
    p, c = previous or p, current or c
    with duckdb.connect(":memory:") as conn:
        assert record_snapshot(conn, p, "fixture", "prior") == "prior"
        baseline = replay_snapshot(conn, "prior")
        window = solstice_window.recorded_window_activity(baseline, c, c["spot"])
        c["metrics"]["grids"] = {"window":window_grid_section(window)}
        c["metrics"]["surface_coverage"] = build_surface_coverage(c["metrics"], c["grid"])
        assert record_snapshot(conn, c, "fixture", "snap1") == "snap1"
        raw = recorded_display(replay_snapshot(conn,"snap1"),"SPY","snap1")
        if raw is not None:
            raw["window_baseline"] = recorded_display(baseline,"SPY","prior")
        return raw, window


def values(facts):
    return {f["metric"]:f["value"] for f in facts}


def test_measured_zero_window_is_a_valid_observation_not_a_missing_baseline():
    p,c = frames()
    pmeta = dict(ticker="SPY",data_source="fixture",scope_key="exact",formula_version="gex.v2",session_date="2026-09-11",asof=p["event_time"])
    cmeta = {**pmeta,"asof":c["event_time"]}
    w = solstice_window.window_activity_surface(pmeta,cmeta,[contract(volume=100)],[contract(volume=100)],100)
    assert w["status"] == "ok" and w["window_net"] == 0
    assert w["coverage"]["n_comparable_contracts"] == 1


def test_window_request_and_two_record_projection_keep_interval_convention_and_server_numbers():
    assert request_spec({"question":"Why this wall?","screen":selection()})["screen"]["overlayMetric"] == "window"
    raw,w = pair()
    assert w["window_net"] == 500
    section = raw["metrics"]["grids"]["window"]
    assert section["comparison"]["previous_snapshot_id"] == "prior"
    assert section["interval"] == w["interval"]
    facts,gaps = display_facts(raw,{**selection(),"selectedValue":999,"windowNet":999},"SPY",NOW)
    v = values(facts)
    assert v["Selected display cell"] == 500
    assert v["Displayed signed profile"] == [500]
    assert v["Window interval start"] == frames()[0]["event_time"]
    assert v["Window interval end"] == frames()[1]["event_time"]
    assert v["Window volume correction policy"] == "refuse-retraction"
    assert any("aggressor" in g.lower() or "not buyer" in g.lower() for g in gaps)


def test_recording_preserves_missing_and_invalid_delta_input_states_without_losing_valid_values():
    p,c = frames()
    for raw,volume in ((p,100),(c,110)):
        raw["contracts"] += [contract(osi="missing",delta=None,volume=volume),contract(osi="invalid",delta=True,volume=volume)]
    raw,w = pair(p,c)
    assert w["window_net"] == 500
    assert w["coverage"]["n_missing_delta"] == 1
    assert w["coverage"]["n_invalid_delta"] == 1
    sec = raw["metrics"]["grids"]["window"]
    assert sec["cell_missing_delta"]["2026-09-18"]["100"] == 1
    assert sec["cell_invalid_delta"]["2026-09-18"]["100"] == 1
    facts,gaps = display_facts(raw,selection(),"SPY",NOW)
    assert values(facts)["Selected display cell"] == 500
    assert values(facts)["Displayed profile missing delta"] == [1]
    assert values(facts)["Displayed profile invalid delta"] == [1]
    assert any("partial" in g.lower() for g in gaps)


def test_nonfinite_input_is_recorded_as_invalid_not_a_failed_snapshot_or_missing_delta():
    p,c = frames()
    for raw,volume in ((p,100),(c,110)):
        raw["contracts"].append(contract(osi="invalid-nan",delta=float("nan"),volume=volume))
    raw,w = pair(p,c)
    assert raw is not None and w["coverage"]["n_invalid_delta"] == 1
    assert w["coverage"]["n_missing_delta"] == 0 and w["window_net"] == 500


@pytest.mark.parametrize("field,value,reason", [
    ("data_source","other","PROVIDER_MISMATCH"),
    ("formula_version","other","FORMULA_MISMATCH"),
    ("map_query",{"bad":"scope"},"IDENTITY_UNDECLARED"),
    ("event_time",None,"IDENTITY_UNDECLARED"),
    ("event_time",(NOW+timedelta(seconds=1)).isoformat(),"SOURCE_CLOCK_INVALID"),
])
def test_producer_refuses_uncomparable_or_future_source_context(field,value,reason):
    p,c = frames()
    c[field] = value
    _,w = pair(p,c)
    assert w["status"] == "unavailable" and w["window_net"] is None
    assert w["reason"] == reason


def test_retraction_is_quarantined_never_negative_flow():
    p,c = frames()
    c["contracts"] = [contract(volume=99)]
    _,w = pair(p,c)
    assert w["reason"] == "VOLUME_REBASE" and w["window_net"] is None


@pytest.mark.parametrize("mutate", [
    lambda raw:raw.pop("window_baseline"),
    lambda raw:raw["window_baseline"].update(snapshotId="other"),
    lambda raw:raw["metrics"]["grids"]["window"].pop("comparison"),
    lambda raw:raw["metrics"]["grids"]["window"].update(greek_convention="recomputed-live"),
])
def test_old_incomplete_or_conflicting_records_withhold_all_facts(mutate):
    raw,_ = pair()
    mutate(raw)
    facts,gaps = display_facts(raw,selection(),"SPY",NOW)
    assert facts == [] and gaps


def test_previous_record_must_be_available_before_current_without_lookahead():
    p,c = frames()
    p["asof"] = (NOW+timedelta(seconds=1)).isoformat()
    _,w = pair(p,c)
    assert w["reason"] == "AVAILABLE_AT_CONFLICT" and w["window_net"] is None


def test_source_session_is_new_york_date_not_utc_build_day():
    p,c = frames()
    p.update(event_time="2026-09-10T23:59:00+00:00",fetched_at="2026-09-10T23:59:01+00:00",asof="2026-09-10T23:59:02+00:00")
    c.update(event_time="2026-09-11T00:01:00+00:00",fetched_at="2026-09-11T00:01:01+00:00",asof="2026-09-11T00:01:02+00:00")
    _,w = pair(p,c)
    assert w["window_net"] == 500
    assert w["comparison"]["current"]["session_date"] == "2026-09-10"
    c.update(event_time="2026-09-11T04:01:00+00:00",fetched_at="2026-09-11T04:01:01+00:00",asof="2026-09-11T04:01:02+00:00")
    _,w = pair(p,c)
    assert w["reason"] == "SESSION_ROLL" and w["window_net"] is None


def test_displayed_interval_conflict_withholds_all_facts():
    raw,_ = pair()
    facts,gaps = display_facts(raw,{**selection(),"windowInterval":{"start":"wrong","end":"wrong"}},"SPY",NOW)
    assert not facts and any("INTERVAL_CONFLICT" in g for g in gaps)


@pytest.mark.asyncio
async def test_window_research_reads_two_exact_records_and_no_live_provider():
    raw,_ = pair()
    previous = raw.pop("window_baseline")
    records = Mock(side_effect=lambda ticker,sid:{"snap1":raw,"prior":previous}.get(sid))
    forbidden = Mock(side_effect=AssertionError("Window requested a live substitute"))
    reads = ResearchReads(forbidden,forbidden,forbidden,read_recorded_map=records)
    snap = await reads.snapshot("SPY","all",screen=selection(),now=NOW)
    assert values(snap["facts"])["Selected display cell"] == 500
    assert [c.args for c in records.call_args_list] == [("SPY","snap1"),("SPY","prior")]
    forbidden.assert_not_called()
