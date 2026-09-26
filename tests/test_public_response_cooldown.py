import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from services import public_budget, public_request_pacer
from services.public_api import PublicBroker
from services.public_api_adapter import _note_public_429

class ResponseCooldownTests(unittest.IsolatedAsyncioTestCase):
    async def test_broker_response_cools_once_and_preserves_existing_hooks(self):
        budget = public_budget.PublicBudget()
        existing = AsyncMock()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "120"})), event_hooks={"response": [existing]}) as client:
            broker = PublicBroker("fake", client=client)
            broker._access_token = "fake"
            broker._token_expires_at = time.time() + 60
            with patch.object(public_budget, "budget", budget):
                try:
                    await broker.get_all_instruments(type_filter=["EQUITY"])
                except httpx.HTTPStatusError as exc:
                    error = exc
                self.assertEqual(budget.total_429, 1)
                existing.assert_awaited_once()
                _note_public_429(error)
                self.assertEqual(budget.total_429, 1)
                with self.assertRaises(public_budget.BudgetExhausted):
                    await public_request_pacer.pace_request(httpx.Request("GET", "https://api.public.com/unrelated"))

    async def test_inflight_shorter_response_cannot_shorten_cooldown(self):
        budget = public_budget.PublicBudget()
        budget.record_429("api.public.com", now=100, retry_after=300)
        budget.record_429("api.public.com", now=101, retry_after=3)
        self.assertEqual(budget._cooldowns["api.public.com"], 400)

if __name__ == "__main__":
    unittest.main()
