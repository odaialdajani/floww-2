"""Market discovery is explicit, bounded and cache-only; selected SPY is not the universe."""
import asyncio
import time
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("mongomock_motor", reason="mongo mock unavailable in this env")
from mongomock_motor import AsyncMongoMockClient

from services.agent.contracts import request_spec
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService


@pytest.mark.parametrize("question", ["Find unusual activity across all available stocks", "Inspect the whole market", "What stands out across all available data?"])
def test_clear_market_question_does_not_become_selected_spy(question):
    spec = request_spec({"question": question, "screen": {"ticker": "SPY"}})
    assert spec["tickers"] == []
    assert spec["ticker"] is None
    assert spec["scope"] == "market"
    assert spec["market_limit"] == 50


@pytest.mark.asyncio
async def test_market_job_uses_one_cache_read_and_saves_owned_answer_without_selected_lookup():
    repository = AgentRepository(AsyncMongoMockClient().test)
    await repository.initialize()
    answer = dict(scope="market", summary="Cached market result", facts=[], gaps=[], sections=[], actions=[])
    reads = type("Reads", (), {"snapshot": AsyncMock(side_effect=AssertionError("Selected ticker must not narrow market discovery")),
                                "market_snapshot": AsyncMock(return_value=answer)})()
    model = type("Model", (), {"settings_for": AsyncMock(side_effect=AssertionError("Market discovery does not need model settings")),
                                "once": AsyncMock(side_effect=AssertionError("No model call for cache-only discovery"))})()
    service = ResearchService(repository, reads, model=model)
    spec = request_spec({"question": "Find unusual activity across all available stocks", "screen": {"ticker": "SPY"}})
    turn = await service.ask("alice", f"{int(time.time()*1000)}-{uuid.uuid4()}", spec)
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repository.read("alice", turn["turn_id"])
    assert saved["status"] == "completed"
    assert saved["answer"]["scope"] == "market"
    reads.snapshot.assert_not_awaited()
    reads.market_snapshot.assert_awaited_once_with(limit=50)
    model.settings_for.assert_not_awaited()
    model.once.assert_not_awaited()
    assert await repository.read("bob", turn["turn_id"]) is None


def scan_view(now=1000, universe=8834):
    columns = ["underlying_ticker", "ticker", "contract_type", "strike_price", "expiration_date", "day_volume", "open_interest", "implied_volatility", "delta", "underlying_price"]
    return dict(columns=columns, rows=[["AMD", "AMD-option", "call", 100, "2026-10-16", 25000, 10000, .3, .5, 100]],
                quote_truth={}, tickers=["SPY", "AMD"],
                coverage=dict(universe=universe, attempted=100, fresh=2, never_scanned=universe-100, latest_failed=4,
                              max_age_s=1, received_at_by_ticker={"AMD": now-1, "SPY": now-1},
                              checked_at=now-1, expiries_per_ticker=2, rows_per_ticker_cap=120,
                              fresh_window_seconds=60, complete_realtime_market=False), recent_findings=[])


@pytest.mark.asyncio
async def test_market_reader_does_not_enter_selected_or_provider_reads_and_cold_cache_stays_unavailable():
    def forbidden(*args, **kwargs):
        raise AssertionError("Provider/selected-chart functions are not market discovery")
    reads = ResearchReads(forbidden, forbidden, forbidden, peek_scan=lambda: None)
    answer = await reads.market_snapshot()
    assert answer["scope"] == "market"
    assert answer["status"] == "unavailable"
    assert answer["facts"] == [] and answer["actions"] == []
    assert "not" in answer["summary"].lower() or "unavailable" in answer["summary"].lower()


@pytest.mark.asyncio
async def test_market_reader_keeps_full_denominator_original_receipts_and_fact_bound_actions():
    view = scan_view()
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=lambda: view)
    answer = await reads.market_snapshot(now=datetime.fromtimestamp(1000, UTC))
    assert answer["coverage"]["universe"] == 8834
    assert answer["coverage"]["never_scanned"] == 8734
    assert answer["coverage"]["complete_realtime_market"] is False
    assert answer["candidates"][0]["ticker"] == "AMD"
    assert answer["candidates"][0]["received_at"] == datetime.fromtimestamp(999, UTC).isoformat()
    assert all(fact["ticker"] == "AMD" for fact in answer["facts"])
    assert all(fact["status"] != "ok" for fact in answer["facts"])
    assert answer["actions"][0]["kind"] == "open_chart"
    assert answer["actions"][0]["view"] == "heatseeker"
    assert answer["actions"][0]["ticker"] == "AMD"
    ledger = {fact["id"] for fact in answer["facts"]}
    assert set(answer["actions"][0]["fact_ids"]) <= ledger
    assert view["coverage"]["checked_at"] == 999


@pytest.mark.asyncio
async def test_market_reader_excludes_expired_rows_instead_of_freshening_them():
    view = scan_view()
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=lambda: view)
    answer = await reads.market_snapshot(now=datetime.fromtimestamp(1061, UTC))
    assert answer["candidates"] == []
    assert answer["actions"] == []
    assert answer["coverage"]["fresh"] == 0
    assert answer["coverage"]["checked_at"] == 999


@pytest.mark.parametrize("scope", ["broker", "orders", {}, True])
def test_unknown_market_scope_is_refused(scope):
    with pytest.raises(ValueError):
        request_spec({"question": "Find activity", "scope": scope})


@pytest.mark.parametrize("mode", ["replay", "range-replay"])
def test_market_scope_cannot_mix_with_recorded_selection(mode):
    with pytest.raises(ValueError):
        request_spec({"question": "Find all stocks", "scope": "market", "screen": {"ticker": "SPY", "displayMode": mode}})


@pytest.mark.asyncio
async def test_many_spy_contracts_do_not_hide_other_checked_stock_examples():
    view = scan_view()
    for i in range(60):
        view["rows"].append(["SPY", "SPY-option-"+str(i), "call", 200+i, "2026-10-16", 30000+i, 10000, .3, .5, 500])
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=lambda: view)
    answer = await reads.market_snapshot(now=datetime.fromtimestamp(1000, UTC))
    assert [row["ticker"] for row in answer["candidates"]] == ["SPY", "AMD"]
    assert answer["coverage"]["candidates_checked"] == 61
    assert answer["coverage"]["stocks_with_candidates"] == 2
    assert answer["coverage"]["candidate_contracts_omitted"] == 59
    assert {action["ticker"] for action in answer["actions"]} == {"SPY", "AMD"}


@pytest.mark.parametrize("question", ["Not all stocks, only SPY", "Do not scan all stocks; explain SPY", "Don't inspect the whole market; use SPY"])
def test_negated_market_request_keeps_literal_selected_stock_choice(question):
    spec = request_spec({"question": question, "screen": {"ticker": "QQQ"}})
    assert spec.get("scope") != "market"
    assert spec["tickers"] == ["SPY"]
    with pytest.raises(ValueError):
        request_spec({"question": question, "scope": "market", "screen": {"ticker": "QQQ"}})


def test_unrelated_no_orders_instruction_does_not_negate_whole_market_research():
    spec = request_spec({"question": "Do not place orders. Inspect the whole market."})
    assert spec["scope"] == "market"


@pytest.mark.asyncio
@pytest.mark.parametrize("oi", [None, 0, -1, float("nan")])
async def test_market_unknown_oi_stays_unknown_and_never_creates_ratio(oi):
    view = scan_view()
    view["rows"][0][6] = oi
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=lambda: view)
    answer = await reads.market_snapshot(now=datetime.fromtimestamp(1000, UTC))
    candidate = answer["candidates"][0]
    assert candidate["open_interest"] == (0 if oi == 0 else None)
    assert candidate["volume_open_interest_ratio"] is None
    ratio = next(item for item in answer["facts"] if item["metric"] == "Reported volume/open interest ratio")
    assert ratio["value"] is None and ratio["status"] == "unavailable"


@pytest.mark.asyncio
async def test_market_examples_are_bounded_after_inspecting_all_cached_stocks():
    view = scan_view()
    for i in range(70):
        ticker = "X"+str(i)
        view["coverage"]["received_at_by_ticker"][ticker] = 999
        view["rows"].append([ticker, ticker+"-option", "put", 100+i, "2026-10-16", 3000+i, None, None, None, None])
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=lambda: view)
    answer = await reads.market_snapshot(limit=50, now=datetime.fromtimestamp(1000, UTC))
    assert len(answer["candidates"]) == 50
    assert answer["coverage"]["stocks_with_candidates"] == 71
    assert answer["coverage"]["candidates_checked"] == 71
    assert answer["coverage"]["candidates_truncated"] is True
    assert answer["coverage"]["universe"] == 8834
    assert len(answer["actions"]) == 3
    assert len({action["ticker"] for action in answer["actions"]}) == 3
    assert len(answer["facts"]) == 150


@pytest.mark.asyncio
async def test_malformed_cache_rows_never_escape_into_actions_or_crash():
    view = scan_view()
    view["coverage"]["source"] = {"secret": "not public"}
    good = view["rows"][0]
    view["rows"] += [[{}, *good[1:]], [good[0], good[1], {}, *good[3:]],
                     ["https://bad.example", *good[1:]], [good[0], "", *good[2:]], ["bad"]]
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=lambda: view)
    answer = await reads.market_snapshot(now=datetime.fromtimestamp(1000, UTC))
    assert len(answer["candidates"]) == 1
    assert answer["actions"][0]["ticker"] == "AMD"
    assert "secret" not in str(answer) and "https://" not in str(answer)


@pytest.mark.asyncio
async def test_market_read_retains_eight_capability_limit_without_hidden_provider_work():
    from services.agent.read_budget import ReadBudget, budget_scope
    getter = AsyncMock()
    calls = []
    def peek():
        calls.append(1)
        return scan_view()
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=peek)
    budget = ReadBudget(timeout=120)
    with budget_scope(budget):
        for _ in range(8):
            assert (await reads.market_snapshot(now=datetime.fromtimestamp(1000, UTC)))["candidates"]
        denied = await reads.market_snapshot(now=datetime.fromtimestamp(1000, UTC))
    assert denied["status"] == "unavailable"
    assert len(calls) == 8
    assert budget.state()["reserved"] == 8
    getter.assert_not_awaited()


@pytest.mark.parametrize("limit", [0, 51, True, "50"])
def test_market_result_limit_is_enforced_server_side(limit):
    with pytest.raises(ValueError):
        request_spec({"question": "Whole market", "market_limit": limit})


def test_selected_named_data_is_not_misread_as_market_scope():
    spec = request_spec({"question": "Explain SPY across all available data", "screen": {"ticker": "SPY"}})
    assert spec.get("scope") != "market" and spec["tickers"] == ["SPY"]
    with pytest.raises(ValueError):
        request_spec({"question": "Scan all stocks", "scope": "selected"})


@pytest.mark.asyncio
async def test_earlier_published_findings_remain_dated_when_no_names_are_fresh():
    view = scan_view()
    view["recent_findings"] = [{"ticker": "AMD", "received_at": 900,
                                "contracts": 1, "examples": [list(view["rows"][0])]}]
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=lambda: view)
    answer = await reads.market_snapshot(now=datetime.fromtimestamp(1061, UTC))
    assert answer["coverage"]["fresh"] == 0
    assert answer["status"] == "stale"
    assert answer["summary"].startswith("Earlier cached activity")
    assert answer["current_candidates"] == []
    assert len(answer["earlier_candidates"]) == 1
    assert answer["earlier_candidates"][0]["received_at"] == datetime.fromtimestamp(900, UTC).isoformat()
    assert all(item["status"] == "stale" for item in answer["facts"] if item["value"] is not None)
    assert all(item["event_time"] is None for item in answer["facts"])
    assert len(answer["actions"]) == 1
    assert set(answer["actions"][0]["fact_ids"]) <= {item["id"] for item in answer["facts"]}
    assert view["recent_findings"][0]["received_at"] == 900


@pytest.mark.asyncio
async def test_current_and_earlier_parts_share_total_example_and_action_bounds():
    view = scan_view()
    for i in range(70):
        ticker = "Z"+str(i)
        row = [ticker, ticker+"-dated", "call", 100+i, "2026-10-16", 3000+i, None, None, None, None]
        view["recent_findings"].append({"ticker": ticker, "received_at": 900-i, "contracts": 1, "examples": [row]})
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [], peek_scan=lambda: view)
    answer = await reads.market_snapshot(now=datetime.fromtimestamp(1000, UTC))
    assert len(answer["current_candidates"]) == 1
    assert len(answer["earlier_candidates"]) == 49
    assert len(answer["candidates"]) == 50
    assert len(answer["actions"]) == 3
    assert answer["coverage"]["earlier_stocks_with_candidates"] == 70
    assert answer["coverage"]["earlier_candidates_truncated"] is True
    assert answer["coverage"]["universe"] == 8834
    assert {item["status"] for item in answer["facts"]} <= {"degraded", "stale", "unavailable"}


@pytest.mark.parametrize("volume", [2500.8, 199.9, True])
def test_fractional_daily_contract_counts_are_not_floored_into_candidates(volume):
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["rows"][0][5] = volume
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    assert answer["candidates"] == []
    assert answer["actions"] == []


@pytest.mark.parametrize("oi", [0.9, 10000.5, True])
def test_fractional_open_interest_remains_unknown_without_a_made_up_ratio(oi):
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["rows"][0][6] = oi
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    assert answer["candidates"][0]["open_interest"] is None
    assert answer["candidates"][0]["volume_open_interest_ratio"] is None
    readings = {item["metric"]: item for item in answer["facts"]}
    assert readings["Reported open interest"]["status"] == "unavailable"


def test_zero_declared_universe_cannot_advertise_a_checked_stock_or_action():
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["coverage"]["universe"] = 0
    view["coverage"]["attempted"] = 0
    view["coverage"]["never_scanned"] = 0
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    assert answer["status"] == "unavailable"
    assert answer["candidates"] == answer["facts"] == answer["actions"] == []
    assert answer["coverage"]["roster_status"] == "inconsistent"
    assert "out of 0" not in answer["summary"]


def test_complete_declared_roster_excludes_foreign_current_and_dated_findings():
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["tickers"] = ["QQQ"]
    view["coverage"].update(universe=1, attempted=1, never_scanned=0, latest_failed=0, received_at_by_ticker={"AMD":999})
    view["recent_findings"] = [{"ticker":"AMD", "received_at":900, "examples":[list(view["rows"][0])]}]
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    assert answer["candidates"] == answer["facts"] == answer["actions"] == []
    assert answer["coverage"]["fresh"] == 0
    assert answer["coverage"]["roster_status"] == "complete"
    assert answer["coverage"]["outside_roster_receipts_excluded"] == 1


@pytest.mark.parametrize("roster", [None, ["SPY"]])
def test_legacy_missing_or_partial_roster_is_explicitly_unverified(roster):
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["tickers"] = roster
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    assert answer["candidates"][0]["ticker"] == "AMD"
    assert answer["coverage"]["roster_status"] == "unknown"
    assert answer["coverage"]["membership_verified"] is False
    assert "unverified" in answer["summary"]
    assert any("membership" in gap for gap in answer["gaps"])


@pytest.mark.parametrize("roster", [["AMD","AMD"], ["AMD",{}]])
def test_malformed_or_duplicate_published_roster_is_refused(roster):
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["tickers"] = roster
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    assert answer["candidates"] == answer["actions"] == []
    assert answer["coverage"]["roster_status"] == "inconsistent"


def test_complete_matching_roster_preserves_real_count_and_checked_chart_choices():
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["coverage"].update(universe=2, attempted=2, never_scanned=0, latest_failed=0, catalog_available=True)
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    assert answer["coverage"]["roster_status"] == "complete"
    assert answer["coverage"]["membership_verified"] is True
    assert answer["coverage"]["fresh"] == 2
    assert answer["candidates"][0]["day_volume"] == 25000
    assert answer["actions"][0]["ticker"] == "AMD"
    assert "out of 2." in answer["summary"]


@pytest.mark.parametrize("patch", [{"attempted":8835}, {"attempted":100,"never_scanned":8733}, {"catalog_available":True}])
def test_other_declared_roster_count_contradictions_offer_no_choices(patch):
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["coverage"].update(patch)
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    assert answer["status"] == "unavailable"
    assert answer["coverage"]["roster_status"] == "inconsistent"
    assert answer["candidates"] == answer["actions"] == []


@pytest.mark.parametrize("question", ["Find unusual activity across all the available stocks", "Inspect all ETFs and funds",
    "Check every eligible stock", "Inspect all accessible symbols", "Inspect each available fund",
    "Find all the possible tickers", "Inspect all available eligible ETFs"])
def test_clear_fund_and_qualified_market_scope_does_not_use_selected_spy(question):
    spec = request_spec({"question":question,"screen":{"ticker":"SPY"}})
    assert spec["scope"] == "market"
    assert spec["tickers"] == []
    with pytest.raises(ValueError):
        request_spec({"question":question,"scope":"selected","screen":{"ticker":"SPY"}})


@pytest.mark.parametrize("question", ["Do not scan all the available stocks; explain SPY",
    "Don't inspect all ETFs and funds; explain SPY", "Not every eligible stock, only SPY", "Do not scan each available fund; explain SPY"])
def test_negated_fund_and_qualified_market_scope_stays_selected(question):
    spec = request_spec({"question":question,"screen":{"ticker":"SPY"}})
    assert spec.get("scope") != "market"
    assert spec["tickers"] == ["SPY"]
    with pytest.raises(ValueError):
        request_spec({"question":question,"scope":"market","screen":{"ticker":"SPY"}})


def test_ambiguous_activity_question_keeps_its_selected_stock():
    spec = request_spec({"question":"Find unusual activity","screen":{"ticker":"SPY"}})
    assert spec.get("scope") != "market"
    assert spec["tickers"] == ["SPY"]


def test_market_progress_preserves_original_attempt_meaning_without_changing_coverage():
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["coverage"]["progress"] = {"status":"durable", "universe":8834, "pending":42, "inflight":2, "deferred":7,
        "pending_includes_inflight_and_deferred":True,"pass_complete":True,"directory_at":900,"last_complete":850}
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    progress = answer["coverage"]["progress"]
    assert progress["pending"] == 42
    assert progress["inflight"] == 2 and progress["deferred"] == 7
    assert progress["pending_includes_inflight_and_deferred"] is True
    assert progress["pass_complete"] is True
    assert progress["directory_at"] == 900 and progress["last_complete"] == 850
    assert "attempt" in progress["completion_meaning"] and "fresh" in progress["completion_meaning"]
    assert answer["coverage"]["universe"] == 8834
    assert answer["coverage"]["fresh"] == 2


@pytest.mark.parametrize("invalid", [1001, float("nan"), True, -1, "900"])
def test_market_progress_refuses_invalid_or_future_original_times(invalid):
    from services.agent.market_reads import market_answer
    view = scan_view()
    view["coverage"]["progress"] = {"status":"durable", "directory_at":invalid,"last_complete":invalid,
        "pending_includes_inflight_and_deferred":"true","pass_complete":1}
    answer = market_answer(view, now=datetime.fromtimestamp(1000, UTC))
    progress = answer["coverage"]["progress"]
    assert progress["directory_at"] is None and progress["last_complete"] is None
    assert progress["pending_includes_inflight_and_deferred"] is None and progress["pass_complete"] is None
    assert answer["coverage"]["universe"] == 8834
