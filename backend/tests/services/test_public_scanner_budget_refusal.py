"""Scanner can observe admission refusals without changing legacy fetch behavior."""
from unittest.mock import AsyncMock

import pytest

from services import public_api_adapter as adapter
from services.public_budget import BudgetExhausted
from tests.offline_network import deny_external_network  # noqa: F401


@pytest.mark.asyncio
async def test_optional_scanner_budget_refusal_preserves_default_and_spends_no_calls(monkeypatch):
    monkeypatch.setattr(adapter, "BROKER", None)
    reject = AsyncMock(side_effect=BudgetExhausted(reason="token_bucket"))
    broker = AsyncMock(side_effect=AssertionError("admission precedes provider initialization"))
    monkeypatch.setattr(adapter._public_budget.budget, "acquire_n", reject)
    monkeypatch.setattr(adapter, "_get_broker", broker)
    assert await adapter.fetch_chain_from_public_api("SCANNERTEST") is None
    with pytest.raises(BudgetExhausted) as error:
        await adapter.fetch_chain_from_public_api("SCANNERTEST", raise_budget_exhausted=True)
    assert error.value.reason == "token_bucket"
    broker.assert_not_called()
