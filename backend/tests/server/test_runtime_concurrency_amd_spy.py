"""Task 4, step 3: simultaneous AMD/SPY work and the liveness of /api/version.

Two things have to hold at once while two tickers are being read: the two reads
are genuinely concurrent (they overlap instead of queueing), and the rest of the
app stays answerable — /api/version is the cheapest unrelated read there is, so
if the event loop is held by chart work, that probe is what degrades first.

Scope limit, stated so nobody reads more into these numbers than they say: the
app under test is a bare FastAPI instance carrying only the chart and health
routers, built and closed inside each test. It runs with no lifespan, so none of
the running service's startup warm-up, middleware chain, auth, CORS, background
tasks or the real server's other routers are exercised. The liveness measured
here is the cost of serving this probe while chart work is in flight — nothing
about the deployed server's request path. The bounded store executor is not in
this path either (see the report).

Each read gets its own client, like two browser tabs, and the probe loop yields
between probes the way a real poller does: an in-process probe loop that never
yields would starve the very requests it is meant to observe, and this
characterization is about the app, not about the harness.
"""

from __future__ import annotations

import asyncio
import datetime
import threading
import time

import pytest

from tests.runtime_harness import (
    DUCKDB,
    LOOP_BURN_S,
    PROBE_INTERVAL_S,
    PROBE_LIVENESS_BOUND_S,
    PROBE_TIMEOUT_S,
    PUBLIC_READ,
    READ_TIMEOUT_S,
    VENDOR_DELAY_S,
    chart_read,
    client_for,
    hold_loop,
    runtime_env,
    version_probe,
    warm_calendar,
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
async def test_the_overlap_detector_separates_concurrent_from_serial_reads(runtime_env):
    """The concurrency assertion above must be able to fail.

    A control arm: the same two reads run one after the other must NOT report an
    overlap. Without this arm a broken detector that always answered "overlap"
    would keep the concurrency test green while two tickers silently queued, so
    the discriminating direction is pinned here rather than assumed.
    """
    recorder = runtime_env.recorder
    async with runtime_env.client() as client:
        serial_first = await chart_read(client, "AMD")
        serial_second = await chart_read(client, "SPY")

    assert serial_first[0].status_code == serial_second[0].status_code == 200
    overlap = recorder.any_overlap(PUBLIC_READ)
    assert not overlap, (
        f"two sequential reads were reported as overlapping, so the concurrency "
        f"assertion cannot distinguish concurrent from serial: {recorder.windows(PUBLIC_READ)}")
    # And the same detector on genuinely concurrent reads does report overlap,
    # from the same recorder, in the same test.
    concurrent = await _read_both(runtime_env)
    assert all(response.status_code == 200 for response, _wall in concurrent)
    assert recorder.any_overlap(PUBLIC_READ), (
        "the detector stopped seeing overlap once the reads were concurrent")
    print(f"OVERLAP serial_windows={recorder.windows(PUBLIC_READ)[:2]} "
          f"serial_overlap={overlap} "
          f"all_windows={[[round(a, 3), round(b, 3)] for a, b in recorder.windows(PUBLIC_READ)]}")


@pytest.mark.asyncio
async def test_version_stays_answered_while_two_tickers_are_read(runtime_env):
    """/api/version must serve every probe while two tickers are being read.

    Three contracts, not one:

    * every probe answers 200 with the process's startup stamp, and that stamp is
      identical on every probe — a running process reports its startup source,
      not a later checkout, so a differing body is a real failure and not a
      vacuous "sha is truthy" check;
    * no probe is held for anywhere near as long as one vendor read
      (PROBE_LIVENESS_BOUND_S, sized in runtime_harness.py below the ~0.18s
      synchronous calendar hold this path is known to pay);
    * neither chart read is left unfinished by the probing.
    """
    # Steady state is what this test asserts, so the one-time calendar build the
    # first read in a process pays is done before measuring rather than counted
    # as per-read cost. The cold build is measured by the cold-load probe.
    warm_calendar()

    probe_client = client_for(runtime_env.app)
    amd_client = client_for(runtime_env.app)
    spy_client = client_for(runtime_env.app)
    try:
        _status, _body, idle = await version_probe(probe_client)
        reads = [asyncio.create_task(chart_read(amd_client, "AMD")),
                 asyncio.create_task(chart_read(spy_client, "SPY"))]

        probes: list[float] = []
        bodies: list[dict] = []
        while any(not read.done() for read in reads):
            status, body, elapsed = await asyncio.wait_for(
                version_probe(probe_client), timeout=PROBE_TIMEOUT_S)
            probes.append(elapsed)
            bodies.append(body)
            assert status == 200, status
            await asyncio.sleep(PROBE_INTERVAL_S)

        done, pending = await asyncio.wait(reads, timeout=READ_TIMEOUT_S)
        assert not pending, f"a chart read never finished: {pending}"
        results = [read.result() for read in reads]
    finally:
        await asyncio.gather(probe_client.aclose(), amd_client.aclose(),
                             spy_client.aclose(), return_exceptions=True)

    assert probes, "no /api/version probe ran while the reads were in flight"
    for ticker, (response, _wall) in zip(("AMD", "SPY"), results, strict=True):
        assert response.status_code == 200, f"{ticker}: {response.text}"

    # The startup stamp is stable and parseable, not merely present.
    for body in bodies:
        assert body == bodies[0], (
            f"/api/version changed its answer between probes: {bodies[0]} vs {body}")
        assert len(body["sha"]) >= 7, f"the startup stamp is not a commit id: {body}"
        datetime.datetime.fromisoformat(body["started_at"])

    worst = max(probes)
    assert worst < PROBE_LIVENESS_BOUND_S, (
        f"/api/version waited {worst:.6f}s while two tickers were read; the "
        f"bound is {PROBE_LIVENESS_BOUND_S:.3f}s, which is an order of magnitude "
        f"above the observed jitter (worst across runs: 0.004924s) and well below "
        f"the ~0.18s synchronous hold this path pays on its first read. A wait "
        f"this long means the event loop was held by chart work.")
    ordered = sorted(probes)
    print(f"VERSION idle={idle:.6f}s during_work n={len(probes)} "
          f"max={worst:.6f}s median={ordered[len(ordered) // 2]:.6f}s "
          f"bound={PROBE_LIVENESS_BOUND_S:.3f}s "
          f"worst/idle={worst / idle:.1f}x "
          f"vendor_spans={_fmt(runtime_env.recorder.stage(PUBLIC_READ))}")


@pytest.mark.asyncio
async def test_a_known_loop_hold_trips_the_liveness_bound(runtime_env):
    """The liveness bound must be able to fail, so it is held to a known hold.

    This is the control arm for the bound above. A 0.12s synchronous hold on the
    event loop — the same class of hold as the ~0.18s first-read calendar build,
    which the cold-load probe measures — is queued ahead of a /api/version probe
    with real chart work already in flight. The probe cannot be answered until
    the hold ends, so what the poller waited must exceed the bound. Queuing the
    hold first makes the ordering deterministic: no probe path inside the app is
    patched, and no run-to-run race decides the outcome.
    """
    warm_calendar()
    probe_client = client_for(runtime_env.app)
    read_client = client_for(runtime_env.app)
    try:
        read = asyncio.create_task(chart_read(read_client, "SPY"))
        await asyncio.sleep(0.01)
        assert not read.done(), "the chart read finished before the hold started"

        issued = time.perf_counter()
        hold = asyncio.create_task(hold_loop(LOOP_BURN_S))
        probe = asyncio.create_task(version_probe(probe_client))
        status, _body, probe_elapsed = await asyncio.wait_for(
            probe, timeout=PROBE_TIMEOUT_S)
        waited = time.perf_counter() - issued
        assert await asyncio.wait_for(hold, timeout=PROBE_TIMEOUT_S) is None, (
            "the control hold did not finish")

        response, _wall = await asyncio.wait_for(read, timeout=READ_TIMEOUT_S)
    finally:
        await asyncio.gather(probe_client.aclose(), read_client.aclose(),
                             return_exceptions=True)

    assert status == 200, status
    assert response.status_code == 200, response.text
    assert waited >= PROBE_LIVENESS_BOUND_S, (
        f"a probe queued behind a {LOOP_BURN_S:.2f}s hold on the event loop was "
        f"answered after {waited:.6f}s, so the {PROBE_LIVENESS_BOUND_S:.3f}s bound "
        f"in the steady-state test cannot detect a hold of this class — a hold of "
        f"~0.18s (the first-read calendar build) would go unnoticed")
    print(f"HOLD burn={LOOP_BURN_S:.2f}s waited={waited:.6f}s "
          f"probe_internal={probe_elapsed:.6f}s "
          f"bound={PROBE_LIVENESS_BOUND_S:.3f}s "
          f"vendor_span={_fmt(runtime_env.recorder.stage(PUBLIC_READ))}")


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
