"""
backend/services/slo_tracker.py

SLO (Service Level Objective) tracking + error budget burn rate alerts.
Implements Google SRE Book Ch. 4 patterns.

SLOs tracked:
  - API availability: 99.9% (43.2 min downtime/month budget)
  - API latency: p99 < 200ms
  - Market-data ingestion uptime: 99% during market hours (Public.com path)
  - WebSocket message delivery: 99.99%
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("slo_tracker")


@dataclass
class SLOTarget:
    name: str
    target_pct: float  # e.g. 99.9 for 99.9%
    window_hours: int = 720  # 30 days default
    description: str = ""

    @property
    def error_budget_pct(self) -> float:
        return 100.0 - self.target_pct


@dataclass
class SLIMeasurement:
    timestamp: float
    is_success: bool
    latency_ms: float = 0.0


@dataclass
class ErrorBudget:
    slo_name: str
    total_measurements: int
    error_count: int
    budget_remaining_pct: float
    burn_rate: float  # > 1.0 means burning faster than sustainable
    alert: bool


# ── SLO Definitions ───────────────────────────────────────────────────────────

SLO_DEFINITIONS = [
    SLOTarget("api_availability", 99.9, 720, "API endpoint availability"),
    SLOTarget("api_latency_p99", 99.0, 720, "API p99 latency < 200ms"),
    SLOTarget("ingestion_uptime", 99.0, 720, "Market-data ingestion uptime during market hours"),
    SLOTarget("ws_delivery", 99.99, 720, "WebSocket message delivery"),
]


class SLOTracker:
    """Track SLOs with sliding window error budget."""

    def __init__(self, window_seconds: int = 86400):
        self._windows: dict[str, deque[SLIMeasurement]] = {}
        self._window_seconds = window_seconds
        for slo in SLO_DEFINITIONS:
            self._windows[slo.name] = deque()

    def record(self, slo_name: str, is_success: bool, latency_ms: float = 0.0) -> None:
        """Record a measurement for an SLO."""
        if slo_name not in self._windows:
            self._windows[slo_name] = deque()
        self._windows[slo_name].append(SLIMeasurement(
            timestamp=time.time(),
            is_success=is_success,
            latency_ms=latency_ms,
        ))
        self._cleanup(slo_name)

    def _cleanup(self, slo_name: str) -> None:
        """Remove measurements outside the window."""
        cutoff = time.time() - self._window_seconds
        dq = self._windows[slo_name]
        while dq and dq[0].timestamp < cutoff:
            dq.popleft()

    def get_error_budget(self, slo_name: str) -> ErrorBudget | None:
        """Calculate error budget for an SLO."""
        slo = next((s for s in SLO_DEFINITIONS if s.name == slo_name), None)
        if not slo:
            return None

        dq = self._windows.get(slo_name, deque())
        total = len(dq)
        if total == 0:
            return ErrorBudget(slo_name, 0, 0, 100.0, 0.0, False)

        errors = sum(1 for m in dq if not m.is_success)
        error_rate = errors / total
        budget_used_pct = error_rate / (slo.error_budget_pct / 100.0) * 100
        budget_remaining = max(0, 100.0 - budget_used_pct)

        # Burn rate: how fast we're consuming budget relative to sustainable rate
        # burn_rate > 1.0 means we'll exhaust budget before window ends
        window_fraction = self._window_seconds / (slo.window_hours * 3600)
        burn_rate = budget_used_pct / 100.0 / window_fraction if window_fraction > 0 else 0.0

        # Alert if burn rate > 1.64 (Google SRE: fast burn)
        alert = burn_rate > 1.64 and budget_remaining < 50.0

        return ErrorBudget(
            slo_name=slo_name,
            total_measurements=total,
            error_count=errors,
            budget_remaining_pct=round(budget_remaining, 2),
            burn_rate=round(burn_rate, 2),
            alert=alert,
        )

    def get_all_budgets(self) -> list[ErrorBudget]:
        """Get error budgets for all SLOs."""
        return [b for b in (self.get_error_budget(s.name) for s in SLO_DEFINITIONS) if b]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all SLOs for the dashboard."""
        budgets = self.get_all_budgets()
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "slos": [
                {
                    "name": b.slo_name,
                    "total": b.total_measurements,
                    "errors": b.error_count,
                    "budget_remaining_pct": b.budget_remaining_pct,
                    "burn_rate": b.burn_rate,
                    "alert": b.alert,
                }
                for b in budgets
            ],
        }


# Global singleton
tracker = SLOTracker()
