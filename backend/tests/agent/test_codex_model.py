import asyncio
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.codex_bridge import POLICY, CodexBridge, child_environment
from services.agent.codex_model import DEFAULT_SETTINGS, CodexModel, OAuthUsage, allowed_relationships
from services.agent.repository import AgentRepository


def test_relationship_menu_does_not_compare_unknown_structure_time():
    facts = [
        dict(id="price", ticker="SPY", metric="Underlying price", value=500, unit="USD", horizon="all",
             source="public-mid", status="ok", event_time="2026-09-11T20:00:00+00:00"),
        dict(id="flip", ticker="SPY", metric="Flip", value=501, unit="USD", horizon="all",
             source="public_api", status="degraded", event_time=None),
    ]
    menu = allowed_relationships(facts)
    assert {"kind": "fresh", "fact_id": "price"} in menu
    assert {"kind": "available", "fact_id": "flip"} in menu
    assert not any(r["kind"] in {"above", "below", "rising", "falling"} for r in menu)


def test_child_has_no_market_credentials_and_tools_disabled(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_KEY", "must-not-pass")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-pass")
    monkeypatch.setenv("DATABASE_URL", "must-not-pass")
    assert not {"PUBLIC_API_KEY", "OPENROUTER_API_KEY", "DATABASE_URL"} & child_environment().keys()
    assert POLICY["mcp_servers"] == {} and POLICY["notify"] == []
    assert POLICY["features.shell_tool"] is False and POLICY["features.multi_agent"] is False


@pytest.mark.asyncio
async def test_server_tool_request_is_rejected():
    bridge = CodexBridge()
    bridge.process = type(
        "P",
        (),
        {
            "stdout": type(
                "S",
                (),
                {"readline": AsyncMock(return_value=json.dumps({"id": 4, "method": "item/tool/call"}).encode())},
            )()
        },
    )()
    bridge.send = AsyncMock()
    with pytest.raises(ValueError, match="unavailable capability"):
        await bridge.receive()
    assert bridge.send.call_args.args[0]["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_quota_race_and_same_turn_replay_cannot_redispatch():
    usage = OAuthUsage(AsyncMongoMockClient().db.usage, daily_limit=3)
    results = await asyncio.gather(*(usage.reserve("owner", f"turn-{i}", DEFAULT_SETTINGS) for i in range(20)))
    assert sum(r is not None for r in results) == 3
    assert (await usage.state())["calls"] == 3
    assert await usage.reserve("owner", "turn-0", DEFAULT_SETTINGS) is None
    assert (await usage.state())["actual_cost"] is None


@pytest.mark.asyncio
async def test_same_turn_cannot_redispatch_after_utc_day_rollover(monkeypatch):
    import services.agent.codex_model as module
    class Clock(datetime):
        current = datetime(2026,9,11,23,59,tzinfo=UTC)
        @classmethod
        def now(cls, tz=None):
            return cls.current
    monkeypatch.setattr(module,"datetime",Clock)
    usage = OAuthUsage(AsyncMongoMockClient().db.usage)
    assert await usage.reserve("alice","saved-turn",DEFAULT_SETTINGS)
    Clock.current += timedelta(minutes=2)
    assert await usage.reserve("alice","saved-turn",DEFAULT_SETTINGS) is None
    assert (await usage.state())["calls"] == 0
    assert await usage.reserve("alice","new-turn",DEFAULT_SETTINGS)
    assert (await usage.state())["calls"] == 1


@pytest.mark.asyncio
async def test_saved_request_keeps_its_original_ai_choices_on_replay():
    from services.agent.contracts import request_spec
    from services.agent.research import ResearchService
    repo = AgentRepository(AsyncMongoMockClient().db)
    await repo.initialize()
    model = type("Settings",(),{"settings_for":AsyncMock(return_value={**DEFAULT_SETTINGS,"effort":"low"})})()
    service = ResearchService(repo,None,model=model)
    service._work = AsyncMock()
    spec = request_spec({"question":"Explain SPY structure", "screen":{"ticker":"SPY"}})
    request_id = f"{int(time.time()*1000)}-{uuid.uuid4()}"
    first = await service.ask("alice",request_id,spec)
    await service.tasks[first["turn_id"]]
    model.settings_for.return_value = {**DEFAULT_SETTINGS,"effort":"medium"}
    replay = await service.ask("alice",request_id,spec)
    assert replay["turn_id"] == first["turn_id"]
    assert replay["spec"]["ai_settings"]["effort"] == "low"
    assert service._work.await_count == 1 and model.settings_for.await_count == 1
    await service.close()


class FakeBridge:
    calls = 0
    error = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def catalog(self):
        return [dict(id=DEFAULT_SETTINGS["model"], label="Example", efforts=["low", "medium"], speeds=["default"])]

    async def answer(self, *_):
        type(self).calls += 1
        if type(self).error:
            raise TimeoutError()
        return {"sections": []}, {"total": {"totalTokens": 99}}, "thread", "turn"


@pytest.mark.asyncio
async def test_settings_owner_scoped_and_uncertain_work_never_repeated():
    db = AsyncMongoMockClient().db
    repo = AgentRepository(db)
    await repo.initialize()
    model = CodexModel(repo, db.usage, bridge_factory=FakeBridge)
    await repo.save_preferences("alice", {"ai_settings": {**DEFAULT_SETTINGS, "effort": "low"}})
    assert (await model.settings_for("alice"))["effort"] == "low"
    assert (await model.settings_for("bob"))["effort"] == "medium"
    with pytest.raises(ValueError):
        await model.validate_settings({**DEFAULT_SETTINGS, "speed": "priority"})
    FakeBridge.calls, FakeBridge.error = 0, True
    result = await model.once("hello", [], "sample-turn", owner="alice", settings=DEFAULT_SETTINGS)
    assert result["status"] == "unavailable" and result["actual_cost"] is None
    await model.once("hello", [], "sample-turn", owner="alice", settings=DEFAULT_SETTINGS)
    assert FakeBridge.calls == 1
    assert (await model.spend.state())["calls"] == 1
