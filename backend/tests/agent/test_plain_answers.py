import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.contracts import request_spec
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService, deterministic_answer


@pytest.mark.asyncio
async def test_fallback_explains_supplied_flip_and_expiry_without_direction_claim():
    source = {
        "spot": 100,
        "source": "fixture",
        "event_time": "2026-09-11T15:00:00Z",
        "contracts": [
            {"strike": 100, "type": "C", "gamma": 0.01, "open_interest": 100, "expiry": "2026-09-18"},
            {"strike": 105, "type": "P", "gamma": 0.02, "open_interest": 100, "expiry": "2026-09-18"},
        ],
    }
    snapshot = await ResearchReads(lambda *a: source, lambda *a: None, lambda *a: []).snapshot(
        "SPY", "all", now=datetime(2026, 9, 11, 15, tzinfo=UTC)
    )
    answer = deterministic_answer(
        [snapshot], request_spec({"question": "Explain positioning", "screen": {"ticker": "SPY"}})
    )
    text = " ".join(section["text"] for section in answer["sections"])
    assert "below" in text and "flip" in text and "2026-09-18" in text
    assert "amplif" in text and "direction" in text


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Send an order for AAPL shares", "No order"),
        ("Show the next MSFT earnings release", "event date"),
        ("What chance does DIA have of reaching my target?", "probability"),
        ("Use the adjusted DIA deliverable", "deliverable"),
    ],
)
def test_unsupported_request_gets_explicit_limit_instead_of_irrelevant_market_answer(question, expected):
    answer = deterministic_answer([], request_spec({"question": question, "screen": {"ticker": "SPY"}}))
    assert expected.lower() in answer["summary"].lower()


@pytest.mark.asyncio
async def test_saved_change_question_reads_owned_history_without_a_model():
    now = datetime.now(UTC)
    source = {"spot": 90, "source": "fixture", "event_time": (now - timedelta(minutes=1)).isoformat(), "contracts": []}
    reads = ResearchReads(lambda *a: source, lambda *a: None, lambda *a: [])
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    await repo.save_anchor("alice", await reads.snapshot("DIA", "all", now=now))
    source.update(spot=93, event_time=now.isoformat())
    service = ResearchService(repo, reads)
    for owner in ("alice", "bob"):
        spec = request_spec({"question": "What changed since the previous reading?", "screen": {"ticker": "DIA"}})
        turn = await service.ask(owner, f"{int(time.time() * 1000)}-{uuid.uuid4()}", spec)
        await service.tasks[turn["turn_id"]]
        answer = (await repo.read(owner, turn["turn_id"]))["answer"]
        if owner == "alice":
            assert any("Price change: +3 USD" in section["text"] for section in answer["sections"])
        else:
            assert any("No earlier compatible" in reason for reason in answer["gaps"])
    await service.close()
