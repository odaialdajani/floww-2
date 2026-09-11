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
    assert (await history_facts(repo, "alice", {**after, "observed_at": None}))[0] == []
    assert "coverage" in (await history_facts(repo, "alice", {**after, "coverage_id": "changed"}))[1]
