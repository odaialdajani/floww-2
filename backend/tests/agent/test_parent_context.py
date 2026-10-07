"""Owned completed parent context stays separate from the child's current evidence."""
import asyncio
import copy
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.contracts import fact, request_spec
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService


def identity():
    return f"{int(time.time()*1000)}-{uuid.uuid4()}"


async def parent_record(repository, *, owner="alice", status="completed", facts=None):
    spec = request_spec({"question": "Explain SPY", "screen": {"ticker": "SPY"}})
    turn, _ = await repository.admit(owner, identity(), spec)
    if status == "completed":
        await repository.finish(owner, turn["turn_id"], "completed", answer={"facts": facts or [], "summary": "PRIVATE account prose must never enter child context"})
    return turn["turn_id"]


@pytest.mark.parametrize("value", ["bad", "x"*100, {}, True, "../other-owner"])
def test_parent_identity_is_validated_before_lookup(value):
    with pytest.raises(ValueError):
        request_spec({"question": "Explain SPY", "parent_turn_id": value})


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["other_owner", "missing", "running"])
async def test_invalid_parent_cannot_admit_or_start_child_work(kind):
    repository = AgentRepository(AsyncMongoMockClient().test)
    await repository.initialize()
    parent = (str(uuid.uuid4()) if kind == "missing" else
              await parent_record(repository, owner="bob" if kind == "other_owner" else "alice", status="queued" if kind == "running" else "completed"))
    reads = SimpleNamespace(snapshot=AsyncMock(return_value={"ticker":"QQQ", "horizon":"all", "snapshot_id":"fixture", "facts":[], "gaps":[], "anchor_kind":"display"}), market_snapshot=AsyncMock())
    model = SimpleNamespace(settings_for=AsyncMock(return_value={"model":"fixture", "effort":"medium", "speed":"default"}), once=AsyncMock())
    service = ResearchService(repository, reads, model=model)
    spec = request_spec({"question": "Explain QQQ", "screen": {"ticker": "QQQ"}, "parent_turn_id": parent})
    before = await repository.turns.count_documents({})
    try:
        with pytest.raises(ValueError):
            await service.ask("alice", identity(), spec)
        assert await repository.turns.count_documents({}) == before
        reads.snapshot.assert_not_awaited()
        model.settings_for.assert_not_awaited()
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_completed_parent_supplies_only_public_dated_context_without_current_fact_or_scope_substitution():
    repository = AgentRepository(AsyncMongoMockClient().test)
    await repository.initialize()
    prior = fact("Underlying price", 100, "USD", ticker="SPY", source="public_api", snapshot_id="prior",
                 event_time="2026-10-05T15:00:00Z", received_at="2026-10-05T15:00:02Z")
    private = fact("Portfolio balance", 12345, "USD", ticker="SPY", source="account portfolio", snapshot_id="private",
                   event_time="2026-10-05T15:00:00Z")
    forged = {**prior, "value": 999}
    parent = await parent_record(repository, facts=[prior, private, forged])
    current = fact("Underlying price", 200, "USD", ticker="QQQ", source="public_api", snapshot_id="current",
                   event_time=datetime.now(UTC).isoformat())
    snapshot = {"ticker": "QQQ", "horizon": "all", "snapshot_id": "current", "facts": [current],
                "gaps": [], "anchor_kind": "display"}
    reads = SimpleNamespace(snapshot=AsyncMock(return_value=snapshot))
    model = SimpleNamespace(single_attempt=True, settings_for=AsyncMock(return_value={"model":"fixture","effort":"medium","speed":"default"}),
                            once=AsyncMock(return_value={"status":"unavailable","reason":"Fixture interpretation unavailable"}))
    service = ResearchService(repository, reads, model=model)
    spec = request_spec({"question": "Explain QQQ", "screen": {"ticker": "QQQ"}, "parent_turn_id": parent})
    assert spec["tickers"] == ["QQQ"]
    child = await service.ask("alice", identity(), spec)
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repository.read("alice", child["turn_id"])
    assert saved["status"] == "completed"
    context = saved["answer"]["parent_context"]
    assert context["turn_id"] == parent
    assert context["facts"] == [prior]
    assert context["facts"][0]["event_time"] == prior["event_time"]
    assert context["usage"] == "prior_saved_only"
    assert all(item["ticker"] == "QQQ" for item in saved["answer"]["facts"])
    assert "PRIVATE" not in str(context) and "portfolio" not in str(context).lower()
    assert model.once.await_count == 1
    assert model.once.call_args.kwargs["history_note"]["parent_context"] == context
    assert await repository.read("bob", child["turn_id"]) is None
    assert (await repository.read("alice", parent))["answer"]["facts"] == [prior, private, forged]
    assert copy.deepcopy(prior) == context["facts"][0]


@pytest.mark.asyncio
async def test_market_child_keeps_scope_and_no_model_calls_while_retaining_supported_parent():
    repository = AgentRepository(AsyncMongoMockClient().test)
    await repository.initialize()
    prior = fact("Reported daily option volume", 3000, "contracts", ticker="AMD", source="cached Public options scan", snapshot_id="prior-scan",
                 received_at="2026-10-05T15:00:02Z", status="stale")
    parent = await parent_record(repository, facts=[prior])
    answer = dict(scope="market", facts=[], summary="No cached scan", actions=[])
    reads = SimpleNamespace(market_snapshot=AsyncMock(return_value=answer), snapshot=AsyncMock())
    model = SimpleNamespace(settings_for=AsyncMock(), once=AsyncMock())
    service = ResearchService(repository, reads, model=model)
    child = await service.ask("alice", identity(), request_spec({"question":"Whole market", "scope":"market", "parent_turn_id":parent}))
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repository.read("alice", child["turn_id"])
    assert saved["answer"]["scope"] == "market"
    assert saved["answer"]["parent_context"]["facts"] == [prior]
    assert saved["answer"]["facts"] == [] and saved["answer"]["actions"] == []
    model.once.assert_not_awaited()
    model.settings_for.assert_not_awaited()


@pytest.mark.asyncio
async def test_parent_fact_and_byte_limits_preserve_whole_original_values():
    from services.agent.contracts import canonical
    from services.agent.parent_context import completed_parent_context
    originals = [fact("Underlying price", i+1, "USD", ticker="SPY", source="public_api", snapshot_id="prior-"+str(i),
                      event_time="2026-10-05T15:00:00Z") for i in range(100)]
    context = completed_parent_context({"turn_id":str(uuid.uuid4()), "created_at":datetime.now(UTC), "answer":{"facts":originals}})
    assert len(context["facts"]) == 12
    assert len(canonical(context).encode()) <= 8192
    assert context["facts"] == originals[:12]
    assert context["omitted_facts"] == 88
    arrays = [fact("Gamma exposure strikes", [float(i)+j/1000 for j in range(64)], "USD", ticker="SPY", source="public_api", snapshot_id="array-"+str(i),
                   event_time="2026-10-05T15:00:00Z") for i in range(100)]
    context = completed_parent_context({"turn_id":str(uuid.uuid4()), "answer":{"facts":arrays}})
    assert len(canonical(context).encode()) <= 8192
    assert all(item in arrays and len(item["value"]) == 64 for item in context["facts"])


def test_parent_projection_excludes_undated_private_and_arbitrary_prior_commentary():
    from services.agent.parent_context import completed_parent_context
    public = fact("Underlying price", 100, "USD", ticker="SPY", source="public_api", snapshot_id="prior",
                  event_time="2026-10-05T15:00:00Z", reason="Arbitrary earlier commentary should not enter the next prompt")
    undated = fact("Underlying price", 101, "USD", ticker="SPY", source="public_api", snapshot_id="no-date")
    hidden = fact("Underlying price", 102, "USD", ticker="SPY", source="private-account", snapshot_id="hidden", event_time="2026-10-05T15:00:00Z")
    malformed = [{**public, "metric":{}}, {**public, "status":{}}, {**public, "account_id":"private"}]
    context = completed_parent_context({"turn_id":str(uuid.uuid4()), "answer":{"facts":[public,undated,hidden,*malformed],"summary":"private old prose"},"question":"private user question"})
    assert len(context["facts"]) == 1
    assert context["facts"][0]["id"] == public["id"]
    assert context["facts"][0]["event_time"] == public["event_time"]
    assert "reason" not in context["facts"][0]
    assert "commentary" not in str(context) and "private" not in str(context)


@pytest.mark.asyncio
async def test_prior_healthy_fact_cannot_unlock_a_model_without_current_evidence():
    repository = AgentRepository(AsyncMongoMockClient().test)
    await repository.initialize()
    prior = fact("Underlying price", 100, "USD", ticker="SPY", source="public_api", snapshot_id="prior", event_time="2026-10-05T15:00:00Z")
    parent = await parent_record(repository, facts=[prior])
    reads = SimpleNamespace(snapshot=AsyncMock(return_value={"ticker":"QQQ","horizon":"all","snapshot_id":"empty","facts":[],"gaps":[],"anchor_kind":"display"}))
    model = SimpleNamespace(settings_for=AsyncMock(return_value={"model":"fixture","effort":"medium","speed":"default"}), once=AsyncMock())
    service = ResearchService(repository, reads, model=model)
    child = await service.ask("alice", identity(), request_spec({"question":"Explain QQQ", "parent_turn_id":parent}))
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repository.read("alice", child["turn_id"])
    assert saved["answer"]["facts"] == []
    assert saved["answer"]["parent_context"]["facts"] == [prior]
    model.once.assert_not_awaited()


@pytest.mark.asyncio
async def test_parent_context_replay_keeps_same_owned_request_without_new_work():
    repository = AgentRepository(AsyncMongoMockClient().test)
    await repository.initialize()
    prior = fact("Underlying price", 100, "USD", ticker="SPY", source="public_api", snapshot_id="prior", event_time="2026-10-05T15:00:00Z")
    parent = await parent_record(repository, facts=[prior])
    reads = SimpleNamespace(market_snapshot=AsyncMock(return_value={"scope":"market","facts":[],"actions":[],"summary":"Cached scan"}))
    service = ResearchService(repository, reads)
    spec = request_spec({"question":"Whole market","parent_turn_id":parent})
    key = identity()
    first = await service.ask("alice", key, spec)
    await asyncio.gather(*list(service.tasks.values()))
    replay = await service.ask("alice", key, spec)
    assert replay["turn_id"] == first["turn_id"]
    reads.market_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_cannot_publish_a_parent_fact_as_the_childs_current_reading():
    repository = AgentRepository(AsyncMongoMockClient().test)
    await repository.initialize()
    prior = fact("Underlying price", 100, "USD", ticker="SPY", source="public_api", snapshot_id="prior", event_time="2026-10-05T15:00:00Z")
    parent = await parent_record(repository, facts=[prior])
    current = fact("Underlying price", 200, "USD", ticker="QQQ", source="public_api", snapshot_id="current", event_time=datetime.now(UTC).isoformat())
    reads = SimpleNamespace(snapshot=AsyncMock(return_value={"ticker":"QQQ", "horizon":"all", "snapshot_id":"current", "facts":[current], "gaps":[], "anchor_kind":"display"}))
    model = SimpleNamespace(single_attempt=True, settings_for=AsyncMock(return_value={"model":"fixture", "effort":"medium", "speed":"default"}),
                            once=AsyncMock(return_value={"status":"ok", "name":"research_answer", "data":{"sections":[{"name":"Market", "fact_ids":[prior["id"]], "interpretation":"descriptive"}], "relationships":[], "explanations":[]}}))
    service = ResearchService(repository, reads, model=model)
    child = await service.ask("alice", identity(), request_spec({"question":"Explain QQQ", "parent_turn_id":parent}))
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repository.read("alice", child["turn_id"])
    assert saved["status"] == "completed"
    assert saved["answer"]["model_rejection"]["code"] == "unknown_evidence"
    assert saved["answer"]["facts"] == [current]
    assert "model_sections" not in saved["answer"]
    assert model.once.await_count == 1
