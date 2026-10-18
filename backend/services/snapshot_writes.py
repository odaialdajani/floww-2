"""Bound ordinary snapshot writes before allocating tasks or worker-queue entries.

A slot belongs to the physical write, not its asyncio waiter. Cancelling a
request cannot release capacity while its database transaction is still running.
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
        # Recorder transactions already serialize on the shared connection lock.
        # One worker avoids wasting the general executor on waiting DB writers.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="snapshot-recorder")
        self._committed = 0
        self._failed = 0
        self._refused = 0

    def submit(self, conn, payload: dict, query_key: str, snapshot_id: str,
               *, capability: dict | None = None) -> SnapshotWrite | None:
        with self._lock:
            if len(self._pending) >= self._max_pending:
                self._refused += 1
                return None
            # Admission precedes the deep copy and the executor's own queue.
            frozen = copy.deepcopy(payload)
            future = self._executor.submit(self._record, conn, frozen, query_key,
                                           snapshot_id, copy.deepcopy(capability))
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
