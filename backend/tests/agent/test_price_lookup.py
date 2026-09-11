import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.contracts import request_spec
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService


@pytest.mark.parametrize(
    "question",
    [
        "What is SPY's spot price?",
        "Show the current underlying price",
        "SPY spot price",
        "What is the spot price of SPY?",
        "Show me the current underlying price for SPY",
    ],
)
def test_exact_spot_lookup_is_recognized(question):
    assert request_spec({"question": question, "screen": {"ticker": "SPY"}})["price_only"]


@pytest.mark.parametrize(
    "question",
    [
        "What is SPY's price versus its flip?",
        "What was SPY's spot price yesterday?",
        "SPY option price",
        "Compare SPY and QQQ spot prices",
        "Why did SPY's spot price rise?",
    ],
)
def test_other_questions_keep_full_research(question):
    assert not request_spec({"question": question, "screen": {"ticker": "SPY"}, "price_only": True})["price_only"]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_time", [None, "2020-01-01T00:00:00Z", "fresh"])
async def test_spot_lookup_saves_only_price_without_model_map_alert_or_background_work(source_time):
    stamp = datetime.now(UTC).isoformat() if source_time == "fresh" else source_time
    source = {"spot": 123.45, "event_time": stamp, "source": "synthetic test", "contracts": []}
    map_read, alert_read = Mock(return_value=None), Mock(return_value=[])
    reads = ResearchReads(lambda *args: source, map_read, alert_read)
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    repo.watch_observations = AsyncMock()
    model = AsyncMock()
    service = ResearchService(repo, reads, model=model)
    screen = {"ticker": "SPY", "selectedExpiry": "2026-09-18", "mapQuery": {"expiries": 6}}
    spec = request_spec({"question": "What is SPY's spot price?", "screen": screen})
    turn = await service.ask("alice", f"{int(time.time() * 1000)}-{uuid.uuid4()}", spec)
    await service.tasks[turn["turn_id"]]
    saved = await repo.read("alice", turn["turn_id"])
    assert saved["status"] == "completed"
    answer = saved["answer"]
    assert [f["metric"] for f in answer["facts"]] == ["Underlying price"]
    assert answer["facts"][0]["value"] == 123.45
    assert answer["facts"][0]["status"] == ("ok" if source_time == "fresh" else "stale" if source_time else "degraded")
    assert answer["context"] == screen
    assert "cached underlying price" in answer["summary"]
    assert "123.45" in answer["summary"]
    assert "factual lookup" in answer["model_status"]
    map_read.assert_not_called()
    alert_read.assert_not_called()
    repo.watch_observations.assert_not_called()
    assert not model.mock_calls
    await service.close()


@pytest.mark.asyncio
async def test_saved_price_lookup_supports_later_change_question_with_real_contract_coverage():
    now = datetime.now(UTC)
    source = {
        "spot": 100,
        "source": "synthetic",
        "event_time": (now - timedelta(minutes=1)).isoformat(),
        "contracts": [
            {
                "expiry": (now + timedelta(days=7)).date().isoformat(),
                "strike": 100,
                "type": "C",
                "gamma": 0.01,
                "oi": 10,
            }
        ],
    }
    reads = ResearchReads(lambda *args: source, lambda *args: None, lambda *args: [])
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    service = ResearchService(repo, reads)
    for question in ["What is SPY's spot price?", "What changed since the previous observation?"]:
        spec = request_spec({"question": question, "screen": {"ticker": "SPY"}})
        turn = await service.ask("alice", f"{int(time.time() * 1000)}-{uuid.uuid4()}", spec)
        await service.tasks[turn["turn_id"]]
        source.update(spot=103, event_time=now.isoformat())
    answer = (await repo.read("alice", turn["turn_id"]))["answer"]
    assert any("Price change: +3 USD" in section["text"] for section in answer["sections"])
    await service.close()
