"""
backend/services/paper_trading.py

Paper trade order management with full lifecycle.

Features:
- Order creation, validation, execution simulation
- Position tracking with real-time P&L
- Execution cost analysis (Almgren-Chriss + Kyle Lambda)
- Trade history and performance attribution
- Risk checks (position limits, Greeks exposure)

References:
- Almgren, R. & Chriss, N. (2000). "Optimal Execution of Portfolio Transactions."
- Kyle, A.S. (1985). "Continuous Auctions and Insider Trading."
- Hasbrouck, J. (1995). "One Security, Many Markets."
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from services.execution_engine import ExecutionEngine, ExecutionResult, MarketState, Order

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """Paper trading engine with simulated execution.

    Simulates order execution with realistic market impact,
    tracks positions, P&L, and provides performance analytics.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        max_position_pct: float = 0.10,  # max 10% of capital per position
        max_delta_exposure: float = 500.0,  # max net delta
        commission_per_contract: float = 0.65,
        on_position_closed: Any = None,
    ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.max_position_pct = max_position_pct
        self.max_delta_exposure = max_delta_exposure
        self.commission_per_contract = commission_per_contract
        # Optional callable(symbol, exit_price) fired when a symbol's net
        # position transitions to FLAT (round-trip closed). Used by the
        # Flowseeker journal bridge to auto-close seeded cards; injected
        # rather than imported so the engine stays decoupled.
        self.on_position_closed = on_position_closed

        self.execution_engine = ExecutionEngine()
        self.kyle_lambda = self.execution_engine.kyle_lambda

        self.positions: dict[str, dict[str, Any]] = {}  # symbol -> position
        self.orders: dict[str, Order] = {}
        self.trade_history: list[dict[str, Any]] = []
        self._order_counter = 0

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "almgren_chriss",
        urgency: float = 0.5,
        limit_price: float = 0.0,
        market: MarketState | None = None,
    ) -> dict[str, Any]:
        """Submit a paper trade order.

        Returns dict with order details and execution plan.
        """
        # Risk checks
        risk_check = self._check_risk(symbol, side, quantity, market)
        if not risk_check["approved"]:
            return {
                "status": "rejected",
                "reason": risk_check["reason"],
                "order": None,
            }

        # Create order
        self._order_counter += 1
        order_id = f"PAPER-{self._order_counter:06d}"
        order = Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            urgency=urgency,
            limit_price=limit_price,
            metadata={"order_id": order_id},
        )

        # Plan execution
        execution_plan = []
        cost_estimate = {}
        if market:
            execution_plan = self.execution_engine.plan_execution(
                order, market, time_horizon_seconds=300.0
            )
            cost_estimate = self.execution_engine.estimate_execution_cost(
                order, market, time_horizon_seconds=300.0
            )

        self.orders[order_id] = order

        return {
            "status": "accepted",
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
            "execution_plan": execution_plan,
            "cost_estimate": cost_estimate,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def execute_order(
        self,
        order_id: str,
        market: MarketState,
    ) -> ExecutionResult:
        """Execute a paper trade with simulated market impact."""
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        start_time = time.monotonic()

        # Simulate execution with Kyle Lambda impact
        kyle_impact = self.kyle_lambda.estimate_impact(order.quantity)
        fill_price = market.ask + kyle_impact if order.side == "buy" else market.bid - kyle_impact

        # Add some random slippage (normal distribution, 1 bps std)
        slippage = fill_price * 0.0001 * (hash(order_id) % 100 - 50) / 50
        fill_price += slippage

        # Commission
        commission = self.commission_per_contract * order.quantity
        total_cost = fill_price * order.quantity + commission

        # Update cash
        if order.side == "buy":
            self.cash -= total_cost
        else:
            self.cash += fill_price * order.quantity - commission

        # Update position
        self._update_position(order, fill_price)

        # Record trade
        trade = {
            "order_id": order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "fill_price": round(fill_price, 4),
            "commission": commission,
            "total_cost": round(total_cost, 2),
            "kyle_impact": round(kyle_impact, 6),
            "slippage_bps": round(abs(slippage / fill_price) * 10000, 2),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.trade_history.append(trade)

        # Update order status
        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price
        order.status = "filled"

        duration_ms = (time.monotonic() - start_time) * 1000

        arrival_price = market.ask if order.side == "buy" else market.bid
        impl_shortfall = abs(fill_price - arrival_price) * order.quantity

        return ExecutionResult(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            requested_qty=order.quantity,
            filled_qty=order.quantity,
            avg_price=round(fill_price, 4),
            total_cost=round(total_cost, 2),
            implementation_shortfall=round(impl_shortfall, 2),
            market_impact=round(kyle_impact * order.quantity, 4),
            timing_cost=0.0,
            slippage_bps=round(abs(slippage / fill_price) * 10000, 2),
            slices_executed=1,
            duration_ms=round(duration_ms, 2),
        )

    def _update_position(self, order: Order, fill_price: float):
        """Update internal position tracking."""
        key = f"{order.symbol}_{order.side}"
        if key not in self.positions:
            self.positions[key] = {
                "symbol": order.symbol,
                "side": order.side,
                "quantity": 0,
                "avg_cost": 0.0,
                "realized_pnl": 0.0,
            }

        pos = self.positions[key]
        old_qty = pos["quantity"]
        new_qty = old_qty + order.quantity
        if new_qty != 0:
            pos["avg_cost"] = (pos["avg_cost"] * old_qty + fill_price * order.quantity) / new_qty
        pos["quantity"] = new_qty

        # Flat transition: symbol NET position (buy + sell legs) crossed to
        # zero -> round-trip closed. Positions are keyed per symbol_side, so
        # flatness is computed by netting across all of the symbol's legs.
        # (No old_qty guard: the CLOSING leg's own side starts at 0, so the
        # guard would skip exactly the fill that flattens the position.)
        if self.on_position_closed:
            buy_qty = sum(p["quantity"] for k, p in self.positions.items()
                          if p["symbol"] == order.symbol and k.endswith("_buy"))
            sell_qty = sum(p["quantity"] for k, p in self.positions.items()
                           if p["symbol"] == order.symbol and k.endswith("_sell"))
            if abs(buy_qty - sell_qty) < 1e-9:
                try:
                    self.on_position_closed(order.symbol, float(fill_price))
                except Exception as e:
                    # Hook failure must never break order execution.
                    logger.warning("on_position_closed hook failed for %s: %s",
                                   order.symbol, e)

    def _check_risk(
        self,
        symbol: str,
        side: str,
        quantity: int,
        market: MarketState | None,
    ) -> dict[str, Any]:
        """Pre-trade risk checks."""
        # Position limit
        key = f"{symbol}_{side}"
        current_qty = self.positions.get(key, {}).get("quantity", 0)
        new_qty = current_qty + quantity
        max_qty = int(self.initial_capital * self.max_position_pct / (market.ask if market else 100))
        if new_qty > max_qty:
            return {
                "approved": False,
                "reason": f"Position limit: {new_qty} > {max_qty} (max {self.max_position_pct*100}% of capital)",
            }

        # Cash check for buys
        if side == "buy" and market:
            est_cost = market.ask * quantity * 1.01  # 1% buffer
            if est_cost > self.cash:
                return {
                    "approved": False,
                    "reason": f"Insufficient cash: need ${est_cost:,.2f}, have ${self.cash:,.2f}",
                }

        return {"approved": True, "reason": ""}

    def get_portfolio_summary(self) -> dict[str, Any]:
        """Get current portfolio summary.

        Positions are stored per ``symbol_side``; here we NET the buy and sell
        legs per symbol so a closed round-trip shows flat (0 open positions, ~0
        P&L) instead of double-counting both legs as open longs.
        """
        # Aggregate buy/sell legs into a net position per symbol.
        by_symbol: dict[str, dict[str, float]] = {}
        for pos in self.positions.values():
            agg = by_symbol.setdefault(
                pos["symbol"],
                {"buy_qty": 0.0, "buy_cost": 0.0, "sell_qty": 0.0, "sell_cost": 0.0},
            )
            if pos["side"] == "buy":
                agg["buy_qty"] += pos["quantity"]
                agg["buy_cost"] += pos["avg_cost"] * pos["quantity"]
            else:
                agg["sell_qty"] += pos["quantity"]
                agg["sell_cost"] += pos["avg_cost"] * pos["quantity"]

        total_value = self.cash
        positions_summary = []
        for symbol, agg in by_symbol.items():
            net_qty = agg["buy_qty"] - agg["sell_qty"]
            if abs(net_qty) < 1e-9:
                continue  # round-trip closed -> flat, no open position
            # Value the net position at the average cost of its dominant side.
            if net_qty > 0:
                avg_cost = agg["buy_cost"] / agg["buy_qty"] if agg["buy_qty"] else 0.0
            else:
                avg_cost = agg["sell_cost"] / agg["sell_qty"] if agg["sell_qty"] else 0.0
            positions_summary.append({
                "symbol": symbol,
                "side": "long" if net_qty > 0 else "short",
                "quantity": net_qty,
                "avg_cost": round(avg_cost, 4),
            })
            # Simplified: mark-to-cost for paper (assume current price = avg_cost).
            total_value += avg_cost * net_qty

        return {
            "cash": round(self.cash, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_value - self.initial_capital, 2),
            "total_pnl_pct": round((total_value - self.initial_capital) / self.initial_capital * 100, 2) if self.initial_capital else 0.0,
            "open_positions": len(positions_summary),
            "positions": positions_summary,
            "total_trades": len(self.trade_history),
        }

    def get_trade_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.trade_history[-limit:]

    def get_pnl_attribution(
        self, current_prices: dict[str, float] | None = None
    ) -> dict[str, Any]:
        """P&L attribution by ticker (Phase 6.5 remainder, 2026-09-05).

        Replays trade_history with average-cost matching per symbol, the same
        convention as get_portfolio_summary (fills are recorded with their
        realized fill_price, so this is deterministic for a given history):
          - buys accumulate cost; sells realize (sell_price - avg_buy) * qty
          - short-first flow mirrors: covers realize (avg_short - buy_price)
          - commissions summed per symbol (not allocated to open/closed)
        Unrealized P&L needs live marks: pass current_prices
        {symbol: price} or it reports null (honest unknown, never
        mark-to-model).
        """
        prices = current_prices or {}
        by_symbol: dict[str, dict[str, float]] = {}
        for t in self.trade_history:
            sym = t.get("symbol", "")
            qty = float(t.get("quantity") or 0)
            px = float(t.get("fill_price") or 0)
            fee = float(t.get("commission") or 0)
            if not sym or qty <= 0:
                continue
            a = by_symbol.setdefault(sym, {
                "trades": 0, "buy_qty": 0.0, "sell_qty": 0.0,
                "buy_cost": 0.0, "sell_proceeds": 0.0,
                "realized_pnl": 0.0, "commissions": 0.0,
            })
            a["trades"] += 1
            a["commissions"] += fee
            if t.get("side") == "buy":
                # Covering a short first (if any), else adding long.
                # Accumulation stays GROSS (net = buys − sells); average cost
                # is invariant to partial closes, realized captures the rest.
                short_open = a["sell_qty"] - a["buy_qty"]
                if short_open > 0:
                    covering = min(qty, short_open)
                    avg_short = (a["sell_proceeds"] / a["sell_qty"]) if a["sell_qty"] else 0.0
                    a["realized_pnl"] += (avg_short - px) * covering
                a["buy_qty"] += qty
                a["buy_cost"] += px * qty
            else:
                # Closing a long first (if any), else opening short.
                long_open = a["buy_qty"] - a["sell_qty"]
                if long_open > 0:
                    closing = min(qty, long_open)
                    avg_buy = (a["buy_cost"] / a["buy_qty"]) if a["buy_qty"] else 0.0
                    a["realized_pnl"] += (px - avg_buy) * closing
                a["sell_qty"] += qty
                a["sell_proceeds"] += px * qty

        symbols = []
        total_realized = 0.0
        total_unrealized = 0.0
        for sym, a in sorted(by_symbol.items()):
            net = a["buy_qty"] - a["sell_qty"]
            if net > 0:
                avg = (a["buy_cost"] / a["buy_qty"]) if a["buy_qty"] else 0.0
            elif net < 0:
                avg = (a["sell_proceeds"] / a["sell_qty"]) if a["sell_qty"] else 0.0
            else:
                avg = 0.0
            if sym in prices and prices[sym] is not None and net != 0:
                unrealized = (prices[sym] - avg) * net
            else:
                unrealized = None  # no live mark: unknown, never mark-to-model
            if unrealized is not None:
                total_unrealized += unrealized
            total_realized += a["realized_pnl"]
            symbols.append({
                "symbol": sym,
                "trades": a["trades"],
                "net_qty": round(net, 4),
                "realized_pnl": round(a["realized_pnl"], 2),
                "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
                "commissions": round(a["commissions"], 2),
            })
        return {
            "symbols": symbols,
            "total_realized_pnl": round(total_realized, 2),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "data_source": "paper_trading",
        }

    def get_state(self) -> dict[str, Any]:
        return {
            "cash": round(self.cash, 2),
            "initial_capital": self.initial_capital,
            "open_positions": len([p for p in self.positions.values() if p["quantity"] > 0]),
            "total_orders": len(self.orders),
            "total_trades": len(self.trade_history),
            "execution_engine": self.execution_engine.get_state(),
        }
