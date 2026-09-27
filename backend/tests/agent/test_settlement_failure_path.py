"""A failed settlement must not fail the request or claim the cost was billed.

`backend/services/agent/model.py` swallows an exception from
`self.spend.settle(...)`. That is deliberate -- the cost stays reserved and
`reconcile()` looks it up later -- but nothing pinned it, so the swallow could
have become "report settled anyway" and no test would have noticed.

These tests pin the observable split:

  settle succeeds -> accounting="settled",  actual_cost is the real figure
  settle raises   -> accounting="reserved", actual_cost is None, cost still held

The second case is the one that matters. If actual_cost were reported on a
failed settlement, the ledger would be told the generation was billed while the
reservation was never consumed.
"""

import json

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.model import GroundedModel
from services.agent.spend import SpendLedger

ALLOWED_MODEL = "openai/gpt-4.1-mini"

ENDPOINT = {
    "tag": "openai",
    "supported_parameters": ["tools", "tool_choice", "max_tokens"],
    "supports_tool_choice": {"required": True},
    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
    "context_length": 200000,
    "max_completion_tokens": 64000,
}


def _ok_with_usage(cost: float):
    """Transport: endpoint list on GET, a valid tool-call reply on POST."""

    def send(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"endpoints": [ENDPOINT]}})
        return httpx.Response(
            200,
            json={
                "id": "gen-fixture",
                "usage": {"cost": cost},
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

    return httpx.MockTransport(send)


FACTS = [{"id": "spot", "value": 100}]


@pytest.mark.asyncio
async def test_successful_settlement_reports_settled_and_actual_cost():
    spend = SpendLedger(AsyncMongoMockClient().test.budget)
    await spend.initialize()

    result = await GroundedModel(
        spend, model=ALLOWED_MODEL, api_key="fixture", transport=_ok_with_usage(0.002)
    ).once("Explain", FACTS, "turn")

    assert result["status"] == "ok"
    assert result["accounting"] == "settled"
    assert result["actual_cost"] == pytest.approx(0.002)
    assert (await spend.state())["spent_units"] > 0


@pytest.mark.asyncio
async def test_failed_settlement_reports_reserved_and_never_claims_billed():
    """The regression guard for the silent except at model.py:214.

    settle() raising must leave the generation unsettled. The result must not
    carry an actual_cost, because reporting one tells the caller the request
    was billed when the reservation was never consumed.
    """
    spend = SpendLedger(AsyncMongoMockClient().test.budget)
    await spend.initialize()

    async def exploding_settle(*args, **kwargs):
        raise RuntimeError("settlement backend unavailable")

    # Patch the instance method the production code calls.
    original = spend.settle
    spend.settle = exploding_settle
    try:
        result = await GroundedModel(
            spend, model=ALLOWED_MODEL, api_key="fixture", transport=_ok_with_usage(0.002)
        ).once("Explain", FACTS, "turn")
    finally:
        spend.settle = original

    # The request itself still succeeded -- a billing failure is not a
    # generation failure, and must not be reported as one.
    assert result["status"] == "ok"
    assert result["accounting"] == "reserved"
    assert result["actual_cost"] is None, (
        "a failed settlement reported an actual_cost, which claims the "
        "generation was billed"
    )

    state = await spend.state()
    assert int(state["reserved_units"]) > 0, "the reservation must still be held for reconcile()"
    assert int(state["spent_units"]) == 0, "nothing may be marked spent when settle() failed"
