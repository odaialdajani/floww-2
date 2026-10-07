"""A named past day selects only owned saved source observations on that day."""
import copy
import hashlib
import time as clock
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.contracts import canonical, fact, request_spec, validate_model_answer
from services.agent.read_budget import ReadBudget, budget_scope
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService
from services.agent.saved_history import history_facts

DATE = {"date": "2026-10-01"}


def snapshot(identity, value, observed, *, source="fixture", unit="USD", horizon="all", coverage="same", ticker="SPY", kind=None):
    reading = fact("Underlying price", value, unit, ticker=ticker, horizon=horizon, source=source,
                   snapshot_id=identity, event_time=observed)
    return {"ticker": ticker, "horizon": horizon, "snapshot_id": identity, "coverage_id": coverage,
            "coverage": 2, "captured_at": observed or "2026-10-01T15:00:00+00:00",
            "observed_at": observed, "facts": [reading], "gaps": [], "window": {},
            **({"anchor_kind": kind} if kind else {})}


def current():
    return snapshot("current", 108, "2026-10-06T15:00:00+00:00")


async def save_turn_snapshot(repo, owner, item, created_at):
    await repo.turns.insert_one({"owner": owner, "turn_id": item["snapshot_id"], "status": "completed",
                                 "created_at": created_at, "answer": {"snapshots": [copy.deepcopy(item)]}})


async def save_anchor_snapshot(repo, owner, item, created_at):
    await repo.snapshots.insert_one({"owner": owner, "ticker": item["ticker"], "created_at": created_at,
                                     "expires_at": datetime.now(UTC) + timedelta(days=1), "snapshot": copy.deepcopy(item)})


@pytest.mark.parametrize("question", ["What changed for SPY since 2026-10-01?",
                                       "Compare SPY from 2026-10-01", "Show SPY history for 2026-10-01",
    "For SPY, compare the currently selected reading with the latest compatible saved observation on 2026-10-01 in New York market time. Keep missing data unknown; do not substitute another date."])
def test_fully_specified_comparison_day_is_kept_in_request(question):
    spec = request_spec({"question": question})
    assert spec["history_baseline"] == DATE
    assert spec["horizon"] == "all"


def test_structured_date_is_owned_request_data_and_conflicts_are_refused():
    body = {"question": "Compare SPY with my saved observation", "history_baseline": DATE}
    before = copy.deepcopy(body)
    assert request_spec(body)["history_baseline"] == DATE
    assert body == before
    with pytest.raises(ValueError):
        request_spec({**body, "question": "Compare SPY since 2026-10-02"})
    with pytest.raises(ValueError):
        request_spec({**body, "question": "Do not use saved history; show current SPY gamma"})


@pytest.mark.parametrize("value", [{"date": "2026-02-30"}, {"date": "2026-1-1"}, {"date": 3},
                                    {"date": "2026-10-01", "time": "14:30"}, [], "2026-10-01"])
def test_structured_day_has_one_strict_calendar_date(value):
    with pytest.raises(ValueError):
        request_spec({"question": "Compare SPY with saved history", "history_baseline": value})


@pytest.mark.parametrize("question", ["Show SPY history for October 1", "Compare SPY since 10/1",
                                       "Compare SPY since Monday", "Compare SPY since 2026-10-01 at 14:30",
                                       "Compare SPY since yesterday at 2 pm"])
def test_ambiguous_day_or_unqualified_clock_requests_explicit_date(question):
    with pytest.raises(ValueError) as error:
        request_spec({"question": question})
    assert "YYYY-MM-DD" in str(error.value) or "date picker" in str(error.value).lower()


def test_multiple_baseline_days_cannot_be_silently_replaced():
    with pytest.raises(ValueError):
        request_spec({"question": "Compare SPY since 2026-10-01 and 2026-10-02"})


def test_expiry_day_stays_separate_from_history_day():
    spec = request_spec({"question": "Compare SPY since 2026-10-01 for expiry on 2026-10-16"})
    assert spec["history_baseline"] == DATE
    assert spec["question_scope"] == {"selected_expiry": "2026-10-16"}
    expiry_only = request_spec({"question": "Explain SPY expiry on 2026-10-16"})
    assert "history_baseline" not in expiry_only or expiry_only["history_baseline"] is None


@pytest.mark.parametrize("screen, scope", [({}, "market"),
    ({"ticker": "SPY", "page": "heatseeker", "displayMode": "replay", "contextVersion": 2,
      "snapshotId": "recorded", "provider": "fixture", "formula": "fixture", "activePane": "gex",
      "mapExpiries": ["2026-10-16"], "mapQuery": {}, "mapVersion": "2026-10-06T15:00:00Z"}, "selected")])
def test_dated_history_does_not_mix_market_scan_or_replayed_chart(screen, scope):
    with pytest.raises(ValueError):
        request_spec({"question": "Compare saved observations since 2026-10-01", "ticker": "SPY",
                      "history_baseline": DATE, "scope": scope, "screen": screen})


@pytest.mark.asyncio
@pytest.mark.parametrize("storage", ["turn", "anchor"])
async def test_requested_new_york_day_uses_latest_source_time_even_beyond_thirty_recent_records(storage):
    repo = AgentRepository(AsyncMongoMockClient().test)
    store = save_turn_snapshot if storage == "turn" else save_anchor_snapshot
    old = snapshot("requested-earlier", 90, "2026-10-01T15:00:00+00:00")
    late = snapshot("requested-latest", 93, "2026-10-02T00:30:00+00:00")  # Oct 1 in New York.
    late["observed_at"] = "2026-10-05T15:00:00+00:00"  # Chain/snapshot time is not price time.
    await store(repo, "alice", old, datetime(2026, 10, 5, 15, tzinfo=UTC))
    await store(repo, "alice", late, datetime(2026, 9, 1, 15, tzinfo=UTC))
    await store(repo, "bob", snapshot("foreign", 1, "2026-10-02T01:00:00+00:00"), datetime(2026, 10, 6, 14, tzinfo=UTC))
    for index in range(60):
        other_day = snapshot(f"newer-created-{index}", 100, "2026-10-03T15:00:00+00:00")
        await store(repo, "alice", other_day, datetime(2026, 10, 6, 14, tzinfo=UTC) + timedelta(seconds=index))
    after = current()
    before = copy.deepcopy(after)
    facts, note = await history_facts(repo, "alice", after, history_baseline=DATE)
    assert len(facts) == 2 and facts[0] == late["facts"][0] and facts[-1]["value"] == 15
    assert facts[-1]["parents"] == [late["facts"][0]["id"], after["facts"][0]["id"]]
    assert "2026-10-02T00:30" in note and "2026-10-01" in note
    assert after == before
    assert (await history_facts(repo, "unknown-owner", after, history_baseline=DATE))[0] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("difference", [{"source": "other-provider"}, {"unit": "cents"},
                                        {"coverage": "different"}, {"horizon": "week"}, {"ticker": "QQQ"}])
async def test_latest_compatible_observation_skips_different_source_unit_coverage_or_scope(difference):
    repo = AgentRepository(AsyncMongoMockClient().test)
    good = snapshot("compatible", 90, "2026-10-01T15:00:00+00:00")
    bad = snapshot("incompatible", 1, "2026-10-01T19:00:00+00:00", **difference)
    await save_turn_snapshot(repo, "alice", good, datetime(2026, 9, 1, tzinfo=UTC))
    await save_turn_snapshot(repo, "alice", bad, datetime(2026, 10, 5, tzinfo=UTC))
    facts, _ = await history_facts(repo, "alice", current(), history_baseline=DATE)
    assert facts[0] == good["facts"][0] and facts[-1]["value"] == 18


@pytest.mark.asyncio
async def test_missing_day_or_unknown_price_time_never_substitutes_another_observation():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await save_turn_snapshot(repo, "alice", snapshot("other-day", 90, "2026-09-30T15:00:00+00:00"), datetime.now(UTC))
    unknown = snapshot("unknown-time", 1, None)
    await save_turn_snapshot(repo, "alice", unknown, datetime.now(UTC))
    facts, note = await history_facts(repo, "alice", current(), history_baseline=DATE)
    assert facts == [] and "2026-10-01" in note
    missing_current_time = current()
    missing_current_time["facts"][0]["event_time"] = None
    assert (await history_facts(repo, "alice", missing_current_time, history_baseline=DATE))[0] == []


@pytest.mark.asyncio
async def test_new_york_day_bounds_follow_daylight_saving_change():
    repo = AgentRepository(AsyncMongoMockClient().test)
    late = snapshot("local-sunday", 90, "2026-11-02T04:30:00+00:00")  # Sunday 23:30 after clocks changed.
    next_day = snapshot("local-monday", 1, "2026-11-02T05:15:00+00:00")
    await save_turn_snapshot(repo, "alice", late, datetime.now(UTC))
    await save_turn_snapshot(repo, "alice", next_day, datetime.now(UTC))
    after = snapshot("later-current", 93, "2026-11-03T15:00:00+00:00")
    facts, _ = await history_facts(repo, "alice", after, history_baseline={"date": "2026-11-01"})
    assert facts[0] == late["facts"][0] and facts[-1]["value"] == 3


@pytest.mark.asyncio
async def test_asked_exact_close_requires_owned_verified_close_anchor_on_that_day():
    repo = AgentRepository(AsyncMongoMockClient().test)
    closing = "2026-10-01T20:00:00+00:00"
    ordinary = snapshot("ordinary-at-close", 1, closing)
    wrong_window = snapshot("wrong-window", 2, closing, kind="close")
    wrong_window["window"] = {"session_close": "2026-10-02T20:00:00+00:00"}
    valid = snapshot("verified-close", 90, closing, kind="close")
    valid["window"] = {"session_close": closing}
    for owner, item in [("alice", ordinary), ("alice", wrong_window), ("bob", valid)]:
        await save_anchor_snapshot(repo, owner, item, datetime.now(UTC))
    assert (await history_facts(repo, "alice", current(), closing_only=True, history_baseline=DATE))[0] == []
    await save_anchor_snapshot(repo, "alice", valid, datetime.now(UTC))
    facts, note = await history_facts(repo, "alice", current(), closing_only=True, history_baseline=DATE)
    assert facts[0] == valid["facts"][0] and facts[-1]["value"] == 18
    assert closing in note


@pytest.mark.asyncio
async def test_nontrading_requested_close_does_not_fall_back_to_friday():
    repo = AgentRepository(AsyncMongoMockClient().test)
    friday = snapshot("friday-close", 90, "2026-10-02T20:00:00+00:00", kind="close")
    friday["window"] = {"session_close": "2026-10-02T20:00:00+00:00"}
    await save_anchor_snapshot(repo, "alice", friday, datetime.now(UTC))
    facts, note = await history_facts(repo, "alice", current(), closing_only=True, history_baseline={"date": "2026-10-03"})
    assert facts == [] and "2026-10-03" in note


@pytest.mark.asyncio
async def test_history_read_memo_and_saved_activity_are_separate_for_each_requested_day(monkeypatch):
    import services.agent.research as module
    repository = AgentRepository(AsyncMongoMockClient().test)
    service = ResearchService(repository, None)
    called = []
    async def saved_only(repository, owner, snapshot, **kwargs):
        called.append(copy.deepcopy(kwargs["history_baseline"]))
        return [], "No saved observation for " + kwargs["history_baseline"]["date"]
    monkeypatch.setattr(module, "history_facts", saved_only)
    budget = ReadBudget()
    days = [DATE, {"date": "2026-09-30"}, DATE]
    with budget_scope(budget):
        for day in days:
            await service._history(repository, "alice", current(), history_baseline=day)
    assert called == days[:2]
    assert len(budget.attempts) == 2
    assert DATE["date"] in str(budget.attempts[0]["scope"])
    assert "2026-09-30" in str(budget.attempts[1]["scope"])


@pytest.mark.asyncio
async def test_model_inspection_uses_owned_requested_day_and_cannot_override_it():
    repo = AgentRepository(AsyncMongoMockClient().test)
    repo.progress = AsyncMock(return_value=True)
    after = current()
    result = {"status": "ok", "name": "research_answer", "data": {"sections": [
        {"name": "Market", "fact_ids": [after["facts"][0]["id"]], "interpretation": "descriptive"}]}}
    model = type("Model", (), {"once": AsyncMock(side_effect=[
        {"status": "ok", "name": "inspect_history", "data": {"ticker": "SPY"}}, result])})()
    service = ResearchService(repo, None, model=model)
    service._history = AsyncMock(return_value=([], "No saved observation on requested day"))
    spec = request_spec({"question": "Compare SPY since 2026-10-01", "history_baseline": DATE})
    answer = {"facts": after["facts"], "sections": [], "gaps": []}
    with budget_scope(ReadBudget(), spec):
        await service._interpret("alice", "owned-turn", spec, answer, [after])
    assert service._history.call_args.kwargs["history_baseline"] == DATE
    assert service._history.call_args.args[1] == "alice"
    service._history.reset_mock()
    model.once = AsyncMock(side_effect=[{"status": "ok", "name": "inspect_history", "data": {
        "ticker": "SPY", "history_baseline": {"date": "2026-10-02"}}}, result])
    with budget_scope(ReadBudget(), spec):
        await service._interpret("alice", "other-owned-turn", spec, {"facts": after["facts"], "sections": [], "gaps": []}, [after])
    service._history.assert_not_awaited()


@pytest.mark.asyncio
async def test_bounded_candidate_exhaustion_is_not_hidden_by_a_coverage_note():
    after = current()
    malformed = snapshot("malformed-time", 90, None)
    mismatch = snapshot("other-coverage", 90, "2026-10-01T15:00:00+00:00", coverage="different")
    repository = type("Repository", (), {"history_candidates": AsyncMock(side_effect=[
        {"snapshots": [malformed], "truncated": True, "limit_per_store": 64},
        {"snapshots": [mismatch], "truncated": False, "limit_per_store": 64}])})()
    facts, note = await history_facts(repository, "alice", after, history_baseline=DATE)
    assert facts == [] and "bounded limit" in note and "64" in note and "2026-10-01" in note


@pytest.mark.parametrize("question", ["Compare SPY since 2026-1-1", "Compare SPY since 2026-10-011", "Compare SPY since 10-01-2026"])
def test_malformed_or_reversed_numeric_day_never_becomes_latest_history(question):
    with pytest.raises(ValueError) as error:
        request_spec({"question": question})
    assert "YYYY-MM-DD" in str(error.value) or "date picker" in str(error.value).lower()



def raw_clock_snapshot(identity, value, observed):
    """A legacy verified UTC spelling keeps its original fields and identity."""
    item = snapshot(identity, value, observed)
    reading = item["facts"][0]
    reading["event_time"] = observed
    reading["id"] = "ev" + hashlib.sha256(canonical({key: value for key, value in reading.items() if key != "id"}).encode()).hexdigest()
    return item


@pytest.mark.asyncio
async def test_verified_zero_fraction_z_price_is_earlier_than_subsecond_current_quote():
    repo = AgentRepository(AsyncMongoMockClient().test)
    prior = raw_clock_snapshot("prior-z", 90, "2026-10-01T15:00:00Z")
    after = snapshot("after-subsecond", 93, "2026-10-01T15:00:00.100000+00:00")
    await save_turn_snapshot(repo, "alice", prior, datetime.now(UTC))
    before = copy.deepcopy(prior["facts"][0])
    facts, _ = await history_facts(repo, "alice", after, history_baseline=DATE)
    assert facts[0] == before and facts[-1]["value"] == 3
    stored = await repo.turns.find_one({"owner": "alice", "turn_id": prior["snapshot_id"]})
    assert stored["answer"]["snapshots"][0]["facts"][0] == before


@pytest.mark.asyncio
async def test_source_instant_sort_keeps_latest_subsecond_observation_before_candidate_cap():
    repo = AgentRepository(AsyncMongoMockClient().test)
    for index in range(64):
        await save_turn_snapshot(repo, "alice", raw_clock_snapshot(f"older-z-{index}", 90, "2026-10-01T15:00:00Z"), datetime.now(UTC))
    latest = raw_clock_snapshot("latest-fraction", 199, "2026-10-01T15:00:00.999999+00:00")
    await save_turn_snapshot(repo, "alice", latest, datetime(2026, 9, 1, tzinfo=UTC))
    after = snapshot("after-latest", 200, "2026-10-01T15:01:00+00:00")
    facts, _ = await history_facts(repo, "alice", after, history_baseline=DATE)
    assert facts[0] == latest["facts"][0] and facts[-1]["value"] == 1


@pytest.mark.parametrize("question", ["What was SPY's spot price on 2026-10-01?", "Show SPY underlying price on 2026-10-01"])
def test_explicit_dated_price_question_cannot_become_a_current_spot_lookup(question):
    spec = request_spec({"question": question})
    assert spec["history_baseline"] == DATE and spec["price_only"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["missing", "unavailable", "invalid", "degraded", "stale"])
async def test_price_change_cannot_upgrade_the_prior_observation_quality(status):
    repo = AgentRepository(AsyncMongoMockClient().test)
    prior = snapshot("limited-parent", 90, "2026-10-01T15:00:00+00:00")
    prior["facts"][0] = fact("Underlying price", 90, "USD", ticker="SPY", horizon="all", source="fixture",
                             snapshot_id="limited-parent", event_time="2026-10-01T15:00:00+00:00",
                             status=status, reason=f"Prior reading is {status}")
    await save_turn_snapshot(repo, "alice", prior, datetime.now(UTC))
    facts, _ = await history_facts(repo, "alice", current(), history_baseline=DATE)
    if status in {"missing", "unavailable", "invalid"}:
        assert facts == []
    else:
        assert facts[0] == prior["facts"][0]
        change = facts[-1]
        assert change["value"] == 18 and change["status"] == status
        assert f"Prior reading is {status}" in change["reason"]
        with pytest.raises(ValueError, match="[Ll]imited"):
            validate_model_answer({"sections": [{"name": "History", "fact_ids": [change["id"]],
                                                   "interpretation": "descriptive"}]}, {change["id"]: change})


@pytest.mark.asyncio
async def test_price_change_inherits_worst_current_and_prior_quality_and_reasons():
    repo = AgentRepository(AsyncMongoMockClient().test)
    prior = snapshot("degraded-prior", 90, "2026-10-01T15:00:00+00:00")
    after = current()
    prior["facts"][0].update(status="degraded", reason="Prior coverage is limited")
    after["facts"][0].update(status="stale", reason="Current quote is out of date")
    await save_turn_snapshot(repo, "alice", prior, datetime.now(UTC))
    facts, _ = await history_facts(repo, "alice", after, history_baseline=DATE)
    assert facts[-1]["status"] == "stale"
    assert "Prior coverage is limited" in facts[-1]["reason"] and "Current quote is out of date" in facts[-1]["reason"]


@pytest.mark.asyncio
async def test_finite_unavailable_current_price_is_not_a_comparison_input():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await save_turn_snapshot(repo, "alice", snapshot("valid-prior", 90, "2026-10-01T15:00:00+00:00"), datetime.now(UTC))
    after = current()
    after["facts"][0].update(status="unavailable", reason="Current quote is not verified")
    assert (await history_facts(repo, "alice", after, history_baseline=DATE))[0] == []


@pytest.mark.asyncio
async def test_saved_history_aggregation_has_database_deadline_and_no_disk_spill():
    repo = AgentRepository(AsyncMongoMockClient().test)
    calls = []
    class EmptyCursor:
        async def to_list(self, *, length):
            assert length <= 65
            return []
    class Collection:
        def aggregate(self, stages, **options):
            calls.append(options)
            return EmptyCursor()
    repo.turns = repo.snapshots = Collection()
    await repo.history_candidates("alice", ticker="SPY", horizon="all", before="2026-10-06T15:00:00+00:00",
                                  start="2026-10-01T04:00:00+00:00", end="2026-10-02T04:00:00+00:00",
                                  coverage_id="same", source="fixture", unit="USD")
    assert len(calls) == 2
    for options in calls:
        assert type(options.get("maxTimeMS")) is int and 0 < options["maxTimeMS"] <= 2000
        assert options.get("allowDiskUse") is False


@pytest.mark.asyncio
async def test_database_deadline_returns_incomplete_history_not_false_absence():
    from pymongo.errors import ExecutionTimeout
    repo = AgentRepository(AsyncMongoMockClient().test)
    class Collection:
        def aggregate(self, stages, **options):
            raise ExecutionTimeout("private raw database details", code=50)
    repo.turns = Collection()
    facts, note = await history_facts(repo, "alice", current(), history_baseline=DATE)
    assert facts == [] and "incomplete" in note.lower() and "time limit" in note.lower() and "2026-10-01" in note
    assert "private raw" not in note


@pytest.mark.asyncio
async def test_plain_dated_price_runs_as_explicit_saved_day_not_current_price_summary():
    repo = AgentRepository(AsyncMongoMockClient().test)
    prior = snapshot("plain-price-prior", 90, "2026-10-01T15:00:00+00:00")
    await save_turn_snapshot(repo, "alice", prior, datetime.now(UTC))
    after = current()
    reads = type("Reads", (), {"snapshot": AsyncMock(return_value=after)})()
    service = ResearchService(repo, reads)
    spec = request_spec({"question": "What was SPY's spot price on 2026-10-01?"})
    turn = await service.ask("alice", f"{int(clock.time() * 1000)}-{uuid.uuid4()}", spec)
    await service.tasks[turn["turn_id"]]
    saved = await repo.read("alice", turn["turn_id"])
    assert saved["status"] == "completed"
    answer = saved["answer"]
    assert answer["history_baseline"] == DATE
    section = next(item for item in answer["sections"] if item["name"] == "What changed")
    assert "2026-10-01T15:00" in section["text"] and "2026-10-01" in section["text"]
    assert prior["facts"][0]["id"] in section["fact_ids"]
    assert "cached underlying price:" not in answer["summary"]
    assert any(item["metric"] == "Price change since saved observation" and item["value"] == 18 for item in answer["facts"])


@pytest.mark.parametrize("question", ["What were SPY's spot prices on 2026-10-01?", "Show SPY and QQQ underlying prices on 2026-10-01"])
def test_plural_dated_prices_keep_the_explicit_saved_day(question):
    spec = request_spec({"question": question})
    assert spec["history_baseline"] == DATE and spec["price_only"] is False


def test_expiry_price_wording_is_not_a_history_date_selector():
    spec = request_spec({"question": "Show SPY spot price for expiry on 2026-10-16"})
    assert "history_baseline" not in spec or spec["history_baseline"] is None
    assert spec["question_scope"] == {"selected_expiry": "2026-10-16"}


@pytest.mark.parametrize("question, tickers, expected", [
    ("What was SPY's spot price on 2026-10-01?", ["SPY"], set()),
    ("What were SPY QQQ IWM prices on 2026-10-01?", ["SPY", "QQQ", "IWM"], set()),
    ("Explain SPY gamma from the saved observation on 2026-10-01", ["SPY"], {"structure"}),
    ("Compare SPY flow with the saved observation on 2026-10-01", ["SPY"], {"flow"}),
    ("Show SPY full readings since 2026-10-01", ["SPY"], {"structure", "volatility", "flow", "map"}),
])
def test_validated_date_read_plan_keeps_only_requested_current_dimensions(question, tickers, expected):
    from services.agent.read_budget import capability_plan
    spec = {"question": question, "tickers": tickers, "history_baseline": DATE}
    assert capability_plan(spec) == expected


def test_date_read_plan_cannot_override_explicit_history_exclusion():
    from services.agent.read_budget import capability_plan
    spec = {"question": "Do not use saved history; show SPY gamma", "tickers": ["SPY"], "history_baseline": DATE}
    assert capability_plan(spec) == {"structure", "volatility", "flow", "map"}


def test_invalid_date_is_not_a_history_only_read_permission():
    from services.agent.read_budget import capability_plan
    with pytest.raises(ValueError):
        capability_plan({"question": "SPY price", "tickers": ["SPY"], "history_baseline": {"date": "2026-02-30"}})


def test_relationship_trend_rejects_reverse_z_clock_and_accepts_actual_microsecond_order():
    from services.agent.contracts import relationship_text
    prior = raw_clock_snapshot("trend-prior", 93, "2026-10-01T15:00:00Z")["facts"][0]
    after = snapshot("trend-after", 90, "2026-10-01T15:00:00.100000+00:00")["facts"][0]
    ledger = {item["id"]: item for item in [prior, after]}
    with pytest.raises(ValueError, match="[Tt]ime-ordered"):
        relationship_text({"kind": "rising", "fact_id": prior["id"], "other_fact_id": after["id"]}, ledger)
    text = relationship_text({"kind": "falling", "fact_id": after["id"], "other_fact_id": prior["id"]}, ledger)
    assert "fell from" in text


def test_fresh_and_same_time_comparison_cannot_promote_naive_market_clocks():
    from services.agent.contracts import relationship_text
    first = snapshot("unknown-zone", 93, "2026-10-01T15:00:00+00:00")["facts"][0]
    second = snapshot("other-unknown-zone", 90, "2026-10-01T15:00:00+00:00")["facts"][0]
    first["event_time"] = second["event_time"] = "2026-10-01T15:00:00"
    ledger = {item["id"]: item for item in [first, second]}
    with pytest.raises(ValueError):
        relationship_text({"kind": "fresh", "fact_id": first["id"]}, ledger)
    with pytest.raises(ValueError, match="[Tt]ime is unknown"):
        relationship_text({"kind": "above", "fact_id": first["id"], "other_fact_id": second["id"]}, ledger)


def test_historical_healthy_relationship_text_remains_about_the_saved_observation():
    from services.agent.contracts import relationship_text
    item = snapshot("saved-old", 90, "2026-10-01T15:00:00+00:00")["facts"][0]
    text = relationship_text({"kind": "fresh", "fact_id": item["id"]}, {item["id"]: item})
    assert "saved observation" in text and "fresh now" not in text



def test_positive_dated_price_clause_without_history_permission_is_clearly_refused():
    with pytest.raises(ValueError) as error:
        request_spec({"question": "Do not use saved history; what was SPY's spot price on 2026-10-01?"})
    assert "history" in str(error.value).lower() or "date" in str(error.value).lower()


def test_date_only_in_excluded_history_clause_does_not_change_current_price_request():
    spec = request_spec({"question": "Do not read historical data from 2026-10-01; show current SPY spot price"})
    assert spec["tickers"] == ["SPY"]
    assert "history_baseline" not in spec or spec["history_baseline"] is None


def test_negated_market_wide_probability_does_not_change_named_stock_flow_scope():
    body = {"question": "In this labeled $QQQ test set, what do the aligned bullish alerts support, and why is their flow reading not a market-wide probability?",
            "ticker": "QQQ", "horizon": "all", "screen": {"ticker": "QQQ", "page": "heatseeker", "horizon": "all",
                                                                  "displayMode": "live", "overlayMetric": "raw"}}
    spec = request_spec(body)
    assert spec["tickers"] == ["QQQ"] and spec.get("scope") != "market"


def test_positive_market_request_still_overrides_screen_stock_after_negation_guard():
    spec = request_spec({"question": "Scan the whole market for unusual activity", "ticker": "QQQ", "screen": {"ticker": "QQQ"}})
    assert spec["scope"] == "market" and spec["tickers"] == []


def test_direct_negation_with_article_keeps_named_stock_scope():
    spec = request_spec({"question": "Show QQQ flow, not a whole-market scan", "ticker": "QQQ"})
    assert spec["tickers"] == ["QQQ"] and spec.get("scope") != "market"
