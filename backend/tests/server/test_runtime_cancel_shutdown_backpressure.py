"""Task 4, steps 4-5: cancellation, shutdown and backpressure acceptance.

Three acceptance properties are exercised at the boundary where a request can
walk away, the app can stop, or the bounded pool can refuse:

  * cancellation — a reader that walks away never cancels the shared work it
    joined, never strands a DuckDB handle, and never keeps an admission slot
    that its own physical call no longer holds;
  * shutdown — admitted store work drains (or is refused), no store worker
    outlives the drain, and unrelated reads stay answerable while it runs;
  * backpressure — a refusal is an explicit refusal: a documented status and
    message, never an empty successful answer that claims no data exists.

Everything runs offline on the shared harness doubles and isolated temporary
stores. No service is started, stopped, or contacted.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading

import pytest

from services import store_executor
from tests.runtime_harness import client_for, greeks_env, hold_pool, runtime_env


def _store_threads() -> list[str]:
    return sorted(thread.name for thread in threading.enumerate()
                  if thread.name.startswith("store-io"))


@pytest.fixture
def drained_pool():
    """Own the process-wide pool and admission map for the whole test."""
    yield
    with contextlib.suppress(Exception):
        store_executor.shutdown_store()
    store_executor._loop_slots.clear()
    assert not _store_threads(), "a store worker outlived this test"


# ── Cancellation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_cancelled_chart_reader_never_cancels_the_shared_work(runtime_env):
    """The second reader's data must survive the first reader walking away.

    The bars step joins one in-flight read per (ticker, window). A cancelled
    waiter therefore cannot cancel that shared work, cannot leak the budget slot
    it never owned, and must leave the other waiter's answer intact.
    """
    # Hold the vendor read open: a real round trip that has not answered yet.
    gate = runtime_env.broker.gate("SPY")
    first_client = client_for(runtime_env.app)
    second_client = client_for(runtime_env.app)
    try:
        first = asyncio.create_task(
            first_client.get("/api/heatseeker/price-history/SPY",
                             params={"days": 260}))
        for _ in range(200):
            if runtime_env.broker.entered.get("SPY", threading.Event()).is_set():
                break
            await asyncio.sleep(0.01)
        assert runtime_env.broker.entered["SPY"].is_set(), (
            "the first reader never reached the vendor read")
        # A second reader for the same window joins the in-flight read.
        second = asyncio.create_task(
            second_client.get("/api/heatseeker/price-history/SPY",
                              params={"days": 260}))
        await asyncio.sleep(0.05)

        first.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await first
        gate.set()
        response = await asyncio.wait_for(second, timeout=5.0)
    finally:
        gate.set()
        await asyncio.gather(first_client.aclose(), second_client.aclose(),
                             return_exceptions=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["price_status"] == "available", body["price_status"]
    # The shared read ran once for both waiters, not once per waiter.
    assert runtime_env.broker.calls == ["SPY"], runtime_env.broker.calls
    # No admission slot is left held by the work that finished.
    assert runtime_env.budget.status()["inflight"] == 0, (
        "the budget slot of the shared read was never released")


@pytest.mark.asyncio
async def test_a_cancelled_store_read_keeps_its_handle_and_its_slot(greeks_env,
                                                                   monkeypatch,
                                                                   drained_pool):
    """A cancelled store read returns its slot and strands no DuckDB handle.

    The admission slot belongs to the physical call, so a cancelled reader only
    gives it back when the call finishes; and the read-only handle the worker
    opened has to close there too, because DuckDB refuses a read-write open of
    the same file while a read-only handle is still held.
    """
    import duckdb

    import routes.greeks as greeks

    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    real_read = greeks._read_greeks_profile

    def _held_read(db_path, ticker):
        entered.set()
        release.wait(timeout=30)
        try:
            return real_read(db_path, ticker)
        finally:
            finished.set()

    monkeypatch.setattr(greeks, "_read_greeks_profile", _held_read)

    loop = asyncio.get_running_loop()
    before = store_executor._slots_for(loop)._value
    client = client_for(greeks_env.app)
    try:
        task = asyncio.create_task(client.get("/api/greeks/profile/SPY"))
        for _ in range(200):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set(), "the store read never started on a store worker"

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not finished.is_set(), (
            "the physical store call was cancelled with its reader")

        release.set()
        for _ in range(300):
            if finished.is_set() and store_executor._slots_for(loop)._value == before:
                break
            await asyncio.sleep(0.01)
    finally:
        await client.aclose()
    assert finished.is_set(), "the physical store call never completed"
    assert store_executor._slots_for(loop)._value == before, (
        "the cancelled read kept or lost an admission slot")

    # A read-write open of the same file is only possible once every read-only
    # handle the worker opened has been closed.
    writer = duckdb.connect(str(greeks_env.path))
    try:
        writer.execute("SELECT COUNT(*) FROM gflows_greeks").fetchone()
    finally:
        writer.close()


# ── Shutdown ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shutdown_drains_admitted_work_and_keeps_reads_answerable(runtime_env,
                                                                       drained_pool):
    """The drain joins admitted work, refuses new work, and never hangs.

    A second call arriving while the drain holds the pool is refused with the
    pool's own shutdown reason — never queued behind a drain that already owns
    the pool, and never served by a pool the drain would not join.
    """
    started = threading.Event()
    release = threading.Event()

    def _hold():
        started.set()
        release.wait(timeout=30)
        return "held"

    holder = asyncio.create_task(store_executor.run_store(_hold))
    try:
        assert await asyncio.to_thread(started.wait, 5), "the store call never started"

        drain = asyncio.create_task(store_executor.close_store())
        await asyncio.sleep(0.05)
        assert store_executor._shutting_down, "the drain never announced itself"

        # Unrelated reads stay answerable while the drain runs.
        async with runtime_env.client() as client:
            status, body, elapsed = await runtime_env.version(client)
        assert status == 200 and body["sha"], body
        assert elapsed < 5.0, f"an unrelated read waited on the drain: {elapsed:.3f}s"

        refused = None
        try:
            await store_executor.run_store(lambda: "never served")
        except store_executor.StoreBusy as exc:
            refused = str(exc)
        assert refused is not None, "a call during the drain was admitted"
        assert "shutting down" in refused, (
            f"the refusal did not name the drain as its cause: {refused}")
    finally:
        release.set()
        await asyncio.gather(holder, drain, return_exceptions=True)

    assert await store_executor.run_store(lambda: "ok") == "ok", (
        "the pool did not restart after the drain")


@pytest.mark.asyncio
async def test_no_store_worker_outlives_the_drain(drained_pool):
    """Every worker thread the pool started is joined by the drain."""
    started = threading.Event()
    release = threading.Event()

    def _hold():
        started.set()
        release.wait(timeout=30)

    holders = [asyncio.create_task(store_executor.run_store(_hold))
               for _ in range(store_executor.STORE_WORKERS)]
    try:
        assert await asyncio.to_thread(started.wait, 5), "the workers never started"
        assert _store_threads(), "no store worker thread was observed"
        release.set()
        await asyncio.gather(*holders, return_exceptions=True)
    finally:
        release.set()
        with contextlib.suppress(Exception):
            await store_executor.close_store()
    assert not _store_threads(), f"store workers outlived the drain: {_store_threads()}"


# ── Backpressure ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_saturated_pool_answers_backpressure_not_an_empty_answer(greeks_env,
                                                                       monkeypatch,
                                                                       drained_pool):
    """A saturated store pool is an explicit 503, never an empty profile.

    The bounded pool refuses the call when its admission budget is full. The
    caller must be able to tell that refusal apart from "this ticker has no
    Greeks data", which the same route answers with a 404.
    """
    loop = asyncio.get_running_loop()
    started = threading.Event()
    release = threading.Event()
    holders = hold_pool(store_executor, started, release)
    monkeypatch.setattr(store_executor, "STORE_ADMISSION_TIMEOUT_S", 0.05)
    try:
        assert await asyncio.to_thread(started.wait, 5), "the pool never saturated"
        assert store_executor._slots_for(loop)._value == 0, (
            "the admission budget was not exhausted, so the read is not under "
            "backpressure and this test would prove nothing")

        async with client_for(greeks_env.app) as client:
            busy = await client.get("/api/greeks/profile/SPY")
            # An unrelated read must stay answerable while the pool is full.
            version = await client.get("/api/version")

        assert busy.status_code == 503, busy.text
        body = busy.json()
        assert body["error"] == "Store temporarily unavailable", body
        assert "strikes" not in body, (
            "a refused read answered with an empty Greeks profile")
        assert version.status_code == 200 and version.json()["sha"], version.text
    finally:
        release.set()
        await asyncio.gather(*holders, return_exceptions=True)

    # With the pool drained, the same read succeeds on the isolated store.
    async with client_for(greeks_env.app) as client:
        recovered = await client.get("/api/greeks/profile/SPY")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["n_strikes"] == 5, recovered.json()


@pytest.mark.asyncio
async def test_a_saturated_pool_never_answers_a_successful_empty_history(greeks_env,
                                                                        monkeypatch,
                                                                        drained_pool):
    """Backpressure must not be reported as 'this ticker has no data'.

    The same route distinguishes an unseeded ticker (404) from a refused store
    call (503). Under saturation the answer has to stay the 503: a 404 would
    tell the caller the ticker was never seeded, which the refusal cannot know.
    """
    started = threading.Event()
    release = threading.Event()
    holders = hold_pool(store_executor, started, release)
    monkeypatch.setattr(store_executor, "STORE_ADMISSION_TIMEOUT_S", 0.05)
    try:
        assert await asyncio.to_thread(started.wait, 5), "the pool never saturated"
        async with client_for(greeks_env.app) as client:
            busy = await client.get("/api/greeks/profile/UNSEEDED")
            assert busy.status_code == 503, busy.text
            assert busy.json()["error"] == "Store temporarily unavailable", busy.text
    finally:
        release.set()
        await asyncio.gather(*holders, return_exceptions=True)

    async with client_for(greeks_env.app) as client:
        missing = await client.get("/api/greeks/profile/UNSEEDED")
    assert missing.status_code == 404, missing.text
    assert "No Greeks data" in missing.text, missing.text
