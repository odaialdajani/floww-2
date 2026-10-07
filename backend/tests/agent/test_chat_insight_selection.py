"""Regression checks for grounded chat selection, never model-authored claims."""
import asyncio
import copy
import json
import time
import uuid
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.answer_sections import requested_sections
from services.agent.codex_model import answer_schema
from services.agent.contracts import fact, request_spec, validate_model_answer
from services.agent.explanations import explanation_menu
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService


def validate(value, schema):
    """Exercise the small JSON Schema subset used by the checked provider output."""
    if "anyOf" in schema:
        for choice in schema["anyOf"]:
            try:
                validate(value, choice)
                return
            except ValueError:
                pass
        raise ValueError("No permitted choice")
    types = schema.get("type", [])
    types = types if isinstance(types, list) else [types]
    actual = "null" if value is None else "object" if isinstance(value, dict) else "array" if isinstance(value, list) else "string"
    if types and actual not in types:
        raise ValueError("Wrong type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("Unknown choice")
    if isinstance(value, dict):
        if set(schema.get("required", [])) - set(value):
            raise ValueError("Required choice missing")
        if schema.get("additionalProperties") is False and set(value) - set(schema.get("properties", {})):
            raise ValueError("Unknown field")
        for key, item in value.items():
            validate(item, schema["properties"][key])
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10000):
            raise ValueError("Choice count")
        for item in value:
            validate(item, schema.get("items", {}))


def reading(metric="Underlying price", value=93, unit="USD", status="ok", snapshot="current"):
    return fact(metric, value, unit, ticker="SPY", source="fixture", snapshot_id=snapshot,
                event_time="2026-10-06T15:00:00Z", status=status)


def test_request_choices_reject_unknown_or_overconfident_evidence():
    good, limited = reading(), reading("Cached map price", status="degraded")
    menu = explanation_menu([good, limited])
    schema = answer_schema([good, limited])
    answer = {"sections": [{"name": "Market", "fact_ids": [limited["id"]],
                             "interpretation": "limited"}], "relationships": [],
              "explanations": [menu[0]["id"]]}
    validate(answer, schema)
    validate_model_answer(answer, {f["id"]: f for f in [good, limited]})
    for patch in ({"interpretation": "descriptive"}, {"fact_ids": ["invented"]}):
        bad = copy.deepcopy(answer)
        bad["sections"][0].update(patch)
        with pytest.raises(ValueError):
            validate(bad, schema)
    bad = copy.deepcopy(answer)
    bad["explanations"] = ["invented"]
    with pytest.raises(ValueError):
        validate(bad, schema)
    bad = copy.deepcopy(answer)
    bad["relationships"] = [{"kind": "fresh", "fact_id": limited["id"], "other_fact_id": None}]
    with pytest.raises(ValueError):
        validate(bad, schema)
    answer["sections"][0] = {"name": "Market", "fact_ids": [good["id"]], "interpretation": "descriptive"}
    validate(answer, schema)


def test_volatility_dates_do_not_count_as_numeric_estimates():
    raw = [reading("Implied move expiry instant", "2026-10-09T20:00:00Z", "instant"),
           reading("Realized volatility observation dates", ["2026-10-01"], "dates")]
    assert "missing_volatility" in {x["kind"] for x in explanation_menu(raw)}
    estimates = [reading("At-the-money implied volatility", .2, "annualized fraction"),
                 reading("Realized daily close volatility", .15, "annualized fraction")]
    assert "missing_volatility" not in {x["kind"] for x in explanation_menu(raw + estimates)}
    wrong_units = [{**item, "unit": "dates"} for item in estimates]
    assert "missing_volatility" in {x["kind"] for x in explanation_menu(raw + wrong_units)}


@pytest.mark.asyncio
async def test_saved_history_question_reads_only_owner_history():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    current = {"ticker": "SPY", "horizon": "all", "snapshot_id": "current",
               "facts": [reading()], "gaps": [], "coverage_id": "same"}
    service = ResearchService(repo, type("Reads", (), {"snapshot": AsyncMock(return_value=current)})())
    service._history = AsyncMock(return_value=([reading("Price change since saved observation", 3)], "Saved comparison"))
    spec = request_spec({"question": "Show SPY saved history"})
    assert "What changed" in requested_sections(spec)
    turn = await service.ask("alice", f"{int(time.time()*1000)}-{uuid.uuid4()}", spec)
    await asyncio.gather(*list(service.tasks.values()))
    service._history.assert_awaited_once()
    assert service._history.call_args.args[1] == "alice"
    saved = await repo.read("alice", turn["turn_id"])
    assert any(f["metric"] == "Price change since saved observation" for f in saved["answer"]["facts"])
    assert await repo.read("bob", turn["turn_id"]) is None


@pytest.mark.asyncio
async def test_chat_sends_fixed_missing_data_context_and_saves_safe_rejection(monkeypatch):
    from services.agent.codex_model import DEFAULT_SETTINGS, CodexModel
    events = []
    monkeypatch.setattr("services.problem_journal.record_problem", events.append)
    db = AsyncMongoMockClient().test
    repo = AgentRepository(db)
    await repo.initialize()
    class Bridge:
        captured = None
        schema = None
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return None
        async def catalog(self):
            return [{"id": DEFAULT_SETTINGS["model"], "efforts": ["medium"], "speeds": ["default"]}]
        async def answer(self, content, settings, schema):
            type(self).captured, type(self).schema = json.loads(content), schema
            return {"sections": [{"name": "Market", "fact_ids": [evidence["id"]],
                                   "interpretation": "descriptive"}]}, {}, "thread", "turn"
    evidence = reading(status="degraded")
    snapshot = {"ticker": "SPY", "horizon": "all", "snapshot_id": "current", "facts": [evidence],
                "gaps": ["Chain observation time is unknown", "Implied volatility missing token=do-not-publish"]}
    model = CodexModel(repo, db.usage, bridge_factory=Bridge)
    service = ResearchService(repo, type("Reads", (), {"snapshot": AsyncMock(return_value=snapshot)})(), model=model)
    spec = request_spec({"question": "What data is missing for SPY?",
                         "screen": {"ticker": "SPY", "arbitrary": "do-not-publish"}})
    turn = await service.ask("alice", f"{int(time.time()*1000)}-{uuid.uuid4()}", spec)
    await asyncio.gather(*list(service.tasks.values()))
    payload = Bridge.captured
    assert payload["source_gaps"] and payload["selection"]["tickers"] == ["SPY"]
    assert "do-not-publish" not in json.dumps(payload)
    saved = await repo.read("alice", turn["turn_id"])
    rejection = saved["answer"]["model_rejection"]
    assert rejection == {"code": "limited_evidence_required", "field": "interpretation", "turn_id": turn["turn_id"]}
    assert events and turn["turn_id"] in json.dumps(events)
    assert "descriptive" not in json.dumps(events)
    assert (await model.spend.state())["calls"] == 1


@pytest.mark.parametrize("status", ["degraded", "stale", "missing"])
def test_all_nonhealthy_evidence_is_limited_without_changing_the_reading(status):
    evidence = reading(status=status)
    before = copy.deepcopy(evidence)
    schema = answer_schema([evidence])
    for interpretation in ("descriptive", "mixed"):
        with pytest.raises(ValueError):
            validate({"sections": [{"name": "Market", "fact_ids": [evidence["id"]],
                                    "interpretation": interpretation}], "relationships": [], "explanations": []}, schema)
    assert evidence == before


def test_every_offered_relation_still_passes_final_validator():
    from services.agent.codex_model import decode_relationship_choices, relationship_choices
    facts = [reading(), reading("Displayed flip", 90), reading("Cached map price", 92, status="stale")]
    choices = relationship_choices(facts)
    schema = answer_schema(facts, choices)
    ledger = {f["id"]: f for f in facts}
    for identity, relation in choices.items():
        answer = {"sections": [{"name": "Market", "fact_ids": [facts[0]["id"]], "interpretation": "descriptive"}],
                  "relationships": [identity], "explanations": []}
        validate(answer, schema)
        decoded = decode_relationship_choices(answer, choices)
        assert decoded["relationships"] == [relation]
        assert answer["relationships"] == [identity]
        validate_model_answer(decoded, ledger)
        assert decode_relationship_choices({**answer, "relationships": [relation]}, choices)["relationships"] == [relation]
    for unknown in ("r99", {"kind": "fresh", "fact_id": "unknown"}, None):
        with pytest.raises(ValueError):
            decode_relationship_choices({"relationships": [unknown]}, choices)
    assert decode_relationship_choices({"sections": []}, choices)["relationships"] == []


def test_context_omits_unknown_values_and_informational_scope_notes():
    from services.agent.codex_model import selection_context
    safe, gaps = selection_context([reading()], {"requested_sections": [{"unknown": "secret"}, "Structure"],
                                                 "extra": "secret"},
        ["Expiry scope follows the question; the original chart selection is retained as context only"])
    assert safe["requested_sections"] == ["Structure"] and gaps == []
    assert "secret" not in json.dumps(safe)
    assert selection_context([reading()], {"requested_sections": "secret"}, "secret")[1] == []


def test_rejection_categories_do_not_persist_unknown_error_text():
    from services.agent.research import rejection_diagnostic
    assert rejection_diagnostic(ValueError("secret private arbitrary text"), "turn-one") == {
        "code": "validation_rejected", "field": "answer", "turn_id": "turn-one"}
    assert rejection_diagnostic(KeyError("unknown fact"), "bad/identity") ["turn_id"] == "unknown"


@pytest.mark.asyncio
async def test_real_read_budget_keeps_history_question_focused_and_private():
    from datetime import UTC, datetime

    from services.agent.read_budget import capability_plan
    from services.agent.reads import ResearchReads
    now = datetime(2026, 10, 6, 15, tzinfo=UTC)
    source = {"spot": 90, "source": "fixture", "event_time": "2026-10-06T14:59:00Z", "contracts": []}
    reads = ResearchReads(lambda *a: source, lambda *a: None, lambda *a: [])
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    earlier = await reads.snapshot("SPY", "all", now=now)
    await repo.save_anchor("alice", earlier)
    source.update(spot=93, event_time=now.isoformat())
    class ClockedReads:
        async def snapshot(self, *args, **kwargs):
            return await reads.snapshot(*args, now=now, **kwargs)
    service = ResearchService(repo, ClockedReads())
    spec = request_spec({"question": "Show SPY saved history"})
    assert capability_plan(spec) == set()
    async def ask(owner):
        turn = await service.ask(owner, f"{int(time.time()*1000)}-{uuid.uuid4()}", spec)
        await asyncio.gather(*list(service.tasks.values()))
        return await repo.read(owner, turn["turn_id"])
    own = await ask("alice")
    changes = [f for f in own["answer"]["facts"] if f["metric"] == "Price change since saved observation"]
    assert len(changes) == 1 and changes[0]["value"] == 3
    attempts = own["read_activity"]["attempts"]
    assert [a["capability"] for a in attempts] == ["context", "history"]
    other = await ask("bob")
    assert not any(f["metric"] == "Price change since saved observation" for f in other["answer"]["facts"])


@pytest.mark.parametrize("stale", [False, True])
def test_supplied_contract_quotes_keep_caution_and_age_without_claiming_absence(stale):
    from services.agent.codex_model import selection_context
    facts = [reading("Exact contract bid", 3, status="stale" if stale else "ok"),
             reading("Exact contract ask", 4, status="stale" if stale else "ok")]
    before = copy.deepcopy(facts)
    limits = ["Recorded listed contract only; quotes do not establish aggressor side, dealer intent or trade direction"]
    if stale:
        limits.append("Recorded contract quotes are stale; actual source ages are retained")
    _, gaps = selection_context(facts, source_gaps=limits)
    assert gaps
    assert not any("unavailable" in gap or "missing" in gap or "could not be verified" in gap for gap in gaps)
    assert any("direction" in gap or "intent" in gap or "who" in gap for gap in gaps)
    assert any("old" in gap.lower() or "out of date" in gap.lower() or "stale" in gap.lower() for gap in gaps) is stale
    assert facts == before


def test_actual_absent_contract_quotes_still_report_unavailability():
    from services.agent.codex_model import selection_context
    _, gaps = selection_context([reading()], source_gaps=["Verified exact contract quotes are unavailable"])
    assert any("unavailable" in gap for gap in gaps)


@pytest.mark.asyncio
async def test_dynamic_schema_bytes_are_counted_before_subscription_admission(monkeypatch):
    import services.agent.codex_model as module
    from services.agent.contracts import canonical
    from services.agent.explanations import compact_explanation_menu
    db = AsyncMongoMockClient().test
    repo = AgentRepository(db)
    await repo.initialize()
    facts = [reading("Saved price reading " + str(index), 90 + index) for index in range(12)]
    before = copy.deepcopy(facts)
    question = "Compare these supplied readings"
    selection, gaps = module.selection_context(facts)
    content = canonical({"question": question, "facts": facts, "history": None,
                         "selection": selection, "source_gaps": gaps,
                         "allowed_relationships": module.relationship_choices(facts),
                         **compact_explanation_menu(facts)})
    schema = answer_schema(facts)
    content_bytes = len(content.encode())
    combined_bytes = content_bytes + len(canonical(schema).encode())
    assert len(module.allowed_relationships(facts)) == 64
    assert combined_bytes > content_bytes
    monkeypatch.setattr(module, "MAX_BODY_BYTES", combined_bytes - 1)
    model = module.CodexModel(repo, db.usage)
    model.validate_settings = AsyncMock(side_effect=AssertionError("Must refuse before catalog or transport"))
    model.spend.reserve = AsyncMock(side_effect=AssertionError("Must refuse before reservation"))
    result = await model.once(question, facts, "combined-input-too-large", owner="alice", settings=module.DEFAULT_SETTINGS)
    assert result["status"] == "unavailable" and result["trace"]["status"] == "input_refused"
    model.validate_settings.assert_not_awaited()
    model.spend.reserve.assert_not_awaited()
    assert await db.usage.count_documents({}) == 0
    assert facts == before


@pytest.mark.asyncio
async def test_empty_evidence_refuses_before_subscription_admission():
    from services.agent.codex_model import DEFAULT_SETTINGS, CodexModel
    db = AsyncMongoMockClient().test
    repo = AgentRepository(db)
    await repo.initialize()
    model = CodexModel(repo, db.usage)
    model.validate_settings = AsyncMock(side_effect=AssertionError("Empty facts must not start transport"))
    model.spend.reserve = AsyncMock(side_effect=AssertionError("Empty facts must not spend allowance"))
    result = await model.once("What happened?", [], "empty-evidence", owner="alice", settings=DEFAULT_SETTINGS)
    assert result["status"] == "unavailable"
    model.validate_settings.assert_not_awaited()
    model.spend.reserve.assert_not_awaited()
    assert await db.usage.count_documents({}) == 0


@pytest.mark.asyncio
async def test_request_inside_full_input_bound_keeps_all_numeric_evidence(monkeypatch):
    import services.agent.codex_model as module
    from services.agent.contracts import canonical
    from services.agent.explanations import compact_explanation_menu
    facts = [reading("Saved price reading " + str(index), 90 + index) for index in range(12)]
    before = copy.deepcopy(facts)
    question = "Compare these supplied readings"
    selection, gaps = module.selection_context(facts)
    content = canonical({"question": question, "facts": facts, "history": None,
                         "selection": selection, "source_gaps": gaps,
                         "allowed_relationships": module.relationship_choices(facts),
                         **compact_explanation_menu(facts)})
    full_limit = len(content.encode()) + len(canonical(answer_schema(facts)).encode()) + 1024
    monkeypatch.setattr(module, "MAX_BODY_BYTES", full_limit)
    class Bridge:
        calls = 0
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return None
        async def catalog(self):
            return [{"id": module.DEFAULT_SETTINGS["model"], "efforts": ["medium"], "speeds": ["default"]}]
        async def answer(self, content, settings, schema):
            type(self).calls += 1
            assert json.loads(content)["facts"] == before
            assert len(content.encode()) + len(canonical(schema).encode()) <= full_limit
            return {"sections": [{"name": "Market", "fact_ids": [facts[0]["id"]],
                                   "interpretation": "descriptive"}], "relationships": [], "explanations": []}, {}, "thread", "turn"
    db = AsyncMongoMockClient().test
    repo = AgentRepository(db)
    await repo.initialize()
    model = module.CodexModel(repo, db.usage, bridge_factory=Bridge)
    result = await model.once(question, facts, "within-combined-input", owner="alice", settings=module.DEFAULT_SETTINGS)
    assert result["status"] == "ok" and Bridge.calls == 1
    assert (await model.spend.state())["calls"] == 1
    assert facts == before
