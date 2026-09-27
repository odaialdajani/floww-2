from datetime import UTC, datetime

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.saved_history import history_facts


@pytest.mark.asyncio
async def test_history_requires_owner_source_time_and_matching_contract_coverage():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    now = datetime(2026, 9, 11, 15, tzinfo=UTC)
    source = {
        "spot": 100,
        "source": "fixture",
        "event_time": "2026-09-11T14:59:00Z",
        "contracts": [{"strike": 100, "type": "C", "gamma": 0.01, "open_interest": 10, "expiry": "2026-09-18"}],
    }
    reads = ResearchReads(lambda *a: source, lambda *a: None, lambda *a: [])
    before = await reads.snapshot("SPY", "all", now=now)
    await repo.turns.insert_one(
        {
            "turn_id": "old",
            "owner": "alice",
            "status": "completed",
            "created_at": now,
            "answer": {"snapshots": [before]},
        }
    )
    source.update(spot=102, event_time=now.isoformat())
    after = await reads.snapshot("SPY", "all", now=now)
    facts, note = await history_facts(repo, "alice", after)
    assert facts[-1]["value"] == 2
    assert facts[-1]["parents"][0] == facts[0]["id"]
    assert "14:59" in note
    assert (await history_facts(repo, "bob", after))[0] == []
    # Price comparisons use price time, even when chain time is unknown.
    assert (await history_facts(repo, "alice", {**after, "observed_at": None}))[0][-1]["value"] == 2
    missing_price_time = {**after, "facts": [{**f, "event_time": None} for f in after["facts"]]}
    assert (await history_facts(repo, "alice", missing_price_time))[0] == []
    assert "coverage" in (await history_facts(repo, "alice", {**after, "coverage_id": "changed"}))[1]


@pytest.mark.asyncio
async def test_collected_anchor_is_available_without_an_earlier_question():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    now = datetime(2026, 9, 11, 15, tzinfo=UTC)
    source = {"spot": 100, "source": "fixture", "event_time": "2026-09-11T14:59:00Z", "contracts": []}
    reads = ResearchReads(lambda *a: source, lambda *a: None, lambda *a: [])
    before = await reads.snapshot("SPY", "all", now=now)
    await repo.save_anchor("alice", before)
    await repo.save_anchor(
        "alice",
        {
            **before,
            "snapshot_id": "different-coverage",
            "observed_at": "2026-09-11T14:59:30+00:00",
            "coverage_id": "changed",
        },
    )
    source.update(spot=102, event_time=now.isoformat())
    after = await reads.snapshot("SPY", "all", now=now)
    facts, _ = await history_facts(repo, "alice", after)
    assert facts[-1]["value"] == 2
    assert (await history_facts(repo, "bob", after))[0] == []


@pytest.mark.asyncio
async def test_requested_previous_close_never_uses_an_older_close():
    from services.agent.contracts import fact

    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    current = {
        "ticker": "DIA",
        "horizon": "all",
        "captured_at": "2026-09-11T15:00:00+00:00",
        "observed_at": "2026-09-11T15:00:00+00:00",
        "coverage_id": "same",
        "snapshot_id": "current",
        "facts": [
            fact(
                "Underlying price",
                95,
                "USD",
                ticker="DIA",
                source="fixture",
                snapshot_id="current",
                event_time="2026-09-11T15:00:00Z",
            )
        ],
    }

    def closing(day):
        stamp = f"2026-09-{day}T20:00:00+00:00"
        return {
            **current,
            "snapshot_id": f"close{day}",
            "observed_at": stamp,
            "anchor_kind": "close",
            "window": {"session_close": stamp},
            "facts": [
                fact(
                    "Underlying price",
                    90,
                    "USD",
                    ticker="DIA",
                    source="fixture",
                    snapshot_id=f"close{day}",
                    event_time=stamp,
                )
            ],
        }

    await repo.save_anchor("alice", closing("09"))
    facts, note = await history_facts(repo, "alice", current, closing_only=True)
    assert facts == [] and "2026-09-10" in note
    await repo.save_anchor("alice", closing("10"))
    facts, note = await history_facts(repo, "alice", current, closing_only=True)
    assert facts[-1]["value"] == 5 and "2026-09-10" in note


@pytest.mark.asyncio
async def test_earlier_saved_question_displays_coverage_mismatch_without_a_price_change():
    import asyncio
    import copy

    from services.agent.research import ResearchService

    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    now = datetime(2026, 9, 11, 15, tzinfo=UTC)
    raw = {"spot": 200, "source": "fixture", "event_time": "2026-09-11T14:59:00Z",
           "contracts": [{"strike": 200, "type": "C", "gamma": .01, "open_interest": 10,
                          "expiry": "2026-09-18"}]}
    reads = ResearchReads(lambda *a: raw, lambda *a: None, lambda *a: [])
    before = await reads.snapshot("DIA", "all", now=now)
    await repo.save_anchor("alice", before)
    raw["event_time"] = now.isoformat()
    raw["contracts"].append({**raw["contracts"][0], "strike": 201})
    after = await reads.snapshot("DIA", "all", now=now)

    class Reads:
        async def snapshot(self, *args, **kwargs):
            return copy.deepcopy(after)

    service = ResearchService(repo, Reads())
    question = {"question": "Compare $DIA with my earlier saved reading; does the coverage match?",
                "tickers": ["DIA"], "ticker": "DIA", "horizon": "all", "screen": {},
                "context_conflict": False, "question_scope": None, "price_only": False}
    import uuid
    request_id = f"{int(datetime.now(UTC).timestamp() * 1000)}-{uuid.uuid4()}"
    doc = await service.ask("alice", request_id, question)
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repo.turns.find_one({"turn_id": doc["turn_id"]})
    assert saved["status"] == "completed"
    answer = saved["answer"]
    section = next(s for s in answer["sections"] if s["name"] == "What changed")
    assert "earlier saved coverage: 1 contracts; current saved coverage: 2 contracts" in section["text"]
    assert any("different expiry or contract coverage" in g for g in answer["gaps"])
    assert not any(f["metric"] == "Price change since saved observation" for f in answer["facts"])
    assert (await history_facts(repo, "bob", after))[0] == []
    assert "1 contracts" not in (await history_facts(repo, "bob", after))[1]
