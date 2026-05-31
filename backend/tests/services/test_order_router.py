"""
backend/tests/services/test_order_router.py

Unit tests for order_router.py — paper-trade order client.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class TestPositionTracker:
    def test_update_and_get(self):
        from services.order_router import PositionTracker
        pt = PositionTracker()
        pt.update("SPY", 100)
        assert pt.get("SPY") == 100

    def test_get_missing(self):
        from services.order_router import PositionTracker
        pt = PositionTracker()
        assert pt.get("SPY") == 0

    def test_snapshot(self):
        from services.order_router import PositionTracker
        pt = PositionTracker()
        pt.update("SPY", 100)
        pt.update("QQQ", 50)
        snap = pt.snapshot()
        assert snap == {"SPY": 100, "QQQ": 50}

    def test_snapshot_is_copy(self):
        from services.order_router import PositionTracker
        pt = PositionTracker()
        pt.update("SPY", 100)
        snap = pt.snapshot()
        snap["SPY"] = 999
        assert pt.get("SPY") == 100

    @pytest.mark.asyncio
    async def test_persist_throttle(self):
        from services.order_router import PositionTracker
        pt = PositionTracker()
        pt.update("SPY", 100)
        db = AsyncMock()
        await pt.persist(db)
        assert db.positions.update_one.call_count == 1
        await pt.persist(db)
        assert db.positions.update_one.call_count == 1

    @pytest.mark.asyncio
    async def test_persist_multiple_tickers(self):
        from services.order_router import PositionTracker
        pt = PositionTracker()
        pt.update("SPY", 100)
        pt.update("QQQ", 50)
        db = AsyncMock()
        await pt.persist(db)
        assert db.positions.update_one.call_count == 2

    @pytest.mark.asyncio
    async def test_hydrate(self):
        from services.order_router import PositionTracker
        pt = PositionTracker()
        docs = [
            {"ticker": "SPY", "qty": 100},
            {"ticker": "QQQ", "qty": 50},
        ]
        class MockCursor:
            def __init__(self, docs):
                self._docs = docs
            def __aiter__(self):
                self._idx = 0
                return self
            async def __anext__(self):
                if self._idx >= len(self._docs):
                    raise StopAsyncIteration
                doc = self._docs[self._idx]
                self._idx += 1
                return doc
        mock_cursor = MockCursor(docs)
        mock_db = MagicMock()
        mock_db.positions.find = MagicMock(return_value=mock_cursor)
        await pt.hydrate(mock_db)
        assert pt.get("SPY") == 100
        assert pt.get("QQQ") == 50

    @pytest.mark.asyncio
    async def test_persist_handles_exception(self):
        from services.order_router import PositionTracker
        pt = PositionTracker()
        pt.update("SPY", 100)
        db = AsyncMock()
        db.positions.update_one.side_effect = Exception("Mongo down")
        await pt.persist(db)


class TestOrderRouter:
    def test_client_order_id_deterministic(self):
        from services.order_router import OrderRouter
        router = OrderRouter.__new__(OrderRouter)
        router.account_id = "test"
        id1 = router._make_client_order_id("sig-abc", 1000000)
        id2 = router._make_client_order_id("sig-abc", 1000000)
        assert id1 == id2
        assert len(id1) == 16

    def test_client_order_id_unique_per_signal(self):
        from services.order_router import OrderRouter
        router = OrderRouter.__new__(OrderRouter)
        router.account_id = "test"
        id1 = router._make_client_order_id("sig-abc", 1000000)
        id2 = router._make_client_order_id("sig-xyz", 1000000)
        assert id1 != id2

    def test_build_limit_payload(self):
        from services.order_router import OrderRouter
        router = OrderRouter.__new__(OrderRouter)
        router.account_id = "test"
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 1,
            "order_type": "limit",
            "limit_price": 450.0,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        payload = router._build_order_payload(intent)
        assert payload["orderType"] == "LIMIT"
        assert payload["price"] == 450.0
        assert payload["orderLegCollection"][0]["quantity"] == 1

    def test_build_stop_payload(self):
        from services.order_router import OrderRouter
        router = OrderRouter.__new__(OrderRouter)
        router.account_id = "test"
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 1,
            "order_type": "stop",
            "limit_price": 450.0,
            "stop_loss": 440.0,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        payload = router._build_order_payload(intent)
        assert payload["orderType"] == "STOP"
        assert "stopPrice" in payload

    def test_build_stop_limit_payload(self):
        from services.order_router import OrderRouter
        router = OrderRouter.__new__(OrderRouter)
        router.account_id = "test"
        intent = {
            "ticker": "SPY",
            "side": "sell",
            "qty": 2,
            "order_type": "stop_limit",
            "limit_price": 450.0,
            "stop_loss": 440.0,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        payload = router._build_order_payload(intent)
        assert payload["orderType"] == "STOP_LIMIT"
        assert "stopPrice" in payload

    def test_market_order_rejected_by_default(self):
        from services.order_router import OrderRouter
        router = OrderRouter.__new__(OrderRouter)
        router.account_id = "test"
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 1,
            "order_type": "market",
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        with pytest.raises(ValueError, match="MARKET orders disabled"):
            router._build_order_payload(intent)

    def test_get_state(self):
        from services.order_router import ALLOW_MARKET_ORDERS, OrderRouter
        mock_tokens = MagicMock()
        router = OrderRouter("acc-123", token_manager=mock_tokens)
        state = router.get_state()
        assert state["account_id"] == "acc-123"
        assert state["positions"] == {}
        assert state["cached_orders"] == 0
        assert state["allow_market"] == ALLOW_MARKET_ORDERS

    def test_on_fill_handler(self):
        from services.order_router import OrderRouter
        mock_tokens = MagicMock()
        router = OrderRouter("acc-123", token_manager=mock_tokens)
        handler = MagicMock()
        router.on_fill(handler)
        assert handler in router._fill_handlers

    @pytest.mark.asyncio
    async def test_submit_order_idempotency(self):
        from services.order_router import OrderRouter
        mock_tokens = MagicMock()
        mock_tokens.get_access_token.return_value = "fake-token"
        mock_tokens.is_expired.return_value = False
        router = OrderRouter("acc-123", token_manager=mock_tokens)
        router._order_cache["test-cid"] = {"status": "submitted", "client_order_id": "test-cid"}
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 1,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        with patch.object(router, "_make_client_order_id", return_value="test-cid"):
            result = await router.submit_order(intent)
        assert result["status"] == "submitted"
        assert result["client_order_id"] == "test-cid"

    @pytest.mark.asyncio
    async def test_submit_order_no_token(self):
        from services.order_router import OrderRouter
        mock_tokens = MagicMock()
        mock_tokens.get_access_token.return_value = None
        mock_tokens.is_expired.return_value = True
        mock_tokens.refresh_token = AsyncMock(return_value=None)
        router = OrderRouter("acc-123", token_manager=mock_tokens)
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 1,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        result = await router.submit_order(intent)
        assert result["status"] == "error"
        assert result["reason"] == "no_access_token"

    @pytest.mark.asyncio
    async def test_submit_order_updates_positions(self):
        from services.order_router import OrderRouter
        mock_tokens = MagicMock()
        mock_tokens.get_access_token.return_value = "fake-token"
        mock_tokens.is_expired.return_value = False
        router = OrderRouter("acc-123", token_manager=mock_tokens)
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 5,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        with patch.object(router, "_make_client_order_id", return_value="new-cid"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = {}
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                result = await router.submit_order(intent)
        assert result["status"] == "submitted"
        assert router.position_tracker.get("SPY") == 5

    @pytest.mark.asyncio
    async def test_sell_reduces_position(self):
        from services.order_router import OrderRouter
        mock_tokens = MagicMock()
        mock_tokens.get_access_token.return_value = "fake-token"
        mock_tokens.is_expired.return_value = False
        router = OrderRouter("acc-123", token_manager=mock_tokens)
        router.position_tracker.update("SPY", 10)
        intent = {
            "ticker": "SPY",
            "side": "sell",
            "qty": 3,
            "signal_id": "sig-2",
            "timestamp_us": 2000000,
        }
        with patch.object(router, "_make_client_order_id", return_value="sell-cid"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = {}
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                result = await router.submit_order(intent)
        assert result["status"] == "submitted"
        assert router.position_tracker.get("SPY") == 7

    @pytest.mark.asyncio
    async def test_get_positions_from_schwab(self):
        from services.order_router import OrderRouter
        mock_tokens = MagicMock()
        mock_tokens.get_access_token.return_value = "fake-token"
        mock_tokens.is_expired.return_value = False
        router = OrderRouter("acc-123", token_manager=mock_tokens)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "securitiesAccount": {
                    "positions": [
                        {"instrument": {"symbol": "SPY"}, "longQuantity": 100, "shortQuantity": 0},
                        {"instrument": {"symbol": "QQQ"}, "longQuantity": 0, "shortQuantity": 50},
                    ]
                }
            }
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            positions = await router.get_positions_from_schwab()
        assert positions["SPY"] == 100
        assert positions["QQQ"] == -50

    @pytest.mark.asyncio
    async def test_get_positions_handles_error(self):
        from services.order_router import OrderRouter
        mock_tokens = MagicMock()
        mock_tokens.get_access_token.return_value = None
        mock_tokens.is_expired.return_value = True
        mock_tokens.refresh_token = AsyncMock(return_value=None)
        router = OrderRouter("acc-123", token_manager=mock_tokens)
        positions = await router.get_positions_from_schwab()
        assert positions == {}
