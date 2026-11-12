"""Pure calculations must not pause unrelated request-loop work."""

import asyncio
import ctypes
import sys
import time
from concurrent.futures import Future

import pytest

from services.cpu_execution import close_cpu, run_cpu, shutdown_cpu


async def wait_for_jobs(executor, count):
    async with asyncio.timeout(2):
        while len(executor.jobs) < count:
            await asyncio.sleep(0.001)


def holds_interpreter_lock(seconds):
    # PyDLL retains Python's interpreter lock across the native call. This
    # reproduces a calculation dependency which a thread cannot isolate.
    if sys.platform == "win32":
        sleeper = ctypes.PyDLL("kernel32").Sleep
        sleeper(ctypes.c_ulong(int(seconds * 1000)))
    else:
        sleeper = ctypes.PyDLL(None).usleep
        sleeper(ctypes.c_uint(int(seconds * 1_000_000)))
    return 42


def change_private_input(values):
    values["readings"].append(123.0)
    return values


def failing_calculation():
    raise ValueError("invalid calculation input")


@pytest.fixture(autouse=True)
def clean_executor():
    yield
    shutdown_cpu()


@pytest.mark.asyncio
async def test_native_calculation_cannot_pause_unrelated_request_loop():
    loop = asyncio.get_running_loop()
    ticks = []
    finished = asyncio.Event()

    async def reader():
        while not finished.is_set():
            ticks.append(loop.time())
            await asyncio.sleep(0.005)

    task = asyncio.create_task(reader())
    try:
        await asyncio.sleep(0.02)
        assert await run_cpu(holds_interpreter_lock, 0.3) == 42
        await asyncio.sleep(0.02)
    finally:
        finished.set()
        await task
    assert max(b - a for a, b in zip(ticks, ticks[1:], strict=False)) < 0.15


@pytest.mark.asyncio
async def test_calculation_owns_its_mutable_input_and_result():
    original = {"readings": [0.0, None, -2.0]}
    result = await run_cpu(change_private_input, original)
    assert original == {"readings": [0.0, None, -2.0]}
    assert result == {"readings": [0.0, None, -2.0, 123.0]}


@pytest.mark.asyncio
async def test_slow_calculation_startup_cannot_pause_request_loop(monkeypatch):
    import services.cpu_execution as execution

    class SlowStartingExecutor:
        def submit(self, function, value):
            time.sleep(0.3)
            future = Future()
            future.set_result(function(value))
            return future

        def shutdown(self, **kwargs):
            pass

    monkeypatch.setattr(execution, "ProcessPoolExecutor", lambda **kwargs: SlowStartingExecutor())
    ticks = []
    done = asyncio.Event()

    async def reader():
        while not done.is_set():
            ticks.append(asyncio.get_running_loop().time())
            await asyncio.sleep(0.005)

    task = asyncio.create_task(reader())
    try:
        await asyncio.sleep(0.02)
        assert await run_cpu(int, 42) == 42
        await asyncio.sleep(0.02)
    finally:
        done.set()
        await task
    assert max(b - a for a, b in zip(ticks, ticks[1:], strict=False)) < 0.15


@pytest.mark.asyncio
async def test_calculation_errors_reach_the_reader():
    with pytest.raises(ValueError, match="invalid calculation input"):
        await run_cpu(failing_calculation)


@pytest.mark.asyncio
async def test_aggregate_curve_matches_canonical_calculation_exactly():
    from services.gex_core import calc_aggregate_gex_curve

    contracts = [
        {"strike": 100.0, "oi": 100, "iv": 0.2, "T": 30 / 365, "type": "call"},
        {"strike": 105.0, "oi": 120, "iv": 0.3, "T": 30 / 365, "type": "put"},
    ]
    expected = calc_aggregate_gex_curve(102.0, contracts, "SPY")
    assert await run_cpu(calc_aggregate_gex_curve, 102.0, contracts, "SPY") == expected


@pytest.mark.asyncio
async def test_regime_retains_complete_partial_and_measured_zero_results():
    from services.solstice_regime import regime_at_spot

    contract = {"strike": 100.0, "oi": 100, "iv": 0.2, "T": 30 / 365, "type": "call", "gamma": 0.01}
    for changes in ({}, {"iv": None}, {"oi": 0}):
        contracts = [{**contract, **changes}]
        expected = regime_at_spot(102.0, contracts, "SPY")
        assert await run_cpu(regime_at_spot, 102.0, contracts, "SPY") == expected


@pytest.mark.asyncio
async def test_cancelled_reader_keeps_capacity_until_calculation_finishes(monkeypatch):
    import services.cpu_execution as execution

    class ControlledExecutor:
        def __init__(self):
            self.jobs = []

        def submit(self, function, value):
            future = Future()
            self.jobs.append((future, value))
            return future

        def shutdown(self, **kwargs):
            pass

    executor = ControlledExecutor()
    monkeypatch.setattr(execution, "ProcessPoolExecutor", lambda **kwargs: executor, raising=False)
    readers = [asyncio.create_task(run_cpu(int, value)) for value in range(5)]

    async def turns():
        for _ in range(20):
            await asyncio.sleep(0)

    try:
        await wait_for_jobs(executor, 4)
        assert len(executor.jobs) == 4, "calculation admission was not bounded"
        readers[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await readers[0]
        await turns()
        assert len(executor.jobs) == 4, "cancellation released capacity while work was still running"
        next(future for future, value in executor.jobs if value == 0).set_result(0)
        await wait_for_jobs(executor, 5)
        assert len(executor.jobs) == 5
        for future, value in executor.jobs:
            if not future.done():
                future.set_result(value)
        assert await asyncio.gather(*readers[1:]) == [1, 2, 3, 4]
    finally:
        for reader in readers:
            if not reader.done():
                reader.cancel()
        for future, value in executor.jobs:
            if not future.done():
                future.set_result(value)
        await asyncio.gather(*readers, return_exceptions=True)
        await turns()


@pytest.mark.asyncio
async def test_shutdown_joins_work_after_its_reader_is_cancelled(monkeypatch):
    import services.cpu_execution as execution

    class ControlledExecutor:
        def __init__(self):
            self.jobs = []
            self.closed = False

        def submit(self, function, value):
            future = Future()
            self.jobs.append((future, value))
            return future

        def shutdown(self, **kwargs):
            self.closed = True

    executor = ControlledExecutor()
    monkeypatch.setattr(execution, "ProcessPoolExecutor", lambda **kwargs: executor)
    reader = asyncio.create_task(run_cpu(int, 42))
    await wait_for_jobs(executor, 1)
    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader
    closing = asyncio.create_task(close_cpu())
    try:
        await asyncio.sleep(0.02)
        assert not closing.done()
        assert not executor.closed
    finally:
        executor.jobs[0][0].set_result(42)
        await closing
    assert executor.closed
