"""
backend/services/position_alerts.py

Real-time Position Alert Service — monitors open paper positions and fires
alerts when configurable thresholds are breached.

Alert types:
  STOP_LOSS      — Position P&L drops below stop-loss % threshold
  TAKE_PROFIT    — Position P&L exceeds take-profit % threshold
  DRAW_DOWN     — Portfolio drawdown exceeds max-drawdown % threshold
  MAX_HOLD_TIME — Position held longer than max-hold-time threshold
  POSITION_OPEN — New position opened (informational)

Each alert is:
  1. Logged at appropriate level
  2. Broadcast to all connected WebSocket clients
  3. Fired through AlertDispatcher for CRITICAL severity events

Environment:
  POSITION_ALERT_STOP_LOSS_PCT   — default stop-loss % (default -5.0)
  POSITION_ALERT_TAKE_PROFIT_PCT — default take-profit % (default 10.0)
  POSITION_ALERT_MAX_DRAWDOWN_PCT — default max portfolio drawdown % (default -15.0)
  POSITION_ALERT_MAX_HOLD_MINUTES — default max hold time in minutes (default 1440 = 24h)
  POSITION_ALERT_POLL_SECONDS     — poll interval in seconds (default 30)
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------

class PositionAlertType(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    DRAW_DOWN = "DRAW_DOWN"
    MAX_HOLD_TIME = "MAX_HOLD_TIME"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_CLOSED = "POSITION_CLOSED"


class PositionAlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Config & state
# ---------------------------------------------------------------------------

@dataclass
class PositionAlertConfig:
    """Default thresholds for position alerts.

    Per-position overrides can be set via set_position_thresholds().
    """
    stop_loss_pct: float = -5.0
    take_profit_pct: float = 10.0
    max_drawdown_pct: float = -15.0
    max_hold_minutes: int = 1440  # 24 hours
    poll_seconds: int = 30
    enabled: bool = True

    @classmethod
    def from_env(cls) -> PositionAlertConfig:
        return cls(
            stop_loss_pct=float(os.environ.get("POSITION_ALERT_STOP_LOSS_PCT", "-5.0")),
            take_profit_pct=float(os.environ.get("POSITION_ALERT_TAKE_PROFIT_PCT", "10.0")),
            max_drawdown_pct=float(os.environ.get("POSITION_ALERT_MAX_DRAWDOWN_PCT", "-15.0")),
            max_hold_minutes=int(os.environ.get("POSITION_ALERT_MAX_HOLD_MINUTES", "1440")),
            poll_seconds=int(os.environ.get("POSITION_ALERT_POLL_SECONDS", "30")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_hold_minutes": self.max_hold_minutes,
            "poll_seconds": self.poll_seconds,
            "enabled": self.enabled,
        }


@dataclass
class PositionAlertEvent:
    """A single position alert event."""
    alert_id: str
    alert_type: PositionAlertType
    severity: PositionAlertSeverity
    symbol: str
    side: str
    quantity: int
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": round(self.entry_price, 2),
            "current_price": round(self.current_price, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 4),
            "message": self.message,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Position Alert Service
# ---------------------------------------------------------------------------

class PositionAlertService:
    """Monitors open positions and fires alerts on threshold breaches.

    Usage:
        service = PositionAlertService()
        service.set_paper_trader(paper_trader_instance)
        service.set_price_provider(async_func)  # async (symbol) -> price
        await service.start()  # begins polling loop
        ...
        await service.stop()
    """

    def __init__(
        self,
        config: Optional[PositionAlertConfig] = None,
    ):
        self.config = config or PositionAlertConfig.from_env()
        self._paper_trader: Any = None
        self._price_provider: Optional[Callable[[str], float]] = None
        self._alert_history: List[PositionAlertEvent] = []
        self._acknowledged_ids: Set[str] = set()
        self._position_thresholds: Dict[str, Dict[str, float]] = {}  # symbol -> overrides

        # WebSocket clients
        self._ws_clients: List[Any] = []

        # Polling
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Track already-fired alerts per position to avoid spam
        self._fired_types: Dict[str, Set[str]] = {}  # position_key -> {alert_types}

        # Track peak portfolio value for drawdown calc
        self._peak_portfolio_value: float = 0.0

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_paper_trader(self, trader: Any) -> None:
        """Attach a PaperTrader instance to monitor."""
        self._paper_trader = trader

    def set_price_provider(self, provider: Callable[[str], float]) -> None:
        """Attach an async price provider: async def (symbol: str) -> float."""
        self._price_provider = provider

    def register_ws_client(self, ws: Any) -> None:
        """Register a WebSocket client for real-time alert streaming."""
        if ws not in self._ws_clients:
            self._ws_clients.append(ws)

    def unregister_ws_client(self, ws: Any) -> None:
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    # ------------------------------------------------------------------
    # Per-position thresholds
    # ------------------------------------------------------------------

    def set_position_thresholds(
        self,
        symbol: str,
        *,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        max_hold_minutes: Optional[int] = None,
    ) -> None:
        """Set per-position threshold overrides."""
        overrides = self._position_thresholds.setdefault(symbol, {})
        if stop_loss_pct is not None:
            overrides["stop_loss_pct"] = stop_loss_pct
        if take_profit_pct is not None:
            overrides["take_profit_pct"] = take_profit_pct
        if max_hold_minutes is not None:
            overrides["max_hold_minutes"] = max_hold_minutes

    def get_position_thresholds(self, symbol: str) -> Dict[str, Any]:
        """Get effective thresholds for a symbol (config defaults + overrides)."""
        return {
            "stop_loss_pct": (
                self._position_thresholds.get(symbol, {}).get("stop_loss_pct", self.config.stop_loss_pct)
            ),
            "take_profit_pct": (
                self._position_thresholds.get(symbol, {}).get("take_profit_pct", self.config.take_profit_pct)
            ),
            "max_hold_minutes": (
                self._position_thresholds.get(symbol, {}).get("max_hold_minutes", self.config.max_hold_minutes)
            ),
        }

    def reset_fired_types(self, symbol: str) -> None:
        """Reset fired alert tracking for a symbol (e.g., after position close/re-entry)."""
        keys_to_delete = [k for k in self._fired_types if k.startswith(f"{symbol}_")]
        for k in keys_to_delete:
            del self._fired_types[k]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the alert polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        log.info(
            "PositionAlertService started (poll=%ss, stop_loss=%.1f%%, "
            "take_profit=%.1f%%, max_drawdown=%.1f%%, max_hold=%dmin)",
            self.config.poll_seconds,
            self.config.stop_loss_pct,
            self.config.take_profit_pct,
            self.config.max_drawdown_pct,
            self.config.max_hold_minutes,
        )

    async def stop(self) -> None:
        """Stop the alert polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("PositionAlertService stopped")

    # ------------------------------------------------------------------
    # Alert evaluation
    # ------------------------------------------------------------------

    async def evaluate_positions(self, current_prices: Optional[Dict[str, float]] = None) -> List[PositionAlertEvent]:
        """Evaluate all open positions against alert thresholds.

        Returns newly fired alerts (not duplicates).
        """
        if not self._paper_trader:
            return []

        if not self.config.enabled:
            return []

        fired: List[PositionAlertEvent] = []

        # Gather open positions
        positions = getattr(self._paper_trader, "positions", {})
        if not positions:
            return []

        # Resolve current prices
        prices = dict(current_prices or {})
        if self._price_provider:
            for key, pos in positions.items():
                if pos.status != "open":
                    continue
                if pos.symbol not in prices:
                    try:
                        price = await self._price_provider(pos.symbol)
                        prices[pos.symbol] = price
                    except Exception as e:
                        log.warning("Price fetch failed for %s: %s", pos.symbol, e)

        # Compute portfolio value for drawdown
        portfolio_value = self._compute_portfolio_value(positions, prices)
        self._peak_portfolio_value = max(self._peak_portfolio_value, portfolio_value)
        drawdown_pct = (
            (portfolio_value - self._peak_portfolio_value) / self._peak_portfolio_value
            if self._peak_portfolio_value > 0 else 0.0
        )

        # Check portfolio drawdown (config stores %, divide by 100)
        if drawdown_pct < self.config.max_drawdown_pct / 100.0:
            drawdown_fired = self._check_and_dedupe(
                symbol="PORTFOLIO", position_key="PORTFOLIO_DRAWDOWN",
                alert_type=PositionAlertType.DRAW_DOWN,
                severity=PositionAlertSeverity.CRITICAL,
                side="", quantity=0, entry_price=0.0, current_price=0.0,
                unrealized_pnl=portfolio_value - self._compute_initial_equity(),
                unrealized_pnl_pct=drawdown_pct,
                message=(
                    f"Portfolio drawdown {drawdown_pct:.2%} exceeds "
                    f"threshold {self.config.max_drawdown_pct:.2%}. "
                    f"Current value: ${portfolio_value:,.2f}, "
                    f"Peak: ${self._peak_portfolio_value:,.2f}"
                ),
                details={
                    "portfolio_value": round(portfolio_value, 2),
                    "peak_value": round(self._peak_portfolio_value, 2),
                    "drawdown_pct": round(drawdown_pct, 6),
                },
            )
            if drawdown_fired:
                fired.append(drawdown_fired)

        # Check each open position
        now = datetime.now(timezone.utc)
        for key, pos in positions.items():
            if pos.status != "open":
                continue

            symbol = pos.symbol
            side = pos.side
            price = prices.get(symbol, pos.entry_price)
            position_key = f"{symbol}_{side}_{pos.entry_price}"

            # Compute unrealized P&L
            if side == "LONG":
                unrealized_pnl = (price - pos.entry_price) * pos.quantity
            else:
                unrealized_pnl = (pos.entry_price - price) * pos.quantity

            entry_cost = pos.entry_price * pos.quantity
            unrealized_pnl_pct = (
                unrealized_pnl / entry_cost if abs(entry_cost) > 1e-9 else 0.0
            )

            # Effective thresholds
            thresholds = self.get_position_thresholds(symbol)

            # 1. Stop-loss check
            if unrealized_pnl_pct <= thresholds["stop_loss_pct"] / 100.0:
                event = self._check_and_dedupe(
                    symbol=symbol, position_key=position_key,
                    alert_type=PositionAlertType.STOP_LOSS,
                    severity=PositionAlertSeverity.CRITICAL,
                    side=side, quantity=pos.quantity,
                    entry_price=pos.entry_price, current_price=price,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                    message=(
                        f"STOP LOSS: {side} {symbol} @ ${price:.2f} — "
                        f"P&L {unrealized_pnl_pct:.2%} (threshold: {thresholds['stop_loss_pct']:.1f}%). "
                        f"Entry: ${pos.entry_price:.2f}, Qty: {pos.quantity}"
                    ),
                    details={
                        "threshold": thresholds["stop_loss_pct"],
                        "entry_price": pos.entry_price,
                        "exit_price": price,
                    },
                )
                if event:
                    fired.append(event)

            # 2. Take-profit check
            if unrealized_pnl_pct >= thresholds["take_profit_pct"] / 100.0:
                event = self._check_and_dedupe(
                    symbol=symbol, position_key=position_key,
                    alert_type=PositionAlertType.TAKE_PROFIT,
                    severity=PositionAlertSeverity.WARNING,
                    side=side, quantity=pos.quantity,
                    entry_price=pos.entry_price, current_price=price,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                    message=(
                        f"TAKE PROFIT: {side} {symbol} @ ${price:.2f} — "
                        f"P&L {unrealized_pnl_pct:.2%} (threshold: {thresholds['take_profit_pct']:.1f}%). "
                        f"Entry: ${pos.entry_price:.2f}, Qty: {pos.quantity}"
                    ),
                    details={
                        "threshold": thresholds["take_profit_pct"],
                        "entry_price": pos.entry_price,
                        "exit_price": price,
                    },
                )
                if event:
                    fired.append(event)

            # 3. Max hold time check
            try:
                entry_time = datetime.fromisoformat(pos.entry_time)
                hold_minutes = (now - entry_time).total_seconds() / 60.0
                if hold_minutes >= thresholds["max_hold_minutes"]:
                    # Fire every cooldown period (half of max hold) to avoid spam
                    hold_cooldown_key = f"{position_key}_MAX_HOLD"
                    if hold_cooldown_key not in self._fired_types:
                        self._fired_types[hold_cooldown_key] = set()
                    hold_fired = f"MAX_HOLD_{int(hold_minutes // thresholds['max_hold_minutes'])}"
                    if hold_fired not in self._fired_types[hold_cooldown_key]:
                        self._fired_types[hold_cooldown_key].add(hold_fired)
                        event = self._build_event(
                            alert_type=PositionAlertType.MAX_HOLD_TIME,
                            severity=PositionAlertSeverity.WARNING,
                            symbol=symbol, side=side,
                            quantity=pos.quantity,
                            entry_price=pos.entry_price,
                            current_price=price,
                            unrealized_pnl=unrealized_pnl,
                            unrealized_pnl_pct=unrealized_pnl_pct,
                            message=(
                                f"MAX HOLD TIME: {side} {symbol} held {hold_minutes:.0f}min "
                                f"(threshold: {thresholds['max_hold_minutes']}min). "
                                f"Entry: ${pos.entry_price:.2f}, P&L: {unrealized_pnl_pct:.2%}"
                            ),
                            details={
                                "hold_minutes": round(hold_minutes, 1),
                                "threshold_minutes": thresholds["max_hold_minutes"],
                            },
                        )
                        fired.append(event)
            except (ValueError, AttributeError):
                pass

        # Handle newly opened positions (compare against previous state)
        self._detect_new_positions(positions)

        return fired

    # ------------------------------------------------------------------
    # Dedup & event building
    # ------------------------------------------------------------------

    def _check_and_dedupe(
        self,
        *,
        symbol: str,
        position_key: str,
        alert_type: PositionAlertType,
        severity: PositionAlertSeverity,
        side: str,
        quantity: int,
        entry_price: float,
        current_price: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
        message: str,
        details: Dict[str, Any],
    ) -> Optional[PositionAlertEvent]:
        """Build an alert event only if this alert type hasn't fired for this position."""
        type_key = alert_type.value
        if position_key not in self._fired_types:
            self._fired_types[position_key] = set()

        if type_key in self._fired_types[position_key]:
            return None

        self._fired_types[position_key].add(type_key)
        event = self._build_event(
            alert_type=alert_type, severity=severity,
            symbol=symbol, side=side, quantity=quantity,
            entry_price=entry_price, current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            message=message, details=details,
        )
        self._record_and_broadcast(event)
        return event

    def _build_event(
        self,
        *,
        alert_type: PositionAlertType,
        severity: PositionAlertSeverity,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: float,
        current_price: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
        message: str,
        details: Dict[str, Any],
    ) -> PositionAlertEvent:
        alert_id = f"{alert_type.value}_{symbol}_{int(time.time())}"
        return PositionAlertEvent(
            alert_id=alert_id,
            alert_type=alert_type,
            severity=severity,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            message=message,
            details=details,
        )

    # ------------------------------------------------------------------
    # New position detection
    # ------------------------------------------------------------------

    def _detect_new_positions(self, current_positions: Dict[str, Any]) -> None:
        """Detect newly opened positions and fire informational alerts."""
        if not hasattr(self, "_prev_position_keys"):
            self._prev_position_keys: Set[str] = set()
            for key, pos in current_positions.items():
                if pos.status == "open":
                    self._prev_position_keys.add(key)
            return

        current_keys = {
            key for key, pos in current_positions.items() if pos.status == "open"
        }
        new_keys = current_keys - self._prev_position_keys

        for key in new_keys:
            pos = current_positions[key]
            event = self._build_event(
                alert_type=PositionAlertType.POSITION_OPEN,
                severity=PositionAlertSeverity.INFO,
                symbol=pos.symbol, side=pos.side,
                quantity=pos.quantity,
                entry_price=pos.entry_price,
                current_price=pos.entry_price,
                unrealized_pnl=0.0, unrealized_pnl_pct=0.0,
                message=(
                    f"NEW POSITION: {pos.side} {pos.quantity} {pos.symbol} "
                    f"@ ${pos.entry_price:.2f}"
                ),
                details={"order_id": pos.order_id, "side": pos.side},
            )
            self._record_and_broadcast(event)

        # Track closed positions (for informational alerts)
        closed_keys = self._prev_position_keys - current_keys
        for key in closed_keys:
            # If the position is still in the dict but marked closed
            if key in current_positions:
                pos = current_positions[key]
                if pos.status == "closed":
                    event = self._build_event(
                        alert_type=PositionAlertType.POSITION_CLOSED,
                        severity=PositionAlertSeverity.INFO,
                        symbol=pos.symbol, side=pos.side,
                        quantity=pos.quantity,
                        entry_price=pos.entry_price,
                        current_price=pos.exit_price or pos.entry_price,
                        unrealized_pnl=pos.realized_pnl,
                        unrealized_pnl_pct=(
                            pos.realized_pnl / (pos.entry_price * pos.quantity)
                            if pos.entry_price * pos.quantity > 0 else 0.0
                        ),
                        message=(
                            f"POSITION CLOSED: {pos.side} {pos.quantity} {pos.symbol} — "
                            f"P&L ${pos.realized_pnl:.2f}. "
                            f"Entry: ${pos.entry_price:.2f}, Exit: ${pos.exit_price:.2f}"
                        ),
                        details={
                            "realized_pnl": round(pos.realized_pnl, 2),
                            "exit_price": pos.exit_price,
                        },
                    )
                    self._record_and_broadcast(event)

        self._prev_position_keys = current_keys

    # ------------------------------------------------------------------
    # Broadcast & record
    # ------------------------------------------------------------------

    def _record_and_broadcast(self, event: PositionAlertEvent) -> None:
        """Record alert in history and broadcast to WebSocket clients."""
        self._alert_history.append(event)

        # Truncate history to 1000 events (also applied in get_alert_history)
        if len(self._alert_history) > 1000:
            self._alert_history = self._alert_history[-1000:]

        # Log
        log.log(
            logging.CRITICAL if event.severity == PositionAlertSeverity.CRITICAL
            else logging.WARNING if event.severity == PositionAlertSeverity.WARNING
            else logging.INFO,
            "[POSITION ALERT %s] %s: %s",
            event.severity.value, event.alert_type.value, event.message,
        )

        # Broadcast to WebSocket clients
        asyncio.create_task(self._broadcast(event.to_dict()))

        # Fire through AlertDispatcher for CRITICAL severity
        if event.severity == PositionAlertSeverity.CRITICAL:
            asyncio.create_task(self._dispatch_critical(event))

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        """Send alert payload to all connected WebSocket clients."""
        disconnected = []
        for ws in self._ws_clients:
            try:
                await ws.send_json({"type": "position_alert", "data": payload})
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._ws_clients.remove(ws)

    async def _dispatch_critical(self, event: PositionAlertEvent) -> None:
        """Dispatch CRITICAL position alerts through the AlertDispatcher."""
        try:
            from services.alert_dispatcher import dispatcher
            await dispatcher.dispatch(
                alert_id=event.alert_id,
                severity="CRITICAL",
                title=f"Position {event.alert_type.value}: {event.symbol}",
                message=(
                    f"{event.side} {event.quantity} {event.symbol} @ {event.current_price} "
                    f"P&L: {event.unrealized_pnl_pct:.2%} — {event.message[:100]}"
                ),
                category="PositionAlert",
            )
        except Exception as e:
            log.warning("AlertDispatcher dispatch failed: %s", e)

    # ------------------------------------------------------------------
    # Portfolio helpers
    # ------------------------------------------------------------------

    def _compute_portfolio_value(
        self, positions: Dict[str, Any], prices: Dict[str, float]
    ) -> float:
        """Compute total portfolio value (cash + unrealized P&L)."""
        cash = getattr(self._paper_trader, "cash", 0.0)
        unrealized = 0.0
        for key, pos in positions.items():
            if pos.status != "open":
                continue
            price = prices.get(pos.symbol, pos.entry_price)
            if pos.side == "LONG":
                unrealized += (price - pos.entry_price) * pos.quantity
            else:
                unrealized += (pos.entry_price - price) * pos.quantity
        return cash + unrealized

    def _compute_initial_equity(self) -> float:
        """Get initial capital from paper trader."""
        return getattr(self._paper_trader, "initial_capital", 100_000.0)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Background loop that periodically evaluates positions."""
        while self._running:
            try:
                await self.evaluate_positions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Position alert poll error: %s", e, exc_info=True)

            await asyncio.sleep(self.config.poll_seconds)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_alert_history(
        self,
        limit: int = 50,
        alert_type: Optional[str] = None,
        symbol: Optional[str] = None,
        severity: Optional[str] = None,
        unacknowledged_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get alert history with optional filters."""
        # Truncate history (covers direct list appends too)
        if len(self._alert_history) > 1000:
            self._alert_history = self._alert_history[-1000:]

        filtered = list(self._alert_history)
        if alert_type:
            filtered = [a for a in filtered if a.alert_type.value == alert_type.upper()]
        if symbol:
            filtered = [a for a in filtered if a.symbol.upper() == symbol.upper()]
        if severity:
            filtered = [a for a in filtered if a.severity.value == severity.upper()]
        if unacknowledged_only:
            filtered = [a for a in filtered if not a.acknowledged]

        return [a.to_dict() for a in filtered[-limit:]]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged (silences future same-type alerts for its position)."""
        for event in self._alert_history:
            if event.alert_id == alert_id and not event.acknowledged:
                event.acknowledged = True
                self._acknowledged_ids.add(alert_id)
                log.info("Position alert acknowledged: %s", alert_id)
                return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get current position alert service status."""
        open_count = 0
        if self._paper_trader:
            positions = getattr(self._paper_trader, "positions", {})
            open_count = sum(
                1 for p in positions.values() if p.status == "open"
            )

        return {
            "running": self._running,
            "enabled": self.config.enabled,
            "config": self.config.to_dict(),
            "open_positions": open_count,
            "alert_history_count": len(self._alert_history),
            "unacknowledged_count": sum(
                1 for a in self._alert_history if not a.acknowledged
            ),
            "websocket_clients": len(self._ws_clients),
            "peak_portfolio_value": round(self._peak_portfolio_value, 2),
        }


# Global singleton
position_alert_service = PositionAlertService()
