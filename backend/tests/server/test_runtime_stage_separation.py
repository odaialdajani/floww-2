"""Stage-separated characterization of the cold chart read (Task 4, step 1).

One /api/heatseeker/price-history read is four different kinds of work, and this
file measures each one on its own clock instead of reporting one lumped request
time:

  public_read   the vendor round trip (broker.get_bars) for the requested window
  daily_bars    normalization of the returned daily series into candles
  calculation   build_history frame/scope/node derivation
  duckdb        the store reads (recorder summary + snapshot rows)

Everything runs offline against the vendor double and an isolated temporary
DuckDB file: no live service, no persistent store, no provider spend. The
numbers characterize this repository's code path, not the vendor's latency.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from tests.runtime_harness import (
    ADMISSION,
    BARS_STEP,
    CALCULATION,
    DAILY_BARS,
    DUCKDB,
    PUBLIC_READ,
    chart_read,
    runtime_env,
)

STAGES = (PUBLIC_READ, DAILY_BARS, CALCULATION, DUCKDB)


@pytest.mark.asyncio
async def test_each_stage_of_the_cold_read_is_measured_separately(runtime_env):
    """All four stages run, and each keeps its own wall-clock span."""
    recorder = runtime_env.recorder
    async with runtime_env.client() as client:
        response, elapsed = await chart_read(client, "SPY")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["price_status"] == "available", body["price_status"]
    assert len(body["frames"]) > 0, "the vendor series never reached the chart"

    for stage in STAGES:
        spans = recorder.stage(stage)
        assert spans, f"the {stage} stage was never measured for this read"
        print(f"STAGE {stage}: total={recorder.total(stage):.6f}s "
              f"max={recorder.maximum(stage):.6f}s spans={len(spans)} "
              f"threads={recorder.threads(stage)} labels={recorder.labels(stage)}")

    # The vendor double really served this ticker, exactly once.
    assert runtime_env.broker.calls == ["SPY"], runtime_env.broker.calls
    print(f"REQUEST wall={elapsed:.6f}s bars_step={recorder.total(BARS_STEP):.6f}s "
          f"admission={recorder.total(ADMISSION):.6f}s")


@pytest.mark.asyncio
async def test_the_store_stage_never_runs_on_the_event_loop_thread(runtime_env):
    """DuckDB work leaves the loop; calculation stays on the request thread.

    This route offloads its store reads to the loop's default pool. Its
    calculation span is NOT offloaded today, and this characterization records
    that arrangement instead of assuming either one. The contract that is
    pinned here is the store read: it must never occupy the event loop.
    """
    recorder = runtime_env.recorder
    loop_thread = threading.current_thread().name
    async with runtime_env.client() as client:
        await chart_read(client, "AMD")

    store_threads = recorder.threads(DUCKDB)
    assert store_threads, "no store read was measured"
    assert loop_thread not in store_threads, (
        f"a store read ran on the event loop thread {loop_thread}: "
        f"{recorder.stage(DUCKDB)}")
    print(f"LOOP thread={loop_thread} store_threads={store_threads} "
          f"calculation_threads={recorder.threads(CALCULATION)} "
          f"vendor_threads={recorder.threads(PUBLIC_READ)}")


@pytest.mark.asyncio
async def test_cold_and_repeat_reads_are_timed_separately(runtime_env):
    """A second read of the same ticker is a fresh read, not a stale answer.

    This route never serves a completed result from cache: the shared in-flight
    read only helps overlapping waiters. Both reads must therefore pay their own
    vendor cost, and the recorded spans must show two distinct reads.
    """
    recorder = runtime_env.recorder
    async with runtime_env.client() as client:
        cold, cold_wall = await chart_read(client, "SPY")
        warm, warm_wall = await chart_read(client, "SPY")

    assert cold.status_code == warm.status_code == 200
    assert runtime_env.broker.calls == ["SPY", "SPY"], runtime_env.broker.calls
    assert len(recorder.stage(PUBLIC_READ)) == 2, recorder.stage(PUBLIC_READ)
    for stage in (DAILY_BARS, CALCULATION, DUCKDB):
        assert len(recorder.stage(stage)) >= 2, (
            f"the repeat read skipped the {stage} stage: {recorder.stage(stage)}")
    print(f"COLD wall={cold_wall:.6f}s "
          f"vendor={recorder.total(PUBLIC_READ):.6f}s "
          f"daily_bars={recorder.total(DAILY_BARS):.6f}s "
          f"calculation={recorder.total(CALCULATION):.6f}s "
          f"duckdb={recorder.total(DUCKDB):.6f}s")
    print(f"WARM wall={warm_wall:.6f}s "
          f"vendor={[span['elapsed_s'] for span in recorder.stage(PUBLIC_READ)]} "
          f"daily_bars={[span['elapsed_s'] for span in recorder.stage(DAILY_BARS)]} "
          f"duckdb={[span['elapsed_s'] for span in recorder.stage(DUCKDB)]}")


@pytest.mark.asyncio
async def test_the_daily_bar_evidence_stage_reports_what_it_admitted(runtime_env):
    """The evidence span is measured on its own, whether it admits or refuses.

    A synthetic series is not a real session sequence, so the strict calendar
    validation in the evidence module is expected to refuse it. The point of
    this characterization is that the stage is visible: its cost is charged to
    this route's read, and its refusal is not mistaken for a missing stage.
    """
    recorder = runtime_env.recorder
    async with runtime_env.client() as client:
        response, _ = await chart_read(client, "SPY", days=30)

    assert response.status_code == 200, response.text
    evidence = [span for span in recorder.stage(DAILY_BARS)
                if span["label"] == "evidence"]
    extract = [span for span in recorder.stage(DAILY_BARS)
               if span["label"] == "extract"]
    assert evidence, "the daily-bar evidence stage never ran"
    assert extract, "the daily-bar extraction stage never ran"
    body = response.json()
    print(f"DAILY_BARS extract={[span['elapsed_s'] for span in extract]} "
          f"evidence={[span['elapsed_s'] for span in evidence]} "
          f"frames={len(body['frames'])}")


@pytest.mark.asyncio
async def test_the_cold_calendar_load_is_charged_to_the_first_read():
    """Cold-load path, measured in a fresh interpreter.

    The daily-bar evidence validation needs the exchange calendar, which the
    library builds on first use. That one-time build is therefore charged to
    whichever read first needs it, on that request's thread. An in-process test
    cannot reproduce it (the library keeps its own calendar), so this
    characterization runs the offline probe in a fresh interpreter and records
    the split: the first read pays the build, later reads pay only validation.
    """
    import json
    import subprocess
    import sys
    from pathlib import Path

    probe = Path(__file__).resolve().parents[2] / "scripts" / "runtime_cold_load_probe.py"
    assert probe.is_file(), f"the offline probe is missing: {probe}"

    completed = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, str(probe), "--days", "260", "--vendor-delay", "0"],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    report = json.loads(completed.stdout)

    assert report["first_read"]["status"] == 200, report["first_read"]
    assert report["repeat_read"]["status"] == 200, report["repeat_read"]
    cold_evidence = report["first_evidence_spans_s"]
    warm_evidence = report["later_evidence_spans_s"]
    assert cold_evidence and warm_evidence, report
    assert cold_evidence[0] >= 5 * warm_evidence[0], (
        f"the first read did not pay the one-time calendar build: "
        f"cold={cold_evidence[0]:.6f}s warm={warm_evidence[0]:.6f}s")

    stages = report["stages"]
    assert "MainThread" not in stages["duckdb"]["threads"], (
        "a store read ran on the request thread of the fresh interpreter")
    print(f"COLD-LOAD first_read={report['first_read']} "
          f"repeat_read={report['repeat_read']} "
          f"evidence_first={cold_evidence[0]:.6f}s "
          f"evidence_later={warm_evidence[0]:.6f}s "
          f"ratio={cold_evidence[0] / warm_evidence[0]:.1f}x")
    for name, summary in stages.items():
        print(f"COLD-LOAD stage {name}: spans={summary['spans']} "
              f"total={summary['total_s']:.6f}s max={summary['max_s']:.6f}s "
              f"threads={summary['threads']}")
