"""
backend/services/live_trading_switch.py

Live-trading state machine with circuit breakers.
States: OFF → PAPER_ONLY → LIVE_TINY → LIVE_NORMAL → LIVE_FULL

Each state transition requires 2-factor confirmation.
Circuit breakers auto-demote on risk threshold breaches.

Reference: SEC Rule 15c3-5 (Risk Management Controls for Brokers)
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("live_trading_switch")


class TradingState(IntEnum):
    OFF = 0
    PAPER_ONLY = 1
    LIVE_TINY = 2  # Max $1000 notional
    LIVE_NORMAL = 3
    LIVE_FULL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def max_notional_usd(self) -> Optional[float]:
        limits = {
            TradingState.OFF: 0,
            TradingState.PAPER_ONLY: 0,
            TradingState.LIVE_TINY: 1000,
            TradingState.LIVE_NORMAL: 10000,
            TradingState.LIVE_FULL: None,  # No limit
        }
        return limits.get(self)


class CircuitBreakerReason:
    DAILY_PNL_DRAWDOWN = "daily_pnl_drawdown"
    REJECTED_FILLS = "rejected_fills"
    RECONCILIATION_DISCREPANCY = "reconciliation_discrepancy"
    SLA_BREACH = "sla_breach"
    MANUAL = "manual"


class LiveTradingSwitch:
    """State machine for live-trading enablement with circuit breakers."""

    def __init__(self):
        self._state = TradingState.OFF
        self._last_transition: Optional[datetime] = None
        self._cooldown_until: Optional[datetime] = None
        self._circuit_breaker_log: List[Dict[str, Any]] = []
        self._transition_log: List[Dict[str, Any]] = []

    @property
    def state(self) -> TradingState:
        return self._state

    @property
    def is_live(self) -> bool:
        return self._state >= TradingState.LIVE_TINY

    @property
    def is_paper(self) -> bool:
        return self._state == TradingState.PAPER_ONLY

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self._state.name,
            "state_label": self._state.label,
            "is_live": self.is_live,
            "max_notional_usd": self._state.max_notional_usd,
            "last_transition": self._last_transition.isoformat() if self._last_transition else None,
            "cooldown_active": self._cooldown_until is not None and datetime.now(timezone.utc) < self._cooldown_until,
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
            "circuit_breaker_count": len(self._circuit_breaker_log),
        }

    def request_transition(
        self,
        target: TradingState,
        totp_code: str,
        email_code: str,
        actor: str = "nav",
    ) -> Tuple[bool, str]:
        """Request a state transition. Requires 2FA (TOTP + email code)."""

        # Validate 2FA
        if not self._verify_totp(totp_code):
            return False, "Invalid TOTP code"
        if not self._verify_email_code(email_code):
            return False, "Invalid email code"

        # Check cooldown
        if self._cooldown_until and datetime.now(timezone.utc) < self._cooldown_until:
            remaining = (self._cooldown_until - datetime.now(timezone.utc)).total_seconds()
            return False, f"Cooldown active — {remaining:.0f}s remaining"

        # Can only advance one state at a time
        if target > self._state and target != TradingState(self._state + 1):
            return False, f"Can only advance one state at a time (current: {self._state.name}, requested: {target.name})"

        # Cannot skip states going up
        if target > self._state and int(target) != int(self._state) + 1:
            return False, "Cannot skip states when advancing"

        old_state = self._state
        self._state = target
        self._last_transition = datetime.now(timezone.utc)

        entry = {
            "timestamp": self._last_transition.isoformat(),
            "actor": actor,
            "from_state": old_state.name,
            "to_state": target.name,
        }
        self._transition_log.append(entry)
        logger.info(f"Trading state: {old_state.name} → {target.name} by {actor}")

        return True, f"Transitioned to {target.label}"

    def trip_circuit_breaker(
        self,
        reason: str,
        details: str = "",
        actor: str = "system",
    ) -> None:
        """Trip a circuit breaker — demote one state level, 24h cooldown."""
        old_state = self._state
        new_state = TradingState(max(0, int(self._state) - 1))

        self._state = new_state
        self._cooldown_until = datetime.now(timezone.utc) + timedelta(hours=24)
        self._last_transition = datetime.now(timezone.utc)

        entry = {
            "timestamp": self._last_transition.isoformat(),
            "reason": reason,
            "details": details,
            "actor": actor,
            "from_state": old_state.name,
            "to_state": new_state.name,
            "cooldown_hours": 24,
        }
        self._circuit_breaker_log.append(entry)
        logger.critical(
            f"CIRCUIT BREAKER: {old_state.name} → {new_state.name} "
            f"(reason: {reason}, cooldown: 24h)"
        )

    def check_pnl_drawdown(self, daily_pnl_pct: float, account_equity: float) -> bool:
        """Check if daily P&L drawdown exceeds -2% threshold. Returns True if tripped."""
        if daily_pnl_pct < -2.0:
            self.trip_circuit_breaker(
                CircuitBreakerReason.DAILY_PNL_DRAWDOWN,
                f"Daily P&L {daily_pnl_pct:.2f}% < -2% threshold (equity: ${account_equity:.2f})",
            )
            return True
        return False

    def check_rejected_fills(self, rejected_count_1h: int) -> bool:
        """Check if >5 rejected fills in 1 hour. Returns True if tripped."""
        if rejected_count_1h > 5:
            self.trip_circuit_breaker(
                CircuitBreakerReason.REJECTED_FILLS,
                f"{rejected_count_1h} rejected fills in 1h > 5 threshold",
            )
            return True
        return False

    def check_reconciliation(self, discrepancy_count: int) -> bool:
        """Check for reconciliation discrepancies. Returns True if tripped."""
        if discrepancy_count > 0:
            self.trip_circuit_breaker(
                CircuitBreakerReason.RECONCILIATION_DISCREPANCY,
                f"{discrepancy_count} position discrepancies detected",
            )
            return True
        return False

    def _verify_totp(self, code: str) -> bool:
        """Verify TOTP code. In production, use pyotp. For now, check against env."""
        expected = os.environ.get("TRADING_TOTP_SECRET", "")
        if not expected:
            # Dev mode: accept any 6-digit code
            return len(code) == 6 and code.isdigit()
        # Production: verify against TOTP
        import pyotp  # type: ignore
        totp = pyotp.TOTP(expected)
        return totp.verify(code, valid_window=1)

    def _verify_email_code(self, code: str) -> bool:
        """Verify email confirmation code."""
        expected = os.environ.get("TRADING_EMAIL_CODE", "")
        if not expected:
            # Dev mode: accept any code
            return len(code) >= 4
        return hmac.compare_digest(code.strip(), expected.strip())


# Global singleton
switch = LiveTradingSwitch()
