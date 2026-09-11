"""
backend/services/public_budget.py

Upstream budget gate for the Public.com path (2026-09-04, Phase 9 control).

One fetch_chain_from_public_api(t, N) fans out to ~2+N live Public calls.
Nothing throttled that fan-out (the cvserver path has TTL + coalescing +
429 cool-down + hourly budget; Public had none). This module is the missing
equivalent: token bucket + in-flight cap + per-host 429 cooldown, with
fake-clock-friendly signatures so the contract is pytest-pinned.

Applied at:
  - services/fetch_coordinator.py::FetchCoordinator.fetch (acquire before
    the upstream task is created; BudgetExhausted -> structured degraded
    dict, never an exception to callers).
  - services/cache_router.py::CacheRouter.get_chain (budget-degraded fetch
    + existing stale entry -> serve stale with stale_reason).
  - services/public_api_adapter.py (HTTP 429 sightings -> record_429).

Tuning defaults assume a ~60 req/min retail key. Confirm against the
Public dashboard and adjust CAPACITY/REFILL (proposal packet
.public-path-budget.md has the verify-first steps).
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

logger = logging.getLogger(__name__)

CAPACITY = 60
REFILL_PER_SEC = 1.0
MAX_INFLIGHT = 4
COOLDOWN_BASE_SEC = 15.0
COOLDOWN_MAX_SEC = 300.0
CACHE_MAX_HOSTS = 64


class BudgetExhausted(Exception):
    """Raised when the Public-path budget refuses a fetch.

    Carries retry_after (seconds) so routes can answer with structured
    degraded payloads instead of 429/500.
    """

    def __init__(self, retry_after: int = 5, reason: str = "budget_exhausted"):
        super().__init__(f"Public-path budget exhausted (retry in {retry_after}s)")
        self.retry_after = retry_after
        self.reason = reason


class PublicBudget:
    """Token bucket + in-flight cap + 429 cooldown for Public upstream calls.

    All time goes through ``time.monotonic()`` unless an explicit ``now``
    is passed, so tests can drive refill/cooldown with a fake clock.
    """

    def __init__(
        self,
        capacity: int = CAPACITY,
        refill_per_sec: float = REFILL_PER_SEC,
        max_inflight: int = MAX_INFLIGHT,
    ) -> None:
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._refill = float(refill_per_sec)
        self._max_inflight = int(max_inflight)
        self._inflight = 0
        self._cooldowns: dict[str, float] = {}
        self._cooldown_hits: dict[str, int] = {}
        self._cool_set_at: dict[str, float] = {}
        self._guard = asyncio.Lock()
        self._last = time.monotonic()
        self.total_ok = 0
        self.total_limited = 0
        self.total_429 = 0
        self.total_errors = 0

    def _refill_locked(self, now: float) -> None:
        self._tokens = min(
            self._capacity, self._tokens + max(0.0, now - self._last) * self._refill
        )
        self._last = now

    def _cooldown_left_locked(self, host: str, now: float) -> float:
        return max(0.0, self._cooldowns.get(host, 0.0) - now)

    async def acquire(self, host: str = "public", now: float | None = None) -> None:
        """Take one token + one in-flight slot. Raises BudgetExhausted."""
        await self.acquire_n(1, host, now)

    async def acquire_n(self, n: int, host: str = "public", now: float | None = None) -> None:
        """Atomically debit n tokens + one in-flight slot. Raises BudgetExhausted.

        A chain fetch fans out to ~2+N upstream calls (expirations + quotes +
        one chain per expiry) — debiting the fan-out (B4) instead of one token
        per sweep keeps the 60/min assumption honest. All-or-nothing: on
        refusal NO tokens are debited (no partial spend to account for).
        """
        n = max(1, int(n))
        now = time.monotonic() if now is None else now
        async with self._guard:
            self._refill_locked(now)
            left = self._cooldown_left_locked(host, now)
            if left > 0:
                self.total_limited += 1
                raise BudgetExhausted(retry_after=int(left) + 1, reason="host_cooldown")
            if self._inflight >= self._max_inflight:
                self.total_limited += 1
                raise BudgetExhausted(retry_after=5, reason="inflight_cap")
            if self._tokens < float(n):
                self.total_limited += 1
                deficit = float(n) - self._tokens
                wait = int(deficit / self._refill) + 1 if self._refill > 0 else 60
                raise BudgetExhausted(retry_after=wait, reason="token_bucket")
            self._tokens -= float(n)
            self._inflight += 1

    def release(self) -> None:
        """Return one in-flight slot (call when the upstream call settles)."""
        self._inflight = max(0, self._inflight - 1)

    async def peek_available(self, now: float | None = None) -> float:
        """Refilled token count without spending (adaptive sizing reads this).

        Applies pending refill under the guard so idle time is honored;
        debits nothing, takes no slot. Racy by design (advisory only) —
        the atomic decision stays inside acquire/acquire_n.
        """
        now = time.monotonic() if now is None else now
        async with self._guard:
            self._refill_locked(now)
            return self._tokens

    def record_ok(self, host: str = "public", now: float | None = None) -> None:
        """A success clears any cooldown for the host — unless the success
        reflects lane state older than the 429 sighting (D5: a stale
        in-flight success finishing after a sibling's fresh 429 must not
        erase the still-active contract). Pass the request-start time as
        `now`; defaults to the current clock (sequential flow unchanged).
        """
        now = time.monotonic() if now is None else now
        self.total_ok += 1
        if self._cool_set_at.get(host, 0.0) <= now:
            self._cooldowns.pop(host, None)
            self._cool_set_at.pop(host, None)
            self._cooldown_hits.pop(host, None)

    def record_error(self, host: str = "public") -> int:
        """Record a non-429 upstream failure (transport/timeout/connect).

        Counts only — no cooldown (a single blip must not throttle the
        lane; repeated 429s still own the cooler). Without this, successes
        record but failures vanish and the success rate inflates, hiding
        outages from operators.
        """
        self.total_errors += 1
        return self.total_errors

    def record_429(
        self, host: str = "public", now: float | None = None, retry_after: int | None = None
    ) -> int:
        """Record an upstream 429. Returns the cooldown applied (seconds)."""
        now = time.monotonic() if now is None else now
        self.total_429 += 1
        if retry_after is not None:
            applied = max(1, int(retry_after))
        else:
            hits = self._cooldown_hits.get(host, 0) + 1
            self._cooldown_hits[host] = hits
            applied = int(min(COOLDOWN_MAX_SEC, COOLDOWN_BASE_SEC * (2 ** (hits - 1))))
            applied += random.randint(0, min(5, applied))
        if len(self._cooldowns) >= CACHE_MAX_HOSTS:
            self._cooldowns.pop(next(iter(self._cooldowns)))
        self._cooldowns[host] = now + applied
        self._cool_set_at[host] = now
        logger.warning("Public-path 429 on %s — cooling down %ss", host, applied)
        return applied

    def reset(self, now: float | None = None) -> None:
        """Restore a full bucket: tokens, slots, cooldowns, counters.

        Test isolation only — production never calls this (the singleton
        is the shared quota). Without it, modules sharing the singleton
        exhaust each other's tokens and order-dependence follows.
        """
        now = time.monotonic() if now is None else now
        self._tokens = float(self._capacity)
        self._inflight = 0
        self._cooldowns.clear()
        self._cooldown_hits.clear()
        self._cool_set_at.clear()
        self.total_ok = 0
        self.total_limited = 0
        self.total_429 = 0
        self.total_errors = 0
        self._last = now

    def status(self, now: float | None = None) -> dict[str, Any]:
        """Observability snapshot (admin endpoint shape)."""
        now = time.monotonic() if now is None else now
        return {
            "capacity": self._capacity,
            "available": round(self._tokens, 2),
            "inflight": self._inflight,
            "max_inflight": self._max_inflight,
            "cooldowns": {
                h: max(0, int(ts - now)) for h, ts in self._cooldowns.items()
            },
            "totals": {
                "ok": self.total_ok,
                "limited": self.total_limited,
                "rate_limited_429": self.total_429,
                "errors": self.total_errors,
            },
        }


# Process singleton — the whole point is one shared budget per worker.
budget = PublicBudget()
