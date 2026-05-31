"""
backend/services/order_router.py

Paper-trade order client wrapping Schwab Trader API v1.
Order types: LIMIT (default), STOP, STOP_LIMIT, MARKET (behind flag).
Idempotency via client_order_id = sha256(signal_id:timestamp_us)[:16].
Position tracking: in-memory + Mongo persistence every 10s.

References:
- Almgren, R. & Chriss, N. (2001). "Optimal Execution of Portfolio Transactions."
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from schwab import SchwabTokenManager

logger = logging.getLogger(__name__)

SCHWAB_ORDERS_URL = "https://api.schwabapi.com/trader/v1/accounts/{account_id}/orders"
ALLOW_MARKET_ORDERS = False  # safety flag
POSITION_PERSIST_INTERVAL_S = 10


class PositionTracker:
    """In-memory position tracker with Mongo persistence."""

    def __init__(self):
        self._positions: Dict[str, int] = {}  # ticker -> qty
        self._last_persist = 0.0

    def update(self, ticker: str, qty: int):
        self._positions[ticker] = qty

    def get(self, ticker: str) -> int:
        return self._positions.get(ticker, 0)

    def snapshot(self) -> Dict[str, int]:
        return dict(self._positions)

    async def persist(self, db):
        """Persist positions to Mongo."""
        now = time.time()
        if now - self._last_persist < POSITION_PERSIST_INTERVAL_S:
            return
        self._last_persist = now
        try:
            for ticker, qty in self._positions.items():
                await db.positions.update_one(
                    {"ticker": ticker},
                    {"$set": {"ticker": ticker, "qty": qty, "updated_at": datetime.now(timezone.utc)}},
                    upsert=True,
                )
        except Exception as e:
            logger.warning(f"Position persist failed: {e}")

    async def hydrate(self, db):
        """Load positions from Mongo on startup."""
        try:
            cursor = db.positions.find({})
            async for doc in cursor:
                self._positions[doc["ticker"]] = doc.get("qty", 0)
            logger.info(f"Hydrated {len(self._positions)} positions from Mongo")
        except Exception as e:
            logger.warning(f"Position hydrate failed: {e}")


class OrderRouter:
    """Routes orders to Schwab Trader API with idempotency and tracking."""

    def __init__(self, account_id: str, token_manager: Optional[SchwabTokenManager] = None):
        self.account_id = account_id
        self.tokens = token_manager or SchwabTokenManager()
        self.position_tracker = PositionTracker()
        self._fill_handlers: List = []
        self._order_cache: Dict[str, Any] = {}  # client_order_id -> order response

    def on_fill(self, handler):
        """Register a fill handler."""
        self._fill_handlers.append(handler)

    def _make_client_order_id(self, signal_id: str, timestamp_us: int) -> str:
        """Generate idempotent client order ID."""
        return hashlib.sha256(f"{signal_id}:{timestamp_us}".encode()).hexdigest()[:16]

    def _build_order_payload(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Build Schwab API order payload from TradeIntent."""
        order_type = intent.get("order_type", "limit").upper()

        # Safety: reject MARKET orders by default
        if order_type == "MARKET" and not ALLOW_MARKET_ORDERS:
            raise ValueError("MARKET orders disabled. Set ALLOW_MARKET_ORDERS=1 to enable.")

        side = intent.get("side", "buy").upper()
        qty = intent.get("qty", 1)
        signal_id = intent.get("signal_id", "")
        timestamp_us = intent.get("timestamp_us", int(time.time() * 1e6))
        client_order_id = self._make_client_order_id(signal_id, timestamp_us)

        payload = {
            "clientOrderId": client_order_id,
            "orderType": order_type,
            "session": "NORMAL",
            "price": intent.get("limit_price", 0.0),
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instrument": {
                        "symbol": intent.get("ticker", ""),
                        "assetType": "OPTION",
                    },
                    "instruction": "BUY_TO_OPEN" if side == "BUY" else "SELL_TO_OPEN",
                    "quantity": qty,
                }
            ],
        }

        # Add stop/stop-limit
        if order_type in ("STOP", "STOP_LIMIT"):
            payload["stopPrice"] = intent.get("stop_loss", 0.0)

        return payload

    async def submit_order(self, intent: Dict[str, Any], db=None) -> Dict[str, Any]:
        """Submit an order to Schwab with idempotency check."""
        signal_id = intent.get("signal_id", "")
        timestamp_us = intent.get("timestamp_us", int(time.time() * 1e6))
        client_order_id = self._make_client_order_id(signal_id, timestamp_us)

        # Idempotency check
        if client_order_id in self._order_cache:
            logger.info(f"Duplicate order suppressed: {client_order_id}")
            return self._order_cache[client_order_id]

        payload = self._build_order_payload(intent)
        url = SCHWAB_ORDERS_URL.format(account_id=self.account_id)

        try:
            access_token = self.tokens.get_access_token()
            if not access_token or self.tokens.is_expired():
                access_token = await self.tokens.refresh_token()
            if not access_token:
                return {"status": "error", "reason": "no_access_token"}

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30.0,
                )

                if resp.status_code == 409:
                    # Duplicate order
                    logger.info(f"Schwab duplicate order: {client_order_id}")
                    return {"status": "duplicate", "client_order_id": client_order_id}

                resp.raise_for_status()
                result = {"status": "submitted", "client_order_id": client_order_id}
                self._order_cache[client_order_id] = result

                # Update position tracker
                ticker = intent.get("ticker", "")
                qty = intent.get("qty", 0)
                side = intent.get("side", "buy")
                current = self.position_tracker.get(ticker)
                delta = qty if side == "buy" else -qty
                self.position_tracker.update(ticker, current + delta)

                # Persist
                if db:
                    await self.position_tracker.persist(db)

                return result

        except ValueError as e:
            return {"status": "rejected", "reason": str(e)}
        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            return {"status": "error", "reason": str(e)}

    async def get_positions_from_schwab(self) -> Dict[str, int]:
        """Fetch positions from Schwab API."""
        try:
            access_token = self.tokens.get_access_token()
            if not access_token or self.tokens.is_expired():
                access_token = await self.tokens.refresh_token()
            if not access_token:
                return {}
            url = f"https://api.schwabapi.com/trader/v1/accounts/{self.account_id}"
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"fields": "positions"},
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                positions = {}
                for pos in data.get("securitiesAccount", {}).get("positions", []):
                    symbol = pos.get("instrument", {}).get("symbol", "")
                    qty = pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)
                    if symbol and qty != 0:
                        positions[symbol] = qty
                return positions
        except Exception as e:
            logger.error(f"Failed to fetch Schwab positions: {e}")
            return {}

    def get_state(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "positions": self.position_tracker.snapshot(),
            "cached_orders": len(self._order_cache),
            "allow_market": ALLOW_MARKET_ORDERS,
        }
