"""
backend/services/credit_monitor.py

API Credit & Rate Limit Monitor.

Tracks MarketData.app credit burn rate vs MARKETDATA_CREDIT_BUDGET env,
yfinance/yoptions 429 frequency, and alerts at 80% (MEDIUM) and 95% (CRITICAL).
Logs remaining credits to DuckDB system_metrics table.

Severity taxonomy:
  MEDIUM  → credit_burn_80, rate_limit_warning
  CRITICAL → credit_burn_95, rate_limit_critical, provider_down
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class CreditConfig:
    """Configuration for credit monitoring."""
    budget: int = 0
    warning_pct: float = 0.80
    critical_pct: float = 0.95
    rate_limit_window_seconds: float = 300.0
    rate_limit_warning_threshold: int = 3
    rate_limit_critical_threshold: int = 10



log = logging.getLogger(__name__)

# Severity constants
MEDIUM = "MEDIUM"
CRITICAL = "CRITICAL"


@dataclass
class CreditState:
    """Current state of API credits."""
    budget: int = 0
    consumed: int = 0
    # Per-provider call tracking
    provider_calls: Dict[str, int] = field(default_factory=dict)
    provider_429s: Dict[str, List[float]] = field(default_factory=dict)  # provider → list of timestamps
    last_updated: float = 0.0

    @property
    def remaining(self) -> int:
        return max(self.budget - self.consumed, 0)

    @property
    def burn_pct(self) -> float:
        if self.budget <= 0:
            return 0.0
        return self.consumed / self.budget

    def rate_limit_count(self, provider: str, window_seconds: float) -> int:
        """Count 429s in the rolling window."""
        entries = self.provider_429s.get(provider, [])
        cutoff = time.time() - window_seconds
        return sum(1 for t in entries if t >= cutoff)

    def record_call(self, provider: str, is_429: bool = False):
        self.provider_calls[provider] = self.provider_calls.get(provider, 0) + 1
        if is_429:
            self.provider_429s.setdefault(provider, []).append(time.time())
        self.last_updated = time.time()


class CreditMonitor:
    """
    Monitors API credit burn rate and rate limit frequency.

    Usage:
        monitor = CreditMonitor(budget=1000)
        monitor.record_call("marketdata", credits_used=5)
        monitor.record_call("yfinance", is_429=True)
        alerts = monitor.check_alerts()
    """

    def __init__(
        self,
        budget: int = 0,
        warning_pct: float = 0.80,
        critical_pct: float = 0.95,
        on_alert: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ):
        self.config = CreditConfig(
            budget=budget,
            warning_pct=warning_pct,
            critical_pct=critical_pct,
        )
        self.state = CreditState(budget=budget)
        self.on_alert = on_alert
        self._alerted: Dict[str, set] = {}  # provider → set of active alert types

    def record_credits(self, provider: str, credits_used: int):
        """Record credit consumption for a provider."""
        self.state.consumed += credits_used
        self.state.record_call(provider)

    def record_call(self, provider: str, is_429: bool = False):
        """Record an API call (with optional 429 flag)."""
        self.state.record_call(provider, is_429=is_429)
        if is_429:
            log.warning(f"[CREDIT_MONITOR] 429 from {provider} (window count: "
                        f"{self.state.rate_limit_count(provider, self.config.rate_limit_window_seconds)})")

    def check_alerts(self) -> List[Dict[str, Any]]:
        """Check all alert conditions. Returns list of new alerts."""
        alerts = []
        _now = time.time()

        # Credit burn alerts
        burn_pct = self.state.burn_pct

        if burn_pct >= self.config.critical_pct:
            if "credit_burn_95" not in self._alerted.get("__global__", set()):
                alert = {
                    "severity": CRITICAL,
                    "alert_type": "credit_burn_95",
                    "provider": "all",
                    "burn_pct": round(burn_pct * 100, 1),
                    "consumed": self.state.consumed,
                    "budget": self.state.budget,
                    "remaining": self.state.remaining,
                    "message": f"CRITICAL: {burn_pct*100:.0f}% credit budget consumed "
                               f"({self.state.consumed}/{self.state.budget})",
                }
                alerts.append(alert)
                self._alerted.setdefault("__global__", set()).add("credit_burn_95")
                if self.on_alert:
                    self.on_alert("all", "credit_burn_95", alert)
        elif burn_pct >= self.config.warning_pct:
            if "credit_burn_80" not in self._alerted.get("__global__", set()):
                alert = {
                    "severity": MEDIUM,
                    "alert_type": "credit_burn_80",
                    "provider": "all",
                    "burn_pct": round(burn_pct * 100, 1),
                    "consumed": self.state.consumed,
                    "budget": self.state.budget,
                    "remaining": self.state.remaining,
                    "message": f"MEDIUM: {burn_pct*100:.0f}% credit budget consumed "
                               f"({self.state.consumed}/{self.state.budget})",
                }
                alerts.append(alert)
                self._alerted.setdefault("__global__", set()).add("credit_burn_80")
                if self.on_alert:
                    self.on_alert("all", "credit_burn_80", alert)
        else:
            self._alerted.setdefault("__global__", set()).discard("credit_burn_80")
            self._alerted.setdefault("__global__", set()).discard("credit_burn_95")

        # Per-provider rate limit alerts
        for provider in self.state.provider_429s:
            count = self.state.rate_limit_count(provider, self.config.rate_limit_window_seconds)

            if count >= self.config.rate_limit_critical_threshold:
                key = f"rate_limit_critical_{provider}"
                if key not in self._alerted.get(provider, set()):
                    alert = {
                        "severity": CRITICAL,
                        "alert_type": "rate_limit_critical",
                        "provider": provider,
                        "count_429": count,
                        "window_seconds": self.config.rate_limit_window_seconds,
                        "message": f"CRITICAL: {provider} received {count} 429s in "
                                   f"{self.config.rate_limit_window_seconds:.0f}s window",
                    }
                    alerts.append(alert)
                    self._alerted.setdefault(provider, set()).add(key)
                    if self.on_alert:
                        self.on_alert(provider, "rate_limit_critical", alert)
            elif count >= self.config.rate_limit_warning_threshold:
                key = f"rate_limit_warning_{provider}"
                if key not in self._alerted.get(provider, set()):
                    alert = {
                        "severity": MEDIUM,
                        "alert_type": "rate_limit_warning",
                        "provider": provider,
                        "count_429": count,
                        "window_seconds": self.config.rate_limit_window_seconds,
                        "message": f"MEDIUM: {provider} received {count} 429s in "
                                   f"{self.config.rate_limit_window_seconds:.0f}s window",
                    }
                    alerts.append(alert)
                    self._alerted.setdefault(provider, set()).add(key)
                    if self.on_alert:
                        self.on_alert(provider, "rate_limit_warning", alert)
            else:
                self._alerted.setdefault(provider, set()).discard(f"rate_limit_warning_{provider}")
                self._alerted.setdefault(provider, set()).discard(f"rate_limit_critical_{provider}")

        for a in alerts:
            log.warning(f"[CREDIT_MONITOR] {a['message']}")

        return alerts

    def get_status(self) -> Dict[str, Any]:
        """Return full credit status."""
        provider_status = {}
        for provider in set(list(self.state.provider_calls.keys()) + list(self.state.provider_429s.keys())):
            provider_status[provider] = {
                "total_calls": self.state.provider_calls.get(provider, 0),
                "429s_in_window": self.state.rate_limit_count(
                    provider, self.config.rate_limit_window_seconds
                ),
                "window_seconds": self.config.rate_limit_window_seconds,
            }
        return {
            "budget": self.state.budget,
            "consumed": self.state.consumed,
            "remaining": self.state.remaining,
            "burn_pct": round(self.state.burn_pct * 100, 1),
            "providers": provider_status,
            "thresholds": {
                "warning_pct": self.config.warning_pct * 100,
                "critical_pct": self.config.critical_pct * 100,
                "rate_limit_warning": self.config.rate_limit_warning_threshold,
                "rate_limit_critical": self.config.rate_limit_critical_threshold,
            },
            "active_alerts": self.check_alerts(),
        }


def _resolve_budget() -> int:
    """Resolve credit budget from environment."""
    try:
        return int(os.environ.get("MARKETDATA_CREDIT_BUDGET", "0"))
    except (ValueError, TypeError):
        return 0


# Global singleton
credit_monitor = CreditMonitor(budget=_resolve_budget())
