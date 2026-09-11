from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolated_public_budget_singleton():
    # D1: the adapter debits the shared budget singleton per C8, so each
    # test starts from a full bucket; otherwise module order decides
    # who exhausts whom.
    from services.public_budget import budget

    budget.reset()
    yield
    budget.reset()


@pytest.mark.asyncio
async def test_partial_expiry_failure_keeps_successful_contracts() -> None:
    from services.public_api_adapter import fetch_chain_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_option_expirations = AsyncMock(
        return_value=["2026-09-18", "2026-10-16"]
    )
    broker.get_quotes = AsyncMock(return_value=[MagicMock(mid_price=500.0)])

    contract = MagicMock(expiration="2026-09-18", strike=500.0)
    contract.open_interest = 100
    contract.iv = 0.2
    contract.delta = 0.5
    contract.gamma = contract.theta = contract.vega = None
    contract.bid = contract.ask = contract.last = None
    contract.volume = 0
    broker.get_option_chain_parsed = AsyncMock(
        side_effect=[{"calls": [contract], "puts": []}, RuntimeError("failed")]
    )

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_chain_from_public_api("SPY")

    assert result is not None
    # D4: returned coverage lists only fetched expiries (failed expiry excluded)
    assert result["expiries"] == ["2026-09-18"]
    assert len(result["contracts"]) == 1


@pytest.mark.asyncio
async def test_malformed_contract_is_skipped_without_losing_valid_data() -> None:
    from services.public_api_adapter import fetch_chain_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_option_expirations = AsyncMock(return_value=["2026-09-18"])
    broker.get_quotes = AsyncMock(return_value=[MagicMock(mid_price=500.0)])

    malformed = MagicMock(expiration="not-a-date")
    valid = MagicMock(expiration="2026-09-18", strike=500.0)
    valid.open_interest = 1
    valid.iv = 0.2
    valid.delta = valid.gamma = valid.theta = valid.vega = None
    valid.bid = valid.ask = valid.last = None
    valid.volume = 0
    broker.get_option_chain_parsed = AsyncMock(
        return_value={"calls": [malformed, valid], "puts": []}
    )

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_chain_from_public_api("SPY")

    assert result is not None
    assert len(result["contracts"]) == 1
    assert result["contracts"][0]["expiry"] == "2026-09-18"
