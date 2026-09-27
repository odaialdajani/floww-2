"""Failed/uncertain batch accounting and orderly write completion on stop."""

import asyncio
import threading
from unittest.mock import Mock

import pytest

from services.ingestion_pipeline import IngestionPipeline

TABLES = ("ticks", "chains", "lob_snapshots", "lob_depth")
METRICS = ("ticks_inserted", "chains_inserted", "lob_inserted", "lob_depth_inserted")


def enqueue_all(pipe):
    for enqueue in (pipe.enqueue_tick, pipe.enqueue_chain, pipe.enqueue_lob, pipe.enqueue_lob_depth):
        for _ in range(2):
            enqueue({"symbol": "SPY", "last": 500.0, "volume": 1})


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_table", TABLES)
@pytest.mark.parametrize("error_after_recording", [False, True])
async def test_failed_batch_is_unconfirmed_and_other_types_continue(failed_table, error_after_recording):
    recorded = []
    def write(table, columns, rows):
        if table != failed_table or error_after_recording:
            recorded.append((table, len(rows)))
        if table == failed_table:
            raise RuntimeError("controlled error, commit status unknown")
    store = Mock()
    store.execute_write_bulk.side_effect = write
    pipe = IngestionPipeline(store)
    enqueue_all(pipe)
    await pipe._drain_and_flush()
    await pipe.stop()
    m = pipe.get_metrics()
    assert m.get("unconfirmed_write_rows", 0) == 2
    assert m["errors"] == 1 and m["dropped"] == 0
    assert m["enqueued"] == m["dequeued"] == 8
    assert m["queue_size"] == 0
    assert [c.args[0] for c in store.execute_write_bulk.call_args_list] == list(TABLES)
    for table, metric in zip(TABLES, METRICS, strict=True):
        assert m[metric] == (0 if table == failed_table else 2)
    assert sum(m[k] for k in METRICS) + m["unconfirmed_write_rows"] == m["dequeued"]
    assert len(recorded) == (4 if error_after_recording else 3)


@pytest.mark.asyncio
async def test_all_batches_fail_without_hiding_later_attempts():
    store = Mock()
    store.execute_write_bulk.side_effect = RuntimeError("controlled storage failure")
    pipe = IngestionPipeline(store)
    enqueue_all(pipe)
    await pipe.stop()
    m = pipe.get_metrics()
    assert m.get("unconfirmed_write_rows", 0) == 8
    assert m["errors"] == 4 and m["dropped"] == 0
    assert sum(m[k] for k in METRICS) == 0
    assert store.execute_write_bulk.call_count == 4


@pytest.mark.asyncio
async def test_success_and_overflow_keep_exact_separate_counts():
    store = Mock()
    pipe = IngestionPipeline(store, max_queue_size=8)
    pipe.enqueue_tick({"symbol": "DROPPED"})
    enqueue_all(pipe)
    await pipe.stop()
    m = pipe.get_metrics()
    assert m.get("unconfirmed_write_rows", 0) == 0
    assert m["errors"] == 0 and m["dropped"] == 1
    assert m["enqueued"] == 9 and m["dequeued"] == 8
    assert all(m[k] == 2 for k in METRICS)
    assert store.execute_write_bulk.call_count == 4


@pytest.mark.asyncio
async def test_stop_waits_for_inflight_thread_then_drains_new_arrival():
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    recorded = []
    def write(table, columns, rows):
        if not recorded:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(2), "test failed to release active storage write"
        recorded.extend(row[1] for row in rows)
    store = Mock()
    store.execute_write_bulk.side_effect = write
    pipe = IngestionPipeline(store, flush_interval_ms=1)
    pipe.enqueue_tick({"symbol": "FIRST"})
    await pipe.start()
    stop = None
    try:
        await asyncio.wait_for(started.wait(), 1)
        pipe.enqueue_tick({"symbol": "SECOND"})
        stop = asyncio.create_task(pipe.stop())
        done, _ = await asyncio.wait({stop}, timeout=0.03)
        assert not done, "stop returned while a storage write was still active"
    finally:
        release.set()
        if stop is not None:
            await asyncio.wait_for(stop, 1)
        else:
            await pipe.stop()
    assert recorded == ["FIRST", "SECOND"]
    assert pipe.get_metrics()["ticks_inserted"] == 2
    assert pipe.get_metrics()["errors"] == 0
    assert pipe._writer_task.done()


@pytest.mark.asyncio
async def test_duplicate_start_keeps_one_task_and_sleeping_stop_is_prompt():
    pipe = IngestionPipeline(Mock(), flush_interval_ms=60000)
    await pipe.start()
    first = pipe._writer_task
    try:
        await pipe.start()
        assert pipe._writer_task is first
        await asyncio.wait_for(pipe.stop(), 0.5)
        assert first.done()
    finally:
        await pipe.stop()
        # Clean up an orphan if the unfixed duplicate-start implementation runs.
        if not first.done():
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)
