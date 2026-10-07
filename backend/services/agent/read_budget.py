"""Per-turn capability admission. Provider/model requests have separate ledgers.

A reservation is saved before dispatch. It is not evidence that a callback ran.
Worker entry is counted separately; unresolved work stays charged after timeout.
"""

from __future__ import annotations

import asyncio
import copy
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from services.agent.answer_sections import history_excluded, requests_history
from services.agent.contracts import validate_history_baseline

POLICY = "research-capabilities-1"
LIMIT = 8
PER_READ_SECONDS = 5
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="research-read")
_WORKERS = threading.BoundedSemaphore(4)
_CURRENT = ContextVar("research_read_budget", default=None)
_PLAN = ContextVar("research_read_plan", default=None)


class ReadDenied(Exception):
    """Requested evidence was not entered; its reason is safe to display."""


class ReadActivityUnavailable(Exception):
    """A durable reservation could not be confirmed; fail closed."""


def capability_plan(spec):
    if spec.get("price_only"):
        return set()
    question = spec.get("question", "")
    baseline = validate_history_baseline(spec.get("history_baseline"))
    dated_history = baseline is not None and not history_excluded(question)
    requested = set()
    if re.search(
        r"\b(?:structure|gamma|gex|flip|walls?|levels?|support|resistance|exposure|dealer|vanna|charm|air pockets?|pinning|max pain|put.?call)\b",
        question,
        re.I,
    ):
        requested.add("structure")
    if re.search(r"\b(?:volatility|vol|iv|skew|(?:expected|implied) moves?|realized|realised)\b", question, re.I):
        requested.add("volatility")
    if re.search(r"\b(?:flow|alerts?|activity|buyers?|sellers?)\b", question, re.I):
        requested.add("flow")
    if re.search(r"\b(?:chart|map|cell|selected|screen)\b", question, re.I):
        requested.add("map")
    broad = bool(re.search(r"\b(?:full|complete|overall|everything|checklist|all readings)\b", question, re.I))
    if not broad and dated_history:
        return requested
    if not broad and not requested and requests_history(question):
        return set()
    if broad or len(spec.get("tickers", [])) <= 1:
        return {"structure", "volatility", "flow", "map"}
    # A requested metric comparison needs context + that metric for each ticker.
    # Broad questions retain the broad reading but may exhaust the explicit cap.
    return requested or {"structure", "volatility", "flow", "map"}


@contextmanager
def budget_scope(budget, spec=None):
    token = _CURRENT.set(budget)
    plan = _PLAN.set(capability_plan(spec) if spec is not None else None)
    try:
        yield budget
    finally:
        _PLAN.reset(plan)
        _CURRENT.reset(token)


def current_budget():
    return _CURRENT.get()


def requested(capability):
    plan = _PLAN.get()
    return plan is None or capability in plan


class ReadBudget:
    def __init__(self, *, save=None, timeout=120):
        self.save = save
        self.deadline = time.monotonic() + timeout
        self._lock = threading.RLock()
        self._admission = asyncio.Lock()
        self.attempts = []
        self.denied = []
        self.closed = False
        self.memo = {}

    def state(self):
        with self._lock:
            return dict(
                policy=POLICY,
                limit=LIMIT,
                reserved=len(self.attempts),
                started=sum(a.get("started_at") is not None for a in self.attempts),
                attempts=copy.deepcopy(self.attempts),
                denied=copy.deepcopy(self.denied),
                closed=self.closed,
                entry_count_complete=self.closed,
            )

    def close(self):
        with self._lock:
            for attempt in self.attempts:
                if attempt["outcome"] == "reserved":
                    attempt["outcome"] = "not_started"
            self.closed = True
            return self.state()

    async def _save(self):
        if self.save is None:
            return
        try:
            confirmed = await self.save(self.state())
        except Exception as exc:
            raise ReadActivityUnavailable("Research activity could not be saved") from exc
        if not confirmed:
            raise asyncio.CancelledError()

    async def _reserve(self, capability, ticker, scope):
        async with self._admission:
            with self._lock:
                reason = (
                    "Question stopped"
                    if self.closed
                    else "Question time limit reached"
                    if time.monotonic() >= self.deadline
                    else "Question reached its eight-capability limit"
                    if len(self.attempts) >= LIMIT
                    else None
                )
                if reason:
                    if not self.closed and len(self.denied) < 32:
                        self.denied.append(dict(capability=capability, ticker=ticker, reason=reason))
                else:
                    attempt = dict(
                        id=len(self.attempts) + 1,
                        capability=capability,
                        ticker=ticker,
                        scope=scope,
                        reserved_at=datetime.now(UTC).isoformat(),
                        started_at=None,
                        ended_at=None,
                        outcome="reserved",
                        worker_unresolved=False,
                    )
                    self.attempts.append(attempt)
            if reason:
                if not self.closed:
                    await self._save()
                raise ReadDenied(reason)
            await self._save()
            with self._lock:
                if self.closed:
                    raise asyncio.CancelledError()
            return attempt

    def _start(self, attempt):
        with self._lock:
            if self.closed or time.monotonic() >= self.deadline:
                return False
            attempt.update(started_at=datetime.now(UTC).isoformat(), outcome="running", worker_unresolved=True)
            return True

    def _end(self, attempt, outcome, *, unresolved=False):
        with self._lock:
            if not self.closed:
                if attempt["outcome"] in {"timed_out", "cancelled"} and outcome in {"completed", "error"}:
                    attempt["worker_unresolved"] = False
                else:
                    attempt.update(
                        outcome=outcome, ended_at=datetime.now(UTC).isoformat(), worker_unresolved=unresolved
                    )

    async def sync(self, capability, ticker, callback, *args, scope=None, **kwargs):
        attempt = await self._reserve(capability, ticker, scope)
        if not _WORKERS.acquire(blocking=False):
            self._end(attempt, "worker_capacity")
            await self._save()
            raise ReadDenied("Research readers are still busy; this reading was not started")

        def invoke():
            try:
                if not self._start(attempt):
                    return False, ReadDenied("Question stopped before this reading started")
                try:
                    value = callback(*args, **kwargs)
                except Exception as exc:
                    self._end(attempt, "error")
                    return False, exc
                self._end(attempt, "completed")
                return True, value
            finally:
                _WORKERS.release()

        try:
            future = asyncio.wrap_future(_POOL.submit(invoke))
        except Exception:
            _WORKERS.release()
            self._end(attempt, "not_dispatched")
            await self._save()
            raise
        try:
            ok, result = await asyncio.wait_for(
                asyncio.shield(future), timeout=max(0, min(PER_READ_SECONDS, self.deadline - time.monotonic()))
            )
        except (TimeoutError, asyncio.CancelledError) as exc:
            self._end(
                attempt, "timed_out" if isinstance(exc, TimeoutError) else "cancelled", unresolved=not future.done()
            )
            # Outer cancellation finalizes from the in-memory state; do not delay it.
            if isinstance(exc, TimeoutError):
                await self._save()
            raise
        await self._save()
        if not ok:
            raise result
        return result

    async def async_call(self, capability, ticker, callback, *args, scope=None, memo_key=None, **kwargs):
        if memo_key is not None and memo_key in self.memo:
            return copy.deepcopy(self.memo[memo_key])
        attempt = await self._reserve(capability, ticker, scope)
        if not self._start(attempt):
            raise ReadDenied("Question stopped before this reading started")
        try:
            result = await asyncio.wait_for(
                callback(*args, **kwargs), timeout=max(0, min(PER_READ_SECONDS, self.deadline - time.monotonic()))
            )
        except (TimeoutError, asyncio.CancelledError) as exc:
            self._end(attempt, "timed_out" if isinstance(exc, TimeoutError) else "cancelled")
            if isinstance(exc, TimeoutError):
                await self._save()
            raise
        except Exception:
            self._end(attempt, "error")
            await self._save()
            raise
        self._end(attempt, "completed")
        await self._save()
        if memo_key is not None:
            self.memo[memo_key] = copy.deepcopy(result)
        return result
