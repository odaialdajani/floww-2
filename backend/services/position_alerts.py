"""On-demand position alerts recovered from a3a2e62b.

This is an offline snapshot evaluator: no broker, quote fetching, sockets,
background tasks, or notifications. The caller supplies a complete position
snapshot and current marks keyed by position_id (not underlying symbol), and
owns quote freshness. Each position carries its explicit premium factor; the
evaluator never guesses an option contract size. Percent limits use percent
units (-5 = -5%); output pnl/drawdown percentages are ratios (-0.05 = -5%).
Use one service instance per account. Portfolio drawdown uses only an explicit
account value and its sampled peak, never cash plus guessed position values.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _number(value: Any, minimum: float | None = None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        return None
    return value


def _aware(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


class PositionAlertType(StrEnum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    DRAW_DOWN = "DRAW_DOWN"
    MAX_HOLD_TIME = "MAX_HOLD_TIME"


class PositionAlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class PositionAlertConfig:
    stop_loss_pct: float = -5.0
    take_profit_pct: float = 10.0
    max_drawdown_pct: float = -15.0
    max_hold_minutes: float = 1440
    enabled: bool = True

    def __post_init__(self):
        for name in ("stop_loss_pct", "take_profit_pct", "max_drawdown_pct", "max_hold_minutes"):
            value = _number(getattr(self, name))
            if value is None:
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if self.stop_loss_pct >= 0 or self.max_drawdown_pct >= 0:
            raise ValueError("Loss limits must be negative percentages")
        if self.take_profit_pct <= 0 or self.max_hold_minutes <= 0:
            raise ValueError("Profit limit and maximum hold time must be positive")
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be boolean")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PositionSnapshot:
    position_id: str
    symbol: str
    side: str
    quantity: float | None
    entry_price: float | None
    premium_factor: float | None
    entry_time: datetime | str | None


@dataclass(frozen=True)
class PositionEvaluation:
    position_id: str
    symbol: str
    side: str
    quantity: float | None
    entry_price: float | None
    current_price: float | None
    unrealized_pnl: float | None
    unrealized_pnl_pct: float | None
    held_minutes: float | None
    unavailable: tuple[str, ...] = ()


@dataclass
class PositionAlertEvent:
    alert_id: str
    alert_type: PositionAlertType
    severity: PositionAlertSeverity
    position_id: str
    symbol: str
    side: str
    quantity: float | None
    entry_price: float | None
    current_price: float | None
    unrealized_pnl: float | None
    unrealized_pnl_pct: float | None
    message: str
    timestamp: str
    acknowledged: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        result = asdict(self)
        result["alert_type"] = self.alert_type.value
        result["severity"] = self.severity.value
        return result


@dataclass
class PositionAlertEvaluation:
    positions: list[PositionEvaluation]
    alerts: list[PositionAlertEvent]
    unavailable: dict[str, list[str]]
    drawdown_pct: float | None


def evaluate_position(position: PositionSnapshot, current_price: Any, *, now: datetime) -> PositionEvaluation:
    """Pure calculation. Missing marks never become the entry price or zero."""
    now = _aware(now)
    if now is None:
        raise ValueError("now must contain a timezone")
    quantity = _number(position.quantity, 0)
    quantity = quantity if quantity is not None and quantity > 0 else None
    factor = _number(position.premium_factor, 0)
    factor = factor if factor is not None and factor > 0 else None
    entry = _number(position.entry_price, 0)
    current = _number(current_price, 0)
    side = str(position.side).upper()
    missing = [name for name, value in (("quantity", quantity), ("entry_price", entry),
               ("premium_factor", factor), ("current_price", current)) if value is None]
    if side not in {"LONG", "SHORT"}:
        missing.append("side")
    pnl, ratio = None, None
    if not missing:
        pnl = _number((current - entry) * quantity * factor * (1 if side == "LONG" else -1))
        cost = _number(entry * quantity * factor)
        if pnl is None or cost is None:
            missing.append("valuation")
        elif cost > 0:
            ratio = _number(pnl / cost)
            if ratio is None:
                missing.append("pnl_ratio")
        else:
            missing.append("entry_cost")
    entered = _aware(position.entry_time)
    held = None
    if entered is None or entered > now:
        missing.append("entry_time")
    else:
        held = (now - entered).total_seconds() / 60
    return PositionEvaluation(position.position_id, position.symbol, side, quantity, entry,
                              current, pnl, ratio, held, tuple(missing))


class PositionAlertService:
    """In-memory dedup/history around pure evaluation; call explicitly per snapshot."""

    def __init__(self, config: PositionAlertConfig | None = None):
        self.config = config or PositionAlertConfig()
        self._overrides: dict[str, PositionAlertConfig] = {}
        self._fired: set[tuple[str, PositionAlertType]] = set()
        self._history: list[PositionAlertEvent] = []
        self._peak_value: float | None = None

    def set_position_thresholds(self, position_id: str, *, stop_loss_pct=None,
                                take_profit_pct=None, max_hold_minutes=None) -> None:
        changes = {k: v for k, v in {"stop_loss_pct": stop_loss_pct, "take_profit_pct": take_profit_pct,
                   "max_hold_minutes": max_hold_minutes}.items() if v is not None}
        self._overrides[position_id] = replace(self._overrides.get(position_id, self.config), **changes)

    def get_position_thresholds(self, position_id: str) -> dict:
        return self._overrides.get(position_id, self.config).to_dict()

    def _event(self, reading, kind, severity, now, message, details):
        key = (reading.position_id, kind)
        if key in self._fired:
            return None
        self._fired.add(key)
        event = PositionAlertEvent(str(uuid4()), kind, severity, reading.position_id, reading.symbol,
            reading.side, reading.quantity, reading.entry_price, reading.current_price,
            reading.unrealized_pnl, reading.unrealized_pnl_pct, message, now.isoformat(), details=details)
        self._history.append(event)
        self._history = self._history[-1000:]
        return event

    def evaluate_positions(self, positions: Sequence[PositionSnapshot], current_prices: Mapping[str, Any], *,
                           now: datetime, portfolio_value: float | None = None) -> PositionAlertEvaluation:
        now = _aware(now)
        if now is None:
            raise ValueError("now must contain a timezone")
        ids = [p.position_id for p in positions]
        if any(not isinstance(i, str) or not i or i == "__portfolio__" for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Positions must have unique nonempty IDs")
        active = set(ids)
        self._fired = {k for k in self._fired if k[0] in active or k[0] == "__portfolio__"}
        readings = [evaluate_position(p, current_prices.get(p.position_id), now=now) for p in positions]
        unavailable = {p.position_id: list(p.unavailable) for p in readings if p.unavailable}
        alerts = []
        for reading in readings:
            cfg = self._overrides.get(reading.position_id, self.config)
            if not self.config.enabled or not cfg.enabled:
                continue
            conditions = [
                (PositionAlertType.STOP_LOSS, PositionAlertSeverity.CRITICAL,
                 reading.unrealized_pnl_pct is not None and reading.unrealized_pnl_pct <= cfg.stop_loss_pct / 100),
                (PositionAlertType.TAKE_PROFIT, PositionAlertSeverity.WARNING,
                 reading.unrealized_pnl_pct is not None and reading.unrealized_pnl_pct >= cfg.take_profit_pct / 100),
                (PositionAlertType.MAX_HOLD_TIME, PositionAlertSeverity.WARNING,
                 reading.held_minutes is not None and reading.held_minutes >= cfg.max_hold_minutes),
            ]
            for kind, severity, breached in conditions:
                if breached:
                    event = self._event(reading, kind, severity, now,
                        f"{kind.value.replace('_', ' ')}: {reading.symbol}",
                        {"held_minutes": reading.held_minutes, "limits_percent": cfg.to_dict()})
                    if event:
                        alerts.append(event)
        value = _number(portfolio_value)
        drawdown = None
        if value is None:
            unavailable["__portfolio__"] = ["portfolio_value"]
        else:
            self._peak_value = value if self._peak_value is None else max(self._peak_value, value)
            if self._peak_value > 0:
                drawdown = _number((value - self._peak_value) / self._peak_value)
            if drawdown is not None and drawdown <= self.config.max_drawdown_pct / 100 and self.config.enabled:
                reading = PositionEvaluation("__portfolio__", "PORTFOLIO", "", None, None, None,
                                             None, None, None)
                event = self._event(reading, PositionAlertType.DRAW_DOWN, PositionAlertSeverity.CRITICAL, now,
                    "Portfolio value fell below the sampled peak limit",
                    {"portfolio_value": value, "sampled_peak": self._peak_value,
                     "drawdown_ratio": drawdown,
                     "max_drawdown_percent": self.config.max_drawdown_pct})
                if event:
                    alerts.append(event)
            elif drawdown is not None:
                self._fired.discard(("__portfolio__", PositionAlertType.DRAW_DOWN))
        return PositionAlertEvaluation(readings, alerts, unavailable, drawdown)

    def get_alert_history(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._history]

    def acknowledge(self, alert_id: str) -> bool:
        for event in self._history:
            if event.alert_id == alert_id:
                event.acknowledged = True
                return True
        return False
