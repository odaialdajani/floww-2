"""
backend/services/order_router.py

Paper-trade order client on Alpaca PAPER (paper-api.alpaca.markets, hardcoded).
Schwab was deleted 2026-09-06: no token manager, no OAuth, no live gate —
paper trading is safe by construction (the venue URL cannot place live orders).
Order types: LIMIT (default), STOP, STOP_LIMIT, MARKET (behind flag).
Idempotency via a stable client_order_id derived from the logical signal ID.
Position tracking: in-memory + Mongo persistence every 10s.

References:
- Almgren, R. & Chriss, N. (2001). "Optimal Execution of Portfolio Transactions."
"""
from __future__ import annotations

import hashlib
import inspect
import logging
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

VENUE = "alpaca-paper"
ALLOW_MARKET_ORDERS = False  # safety flag
POSITION_PERSIST_INTERVAL_S = 10


class PositionTracker:
    """In-memory position tracker with Mongo persistence."""

    def __init__(self):
        self._positions: dict[str, int] = {}  # ticker -> qty
        self._last_persist = 0.0

    def update(self, ticker: str, qty: int):
        self._positions[ticker] = qty

    def get(self, ticker: str) -> int:
        return self._positions.get(ticker, 0)

    def snapshot(self) -> dict[str, int]:
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
                    {"$set": {"ticker": ticker, "qty": qty, "updated_at": datetime.now(UTC)}},
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
    """Routes paper orders to Alpaca with idempotency and tracking."""

    def __init__(self, account_id: str = "paper", broker: Any | None = None):
        self.account_id = account_id
        self._broker = broker  # injectable (tests); lazy AlpacaClient otherwise
        self.position_tracker = PositionTracker()
        self._fill_handlers: list = []
        self._order_cache: dict[str, Any] = {}  # client_order_id -> order response

    def _broker_or_default(self):
        if self._broker is not None:
            return self._broker
        from alpaca_client import AlpacaClient

        self._broker = AlpacaClient()
        return self._broker

    def on_fill(self, handler):
        """Register a fill handler."""
        self._fill_handlers.append(handler)

    def _make_client_order_id(self, signal_id: str, timestamp_us: int) -> str:
        """Generate one stable venue ID per logical signal.

        A retry naturally has a different wall-clock timestamp, so timestamp
        cannot participate when the caller supplied a signal ID. Anonymous
        callers retain timestamp-based uniqueness for backward compatibility.
        """
        logical_key = signal_id or f"anonymous:{timestamp_us}"
        return hashlib.sha256(logical_key.encode()).hexdigest()[:16]

    def _build_order_payload(self, intent: dict[str, Any],
                               allow_market: bool = False) -> dict[str, Any]:
        """Build Alpaca paper order payload from TradeIntent.

        MARKET orders stay rejected by default (safety flag). Callers with
        an explicit user-tap intent (Discord !approve / !buy) opt in per
        call with allow_market=True — the default-deny gate test still pins
        the safe default.
        """
        order_type = intent.get("order_type", "limit").upper()

        # Safety: reject MARKET orders by default
        if order_type == "MARKET" and not (ALLOW_MARKET_ORDERS or allow_market):
            raise ValueError("MARKET orders disabled. Set ALLOW_MARKET_ORDERS=1 to enable.")

        side = intent.get("side", "buy").lower()
        qty = int(intent.get("qty", 1))
        signal_id = intent.get("signal_id", "")
        timestamp_us = intent.get("timestamp_us", int(time.time() * 1e6))
        client_order_id = self._make_client_order_id(signal_id, timestamp_us)

        payload: dict[str, Any] = {
            "client_order_id": client_order_id,
            "symbol": intent.get("ticker", "").upper(),
            "qty": str(qty),
            "side": side,
            "type": order_type.lower(),
            "time_in_force": "day",
        }
        if order_type == "LIMIT":
            payload["limit_price"] = str(intent.get("limit_price", 0.0))
        elif order_type in ("STOP", "STOP_LIMIT"):
            payload["stop_price"] = str(intent.get("stop_loss", 0.0))
            if order_type == "STOP_LIMIT":
                payload["limit_price"] = str(intent.get("limit_price", 0.0))

        return payload

    async def _find_venue_order(self, client_order_id: str) -> dict | None:
        """Recover a venue order without assuming every test broker supports it."""
        try:
            broker = self._broker_or_default()
            lookup = getattr(broker, "get_order_by_client_order_id", None)
            if not callable(lookup):
                return None
            pending = lookup(client_order_id)
            if not inspect.isawaitable(pending):
                return None
            result = await pending
            return result if isinstance(result, dict) else None
        except Exception as exc:
            logger.warning("Venue idempotency lookup failed: %s", exc)
            return None

    def _recovered_submission(
            self, client_order_id: str, order: dict[str, Any]) -> dict[str, Any]:
        """Normalize an already-created venue order into the router contract."""
        out = {
            "status": "submitted",
            "client_order_id": client_order_id,
            "venue": VENUE,
            "broker": order,
            "recovered": True,
        }
        self._order_cache[client_order_id] = out
        return out

    async def submit_order(self, intent: dict[str, Any], db=None,
                           allow_market: bool = False) -> dict[str, Any]:
        """Submit a paper order to Alpaca with idempotency check.

        allow_market=True is the explicit per-tap opt-in for Discord
        market orders (!approve/!buy). Default False preserves the
        default-deny safety posture.
        """
        try:
            payload = self._build_order_payload(intent, allow_market=allow_market)
        except ValueError as e:
            return {"status": "rejected", "reason": str(e)}

        # The payload is the single source of truth. In particular, anonymous
        # intents derive their key from time, so computing it twice could give
        # cache/lookup and venue submission different identifiers.
        client_order_id = str(payload["client_order_id"])

        # Idempotency check
        if client_order_id in self._order_cache:
            logger.info(f"Duplicate order suppressed: {client_order_id}")
            return self._order_cache[client_order_id]

        try:
            broker = self._broker_or_default()
            existing = await self._find_venue_order(client_order_id)
            if existing:
                logger.info("Recovered existing venue order: %s", client_order_id)
                return self._recovered_submission(client_order_id, existing)
            result = await broker.place_stock_order(
                payload["symbol"],
                int(payload["qty"]),
                side=payload["side"],
                order_type=payload["type"],
                limit_price=float(payload.get("limit_price") or 0),
                client_order_id=payload["client_order_id"],
            )
            if not result:
                existing = await self._find_venue_order(client_order_id)
                if existing:
                    logger.info(
                        "Recovered venue order after ambiguous submit: %s",
                        client_order_id,
                    )
                    return self._recovered_submission(client_order_id, existing)
                return {"status": "error", "reason": "alpaca_empty_response",
                        "client_order_id": client_order_id}
            out = {"status": "submitted", "client_order_id": client_order_id,
                   "venue": VENUE, "broker": result}
            self._order_cache[client_order_id] = out

            # Update position tracker
            ticker = intent.get("ticker", "")
            qty = int(intent.get("qty", 0))
            side = intent.get("side", "buy")
            current = self.position_tracker.get(ticker)
            delta = qty if side == "buy" else -qty
            self.position_tracker.update(ticker, current + delta)

            # Persist
            if db:
                await self.position_tracker.persist(db)

            return out

        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            reason = str(e).strip()
            if not reason or reason == str(type(e)):
                reason = type(e).__name__
            else:
                reason = f"{type(e).__name__}: {reason}"
            return {"status": "error", "reason": reason}

    async def fetch_venue_order(self, venue_order_id: str) -> dict | None:
        """Refetch one venue order by its Alpaca ID (fill reconciliation).

        Returns the order dict, or None when the broker lacks the read
        path or the fetch fails. Never raises into the trade path.
        """
        if not venue_order_id:
            return None
        try:
            broker = self._broker_or_default()
            get = getattr(broker, "get_order", None)
            if not callable(get):
                return None
            out = await get(venue_order_id)  # type: ignore[misc]
            return out if isinstance(out, dict) else None
        except Exception as e:
            logger.warning(f"Venue order refetch failed: {e}")
            return None

    async def get_positions_from_alpaca(self) -> dict[str, int]:
        """Fetch positions from Alpaca paper."""
        try:
            broker = self._broker_or_default()
            positions = await broker.get_positions()
            out: dict[str, int] = {}
            for pos in positions or []:
                symbol = pos.get("symbol", "")
                try:
                    qty = int(float(pos.get("qty", 0)))
                except (TypeError, ValueError):
                    continue
                if symbol and qty != 0:
                    out[symbol] = qty
            return out
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca positions: {e}")
            return {}

    # Back-compat alias (renamed when Schwab was deleted 2026-09-06).
    async def get_positions_from_schwab(self) -> dict[str, int]:
        return await self.get_positions_from_alpaca()

    def get_state(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "venue": VENUE,
            "positions": self.position_tracker.snapshot(),
            "cached_orders": len(self._order_cache),
            "allow_market": ALLOW_MARKET_ORDERS,
        }
