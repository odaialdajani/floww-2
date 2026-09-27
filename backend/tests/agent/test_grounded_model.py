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
@pytest.mark.parametrize("model_id,allowed", [("openai/gpt-4.1-mini", True), ("anthropic/claude-sonnet-4", False)])
async def test_only_nonreasoning_model_omits_unsupported_reasoning_control(model_id, allowed):
    spend = SpendLedger(AsyncMongoMockClient().test.budget)
    await spend.initialize()
    endpoint = {**ENDPOINT, "tag": "openai", "supported_parameters": ["tools", "tool_choice", "max_tokens"]}
    calls = []

    def send(request):
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"endpoints": [endpoint]}})
        payload = json.loads(request.content)
        assert "reasoning" not in payload
        assert payload["provider"]["only"] == ["openai"]
        assert payload["provider"]["require_parameters"] is True
        return httpx.Response(
            200,
            json={
                "id": "nonreasoning-test",
                "usage": {"cost": 0.002},
                "choices": [
                    {
                        "message": {
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
                            ]
                        }
                    }
                ],
            },
        )

    result = await GroundedModel(spend, model=model_id, api_key="fixture", transport=httpx.MockTransport(send)).once(
        "Explain", [{"id": "spot", "value": 100}], "turn"
    )
    assert result["status"] == ("ok" if allowed else "unavailable")
    assert calls == (["GET", "POST"] if allowed else ["GET"])
    assert (await spend.state())["spent_units"] == (2000 if allowed else 0)


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


@pytest.mark.asyncio
@pytest.mark.parametrize("over_limit", [False, True])
async def test_final_provider_body_is_bounded_before_reservation(over_limit):
    from decimal import Decimal
    from unittest.mock import AsyncMock

    from services.agent.contracts import canonical
    from services.agent.model import INPUT_CEILING, MAX_BODY_BYTES, MAX_OUTPUT, OUTPUT_CEILING
    from services.agent.spend import money_units

    sent = []
    spend = SpendLedger(AsyncMongoMockClient().test.budget)
    await spend.initialize()

    def send(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"endpoints": [ENDPOINT]}})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "sizing-only", "choices": []})

    model = GroundedModel(spend, api_key="fixture", transport=httpx.MockTransport(send))
    await model.once("", [], "measure")
    final_base = len(canonical(sent[0]).encode("utf-8"))
    spend.reserve = AsyncMock(return_value=False)
    result = await model.once("x" * (MAX_BODY_BYTES - final_base + int(over_limit)), [], "boundary")
    assert len(sent) == 1
    if over_limit:
        assert result["status"] == "unavailable"
        assert result["reason"] == "Evidence exceeds the bounded model input"
        spend.reserve.assert_not_awaited()
    else:
        assert result["status"] == "cost_limited"
        spend.reserve.assert_awaited_once()
        expected = money_units(Decimal(MAX_BODY_BYTES + 8192) * INPUT_CEILING + Decimal(MAX_OUTPUT) * OUTPUT_CEILING)
        assert spend.reserve.await_args.args[1] == expected


@pytest.mark.asyncio
async def test_selected_provider_context_must_fit_final_body():
    from unittest.mock import AsyncMock

    from services.agent.contracts import canonical
    from services.agent.model import MAX_OUTPUT

    sent = []
    endpoint = dict(ENDPOINT)
    spend = SpendLedger(AsyncMongoMockClient().test.budget)
    await spend.initialize()

    def send(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"endpoints": [endpoint]}})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "sizing-only", "choices": []})

    model = GroundedModel(spend, api_key="fixture", transport=httpx.MockTransport(send))
    await model.once("", [], "measure")
    body = sent[0]
    del body["provider"]["only"]
    endpoint["context_length"] = len(canonical(body).encode("utf-8")) + 8192 + MAX_OUTPUT
    spend.reserve = AsyncMock(return_value=False)
    result = await model.once("", [], "final-context")
    assert result["status"] == "unavailable"
    spend.reserve.assert_not_awaited()
    assert len(sent) == 1
