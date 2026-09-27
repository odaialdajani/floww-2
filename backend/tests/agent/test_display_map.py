from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from services.agent.display_map import display_facts, map_cache_key
from services.agent.reads import ResearchReads
from services.agent.research import deterministic_answer

NOW = datetime(2026, 9, 11, 18, tzinfo=UTC)
QUERY = dict(expiries=6, mode="day", dte=None, scalp=False, withTaps=True, maxStrikes=80)


def selection():
    return dict(
        page="flowseeker-pro",
        ticker="SPY",
        mapQuery=QUERY,
        mapVersion=NOW.isoformat(),
        mapStrikes=[95, 100, 105],
        mapExpiries=["2026-09-18"],
        metric="gex",
    )


def cached():
    return dict(
        ticker="SPY",
        spot=100,
        asof=NOW.isoformat(),
        event_time=NOW.isoformat(),
        data_source="recorded test source",
        map_query=QUERY,
        gamma_flip={"gamma_flip": 98},
        grid=dict(strikes=[95, 100, 105], expiries=["2026-09-18"], grid={"2026-09-18": {"95": -4, "100": 3, "105": 8}}),
    )


def test_exact_cache_key_and_reject_unbounded_or_unknown_query():
    assert map_cache_key("SPY", QUERY) == "SPY:6:day:None:False:True:80"
    for bad in (
        {**QUERY, "expiries": True},
        {**QUERY, "maxStrikes": 999999},
        {**QUERY, "mode": "arbitrary"},
        {**QUERY, "url": "external"},
    ):
        with pytest.raises(ValueError):
            map_cache_key("SPY", bad)


def test_displayed_values_have_separate_scope_units_and_source():
    facts, gaps = display_facts(cached(), selection(), "SPY", NOW)
    by_metric = {f["metric"]: f for f in facts}
    assert by_metric["Displayed net gamma"]["value"] == [-4, 3, 8]
    assert by_metric["Displayed cumulative gamma"]["value"] == [-4, -1, 7]
    assert by_metric["Displayed total gamma"]["value"] == 7
    assert by_metric["Displayed flip"]["value"] == 98
    assert by_metric["Displayed net gamma"]["unit"] == "display gamma units"
    assert all(f["source"] == "recorded test source" for f in facts)
    assert by_metric["Displayed net gamma"]["horizon"].startswith("display:")
    assert by_metric["Displayed flip"]["horizon"].startswith("map:")
    assert by_metric["Displayed flip"]["horizon"] == by_metric["Cached map price"]["horizon"]
    assert not gaps


def test_missing_cells_stop_cumulative_and_never_turn_into_zero():
    raw = cached()
    raw["grid"]["grid"]["2026-09-18"]["100"] = None
    facts, gaps = display_facts(raw, selection(), "SPY", NOW)
    values = {f["metric"]: f["value"] for f in facts}
    assert values["Displayed net gamma"] == [-4, None, 8]
    assert values["Displayed cumulative gamma"] == [-4, None, None]
    assert "Displayed total gamma" not in values
    assert gaps


def test_changed_version_wrong_ticker_and_invented_selection_withhold_map():
    for change in (
        {"mapVersion": "old"},
        {"mapStrikes": [999]},
        {"ticker": "QQQ"},
        {"mapExpiries": ["2026-10-01"]},
        {"mapVersion": None},
    ):
        facts, gaps = display_facts(cached(), {**selection(), **change}, "SPY", NOW)
        assert facts == [] and gaps


def test_receipt_or_build_time_does_not_establish_freshness():
    raw = cached()
    del raw["event_time"]
    raw["fetched_at"] = NOW.isoformat()
    facts, gaps = display_facts(raw, selection(), "SPY", NOW)
    assert facts and all(f["status"] == "degraded" and f["event_time"] is None for f in facts)
    assert gaps


def test_selected_vex_cell_uses_verified_server_value_and_scope_changes_identity():
    raw = cached()
    raw["grid"]["vex_grid"] = {"2026-09-18": {"95": 1, "100": 22, "105": 3}}
    screen = {
        **selection(),
        "page": "heatseeker",
        "metric": "vex",
        "selectedStrike": 100,
        "selectedExpiry": "2026-09-18",
        "selectedValue": 999999,
    }
    facts, gaps = display_facts(raw, screen, "SPY", NOW)
    cell = next(f for f in facts if f["metric"] == "Selected display cell")
    assert cell["value"] == 22 and cell["unit"] == "display vex units"
    before = deepcopy(cell)
    screen["mapStrikes"] = [100]
    other, _ = display_facts(raw, screen, "SPY", NOW)
    assert next(f for f in other if f["metric"] == cell["metric"])["id"] != before["id"]


@pytest.mark.asyncio
async def test_real_research_read_uses_exact_cache_query_and_keeps_question_expiry_separate():
    queries = []

    def peek(ticker, query):
        queries.append((ticker, query))
        return cached()

    reads = ResearchReads(lambda *a: {}, peek, lambda *a: [])
    snap = await reads.snapshot("SPY", "all", selected_expiry="2026-10-16", screen=selection(), now=NOW)
    assert queries == [("SPY", QUERY)]
    assert snap["window"]["start"] == "2026-10-16"
    answer = deterministic_answer([snap], {"tickers": ["SPY"], "screen": selection()})
    assert "above its flip of 98 USD" in answer["sections"][0]["text"]
    assert "not recomputed for visible rows" in answer["sections"][0]["text"]
    assert next(f["value"] for f in snap["facts"] if f["metric"] == "Displayed expiry dates") == ["2026-09-18"]
    other = await reads.snapshot(
        "SPY", "all", selected_expiry="2026-10-16", screen={**selection(), "mapStrikes": [100]}, now=NOW
    )
    assert other["snapshot_id"] != snap["snapshot_id"]


def test_visibly_stale_map_cannot_support_current_comparison_and_actual_query_is_required():
    raw = cached()
    raw["event_time"] = (NOW - timedelta(seconds=121)).isoformat()
    facts, gaps = display_facts(raw, selection(), "SPY", NOW)
    assert facts and all(f["status"] == "stale" for f in facts)
    raw["map_query"] = {**QUERY, "maxStrikes": 200}
    facts, gaps = display_facts(raw, selection(), "SPY", NOW)
    assert facts == [] and gaps


def test_solstice_flip_priority_matches_visible_sidebar():
    raw = cached()
    raw["flip_zones"] = [{"price": 97}]
    facts, _ = display_facts(raw, {**selection(), "page": "heatseeker"}, "SPY", NOW)
    assert next(f["value"] for f in facts if f["metric"] == "Displayed flip") == 97
