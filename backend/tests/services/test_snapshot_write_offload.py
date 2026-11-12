"""The async snapshot submit must copy its payload off the event loop.

The payload can carry up to 2000 contracts plus the grid and the metrics, so
the deep copy is the heaviest part of a submit. The async entry point used to
take that copy on the event-loop thread, which bought no offload at all.

The admission contract must survive the move: the pending-count check still
happens BEFORE the copy, the refused counter stays exact, and an admitted slot
is never leaked - not when the copy fails, not when the write fails.
"""

from __future__ import annotations

import asyncio
import threading
from threading import Event

import pytest

from services import heatmap_history
from services.snapshot_writes import SnapshotWrites


class _CountingPayload(dict):
    """A payload that reports where it was copied."""

    def __init__(self, *args, copies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._copies = copies if copies is not None else []

    def __deepcopy__(self, memo):
        self._copies.append(threading.current_thread())
        return dict(self)


@pytest.mark.asyncio
async def test_the_async_submit_copies_the_payload_off_the_event_loop(monkeypatch):
    """The copy must run on the recorder worker, never on the loop thread."""
    writer = SnapshotWrites(max_pending=1)
    loop_thread = threading.current_thread()
    copies: list[threading.Thread] = []

    monkeypatch.setattr(heatmap_history, "record_snapshot",
                        lambda conn, payload, query_key, snapshot_id=None: snapshot_id)
    monkeypatch.setattr(heatmap_history, "record_capability", lambda *a, **k: None)
    try:
        job = await writer.submit_async(
            object(), _CountingPayload({"grid": {"value": 1}}, copies=copies),
            "query", "snap_offloaded")
        assert job is not None
        receipt = await job.wait()
        assert receipt == {"status": "committed", "snapshot_id": "snap_offloaded"}
    finally:
        writer.shutdown()

    assert copies, "the payload was never copied"
    assert all(thread is not loop_thread for thread in copies), (
        "the payload was copied on the event-loop thread")


@pytest.mark.asyncio
async def test_the_async_submit_checks_the_pending_count_before_the_copy(monkeypatch):
    """A refused submit must not copy the payload it just refused."""
    writer = SnapshotWrites(max_pending=1)
    started = Event()
    release = Event()
    copies: list[threading.Thread] = []

    def _blocked_write(conn, payload, query_key, snapshot_id=None):
        started.set()
        assert release.wait(5)
        return snapshot_id

    monkeypatch.setattr(heatmap_history, "record_snapshot", _blocked_write)
    monkeypatch.setattr(heatmap_history, "record_capability", lambda *a, **k: None)
    try:
        first = await writer.submit_async(
            object(), _CountingPayload({"a": 1}, copies=copies), "query", "snap_first")
        assert first is not None
        assert await asyncio.to_thread(started.wait, 2)

        before = len(copies)
        second = await writer.submit_async(
            object(), _CountingPayload({"b": 2}, copies=copies), "query", "snap_second")
        assert second is None, "the second submit was admitted past the cap"
        assert len(copies) == before, (
            "the refused submit copied its payload: the pending-count check "
            "did not happen before the copy")
        assert writer.status()["refused"] == 1, writer.status()
        assert writer.status()["pending"] == 1, writer.status()

        release.set()
        assert (await first.wait())["status"] == "committed"
        await writer.drain()
        assert writer.status()["pending"] == 0, writer.status()
    finally:
        release.set()
        writer.shutdown()


@pytest.mark.asyncio
async def test_a_failing_freeze_releases_the_admitted_slot(monkeypatch):
    """A copy that raises must not leak the slot it was admitted with."""
    writer = SnapshotWrites(max_pending=1)

    class _BadPayload(dict):
        def __deepcopy__(self, memo):
            raise RuntimeError("synthetic copy failure")

    monkeypatch.setattr(heatmap_history, "record_snapshot",
                        lambda conn, payload, query_key, snapshot_id=None: snapshot_id)
    monkeypatch.setattr(heatmap_history, "record_capability", lambda *a, **k: None)
    try:
        job = await writer.submit_async(object(), _BadPayload({"a": 1}), "query", "snap_bad")
        assert job is not None
        receipt = await job.wait()
        assert receipt == {"status": "failed", "reason": "write_failed",
                           "snapshot_id": "snap_bad"}
        await writer.drain()
        status = writer.status()
        assert status["pending"] == 0, status
        assert status["failed"] == 1, status

        # The slot came back: the next submit is admitted, not refused.
        after = await writer.submit_async(object(), {"a": 1}, "query", "snap_after")
        assert after is not None, "the failed freeze leaked its admitted slot"
        assert (await after.wait())["status"] == "committed"
    finally:
        writer.shutdown()


@pytest.mark.asyncio
async def test_the_async_submit_records_the_payload_as_of_admission(monkeypatch):
    """The recorded snapshot must be the payload the submit was admitted with.

    The copy may be taken off the event loop, but it may not be deferred to
    the recorder worker. Between the admission and the worker's turn the
    caller can mutate the payload it passed - the heatmap build holds live
    references to the metrics, the strikes and the grid - and the recorded
    snapshot would then describe something the caller never submitted.
    """
    writer = SnapshotWrites(max_pending=2)
    started = Event()
    release = Event()
    recorded: list[dict] = []

    def _write(conn, payload, query_key, snapshot_id=None):
        if snapshot_id == "snap_blocker":
            started.set()
            assert release.wait(10)
        recorded.append(payload)
        return snapshot_id

    monkeypatch.setattr(heatmap_history, "record_snapshot", _write)
    monkeypatch.setattr(heatmap_history, "record_capability", lambda *a, **k: None)
    try:
        blocker = await writer.submit_async(object(), {"a": 1}, "query", "snap_blocker")
        assert blocker is not None
        assert await asyncio.to_thread(started.wait, 5), "the recorder never started"

        payload = {"ticker": "SPY", "grid": {"value": 1}}
        subject = await writer.submit_async(object(), payload, "query", "snap_subject")
        assert subject is not None

        # The caller mutates what it handed over, after the submit returned.
        payload["ticker"] = "MUTATED"
        payload["grid"]["value"] = 99

        release.set()
        assert (await subject.wait())["status"] == "committed"
        await writer.drain()
    finally:
        release.set()
        writer.shutdown()

    subjects = [p for p in recorded if p.get("ticker")]
    assert subjects, "the subject payload was never recorded"
    assert subjects[0]["ticker"] == "SPY", (
        "the recorded snapshot describes a payload the caller had already "
        "mutated: the copy was taken after the admission")
    assert subjects[0]["grid"]["value"] == 1, (
        "the recorded snapshot carries a later mutation of the submitted grid")


@pytest.mark.asyncio
async def test_a_cancelled_async_submit_does_not_leak_its_slot(monkeypatch):
    """A cancelled submit must give the slot it was admitted with back.

    The async entry point now has an await point: a reader that is cancelled
    while its payload is being frozen must not hold the slot forever.
    """
    writer = SnapshotWrites(max_pending=1)
    entered = Event()
    release = Event()

    class _BlockingPayload(dict):
        def __deepcopy__(self, memo):
            entered.set()
            assert release.wait(10)
            return dict(self)

    monkeypatch.setattr(heatmap_history, "record_snapshot",
                        lambda conn, payload, query_key, snapshot_id=None: snapshot_id)
    monkeypatch.setattr(heatmap_history, "record_capability", lambda *a, **k: None)
    try:
        task = asyncio.create_task(writer.submit_async(
            object(), _BlockingPayload({"a": 1}), "query", "snap_cancelled"))
        assert await asyncio.to_thread(entered.wait, 5), "the copy never started"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()

        after = await writer.submit_async(object(), {"b": 2}, "query", "snap_after")
        assert after is not None, (
            "the cancelled submit leaked the slot it was admitted with")
        assert (await after.wait())["status"] == "committed"
    finally:
        release.set()
        writer.shutdown()


@pytest.mark.asyncio
async def test_the_synchronous_submit_still_freezes_on_the_calling_thread(monkeypatch):
    """The sync entry point keeps its old contract: the copy is immediate."""
    writer = SnapshotWrites(max_pending=1)
    loop_thread = threading.current_thread()
    copies: list[threading.Thread] = []

    monkeypatch.setattr(heatmap_history, "record_snapshot",
                        lambda conn, payload, query_key, snapshot_id=None: snapshot_id)
    monkeypatch.setattr(heatmap_history, "record_capability", lambda *a, **k: None)
    try:
        job = writer.submit(
            object(), _CountingPayload({"grid": {"value": 1}}, copies=copies),
            "query", "snap_sync")
        assert job is not None
        assert copies == [loop_thread], copies
        assert (await job.wait())["status"] == "committed"
    finally:
        writer.shutdown()
