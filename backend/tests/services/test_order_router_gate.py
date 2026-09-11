"""
backend/tests/services/test_order_router_gate.py

Transport-safety regression tests for backend/services/order_router.py.

Pinned properties (post-Schwab-deletion, 2026-09-06):
- submit_order must NEVER touch api.schwabapi.com (asserted by patching
  httpx at the transport layer and failing the test on any call).
- Orders go ONLY to the Alpaca paper venue (paper-api.alpaca.markets is a
  hardcoded constant in alpaca_client; asserted here).
- The MARKET-order guard fires INDEPENDENTLY of transport (ValueError wins
  before any broker call).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _limit_intent(**over) -> dict:
    intent = {
        "ticker": "SPY",
        "side": "buy",
        "qty": 1,
        "order_type": "limit",
        "limit_price": 450.0,
        "signal_id": "sig-gate-1",
        "timestamp_us": 1700000000,
    }
    intent.update(over)
    return intent


class TestPaperOnlyTransport:
    """Alpaca paper is the only venue; Schwab is gone."""

    @pytest.mark.asyncio
    async def test_no_schwab_url_anywhere_on_submit(self):
        from services.order_router import OrderRouter
        broker = MagicMock()
        broker.place_stock_order = AsyncMock(return_value={"id": "x", "status": "accepted"})
        router = OrderRouter("acc-gate-test", broker=broker)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.side_effect = AssertionError("no raw httpx allowed")
            result = await router.submit_order(_limit_intent())
        assert result["status"] == "submitted"
        assert result["venue"] == "alpaca-paper"

    def test_paper_base_url_hardcoded(self):
        import alpaca_client
        assert alpaca_client.ALPACA_BASE_URL == "https://paper-api.alpaca.markets"
        assert "paper" in alpaca_client.ALPACA_BASE_URL

    def test_market_guard_fires_before_broker(self):
        from services.order_router import OrderRouter
        broker = MagicMock()
        broker.place_stock_order = AsyncMock(
            side_effect=AssertionError("must not be called"))
        router = OrderRouter("acc-gate-test", broker=broker)
        with pytest.raises(ValueError, match="MARKET orders disabled"):
            router._build_order_payload(_limit_intent(order_type="market"))

    def test_no_schwab_imports_remain(self):
        import inspect

        import services.order_router as mod
        src = inspect.getsource(mod)
        assert "schwabapi.com" not in src
        assert "SchwabTokenManager" not in src
        assert "FLOWW_ENABLE_LIVE_SCHWAB" not in src
