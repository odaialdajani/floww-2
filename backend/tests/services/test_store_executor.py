"""The bounded store pool must stay off the loop's default thread pool."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from services import store_executor


@pytest.fixture(autouse=True)
def _isolated_store_pool():
    """Every test owns the module's global pool and admission map.

    The pool is process-wide, so a test that leaves it running would hand the
    next test a pool it cannot reason about. Draining here also keeps the
    "no store worker outlives the app" property observable: after the
    fixture, no store worker thread is left behind.
    """
    yield
    store_executor.shutdown_store()
    store_executor._loop_slots.clear()


@pytest.mark.asyncio
async def test_a_store_call_runs_off_the_event_loop_thread():
    threads: list[threading.Thread] = []

    def _work():
        threads.append(threading.current_thread())
        return "ok"

    assert await store_executor.run_store(_work) == "ok"
    assert threads and threads[0] is not threading.main_thread()


@pytest.mark.asyncio
async def test_a_busy_default_pool_does_not_block_a_store_call():
    """A saturated default pool must not delay a store read."""
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="default-busy-test"))

    busy = threading.Event()
    release = threading.Event()

    def _hold():
        busy.set()
        release.wait(timeout=5)

    occupant = asyncio.create_task(asyncio.to_thread(_hold))
    try:
        for _ in range(200):
            if busy.is_set():
                break
            await asyncio.sleep(0.01)
        assert busy.is_set(), "the default pool was never occupied"

        assert await asyncio.wait_for(store_executor.run_store(lambda: "served"),
                                     timeout=5) == "served"
    finally:
        release.set()
        await asyncio.gather(occupant, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_saturated_store_pool_refuses_the_extra_call(monkeypatch):
    """The queue is bounded: the extra caller is refused, never queued."""
    monkeypatch.setattr(store_executor, "STORE_ADMISSION_TIMEOUT_S", 0.05)

    started = threading.Event()
    release = threading.Event()

    def _hold():
        started.set()
        release.wait(timeout=5)

    admitted = store_executor.STORE_WORKERS + store_executor.STORE_QUEUE_SLOTS
    holders = [asyncio.create_task(store_executor.run_store(_hold))
               for _ in range(admitted)]
    try:
        for _ in range(200):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set(), "the store pool never started a call"

        with pytest.raises(store_executor.StoreBusy):
            await store_executor.run_store(lambda: "never served")
    finally:
        release.set()
        await asyncio.gather(*holders, return_exceptions=True)


@pytest.mark.asyncio
async def test_the_store_pool_restarts_after_an_explicit_shutdown():
    await store_executor.close_store()
    assert await store_executor.run_store(lambda: "ok") == "ok"


def test_a_closed_event_loop_is_not_kept_in_the_admission_map():
    """A dead loop must not stay pinned by its admission semaphore.

    A semaphore that has to queue binds itself to the loop it queued on and
    then holds a strong reference to that loop. Weakref cleanup therefore
    never collected the entry: every loop that ever saturated the gate
    stayed alive for the life of the process.
    """
    first = asyncio.new_event_loop()
    try:
        slots = store_executor._slots_for(first)
        total = store_executor.STORE_WORKERS + store_executor.STORE_QUEUE_SLOTS

        async def _bind_to_the_loop():
            for _ in range(total):
                await slots.acquire()
            # This waiter has to queue, and queuing is what binds the
            # semaphore to this loop.
            waiter = asyncio.ensure_future(slots.acquire())
            await asyncio.sleep(0)
            waiter.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiter

        first.run_until_complete(_bind_to_the_loop())
    finally:
        first.close()

    assert first in store_executor._loop_slots, (
        "the closed loop left the admission map before the leak could show")

    second = asyncio.new_event_loop()
    try:
        second_slots = store_executor._slots_for(second)
    finally:
        second.close()

    assert second_slots is not slots, (
        "a new loop was handed the admission semaphore of a closed loop")
    assert first not in store_executor._loop_slots, (
        "a closed event loop stayed pinned in the admission map")


def test_a_call_on_a_new_loop_works_after_the_previous_loop_closed():
    """A semaphore bound to a dead loop cannot be awaited from a new one."""
    first = asyncio.new_event_loop()
    try:
        assert first.run_until_complete(
            store_executor.run_store(lambda: "ok")) == "ok"
    finally:
        first.close()

    second = asyncio.new_event_loop()
    try:
        assert second.run_until_complete(
            store_executor.run_store(lambda: "ok")) == "ok"
    finally:
        second.close()


@pytest.mark.asyncio
async def test_a_call_that_arrives_during_the_shutdown_is_refused():
    """A call during the drain must fail fast, never open a second pool.

    The drain and the pool hand-off have to be atomic: a call that slipped
    between them would create a pool whose threads the shutdown never joins,
    so a store worker would outlive the app.
    """
    started = threading.Event()
    release = threading.Event()

    def _hold():
        started.set()
        release.wait(timeout=10)
        return "held"

    holder = asyncio.create_task(store_executor.run_store(_hold))
    try:
        for _ in range(200):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set(), "the store pool never started a call"

        shutdown = threading.Thread(target=store_executor.shutdown_store)
        shutdown.start()
        try:
            for _ in range(200):
                if getattr(store_executor, "_shutting_down", False):
                    break
                await asyncio.sleep(0.01)
            assert getattr(store_executor, "_shutting_down", False), (
                "the shutdown never announced that it was draining, so a call "
                "arriving during the drain could open a second pool")

            refused = False
            try:
                await store_executor.run_store(lambda: "never served")
            except store_executor.StoreBusy:
                refused = True
            assert refused, (
                "a call that arrived during the shutdown was served by a "
                "second pool whose threads the shutdown never joins")
        finally:
            release.set()
            shutdown.join(timeout=30)
            assert not shutdown.is_alive(), "the shutdown never finished"
    finally:
        release.set()
        await asyncio.gather(holder, return_exceptions=True)

    assert store_executor._executor is None, (
        "the drained pool was not cleared after the shutdown")
    assert await store_executor.run_store(lambda: "ok") == "ok"


@pytest.mark.asyncio
async def test_a_cancelled_caller_keeps_its_slot_until_the_store_call_finishes(monkeypatch):
    """A cancelled reader must not hand its slot back while the write runs.

    The slot belongs to the physical store call. If a cancelled waiter
    returned its slot early, the pool could admit more work than its bounded
    queue allows, and the cancelled write would still be running.
    """
    monkeypatch.setattr(store_executor, "STORE_ADMISSION_TIMEOUT_S", 0.05)
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    def _hold():
        started.set()
        release.wait(timeout=10)
        completed.set()
        return "held"

    admitted = store_executor.STORE_WORKERS + store_executor.STORE_QUEUE_SLOTS
    holders = [asyncio.create_task(store_executor.run_store(_hold))
               for _ in range(admitted)]
    try:
        assert await asyncio.to_thread(started.wait, 5), "the store pool never started a call"

        cancelled = holders[0]
        cancelled.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cancelled
        assert not completed.is_set(), (
            "the physical store call was cancelled with its reader")

        with pytest.raises(store_executor.StoreBusy):
            await store_executor.run_store(lambda: "never served")
    finally:
        release.set()
        await asyncio.gather(*holders, return_exceptions=True)

    assert await store_executor.run_store(lambda: "ok") == "ok", (
        "the slot of the cancelled call never came back")


@pytest.mark.asyncio
async def test_the_slot_is_returned_when_the_store_call_raises():
    """A failing store call must give its slot back like a successful one."""
    loop = asyncio.get_running_loop()
    slots = store_executor._slots_for(loop)
    before = slots._value

    def _boom():
        raise RuntimeError("synthetic store failure")

    with pytest.raises(RuntimeError, match="synthetic store failure"):
        await store_executor.run_store(_boom)

    assert slots._value == before, (
        "the slot of a failed store call was not returned")


@pytest.mark.asyncio
async def test_a_store_call_still_finishes_when_its_loop_is_closed():
    """Closing the loop must not abandon a physical store call."""
    loop = asyncio.new_event_loop()
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def _hold():
        started.set()
        release.wait(timeout=10)
        finished.set()
        return "held"

    async def _read():
        return await store_executor.run_store(_hold)

    def _drive():
        asyncio.set_event_loop(loop)
        # The loop may be stopped while its physical store reader finishes.
        with contextlib.suppress(RuntimeError):
            loop.run_until_complete(_read())

    driver = threading.Thread(target=_drive)
    driver.start()
    try:
        assert await asyncio.to_thread(started.wait, 5), "the store pool never started a call"
        # The reader's loop goes away while the physical call is still running.
        loop.call_soon_threadsafe(loop.stop)
        driver.join(timeout=10)
        release.set()
        assert await asyncio.to_thread(finished.wait, 5), (
            "the physical store call never completed after its loop closed")
    finally:
        release.set()
        driver.join(timeout=10)
        loop.close()


@pytest.mark.asyncio
async def test_a_second_drain_cannot_clear_a_pool_it_did_not_drain(monkeypatch):
    """The pool reference belongs to the drain that claimed it.

    A drain that clears the reference unconditionally can null out a pool that
    a later call already created, and that pool's threads would then be
    joined by nobody.
    """
    entered = threading.Event()
    release = threading.Event()
    drains: list[str] = []

    class _SlowPool:
        def shutdown(self, wait=True):
            drains.append(threading.current_thread().name)
            entered.set()
            release.wait(timeout=10)

    monkeypatch.setattr(store_executor, "_executor", _SlowPool())
    first = threading.Thread(target=store_executor.shutdown_store, name="drain-first")
    second = threading.Thread(target=store_executor.shutdown_store, name="drain-second")
    first.start()
    try:
        assert entered.wait(5), "the drain never started"
        second.start()
        second.join(timeout=5)
        assert store_executor._executor is None, (
            "the drain did not release its claim on the pool, so a second "
            "drain could clear a pool it never drained")
        assert len(drains) == 1, (
            "the pool was drained more than once: a second drain can clear a "
            "pool that a later call already created")
    finally:
        release.set()
        first.join(timeout=30)
        second.join(timeout=30)
        assert not first.is_alive(), "the first drain never finished"
        assert not second.is_alive(), "the second drain never finished"


@pytest.mark.asyncio
async def test_the_gate_stays_closed_until_the_last_drain_finishes():
    """A drain that finished must not reopen the gate for a running drain."""
    entered = threading.Event()
    release = threading.Event()

    class _SlowPool:
        def shutdown(self, wait=True):
            entered.set()
            release.wait(timeout=10)

    original = store_executor._executor
    store_executor._executor = _SlowPool()
    first = threading.Thread(target=store_executor.shutdown_store)
    second = threading.Thread(target=store_executor.shutdown_store)
    try:
        first.start()
        assert entered.wait(5), "the drain never started"
        second.start()
        second.join(timeout=10)
        assert not second.is_alive(), "the second drain never finished"
        # The first drain is still running, so the gate must stay closed.
        with pytest.raises(store_executor.StoreBusy):
            await store_executor.run_store(lambda: "never served")
    finally:
        release.set()
        first.join(timeout=30)
        second.join(timeout=30)
        store_executor._executor = original

    # With every drain finished the gate reopens.
    assert await store_executor.run_store(lambda: "ok") == "ok"


@pytest.mark.asyncio
async def test_a_drain_does_not_reset_the_admission_budget():
    """The admission gate must survive the drain.

    Clearing the map hands the next caller a fresh full budget while the
    physical calls admitted before the shutdown are still running, so the
    bounded pool can be over-admitted.
    """
    loop = asyncio.get_running_loop()
    slots = store_executor._slots_for(loop)

    await store_executor.close_store()

    assert store_executor._slots_for(loop) is slots, (
        "the drain reset the admission budget behind the outstanding calls")


@pytest.mark.asyncio
async def test_a_pool_created_after_a_drain_is_still_owned():
    """A pool created after a drain is joined by the next drain."""
    await store_executor.close_store()
    assert await store_executor.run_store(lambda: "ok") == "ok"
    assert store_executor._executor is not None

    await store_executor.close_store()

    assert store_executor._executor is None
    assert not [thread for thread in threading.enumerate()
                if thread.name.startswith("store-io")], (
        "a store worker outlived the drain that owned it")
