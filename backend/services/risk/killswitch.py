"""
backend/services/risk/killswitch.py — Daily loss kill switch.

Monitors daily P&L and trips a kill switch when losses exceed threshold.
Once tripped, no new trades are allowed until manual reset or next trading day.

Reference: swarmSPX risk/killswitch.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class KillSwitchConfig:
    """Kill switch configuration."""
    daily_loss_pct_threshold: float = -0.02  # -2% daily loss
    max_drawdown_pct: float = -0.05  # -5% max drawdown
    cooldown_minutes: int = 30  # cooldown after trip
    auto_reset_next_day: bool = True  # auto-reset at market open next day


class KillSwitch:
    """
    Daily loss kill switch.

    Usage:
        ks = KillSwitch(config=KillSwitchConfig())
        ks.update_pnl(current_equity, starting_equity)
        if ks.is_tripped:
            block_new_trades()
    """

    def __init__(self, config: Optional[KillSwitchConfig] = None):
        self.config = config or KillSwitchConfig()
        self._tripped = False
        self._trip_reason = ""
        self._trip_time: Optional[datetime] = None
        self._daily_starting_equity: float = 0.0
        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0
        self._current_date: date = date.today()
        self._trade_count_today: int = 0
        self._loss_count_today: int = 0

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    @property
    def trip_reason(self) -> str:
        return self._trip_reason

    @property
    def trip_time(self) -> Optional[datetime]:
        return self._trip_time

    def reset(self):
        """Manual reset."""
        self._tripped = False
        self._trip_reason = ""
        self._trip_time = None
        logger.info("KillSwitch: manually reset")

    def start_day(self, starting_equity: float):
        """Call at market open to reset daily tracking."""
        self._current_date = date.today()
        self._trade_count_today = 0
        self._loss_count_today = 0
        self._daily_starting_equity = starting_equity
        self._peak_equity = starting_equity
        if self.config.auto_reset_next_day:
            self.reset()
        logger.info(f"KillSwitch: new day, equity=${starting_equity:.2f}")

    def update_pnl(self, current_equity: float):
        """Update with current equity. Returns True if kill switch trips."""
        self._current_equity = current_equity

        # Update peak equity
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        # Check daily loss
        if self._daily_starting_equity > 0:
            daily_pnl_pct = (current_equity - self._daily_starting_equity) / self._daily_starting_equity
            if daily_pnl_pct <= self.config.daily_loss_pct_threshold:
                self._trip(f"Daily loss: {daily_pnl_pct:.2%}")
                return True

        # Check max drawdown from peak
        if self._peak_equity > 0:
            drawdown_pct = (current_equity - self._peak_equity) / self._peak_equity
            if drawdown_pct <= self.config.max_drawdown_pct:
                self._trip(f"Max drawdown: {drawdown_pct:.2%}")
                return True

        return False

    def record_trade(self, pnl: float):
        """Record a completed trade."""
        self._trade_count_today += 1
        if pnl < 0:
            self._loss_count_today += 1

    def can_trade(self) -> tuple[bool, str]:
        """Check if trading is allowed. Returns (allowed, reason)."""
        if self._tripped:
            return False, f"Kill switch tripped: {self._trip_reason}"
        return True, ""

    def get_status(self) -> dict:
        """Get current kill switch status."""
        daily_pnl = 0.0
        if self._daily_starting_equity > 0:
            daily_pnl = (self._current_equity - self._daily_starting_equity) / self._daily_starting_equity

        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (self._current_equity - self._peak_equity) / self._peak_equity

        return {
            "tripped": self._tripped,
            "trip_reason": self._trip_reason,
            "trip_time": self._trip_time.isoformat() if self._trip_time else None,
            "current_equity": self._current_equity,
            "daily_starting_equity": self._daily_starting_equity,
            "peak_equity": self._peak_equity,
            "daily_pnl_pct": round(daily_pnl, 4),
            "drawdown_pct": round(drawdown, 4),
            "trade_count_today": self._trade_count_today,
            "loss_count_today": self._loss_count_today,
        }

    def _trip(self, reason: str):
        self._tripped = True
        self._trip_reason = reason
        self._trip_time = datetime.now(timezone.utc)
        logger.critical(f"KillSwitch: TRIPPED — {reason}")
