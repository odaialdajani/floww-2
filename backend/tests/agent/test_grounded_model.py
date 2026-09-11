import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.model import GroundedModel
from services.agent.spend import SpendLedger


@pytest.mark.asyncio
async def test_delayed_usage_lookup_keeps_hold_and_never_repeats_paid_work():
    now = [datetime(2026, 9, 11, 15, tzinfo=UTC)]
    ledger = SpendLedger(AsyncMongoMockClient().test.budget, clock=lambda: now[0])
    await ledger.initialize()
    key = str(uuid.uuid4())
    assert await ledger.reserve(key, 50000, "one")
    await ledger.dispatch(key)
    await ledger.note_generation(key, "known-generation")
    calls = []

    def send(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path == "/api/v1/generation"
        assert request.url.params["id"] == "known-generation"
        return (
            httpx.Response(404)
            if len(calls) == 1
            else httpx.Response(200, json={"data": {"id": "known-generation", "total_cost": 0.02}})
        )

    model = GroundedModel(ledger, api_key="fixture", transport=httpx.MockTransport(send))
    assert await model.reconcile() == 0
    assert (await ledger.state())["reserved_units"] == 50000
    assert await model.reconcile() == 0
    assert len(calls) == 1
    now[0] += timedelta(minutes=6)
    assert await model.reconcile() == 1
    assert (await ledger.state())["spent_units"] == 20000
    assert (await ledger.state())["reserved_units"] == 0


ENDPOINT = {
    "tag": "amazon-bedrock",
    "supported_parameters": ["tools", "tool_choice", "max_tokens", "reasoning"],
    "supports_tool_choice": {"required": True},
    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
    "context_length": 200000,
    "max_completion_tokens": 64000,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [[], {"id": "bad-usage", "usage": [1]}, {"choices": [{"message": []}]}])
async def test_malformed_provider_reply_keeps_reserved_cost_without_raising(response):
    spend = SpendLedger(AsyncMongoMockClient().test.budget)
    await spend.initialize()

    def send(request):
        return httpx.Response(200, json={"data": {"endpoints": [ENDPOINT]}} if request.method == "GET" else response)

    result = await GroundedModel(spend, api_key="fixture", transport=httpx.MockTransport(send)).once(
        "Explain", [], "turn"
    )
    assert result["status"] == "invalid"
    assert (await spend.state())["reserved_units"] > 0


@pytest.mark.asyncio
async def test_paid_dispatch_requires_reservation_and_sends_actual_facts():
    spend = SpendLedger(AsyncMongoMockClient().test.budget)
    await spend.initialize()
    calls = []

    async def send(request):
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"endpoints": [ENDPOINT]}})
        state = await spend.state()
        assert state["reserved_units"] > 0
        body = json.loads(request.content)
        assert "123.45" in body["messages"][1]["content"]
        assert body["provider"]["require_parameters"]
        assert body["provider"]["allow_fallbacks"] is False
        return httpx.Response(
            200,
            json={
                "id": "gen-one",
                "usage": {"cost": 0.012345},
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "research_answer",
                                        "arguments": json.dumps(
                                            {
                                                "sections": [
                                                    {
                                                        "name": "Market",
                                                        "fact_ids": ["spot"],
                                                        "interpretation": "descriptive",
                                                    }
                                                ]
                                            }
                                        ),
                                    }
                                }
                            ],
                        }
                    }
                ],
            },
        )

    model = GroundedModel(spend, api_key="fixture", transport=httpx.MockTransport(send))
    result = await model.once("Explain", [{"id": "spot", "value": 123.45}], "turn")
    assert result["status"] == "ok"
    assert result["actual_cost"] == 0.012345
    assert (await spend.state())["spent_units"] == 12345
    assert (await spend.state())["reserved_units"] == 0
    assert calls == ["GET", "POST"]


@pytest.mark.asyncio
async def test_missing_usage_retains_reservation_and_records_generation():
    spend = SpendLedger(AsyncMongoMockClient().test.budget)
    await spend.initialize()

    def send(request):
        return httpx.Response(
            200,
            json={"data": {"endpoints": [ENDPOINT]}}
            if request.method == "GET"
            else {"id": "gen-unknown", "choices": []},
        )

    result = await GroundedModel(spend, api_key="fixture", transport=httpx.MockTransport(send)).once(
        "Explain", [], "turn"
    )
    assert result["status"] == "invalid"
    assert result["accounting"] == "reserved"
    doc = await spend.collection.find_one({"_id": "openrouter"})
    assert doc["requests"][result["reservation_id"]]["generation_id"] == "gen-unknown"
    assert (await spend.state())["reserved_units"] > 0
