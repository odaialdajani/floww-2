"""Execution boundary for trusted, pure calculation functions."""

import asyncio
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from weakref import WeakKeyDictionary

_lock = threading.Lock()
_executor_lock = threading.Lock()
_executor = None
_loop_slots = WeakKeyDictionary()
_loop_work = WeakKeyDictionary()


def _get_executor():
    global _executor
    with _executor_lock:
        if _executor is None:
            # Spawn imports the pure callable's module, never a forked copy
            # of the app's database clients or running event loop.
            _executor = ProcessPoolExecutor(
                max_workers=2, mp_context=multiprocessing.get_context("spawn"),
            )
        return _executor


async def _execute(function, args, slots):
    try:
        # Creating the pool and spawning its first process can perform I/O.
        # Own submission as well as calculation independently of the reader.
        future = await asyncio.to_thread(lambda: _get_executor().submit(function, *args))
        return await asyncio.wrap_future(future)
    finally:
        slots.release()


async def run_cpu(function, *args):
    """Run trusted pure work with bounded admission and private inputs."""
    loop = asyncio.get_running_loop()
    with _lock:
        slots = _loop_slots.setdefault(loop, asyncio.Semaphore(4))
        work = _loop_work.setdefault(loop, set())
    await slots.acquire()
    task = loop.create_task(_execute(function, args, slots))
    work.add(task)

    def completed(done):
        # A cancelled reader cannot release capacity while its calculation
        # is still running, or repeated cancels would bypass the bound.
        work.discard(done)
        if not done.cancelled():
            done.exception()

    task.add_done_callback(completed)
    return await asyncio.shield(task)


async def close_cpu():
    """Join admitted work, including readers cancelled during pool startup."""
    with _lock:
        work = tuple(_loop_work.get(asyncio.get_running_loop(), ()))
    if work:
        await asyncio.gather(*(asyncio.shield(task) for task in work), return_exceptions=True)
    await asyncio.to_thread(shutdown_cpu)


def shutdown_cpu():
    """Drain after request producers stop; no store is opened here."""
    global _executor
    with _executor_lock:
        executor, _executor = _executor, None
    with _lock:
        _loop_slots.clear()
        _loop_work.clear()
    if executor is not None:
        executor.shutdown(wait=True, cancel_futures=True)
