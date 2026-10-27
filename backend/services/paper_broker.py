#!/usr/bin/env python3
"""
backend/services/paper_broker.py — Paper broker with shadow trading.

Enhanced version of paper_trading.py with fill simulation, slippage model,
and position tracking. Inspired by swarmSPX's paper.py.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Fill:
    """Represents a simulated fill."""
    fill_id: str
    order_id: str
    symbol: str
    side: str
    quantity: int
    fill_price: float
    slippage: float
    market_impact: float
    timestamp: str


@dataclass
class Position:
    """Represents a position in a ticker."""
    symbol: str
    quantity: int  # positive = long, negative = short
    avg_cost: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class PaperBrokerConfig:
    """Configuration for the paper broker."""
    initial_capital: float = 25000.0
    slippage_per_contract: float = 0.01
    market_impact_pct: float = 0.001  # 0.1% per contract
    random_slippage: bool = False
    random_seed: int | None = None


class PaperBroker:
    """Paper broker with shadow trading and fill simulation.

    Simulates order submission, fill execution with slippage,
    position tracking, and PnL calculation.
    """

    def __init__(self, config: PaperBrokerConfig | None = None):
        self.config = config or PaperBrokerConfig()
        self.cash = self.config.initial_capital
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.orders: dict[str, dict] = {}
        self.daily_pnl: float = 0.0
        self.total_realized_pnl: float = 0.0

        if self.config.random_seed is not None:
            np.random.seed(self.config.random_seed)

    def submit_order(self, symbol: str, side: str, quantity: int,
                     order_type: str = "market", limit_price: float = 0.0) -> str:
        """Submit an order and return order_id."""
        order_id = str(uuid.uuid4())[:12]
        self.orders[order_id] = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
            "limit_price": limit_price,
            "status": "submitted",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        logger.info(f"Order submitted: {order_id} {side} {quantity} {symbol}")
        return order_id

    def get_fill_price(self, symbol: str, side: str, quantity: int,
                       market_price: float) -> tuple[float, float, float]:
        """Calculate fill price with slippage and market impact.

        Returns:
            tuple of (fill_price, slippage, market_impact)
        """
        if quantity <= 0:
            logger.warning(f"Zero or negative quantity: {quantity}")
            fill_price = market_price
            slippage = 0.0
            market_impact = 0.0
        else:
            # Base slippage
            slippage = self.config.slippage_per_contract * quantity
            # Market impact proportional to size
            market_impact = self.config.market_impact_pct * market_price * quantity
            # Random component (optional)
            random_component = 0.0
            if self.config.random_slippage:
                random_component = np.random.normal(0, slippage * 0.5)
            # Total slippage
            total_slippage = slippage + market_impact + random_component
            # Apply slippage directionally (worsens fill)
            if side == "buy":
                fill_price = market_price + total_slippage / quantity
            else:
                fill_price = market_price - total_slippage / quantity

        return fill_price, slippage, market_impact

    def execute_fill(self, order_id: str, market_price: float) -> Fill | None:
        """Execute a fill for a submitted order.

        Idempotency guard (paper-recovery D1): an order fills exactly once.
        Replaying ``execute_fill`` on an already-filled order (lost reply,
        operator retry, double-click) is refused — cash, positions and the
        fill list must not move twice for one order.
        """
        if order_id not in self.orders:
            logger.error(f"Order not found: {order_id}")
            return None

        order = self.orders[order_id]
        if order["status"] != "submitted":
            logger.warning(
                f"Duplicate fill refused: order {order_id} is already "
                f"{order['status']}"
            )
            return None
        symbol = order["symbol"]
        side = order["side"]
        quantity = order["quantity"]

        fill_price, slippage, market_impact = self.get_fill_price(
            symbol, side, quantity, market_price
        )

        fill = Fill(
            fill_id=str(uuid.uuid4())[:12],
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            fill_price=fill_price,
            slippage=slippage,
            market_impact=market_impact,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # Update cash
        cost = fill_price * quantity
        if side == "buy":
            self.cash -= cost
        else:
            self.cash += cost

        # Update position
        self._update_position(symbol, side, quantity, fill_price)

        # Track fill
        self.fills.append(fill)
        order["status"] = "filled"

        logger.info(
            f"Fill: {fill.fill_id} {side} {quantity} {symbol} @ {fill_price:.2f} "
            f"(slippage={slippage:.2f}, impact={market_impact:.2f})"
        )
        return fill

    def _update_position(self, symbol: str, side: str, quantity: int,
                         fill_price: float) -> None:
        """Update position after a fill."""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol, quantity=0, avg_cost=0.0)

        pos = self.positions[symbol]

        # Determine signed quantity
        signed_qty = quantity if side == "buy" else -quantity

        if pos.quantity == 0:
            # New position
            pos.quantity = signed_qty
            pos.avg_cost = fill_price
        elif (pos.quantity > 0 and signed_qty > 0) or (pos.quantity < 0 and signed_qty < 0):
            # Adding to position
            total_cost = pos.avg_cost * abs(pos.quantity) + fill_price * quantity
            pos.quantity += signed_qty
            pos.avg_cost = total_cost / abs(pos.quantity)
        else:
            # Reducing or reversing position
            close_qty = min(abs(pos.quantity), quantity)
            pnl = (fill_price - pos.avg_cost) * close_qty
            if pos.quantity < 0:
                pnl = -pnl  # Short position

            pos.realized_pnl += pnl
            self.total_realized_pnl += pnl
            self.daily_pnl += pnl

            remaining = quantity - close_qty
            if remaining > 0:
                # Reversed position
                pos.quantity = remaining if side == "buy" else -remaining
                pos.avg_cost = fill_price
            else:
                pos.quantity += signed_qty
                if pos.quantity == 0:
                    pos.avg_cost = 0.0

    def get_position(self, symbol: str) -> Position | None:
        """Get current position for a ticker."""
        return self.positions.get(symbol)

    def get_all_positions(self) -> list[Position]:
        """Get all open positions."""
        return [p for p in self.positions.values() if p.quantity != 0]

    def get_pnl(self) -> dict:
        """Get PnL summary."""
        unrealized = 0.0
        for pos in self.positions.values():
            if pos.quantity != 0:
                # Unrealized PnL (would need current market price for accuracy)
                unrealized += pos.unrealized_pnl

        return {
            "realized_pnl": round(self.total_realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "total_pnl": round(self.total_realized_pnl + unrealized, 2),
            "cash": round(self.cash, 2),
            "equity": round(self.cash + unrealized, 2),
        }

    def close_position(self, symbol: str, market_price: float) -> Fill | None:
        """Close an entire position."""
        pos = self.positions.get(symbol)
        if not pos or pos.quantity == 0:
            logger.warning(f"No open position for {symbol}")
            return None

        side = "sell" if pos.quantity > 0 else "buy"
        quantity = abs(pos.quantity)

        order_id = self.submit_order(symbol, side, quantity)
        return self.execute_fill(order_id, market_price)

    def get_trade_history(self) -> list[dict]:
        """Get all fills as dicts."""
        return [
            {
                "fill_id": f.fill_id,
                "order_id": f.order_id,
                "symbol": f.symbol,
                "side": f.side,
                "quantity": f.quantity,
                "fill_price": f.fill_price,
                "slippage": f.slippage,
                "market_impact": f.market_impact,
                "timestamp": f.timestamp,
            }
            for f in self.fills
        ]

    def reset_daily_pnl(self) -> None:
        """Reset daily PnL (call at market open)."""
        self.daily_pnl = 0.0
