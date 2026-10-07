"""Focused Ask FLOWW sweep checks; saved fixtures only, no external work."""

from unittest.mock import AsyncMock

import pytest

from services.agent.answer_sections import build_answer_sections, requested_sections, requests_history
from services.agent.contracts import fact
from services.agent.read_budget import ReadBudget, budget_scope, capability_plan
from services.agent.research import ResearchService, deterministic_answer


def exact_reading(metric, value, unit="USD", status="ok"):
    return fact("Exact contract " + metric, value, unit, ticker="SPY", source="saved fixture",
                snapshot_id="listed-observation", horizon="contract:owned-selection",
                contract="listed SPY contract", event_time="2026-10-06T15:00:00Z", status=status)


def contract_snapshot(facts):
    return {"ticker": "SPY", "horizon": "all", "window": {}, "facts": facts, "gaps": [],
            "snapshot_id": "listed-observation", "anchor_kind": "display"}


def request(question, screen=None):
    return {"question": question, "screen": screen or {}, "tickers": ["SPY"], "horizon": "all",
            "context_conflict": False, "question_scope": None, "price_only": False}


def test_selected_contract_quotes_retain_numbers_times_units_and_references():
    facts = [exact_reading("OSI", "SPY261016C00600000", "listed identity"),
             exact_reading("expiry", "2026-10-16", "date"),
             exact_reading("bid", 3.123456), exact_reading("ask", 3.223456),
             exact_reading("spread", .1), exact_reading("mid", 3.173456)]
    sections = build_answer_sections([contract_snapshot(facts)], request("Show this contract's bid and ask"))
    structure = next(s for s in sections if s["name"] == "Structure")
    assert structure["status"] == "available"
    assert structure["fact_ids"] == [f["id"] for f in facts]
    assert "3.123456 USD" in structure["text"] and "3.223456 USD" in structure["text"]
    assert "2026-10-16" in structure["text"] and "2026-10-06T15:00:00+00:00" in structure["text"]
    assert all(s["horizon"] == "contract:owned-selection" for s in structure["segments"] if s["type"] == "fact_reference")


@pytest.mark.parametrize("status", ["stale", "degraded"])
def test_saved_contract_quotes_do_not_claim_absence_or_current_quality(status):
    facts = [exact_reading("bid", 3, status=status), exact_reading("ask", 4, status=status)]
    structure = build_answer_sections([contract_snapshot(facts)], request("Show bid and ask"))[0]
    assert structure["status"] == "degraded"
    assert structure["fact_ids"] == [f["id"] for f in facts]
    assert "3 USD" in structure["text"] and "4 USD" in structure["text"]
    assert "Structure readings are unavailable" not in structure["text"]
    assert "stale; observed" in structure["text"] if status == "stale" else "degraded; observed" in structure["text"]


def test_partial_contract_quote_never_invents_ask_or_midpoint():
    facts = [exact_reading("OSI", "SPY261016C00600000", "listed identity"), exact_reading("bid", 3)]
    structure = build_answer_sections([contract_snapshot(facts)], request("Show bid and ask"))[0]
    assert structure["status"] == "degraded"
    assert structure["fact_ids"] == [f["id"] for f in facts]
    assert "ask" in structure["text"].lower() and "unavailable" in structure["text"].lower()
    assert "Exact contract ask:" not in structure["text"] and "Exact contract mid:" not in structure["text"]


def test_contract_quote_question_keeps_quote_section_alongside_probability_refusal():
    spec = request("What is this contract's bid and ask, and profit probability?", {"selectedContract": {"osi": "listed"}})
    assert "Structure" in requested_sections(spec) and "Trade" in requested_sections(spec)


@pytest.mark.parametrize("question", [
    "Explain SPY gamma without using saved history",
    "Do not use my history; show SPY flow",
    "Don't inspect saved readings; compare SPY and QQQ",
    "Ignore earlier observations and show SPY gamma",
    "Explain SPY gamma; do not use historical data",
    "Show current SPY gamma; do not compare with saved history",
])
def test_clear_history_exclusions_are_respected(question):
    assert not requests_history(question)
    assert "What changed" not in requested_sections(request(question))


@pytest.mark.parametrize("question", [
    "What changed since yesterday?", "Compare SPY with the previous saved reading",
    "Show SPY saved history", "Don't predict a trade; explain what changed since the last close",
])
def test_explicit_history_comparisons_remain_enabled(question):
    assert requests_history(question)


def test_negative_history_mention_does_not_suppress_current_comparison_readings():
    spec = request("Don't inspect saved history; compare SPY and QQQ")
    spec["tickers"] = ["SPY", "QQQ"]
    assert capability_plan(spec) == {"structure", "volatility", "flow", "map"}


@pytest.mark.asyncio
async def test_model_cannot_inspect_history_after_explicit_exclusion():
    reading = fact("Underlying price", 100, "USD", ticker="SPY", source="fixture", snapshot_id="current",
                   event_time="2026-10-06T15:00:00Z")
    snapshot = contract_snapshot([reading])
    spec = request("Do not use saved history; show SPY gamma")
    repository = type("Repository", (), {"progress": AsyncMock(return_value=True)})()
    model = type("Model", (), {"once": AsyncMock(return_value={"status": "ok", "name": "inspect_history", "data": {"ticker": "SPY"}})})()
    service = ResearchService(repository, None, model=model)
    service._history = AsyncMock(return_value=([], "Not supplied"))
    answer = deterministic_answer([snapshot], spec)
    with budget_scope(ReadBudget(), spec):
        await service._interpret("owner", "turn", spec, answer, [snapshot])
    assert model.once.call_args.kwargs["allow_inspect"] is False
    service._history.assert_not_awaited()


def test_missing_history_statement_is_not_a_permission_exclusion():
    assert requests_history("What changed for SPY? No history was supplied yet")


@pytest.mark.parametrize("baseline", [
    "2026-10-01", "10/01/2026", "October 1", "Oct 1, 2026", "Tuesday", "last Friday",
    "10:30", "10:30 AM", "today at 10:30", "yesterday at 10:30",
])
def test_specific_history_baseline_is_preserved_or_refused_without_substitution(baseline):
    from services.agent.contracts import request_spec
    if baseline == "2026-10-01":
        spec = request_spec({"question": "Show SPY change since " + baseline})
        assert spec["history_baseline"] == {"date": baseline}
        assert spec["tickers"] == ["SPY"]
    else:
        with pytest.raises(ValueError, match="Specific.*history"):
            request_spec({"question": "Show SPY change since " + baseline})


@pytest.mark.parametrize("baseline", ["the previous saved observation", "the latest saved reading", "last close", "yesterday", "yesterday's close"])
def test_supported_saved_baselines_remain_available(baseline):
    from services.agent.contracts import request_spec
    assert request_spec({"question": "Show SPY change since " + baseline})["tickers"] == ["SPY"]


def original_relationship_menu(facts):
    from services.agent.contracts import relationship_text
    ledger = {item["id"]: item for item in facts}
    result = []
    for item in facts:
        candidates = [{"kind": kind, "fact_id": item["id"]} for kind in ("fresh", "stale", "available", "event_date")]
        candidates.extend({"kind": kind, "fact_id": item["id"], "other_fact_id": other["id"]}
                          for other in facts if other["id"] != item["id"]
                          for kind in ("above", "below", "rising", "falling"))
        for candidate in candidates:
            try:
                relationship_text(candidate, ledger)
            except (ValueError, TypeError, KeyError):
                continue
            result.append(candidate)
            if len(result) == 64:
                return result
    return result


def test_relationship_filter_preserves_every_choice_and_its_order():
    from services.agent.codex_model import allowed_relationships, relationship_choices
    facts = [exact_reading("bid", 3), exact_reading("ask", 4),
             exact_reading("series", [1, 2, 3]), exact_reading("old bid", 2, status="stale"),
             exact_reading("limited ask", 5, status="degraded")]
    expected = original_relationship_menu(facts)
    assert allowed_relationships(facts) == expected
    assert relationship_choices(facts) == {f"r{index:02d}": relation for index, relation in enumerate(expected)}


def test_nonhealthy_large_fact_set_does_not_attempt_impossible_comparisons(monkeypatch):
    from services.agent import codex_model
    original = codex_model.relationship_text
    calls = []
    def counted(relation, ledger):
        calls.append(relation)
        return original(relation, ledger)
    monkeypatch.setattr(codex_model, "relationship_text", counted)
    facts = [exact_reading("saved cell " + str(i), i, status="degraded") for i in range(120)]
    result = codex_model.allowed_relationships(facts)
    assert result == original_relationship_menu(facts)
    assert len(result) == 64
    assert not any(item["kind"] in {"above", "below", "rising", "falling"} for item in calls)
    assert len(calls) <= 4 * len(facts)


@pytest.mark.parametrize("question", [
    "What changed for SPY after October 1?",
    "Show SPY history for October 1",
    "Compare SPY with the October 1 reading",
])
def test_other_explicit_dated_comparison_wording_is_refused(question):
    from services.agent.contracts import request_spec
    with pytest.raises(ValueError, match="Specific.*history"):
        request_spec({"question": question})


def test_expiry_dates_and_plain_ticker_comparison_are_not_history_baselines():
    from services.agent.contracts import request_spec
    expiry = request_spec({"question": "Explain SPY expiry 2026-10-16"})
    assert expiry["question_scope"] == {"selected_expiry": "2026-10-16"}
    comparison = request_spec({"question": "Compare SPY and QQQ expiry 2026-10-16"})
    assert comparison["tickers"] == ["SPY", "QQQ"]
    assert comparison["question_scope"] == {"selected_expiry": "2026-10-16"}
    assert request_spec({"question": "Compare SPY and QQQ"})["tickers"] == ["SPY", "QQQ"]
