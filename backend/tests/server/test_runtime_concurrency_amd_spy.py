"""Task 4, step 3: simultaneous AMD/SPY work and the liveness of /api/version.

Two things have to hold at once while two tickers are being read: the two reads
are genuinely concurrent (they overlap instead of queueing), and the rest of the
app stays answerable — /api/version is the cheapest unrelated read there is, so
if the event loop is held by chart work, that probe is what degrades first.

Each read gets its own client, like two browser tabs, and the probe loop yields
between probes the way a real poller does: an in-process probe loop that never
yields would starve the very requests it is meant to observe, and this
characterization is about the app, not about the harness.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from tests.runtime_harness import (
    DUCKDB,
    PROBE_INTERVAL_S,
    PROBE_TIMEOUT_S,
    PUBLIC_READ,
    READ_TIMEOUT_S,
    VENDOR_DELAY_S,
    chart_read,
    client_for,
    runtime_env,
    version_probe,
)


def _fmt(spans) -> list[float]:
    return [round(span["elapsed_s"], 6) for span in spans]


async def _read_both(env):
    """Start both ticker reads on their own clients and wait for them."""
    clients = [client_for(env.app) for _ in ("AMD", "SPY")]
    try:
        reads = [asyncio.create_task(chart_read(client, ticker))
                 for client, ticker in zip(clients, ("AMD", "SPY"), strict=True)]
        done, pending = await asyncio.wait(reads, timeout=READ_TIMEOUT_S)
        assert not pending, f"a chart read never finished: {pending}"
        results = [read.result() for read in reads]
    finally:
        for client in clients:
            await client.aclose()
    return results


@pytest.mark.asyncio
async def test_two_tickers_are_read_concurrently(runtime_env):
    """AMD and SPY overlap in time; neither waits for the other's vendor read."""
    recorder = runtime_env.recorder
    results = await _read_both(runtime_env)

    for ticker, (response, _wall) in zip(("AMD", "SPY"), results, strict=True):
        assert response.status_code == 200, f"{ticker}: {response.text}"
        body = response.json()
        assert body["price_status"] == "available", f"{ticker}: {body['price_status']}"
        assert len(body["frames"]) > 0, f"{ticker} produced no candles"

    windows = recorder.windows(PUBLIC_READ)
    assert len(windows) == 2, recorder.stage(PUBLIC_READ)
    assert recorder.any_overlap(PUBLIC_READ), (
        f"the two vendor reads did not overlap: {windows}")
    assert runtime_env.broker.calls == ["AMD", "SPY"], runtime_env.broker.calls
    print(f"CONCURRENT vendor_windows={[[round(a, 3), round(b, 3)] for a, b in windows]}")
    print(f"CONCURRENT vendor_spans={_fmt(recorder.stage(PUBLIC_READ))} "
          f"read_walls={[round(wall, 6) for _response, wall in results]} "
          f"vendor_delay={VENDOR_DELAY_S}s")


@pytest.mark.asyncio
async def test_version_stays_answered_while_two_tickers_are_read(runtime_env):
    """/api/version must not wait on chart work, and must never be refused.

    The probe has to answer with the process's startup stamp while both reads
    are in flight, and it must not be held for as long as one vendor read: the
    event loop still has to serve it between the awaits of the work in flight.
    """
    probe_client = client_for(runtime_env.app)
    try:
        _status, _body, idle = await version_probe(probe_client)
        reads = [asyncio.create_task(chart_read(client_for(runtime_env.app), ticker))
                 for ticker in ("AMD", "SPY")]

        probes: list[float] = []
        while any(not read.done() for read in reads):
            status, body, elapsed = await asyncio.wait_for(
                version_probe(probe_client), timeout=PROBE_TIMEOUT_S)
            probes.append(elapsed)
            assert status == 200, status
            assert body["sha"], body
            await asyncio.sleep(PROBE_INTERVAL_S)

        done, pending = await asyncio.wait(reads, timeout=READ_TIMEOUT_S)
        assert not pending, f"a chart read never finished: {pending}"
        results = [read.result() for read in reads]
    finally:
        await probe_client.aclose()

    assert probes, "no /api/version probe ran while the reads were in flight"
    for ticker, (response, _wall) in zip(("AMD", "SPY"), results, strict=True):
        assert response.status_code == 200, f"{ticker}: {response.text}"

    worst = max(probes)
    assert worst < VENDOR_DELAY_S, (
        f"/api/version waited {worst:.6f}s while two tickers were read; it must "
        f"not be held for as long as one vendor read ({VENDOR_DELAY_S}s)")
    ordered = sorted(probes)
    print(f"VERSION idle={idle:.6f}s during_work n={len(probes)} "
          f"max={worst:.6f}s median={ordered[len(ordered) // 2]:.6f}s "
          f"vendor_spans={_fmt(runtime_env.recorder.stage(PUBLIC_READ))}")


@pytest.mark.asyncio
async def test_the_store_reads_of_both_tickers_run_off_the_request_loop(runtime_env):
    """Both store reads run off the loop, on the pool's threads.

    The store reads of the two tickers are offloaded, so pool threads serve
    them. The observation recorded here is which threads ran them: if a change
    ever moved them back onto the request thread, this test names the thread.
    """
    recorder = runtime_env.recorder
    await _read_both(runtime_env)

    loop_thread = threading.current_thread().name
    store_threads = recorder.threads(DUCKDB)
    assert store_threads, "no store read was measured"
    assert loop_thread not in store_threads, (
        f"a store read ran on the event loop thread {loop_thread}")
    print(f"STORE read_threads={store_threads} loop_thread={loop_thread} "
          f"spans={len(recorder.stage(DUCKDB))} "
          f"spans_s={_fmt(recorder.stage(DUCKDB))}")
