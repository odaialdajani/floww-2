"""Selected listed contracts resolve from the owning record, never live/client quotes."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import duckdb
import pytest

from services.agent.contracts import request_spec
from services.agent.display_map import display_facts
from services.agent.reads import ResearchReads
from services.heatmap_history import record_snapshot, replay_snapshot
from services.solstice_replay import recorded_display
from tests.agent.test_display_map import NOW, _v2_raw, _v2_screen
from tests.offline_network import deny_external_network  # noqa: F401

OSI = "SPY260918C00100000"


def contract(**changes):
    row = dict(osi=OSI, strike_exact="100.0000000000000000001", strike=100,
               expiry="2026-09-18", type="call", series="SPY", multiplier=100,
               multiplier_source="fixture-listed-spec", data_source="recorded test source",
               bid=0, ask=1, volume=0, oi=100, delta=.5, gamma=.01,
               bid_timestamp=(NOW-timedelta(seconds=30)).isoformat(),
               ask_timestamp=(NOW-timedelta(seconds=20)).isoformat(), received_at=NOW.isoformat())
    return {**row, **changes}


def payload():
    raw = _v2_raw()
    raw["metrics"]["walls"] = [{"wall_id": "w1", "low": 99, "high": 101, "gross": 12, "net": 3}]
    raw.update(contracts=[contract()], fetched_at=NOW.isoformat(), exposure_basis="OI",
               expiries_used=["2026-09-18"], source_received_at=NOW.isoformat())
    return raw


def screen(**changes):
    return _v2_screen(selectedWall="w1", selectedStrike=100, selectedExpiry="2026-09-18",
                      selectedContract={"osi": OSI}, **changes)


def record(raw=None):
    with duckdb.connect(":memory:") as conn:
        raw = raw or payload()
        assert record_snapshot(conn, raw, "fixture-scope", "snap1") == "snap1"
        return recorded_display(replay_snapshot(conn, "snap1"), "SPY", "snap1")


def by_metric(facts):
    return {f["metric"]: f for f in facts}


def test_exact_contract_request_admitted_only_with_v2_symbol_scope():
    assert request_spec({"question": "What confirms this selection?", "screen": screen()})["screen"]["selectedContract"] == {"osi": OSI}
    with pytest.raises(ValueError, match="symbol|selected|contract"):
        request_spec({"question": "What about $QQQ?", "screen": screen()})
    with pytest.raises(ValueError, match="v2|contract"):
        request_spec({"question": "Why?", "screen": {"ticker": "SPY", "selectedContract": {"osi": OSI}}})


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_real_record_projection_owns_exact_decimal_quote_age_zero_and_provenance(mode):
    facts, gaps = display_facts(record(), {**screen(displayMode=mode), "selectedValue": 999,
                                          "selectedContract": {"osi": OSI, "bid": 999, "multiplier": 1}}, "SPY", NOW)
    v = by_metric(facts)
    assert v["Exact contract strike"]["value"] == "100.0000000000000000001"
    assert v["Exact contract OSI"]["value"] == OSI
    assert v["Exact contract bid"]["value"] == 0
    assert v["Exact contract ask"]["value"] == 1
    assert v["Exact contract bid age"]["value"] == 30
    assert v["Exact contract ask age"]["value"] == 20
    assert v["Exact contract multiplier"]["value"] == "100.0"
    assert v["Exact contract multiplier source"]["value"] == "fixture-listed-spec"
    assert v["Exact contract owning snapshot"]["value"] == "snap1"
    assert v["Exact contract bid"]["snapshot_id"] == "snap1"
    assert v["Exact contract bid"]["event_time"] == contract()["bid_timestamp"]
    assert any("aggressor" in g.lower() for g in gaps)
    if mode == "replay":
        assert all(f["status"] != "ok" for f in facts)


@pytest.mark.parametrize("change,reason", [
    ({"osi": None}, "CONTRACT_IDENTITY_INCOMPLETE"),
    ({"multiplier_source": None}, "CONTRACT_MULTIPLIER_PROVENANCE_UNAVAILABLE"),
    ({"multiplier": None}, "CONTRACT_MULTIPLIER_PROVENANCE_UNAVAILABLE"),
    ({"bid_timestamp": None}, "CONTRACT_QUOTE_CLOCK_UNAVAILABLE"),
    ({"bid_timestamp": (NOW+timedelta(seconds=1)).isoformat()}, "CONTRACT_QUOTE_CLOCK_INVALID"),
    ({"bid": None}, "CONTRACT_QUOTE_UNAVAILABLE"),
    ({"data_source": "different"}, "CONTRACT_PROVIDER_CONFLICT"),
])
def test_incomplete_or_conflicting_record_never_answers_with_map_or_live_substitute(change, reason):
    raw = payload()
    raw["contracts"] = [contract(**change)]
    selection = screen()
    if "osi" in change:
        selection["selectedContract"] = {"strike": "100.0000000000000000001", "expiry": "2026-09-18", "type": "call"}
    facts, gaps = display_facts(record(raw), selection, "SPY", NOW)
    assert facts == []
    assert any(reason in gap for gap in gaps), gaps


@pytest.mark.parametrize("change", [
    {"selectedStrike": 95}, {"selectedExpiry": None},
    {"selectedContract": {"osi": "other"}},
    {"selectedContract": {"osi": OSI, "strike": "100.0000000000000000002"}},
    {"selectedContract": {"osi": OSI, "series": "other"}},
])
def test_contract_selector_must_match_visible_cell_and_listed_identity(change):
    facts, gaps = display_facts(record(), {**screen(), **change}, "SPY", NOW)
    assert facts == [] and gaps


def test_stale_quotes_remain_historical_facts_with_actual_ages_not_fresh_claims():
    facts, gaps = display_facts(record(), screen(), "SPY", NOW+timedelta(seconds=300))
    bid = by_metric(facts)["Exact contract bid"]
    assert bid["value"] == 0 and bid["status"] == "stale"
    assert by_metric(facts)["Exact contract bid age"]["value"] == 330
    assert any("stale" in g.lower() for g in gaps)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["live", "replay"])
async def test_selected_contract_reads_owning_record_only(mode):
    forbidden = Mock(side_effect=AssertionError("Selected contract attempted live work"))
    recorded = Mock(return_value=record())
    reads = ResearchReads(forbidden, forbidden, forbidden, read_daily_bars=forbidden, read_recorded_map=recorded)
    snap = await reads.snapshot("SPY", "all", screen=screen(displayMode=mode), now=NOW)
    recorded.assert_called_once_with("SPY", "snap1")
    forbidden.assert_not_called()
    assert by_metric(snap["facts"])["Exact contract OSI"]["value"] == OSI


def test_contract_rows_from_another_owning_snapshot_cannot_be_merged():
    raw = record()
    raw["contracts"] = [dict(raw["contracts"][0], snapshot_id="other")]
    facts, gaps = display_facts(raw, screen(), "SPY", NOW)
    assert facts == [] and any("CONTRACT_SNAPSHOT_CONFLICT" in gap for gap in gaps)


@pytest.mark.parametrize("coverage", [None, {"truncated": True}, {"truncated": False, "requested": 2, "returned": 1}])
def test_incomplete_population_metadata_remains_refused(coverage):
    raw = record()
    raw["contract_coverage"] = coverage
    facts, gaps = display_facts(raw, screen(), "SPY", NOW)
    assert facts == [] and any("CONTRACT_POPULATION_PARTIAL" in gap for gap in gaps)


def test_future_record_cannot_be_read_before_its_available_at_clock():
    facts, gaps = display_facts(record(), screen(), "SPY", NOW-timedelta(seconds=1))
    assert facts == [] and any("CONTRACT_QUOTE_CLOCK_INVALID" in gap for gap in gaps)


def test_recorded_projection_does_not_mutate_the_record():
    raw = record()
    before = deepcopy(raw)
    display_facts(raw, screen(), "SPY", NOW)
    assert raw == before
