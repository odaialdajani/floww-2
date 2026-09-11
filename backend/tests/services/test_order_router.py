"""
backend/tests/services/test_order_router.py

Unit tests for order_router.py — Alpaca PAPER order client.
Paper by construction (paper-api.alpaca.markets is hardcoded); no live
gate, no token manager. Broker is injectable for tests.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _mock_broker(**over):
    broker = MagicMock()
    broker.place_stock_order = AsyncMock(return_value={"id": "ord-1", "status": "accepted"})
    broker.get_order_by_client_order_id = AsyncMock(return_value=None)
    broker.get_positions = AsyncMock(return_value=[])
    for k, v in over.items():
        setattr(broker, k, v)
    return broker


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

    def test_client_order_id_stable_across_retry_timestamps(self):
        """One logical signal keeps one venue id across process retries."""
        from services.order_router import OrderRouter
        router = OrderRouter.__new__(OrderRouter)
        router.account_id = "test"
        first = router._make_client_order_id("sig-abc", 1000000)
        retry = router._make_client_order_id("sig-abc", 9000000)
        assert first == retry

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
        assert payload["type"] == "limit"
        assert payload["limit_price"] == "450.0"
        assert payload["qty"] == "1"
        assert payload["symbol"] == "SPY"
        assert payload["time_in_force"] == "day"
        assert len(payload["client_order_id"]) == 16

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
        assert payload["type"] == "stop"
        assert payload["stop_price"] == "440.0"

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
        assert payload["type"] == "stop_limit"
        assert payload["stop_price"] == "440.0"
        assert payload["limit_price"] == "450.0"

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
        from services.order_router import ALLOW_MARKET_ORDERS, VENUE, OrderRouter
        router = OrderRouter("acc-123", broker=_mock_broker())
        state = router.get_state()
        assert state["account_id"] == "acc-123"
        assert state["venue"] == VENUE == "alpaca-paper"
        assert state["positions"] == {}
        assert state["cached_orders"] == 0
        assert state["allow_market"] == ALLOW_MARKET_ORDERS

    def test_on_fill_handler(self):
        from services.order_router import OrderRouter
        router = OrderRouter("acc-123", broker=_mock_broker())
        handler = MagicMock()
        router.on_fill(handler)
        assert handler in router._fill_handlers

    @pytest.mark.asyncio
    async def test_submit_order_idempotency(self):
        from services.order_router import OrderRouter
        router = OrderRouter("acc-123", broker=_mock_broker())
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
    async def test_submit_order_calls_alpaca_paper(self):
        from services.order_router import OrderRouter
        broker = _mock_broker()
        router = OrderRouter("acc-123", broker=broker)
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 5,
            "order_type": "limit",
            "limit_price": 450.0,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        result = await router.submit_order(intent)
        assert result["status"] == "submitted"
        assert result["venue"] == "alpaca-paper"
        broker.place_stock_order.assert_awaited_once()
        call = broker.place_stock_order.call_args
        assert call.args[0] == "SPY" and call.args[1] == 5
        assert router.position_tracker.get("SPY") == 5

    @pytest.mark.asyncio
    async def test_anonymous_submission_uses_one_client_order_id(self):
        """Cache, lookup, response, and venue payload share one generated ID."""
        from services.order_router import OrderRouter

        broker = _mock_broker()
        router = OrderRouter("acc-123", broker=broker)
        with patch("services.order_router.time.time", side_effect=[1.0, 2.0]):
            result = await router.submit_order({
                "ticker": "SPY", "side": "buy", "qty": 1,
            })

        transmitted = broker.place_stock_order.call_args.kwargs["client_order_id"]
        assert result["client_order_id"] == transmitted
        broker.get_order_by_client_order_id.assert_awaited_once_with(transmitted)

    @pytest.mark.asyncio
    async def test_restart_retry_recovers_existing_venue_order(self):
        """A fresh router finds the first order instead of posting a duplicate."""
        from services.order_router import OrderRouter
        broker = _mock_broker()
        broker.get_order_by_client_order_id = AsyncMock(return_value={
            "id": "ord-existing", "status": "accepted",
            "client_order_id": "venue-cid",
        })
        router = OrderRouter("acc-123", broker=broker)
        with patch.object(router, "_make_client_order_id",
                          return_value="venue-cid"):
            result = await router.submit_order({
                "ticker": "SPY", "side": "buy", "qty": 1,
                "signal_id": "sig-retry", "timestamp_us": 9000000,
            })
        assert result["status"] == "submitted"
        assert result["recovered"] is True
        broker.place_stock_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ambiguous_submit_recovers_by_client_order_id(self):
        """A lost POST response is resolved by the stable venue key."""
        from services.order_router import OrderRouter
        broker = _mock_broker()
        broker.place_stock_order = AsyncMock(return_value=None)
        broker.get_order_by_client_order_id = AsyncMock(side_effect=[
            None,
            {"id": "ord-existing", "status": "accepted",
             "client_order_id": "venue-cid"},
        ])
        router = OrderRouter("acc-123", broker=broker)
        with patch.object(router, "_make_client_order_id",
                          return_value="venue-cid"):
            result = await router.submit_order({
                "ticker": "SPY", "side": "buy", "qty": 1,
                "signal_id": "sig-lost-response", "timestamp_us": 1000000,
            })
        assert result["status"] == "submitted"
        assert result["recovered"] is True
        broker.place_stock_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_order_broker_failure_is_error(self):
        from services.order_router import OrderRouter
        broker = _mock_broker()
        broker.place_stock_order = AsyncMock(return_value=None)
        router = OrderRouter("acc-123", broker=broker)
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 1,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }
        result = await router.submit_order(intent)
        assert result["status"] == "error"
        assert result["reason"] == "alpaca_empty_response"

    @pytest.mark.asyncio
    async def test_sell_reduces_position(self):
        from services.order_router import OrderRouter
        router = OrderRouter("acc-123", broker=_mock_broker())
        router.position_tracker.update("SPY", 10)
        intent = {
            "ticker": "SPY",
            "side": "sell",
            "qty": 3,
            "signal_id": "sig-2",
            "timestamp_us": 2000000,
        }
        with patch.object(router, "_make_client_order_id", return_value="sell-cid"):
            result = await router.submit_order(intent)
        assert result["status"] == "submitted"
        assert router.position_tracker.get("SPY") == 7

    @pytest.mark.asyncio
    async def test_get_positions_from_alpaca(self):
        from services.order_router import OrderRouter
        broker = _mock_broker()
        broker.get_positions = AsyncMock(return_value=[
            {"symbol": "SPY", "qty": "100"},
            {"symbol": "QQQ", "qty": "-50"},
            {"symbol": "BAD", "qty": "n/a"},
        ])
        router = OrderRouter("acc-123", broker=broker)
        positions = await router.get_positions_from_alpaca()
        assert positions["SPY"] == 100
        assert positions["QQQ"] == -50
        assert "BAD" not in positions

    @pytest.mark.asyncio
    async def test_get_positions_handles_error(self):
        from services.order_router import OrderRouter
        broker = _mock_broker()
        broker.get_positions = AsyncMock(side_effect=Exception("down"))
        router = OrderRouter("acc-123", broker=broker)
        assert await router.get_positions_from_alpaca() == {}
