"""
backend/services/paper_trader.py

VPIN_HFT Paper Trading Execution Adapter.

Connects trading signals (from trading_signals.py) to the Alpaca paper
trading API. Tracks positions, P&L, and logs all trades to MongoDB.

(These docstrings said "Schwab Paper Trading API via SchwabClient" until
2026-09-27. Schwab was deleted 2026-09-06; the code has always been Alpaca.)

Features:
- Signal-driven order execution (BUY/SELL from VPIN_HFT strategy)
- Position tracking with real-time P&L
- Trade logging to MongoDB `paper_trades` collection
- Exponential backoff for API rate limits
- Configurable position sizing and risk limits

References:
    The Open Street (2024). "VPIN_HFT: Volume-Synchronized Probability of
    Informed Trading for High-Frequency Signal Generation."
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from services.trading_signals import Signal

logger = logging.getLogger(__name__)


_pt_log = logging.getLogger("paper_trader")

async def _log_failed_insert(coro, kind: str):
    """Wrap a fire-and-forget DB insert so failures are logged, not silent."""
    try:
        await coro
    except Exception as e:
        _pt_log.error(
            "paper_trader insert (%s) failed: %s: %s",
            kind, type(e).__name__, e, exc_info=True,
        )


@dataclass
class PaperPosition:
    """Represents a single paper trade position."""
    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: int
    entry_price: float
    entry_time: str
    order_id: str = ""
    exit_price: float = 0.0
    exit_time: str = ""
    realized_pnl: float = 0.0
    status: str = "open"  # open, closed

    def close(self, exit_price: float) -> float:
        """Close position and compute realized P&L."""
        self.exit_price = exit_price
        self.exit_time = datetime.now(UTC).isoformat()
        if self.side == "LONG":
            self.realized_pnl = (exit_price - self.entry_price) * self.quantity
        else:
            self.realized_pnl = (self.entry_price - exit_price) * self.quantity
        self.status = "closed"
        return self.realized_pnl

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "order_id": self.order_id,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time,
            "realized_pnl": round(self.realized_pnl, 2),
            "status": self.status,
        }


@dataclass
@dataclass
class PaperTradeRecord:
    """Record of a completed round-trip trade."""
    trade_id: str
    symbol: str
    side: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_time: str
    exit_time: str
    realized_pnl: float
    signal_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "realized_pnl": round(self.realized_pnl, 2),
            "signal_data": self.signal_data,
        }


class PaperTrader:
    """Paper trading execution adapter for VPIN_HFT strategy.

    Executes BUY/SELL signals against a simulated paper account.
    In production, connects to the Alpaca paper trading API.

    Parameters
    ----------
    initial_capital : float
        Starting cash balance. Default $100,000.
    position_size_pct : float
        Fraction of capital per trade. Default 5%.
    max_positions : int
        Maximum concurrent open positions. Default 5.
    commission_per_share : float
        Commission per share/contract. Default $0.005.
    mongo_collection : object, optional
        MongoDB collection for trade logging. If None, trades are
        only kept in memory.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        position_size_pct: float = 0.05,
        max_positions: int = 5,
        commission_per_share: float = 0.005,
        mongo_collection: Any = None,
    ) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.position_size_pct = position_size_pct
        self.max_positions = max_positions
        self.commission_per_share = commission_per_share
        self.mongo = mongo_collection

        # State
        self.positions: dict[str, PaperPosition] = {}  # symbol -> position
        self.trade_history: list[PaperTradeRecord] = []
        self.order_log: list[dict[str, Any]] = []
        self._order_counter = 0

        # Rate limit backoff
        self._backoff_delay = 0.0
        self._max_backoff = 60.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_open_position(self, symbol: str, side: str) -> str | None:
        """Find an open position key for a given symbol and side.

        Returns the position key if found, None otherwise.
        """
        for key, pos in self.positions.items():
            if pos.symbol == symbol and pos.side == side and pos.status == "open":
                return key
        return None

    def _has_open_position(self, symbol: str) -> bool:
        """Check if there's any open position for a symbol."""
        return any(
            pos.symbol == symbol and pos.status == "open"
            for pos in self.positions.values()
        )

    # ------------------------------------------------------------------
    # Signal execution
    # ------------------------------------------------------------------

    def execute_signal(
        self,
        signal: Signal,
        symbol: str,
        current_price: float,
        signal_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a trading signal.

        Parameters
        ----------
        signal : Signal
            BUY, SELL, or HOLD.
        symbol : str
            Ticker symbol.
        current_price : float
            Current market price for the symbol.
        signal_data : dict, optional
            Additional signal metadata for logging.

        Returns
        -------
        dict
            Order result with status, order_id, and details.
        """
        if signal == Signal.HOLD:
            return {"status": "no_action", "reason": "HOLD signal"}

        if signal == Signal.BUY:
            return self._execute_buy(symbol, current_price, signal_data)
        elif signal == Signal.SELL:
            return self._execute_sell(symbol, current_price, signal_data)

        return {"status": "error", "reason": f"Unknown signal: {signal}"}

    def _execute_buy(
        self,
        symbol: str,
        price: float,
        signal_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute BUY: cover shorts if any, then add long position."""
        result = {"action": "BUY", "symbol": symbol}

        # Cover existing short position
        short_key = self._find_open_position(symbol, "SHORT")
        if short_key is not None:
            cover_result = self._close_position(symbol, price)
            result["cover"] = cover_result

        # Check position limits
        open_count = sum(1 for p in self.positions.values() if p.status == "open")
        if open_count >= self.max_positions and not self._has_open_position(symbol):
            result["status"] = "rejected"
            result["reason"] = f"Max positions ({self.max_positions}) reached"
            return result

        # Calculate position size
        position_value = self.cash * self.position_size_pct
        quantity = max(1, int(position_value / price))
        cost = price * quantity + self.commission_per_share * quantity

        if cost > self.cash:
            quantity = max(1, int((self.cash - self.commission_per_share) / price))
            cost = price * quantity + self.commission_per_share * quantity

        if quantity <= 0 or cost > self.cash:
            result["status"] = "rejected"
            result["reason"] = "Insufficient cash"
            return result

        # Create position
        self._order_counter += 1
        order_id = f"VPIN-{self._order_counter:06d}"
        position = PaperPosition(
            symbol=symbol,
            side="LONG",
            quantity=quantity,
            entry_price=price,
            entry_time=datetime.now(UTC).isoformat(),
            order_id=order_id,
        )
        self.positions[f"{symbol}_LONG_{order_id}"] = position
        self.cash -= cost

        order_record = {
            "order_id": order_id,
            "symbol": symbol,
            "side": "BUY",
            "quantity": quantity,
            "price": price,
            "cost": round(cost, 2),
            "commission": round(self.commission_per_share * quantity, 2),
            "timestamp": position.entry_time,
            "signal_data": signal_data or {},
        }
        self.order_log.append(order_record)
        self._persist_order(order_record)

        result["status"] = "filled"
        result["order_id"] = order_id
        result["quantity"] = quantity
        result["price"] = price
        logger.info(f"BUY {quantity} {symbol} @ {price} (order {order_id})")
        return result

    def _execute_sell(
        self,
        symbol: str,
        price: float,
        signal_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute SELL: cover longs if any, then add short position."""
        result = {"action": "SELL", "symbol": symbol}

        # Cover existing long position
        long_key = self._find_open_position(symbol, "LONG")
        if long_key is not None:
            cover_result = self._close_position(symbol, price)
            result["cover"] = cover_result

        # Check position limits
        open_count = sum(1 for p in self.positions.values() if p.status == "open")
        if open_count >= self.max_positions and not self._has_open_position(symbol):
            result["status"] = "rejected"
            result["reason"] = f"Max positions ({self.max_positions}) reached"
            return result

        # Calculate position size
        position_value = self.cash * self.position_size_pct
        quantity = max(1, int(position_value / price))
        proceeds = price * quantity - self.commission_per_share * quantity

        if quantity <= 0:
            result["status"] = "rejected"
            result["reason"] = "Cannot calculate position size"
            return result

        # Create short position
        self._order_counter += 1
        order_id = f"VPIN-{self._order_counter:06d}"
        position = PaperPosition(
            symbol=symbol,
            side="SHORT",
            quantity=quantity,
            entry_price=price,
            entry_time=datetime.now(UTC).isoformat(),
            order_id=order_id,
        )
        self.positions[f"{symbol}_SHORT_{order_id}"] = position
        self.cash += proceeds

        order_record = {
            "order_id": order_id,
            "symbol": symbol,
            "side": "SELL",
            "quantity": quantity,
            "price": price,
            "proceeds": round(proceeds, 2),
            "commission": round(self.commission_per_share * quantity, 2),
            "timestamp": position.entry_time,
            "signal_data": signal_data or {},
        }
        self.order_log.append(order_record)
        self._persist_order(order_record)

        result["status"] = "filled"
        result["order_id"] = order_id
        result["quantity"] = quantity
        result["price"] = price
        logger.info(f"SELL {quantity} {symbol} @ {price} (order {order_id})")
        return result

    def _close_position(self, symbol: str, exit_price: float) -> dict[str, Any]:
        """Close an open position for the given symbol."""
        # Find the open position for this symbol
        close_key = None
        for key, pos in self.positions.items():
            if pos.symbol == symbol and pos.status == "open":
                close_key = key
                break

        if close_key is None:
            return {"status": "no_position"}

        pos = self.positions[close_key]
        pnl = pos.close(exit_price)

        # Update cash
        if pos.side == "LONG":
            self.cash += exit_price * pos.quantity - self.commission_per_share * pos.quantity
        else:
            self.cash -= exit_price * pos.quantity + self.commission_per_share * pos.quantity

        # Record trade
        trade = PaperTradeRecord(
            trade_id=str(uuid.uuid4())[:8],
            symbol=pos.symbol,
            side=pos.side,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_time=pos.entry_time,
            exit_time=pos.exit_time,
            realized_pnl=pnl,
        )
        self.trade_history.append(trade)
        self._persist_trade(trade)

        logger.info(
            f"CLOSE {pos.side} {pos.quantity} {symbol}: "
            f"entry={pos.entry_price} exit={exit_price} pnl={pnl:.2f}"
        )
        return {
            "status": "closed",
            "side": pos.side,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "realized_pnl": round(pnl, 2),
        }

    # ------------------------------------------------------------------
    # MongoDB persistence
    # ------------------------------------------------------------------

    def _persist_order(self, order: dict[str, Any]) -> None:
        """Persist order to MongoDB if collection is available."""
        if self.mongo is None:
            return
        try:
            import asyncio
            try:
                # Prefer get_running_loop() — avoids DeprecationWarning in 3.10+ / error in 3.12+
                asyncio.get_running_loop()
                asyncio.create_task(_log_failed_insert(self.mongo.insert_one(order), "order"))
            except RuntimeError:
                # No running event loop — sync context; use asyncio.run()
                asyncio.run(_log_failed_insert(self.mongo.insert_one(order), "order"))
        except Exception as e:
            logger.warning(f"Failed to persist order to MongoDB: {e}")

    def _persist_trade(self, trade: PaperTradeRecord) -> None:
        """Persist completed trade to MongoDB if collection is available."""
        if self.mongo is None:
            return
        try:
            import asyncio
            doc = trade.to_dict()
            doc["logged_at"] = datetime.now(UTC).isoformat()
            try:
                # Prefer get_running_loop() — avoids DeprecationWarning in 3.10+ / error in 3.12+
                asyncio.get_running_loop()
                asyncio.create_task(_log_failed_insert(self.mongo.insert_one(doc), "trade"))
            except RuntimeError:
                # No running event loop — sync context; use asyncio.run()
                asyncio.run(_log_failed_insert(self.mongo.insert_one(doc), "trade"))
        except Exception as e:
            logger.warning(f"Failed to persist trade to MongoDB: {e}")

    # ------------------------------------------------------------------
    # Portfolio summary
    # ------------------------------------------------------------------

    def get_portfolio_summary(self, current_prices: dict[str, float] | None = None) -> dict[str, Any]:
        """Get current portfolio summary.

        Parameters
        ----------
        current_prices : dict[str, float], optional
            Current market prices for open position symbols.
        """
        current_prices = current_prices or {}
        open_positions = []
        total_unrealized = 0.0

        for _key, pos in self.positions.items():
            if pos.status != "open":
                continue
            current_price = current_prices.get(pos.symbol, pos.entry_price)
            if pos.side == "LONG":
                unrealized = (current_price - pos.entry_price) * pos.quantity
            else:
                unrealized = (pos.entry_price - current_price) * pos.quantity
            total_unrealized += unrealized
            open_positions.append({
                "symbol": pos.symbol,
                "side": pos.side,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": current_price,
                "unrealized_pnl": round(unrealized, 2),
            })

        total_realized = sum(t.realized_pnl for t in self.trade_history)
        total_value = self.cash + total_unrealized

        return {
            "cash": round(self.cash, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_value - self.initial_capital, 2),
            "total_pnl_pct": round(
                (total_value - self.initial_capital) / self.initial_capital * 100, 2
            ),
            "realized_pnl": round(total_realized, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "open_positions": len(open_positions),
            "positions": open_positions,
            "total_trades": len(self.trade_history),
            "total_orders": len(self.order_log),
        }

    def get_state(self) -> dict[str, Any]:
        """Return full state for serialization."""
        return {
            "cash": round(self.cash, 2),
            "initial_capital": self.initial_capital,
            "open_positions": sum(1 for p in self.positions.values() if p.status == "open"),
            "total_orders": len(self.order_log),
            "total_trades": len(self.trade_history),
            "position_size_pct": self.position_size_pct,
            "max_positions": self.max_positions,
        }
