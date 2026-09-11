"""Usable expiry coverage comes from accepted contracts, not request success."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from services import public_api_adapter as adapter
from tests.services.test_public_adapter_truth import make_broker, make_contract


async def fetch_mocked(chains):
    broker = make_broker(chains)
    with patch.object(adapter, "_resolve_spot_observation", AsyncMock(return_value={
        "price": 520.5, "source": "public-mid", "event_time": None,
        "fetched_at": datetime.now(UTC).isoformat(),
    })):
        return await adapter._fetch_chain_live(broker, "SPY", len(chains))


@pytest.mark.asyncio
async def test_successful_empty_expiry_is_not_available_coverage():
    today = datetime.now(UTC).date()
    empty = (today + timedelta(days=7)).isoformat()
    usable = (today + timedelta(days=14)).isoformat()
    result = await fetch_mocked({empty: [], usable: [make_contract(expiration=usable)]})
    assert result["expiries"] == [usable]
    assert {c["expiry"] for c in result["contracts"]} == {usable}


@pytest.mark.asyncio
async def test_all_rejected_expiry_does_not_leak_into_available_coverage():
    today = datetime.now(UTC).date()
    rejected = (today + timedelta(days=7)).isoformat()
    usable = (today + timedelta(days=14)).isoformat()
    result = await fetch_mocked({
        rejected: [make_contract(expiration=(today - timedelta(days=1)).isoformat()),
                   make_contract(expiration=rejected, strike=float("nan")),
                   make_contract(expiration="invalid")],
        usable: [make_contract(expiration=usable)],
    })
    assert result["expiries"] == [usable]
    assert len(result["contracts"]) == 1


@pytest.mark.asyncio
async def test_mixed_response_uses_actual_accepted_expiry_and_keeps_zero_dte():
    today = datetime.now(UTC).date()
    requested = (today + timedelta(days=7)).isoformat()
    actual = (today + timedelta(days=14)).isoformat()
    result = await fetch_mocked({requested: [
        make_contract(expiration=actual), make_contract(expiration=actual, strike=531),
        make_contract(expiration=today.isoformat()), make_contract(expiration="bad"),
    ]})
    assert result["expiries"] == [actual, today.isoformat()]
    assert {c["expiry"] for c in result["contracts"]} == set(result["expiries"])
    assert len(result["contracts"]) == 3


@pytest.mark.asyncio
async def test_no_accepted_contracts_remains_unavailable():
    result = await fetch_mocked({"bad": [], "also-bad": [make_contract(expiration="invalid")]})
    assert result is None
