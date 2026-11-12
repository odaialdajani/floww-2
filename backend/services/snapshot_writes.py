"""Bound ordinary snapshot writes before allocating tasks or worker-queue entries.

A slot belongs to the physical write, not its asyncio waiter. Cancelling a
request cannot release capacity while its database transaction is still running.
Admission always precedes the freeze, so the pending-count check happens before
the payload is copied and the refused counter stays exact. Both entry points
freeze at admission: the synchronous one on the calling thread, the async one
on a worker thread, so the copy never runs on the event loop and the recorded
snapshot is always the payload the caller submitted, never a later mutation
of it.
Importing this module starts no threads, network reads, capture loops or orders.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)
MAX_PENDING_SNAPSHOT_WRITES = 8


def _freeze_pair(payload, capability):
    """Take both copies in one hop onto the worker thread.

    The copy is pure CPU work that takes no lock, so it belongs on the
    default pool, never on the bounded store pool.
    """
    return copy.deepcopy(payload), copy.deepcopy(capability)


def _failed_worker(error: BaseException):
    """A worker that fails with the given error.

    A payload that cannot be copied is a failed write, not a lost slot: the
    caller still gets a job whose receipt says the write failed.
    """

    def _worker():
        raise error

    return _worker


@dataclass(frozen=True)
class SnapshotWrite:
    _future: Future
    snapshot_id: str

    def receipt(self) -> dict[str, Any]:
        base = {"snapshot_id": self.snapshot_id}
        if not self._future.done():
            return {"status": "queued", **base}
        try:
            recorded_id = self._future.result()
        except Exception:
            return {"status": "failed", "reason": "write_failed", **base}
        if not recorded_id:
            return {"status": "failed", "reason": "no_observation_id", **base}
        if recorded_id != self.snapshot_id:
            return {"status": "failed", "reason": "identity_mismatch", **base}
        return {"status": "committed", **base}

    async def wait(self) -> dict[str, Any]:
        # The receipt reports a typed failure, never database details.
        with suppress(Exception):
            await asyncio.shield(asyncio.wrap_future(self._future))
        return self.receipt()


class SnapshotWrites:
    def __init__(self, max_pending: int = MAX_PENDING_SNAPSHOT_WRITES):
        if type(max_pending) is not int or max_pending < 1:
            raise ValueError("max_pending must be a positive integer")
        self._max_pending = max_pending
        self._lock = threading.Lock()
        self._pending: set[Future] = set()
        # A slot is held from admission until the physical write is queued, so
        # a reader that is still freezing its payload keeps its reservation.
        self._reserved = 0
        # Recorder transactions already serialize on the shared connection lock.
        # One worker avoids wasting the general executor on waiting DB writers.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="snapshot-recorder")
        self._committed = 0
        self._failed = 0
        self._refused = 0

    def _admit(self) -> bool:
        """Reserve one physical slot. Refusal is counted, never silent."""
        with self._lock:
            if len(self._pending) + self._reserved >= self._max_pending:
                self._refused += 1
                return False
            self._reserved += 1
            return True

    def _release(self) -> None:
        with self._lock:
            self._reserved -= 1

    def _enqueue(self, worker, args, snapshot_id) -> SnapshotWrite:
        """Queue one physical job and register it as pending.

        The admission reservation is dropped in the same critical section that
        adds the job to the pending set, so the admitted-slot count can never
        drift: an admitted job is always either pending or released. A job
        that could not even be queued releases the slot it was admitted with.
        """
        with self._lock:
            try:
                future = self._executor.submit(worker, *args)
            except BaseException:
                self._reserved -= 1
                raise
            self._reserved -= 1
            self._pending.add(future)
        job = SnapshotWrite(future, snapshot_id)

        def finished(done):
            receipt = job.receipt()  # Also consumes a physical write exception.
            with self._lock:
                self._pending.discard(done)
                if receipt["status"] == "committed":
                    self._committed += 1
                else:
                    self._failed += 1
            if receipt["status"] != "committed":
                log.warning("snapshot write unacknowledged: %s", receipt.get("reason"))

        # A completed future runs callbacks inline: never attach under _lock.
        future.add_done_callback(finished)
        return job

    def submit(self, conn, payload: dict, query_key: str, snapshot_id: str,
               *, capability: dict | None = None) -> SnapshotWrite | None:
        """Synchronous entry point: admit, freeze here, enqueue.

        The freeze stays on the calling thread, so the recorded payload is the
        one that was admitted and never a later mutation of it.
        """
        if not self._admit():
            return None
        try:
            frozen = copy.deepcopy(payload)
            frozen_capability = copy.deepcopy(capability)
        except BaseException:
            self._release()
            raise
        return self._enqueue(self._record,
                             (conn, frozen, query_key, snapshot_id, frozen_capability),
                             snapshot_id)

    async def submit_async(self, conn, payload: dict, query_key: str, snapshot_id: str,
                           *, capability: dict | None = None) -> SnapshotWrite | None:
        """Async entry point: admit, freeze off the loop, enqueue.

        The copy is the heaviest part of a submit, so it runs on a worker
        thread instead of the event loop. It is still taken at admission: the
        recorded snapshot is the payload the caller submitted, never a later
        mutation of it. Admission precedes the freeze, so the pending-count
        check happens before the copy, the refused counter stays exact, and
        the admitted slot is released on every path.
        """
        if not self._admit():
            return None
        try:
            frozen, frozen_capability = await asyncio.to_thread(
                _freeze_pair, payload, capability)
        except asyncio.CancelledError:
            # A cancelled reader must not hold the slot it was admitted with.
            # The abandoned copy finishes on its own thread; it touches no
            # shared state, only the caller's payload.
            self._release()
            raise
        except Exception as error:
            # A copy that fails is a failed write, not a lost slot.
            return self._enqueue(_failed_worker(error), (), snapshot_id)
        except BaseException:
            self._release()
            raise
        return self._enqueue(self._record,
                             (conn, frozen, query_key, snapshot_id, frozen_capability),
                             snapshot_id)

    @staticmethod
    def _record(conn, payload, query_key, snapshot_id, capability):
        from services.heatmap_history import record_capability, record_snapshot

        recorded_id = record_snapshot(conn, payload, query_key, snapshot_id)
        if recorded_id and capability is not None:
            try:
                record_capability(conn, payload.get("ticker"), "heatmap_build", **capability)
            except Exception:
                log.debug("snapshot committed; capability observation failed")
        return recorded_id

    def status(self) -> dict[str, int]:
        with self._lock:
            return {"max_pending": self._max_pending, "pending": len(self._pending),
                    "committed": self._committed, "failed": self._failed, "refused": self._refused}

    async def drain(self) -> None:
        with self._lock:
            pending = list(self._pending)
        if pending:
            # Shield each physical operation even when the shutdown join expires.
            await asyncio.gather(*(asyncio.shield(asyncio.wrap_future(f)) for f in pending),
                                 return_exceptions=True)

    def shutdown(self) -> None:
        """Join an owned test/standalone writer; never abort accepted writes."""
        self._executor.shutdown(wait=True)


snapshot_writes = SnapshotWrites()
