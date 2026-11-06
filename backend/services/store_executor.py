"""Bounded worker pool for DuckDB/store calls made off the event loop.

Store calls serialize on the shared DuckDB connection lock, and the recorder
holds that lock for a whole write transaction. Sending them to the loop's
default thread pool let those lock waiters fill that pool, so every unrelated
cheap offload queued behind them and the response times of unrelated routes
grew with the recorder transaction. Store work therefore gets its own pool
with a bounded worker count and a bounded queue. Pure CPU work that takes no
lock stays on the default pool.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from typing import Any

log = logging.getLogger(__name__)

# Workers run the admitted store calls. The queue slots bound how many calls
# may wait behind them: a caller that cannot be admitted within the timeout
# is refused instead of growing an unbounded queue.
STORE_WORKERS = 4
STORE_QUEUE_SLOTS = 8
# How long a caller may wait for an admission slot before it is refused with
# StoreBusy. Long enough to outlast a recorder write transaction, short
# enough that a saturated pool answers with a 503 instead of holding the
# request open for half a minute.
STORE_ADMISSION_TIMEOUT_S = 10.0

# Stable, non-secret body of the 503 the store pool returns under load. The
# pool's own refusal text stays internal: every handler that degrades on a
# refused store call answers with this constant instead.
STORE_BUSY_MESSAGE = "Store temporarily unavailable"


class StoreBusy(RuntimeError):
    """The bounded store pool could not admit the call."""


_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_shutting_down = False
# Number of drains currently running. The gate stays closed until the last
# drain finishes, so a second drain cannot reopen the pool while the first
# one is still joining its workers.
_drains = 0
# Admission gate per event loop. Keyed by the loop object, so a new loop
# never reuses the gate of a closed one. Closed loops are dropped on the next
# lookup. The map survives a drain: clearing it would hand the next caller a
# fresh full budget while the physical calls admitted before the drain are
# still running, which is exactly the over-admission the gate prevents.
_loop_slots: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def _submit(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
    """Queue one call on the pool, creating the pool on first use.

    The submit happens under the lock, so a concurrent drain cannot slip
    between the pool lookup and the submit: the call is either queued on the
    pool that the drain joins, or refused with StoreBusy.
    """
    global _executor
    with _lock:
        if _shutting_down:
            raise StoreBusy("store pool is shutting down")
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=STORE_WORKERS,
                                           thread_name_prefix="store-io")
        return _executor.submit(function, *args, **kwargs)


def _slots_for(loop: asyncio.AbstractEventLoop) -> asyncio.Semaphore:
    """One admission gate per event loop, sized to the pool and its queue."""
    with _lock:
        for closed in [known for known in _loop_slots if known.is_closed()]:
            del _loop_slots[closed]
        slots = _loop_slots.get(loop)
        if slots is None:
            slots = asyncio.Semaphore(STORE_WORKERS + STORE_QUEUE_SLOTS)
            _loop_slots[loop] = slots
        return slots


async def run_store(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one store call on the bounded store pool.

    The call never runs on the event loop. Admission is bounded: at most
    STORE_WORKERS + STORE_QUEUE_SLOTS calls are outstanding, and a caller
    that waits longer than the admission timeout gets StoreBusy rather than
    an unbounded wait.
    """
    loop = asyncio.get_running_loop()
    slots = _slots_for(loop)
    try:
        await asyncio.wait_for(slots.acquire(), timeout=STORE_ADMISSION_TIMEOUT_S)
    except TimeoutError as e:
        raise StoreBusy("store pool saturated") from e
    try:
        future = _submit(function, *args, **kwargs)
    except BaseException:
        slots.release()
        raise

    # The slot belongs to the physical call, not to its reader. A cancelled
    # reader must not return the slot while the store work is still running,
    # so the release is tied to the physical future and happens exactly once.
    released = False
    guard = threading.Lock()

    def _release_on_loop():
        nonlocal released
        with guard:
            if released:
                return
            released = True
        slots.release()

    def _physical_done(_done):
        if loop.is_closed():
            # The loop is gone and its gate goes with it, so the slot is
            # dropped rather than returned to a dead semaphore.
            return
        with suppress(RuntimeError):
            loop.call_soon_threadsafe(_release_on_loop)

    future.add_done_callback(_physical_done)
    wrapped = asyncio.wrap_future(future, loop=loop)
    try:
        # Shielded: a cancelled reader never cancels the physical store call.
        return await asyncio.shield(wrapped)
    finally:
        if future.done():
            # The physical call is finished: give its slot back before the
            # reader resumes, so a reader that asks again straight away is
            # not refused because the release is still queued on the loop.
            _release_on_loop()


async def close_store() -> None:
    """Join admitted store work and stop the pool."""
    await asyncio.to_thread(shutdown_store)


def shutdown_store() -> None:
    """Drain after request producers stop; no store is opened here.

    The drain is atomic with respect to new calls: the shutdown flag makes a
    call that arrives while the pool is draining fail fast with StoreBusy
    instead of creating a second pool whose threads this drain would never
    join. The drain claims the pool under the same lock, so a second drain
    can neither drain nor clear a pool it did not claim, and the gate stays
    closed until the last drain finishes. The pool reference is cleared when
    the drain claims it, so no worker outlives this call.
    """
    global _executor, _shutting_down, _drains
    with _lock:
        _drains += 1
        _shutting_down = True
        executor = _executor
        # Claim the pool: a later call cannot queue on it and a later drain
        # cannot clear it, so no pool is ever dropped without being joined.
        _executor = None
    try:
        if executor is not None:
            executor.shutdown(wait=True)
    finally:
        with _lock:
            _drains -= 1
            if _drains == 0:
                _shutting_down = False
