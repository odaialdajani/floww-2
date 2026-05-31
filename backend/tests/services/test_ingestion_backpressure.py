"""Chaos test: queue backpressure under message storm."""
import asyncio
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_queue_fills_then_drains_without_loss_under_burst():
    """Bounded queue should never exceed max size, even under burst."""
    from services.ingestion_pipeline import IngestionPipeline

    db = MagicMock()
    db.conn = MagicMock()
    db.conn.executemany = MagicMock()

    pipeline = IngestionPipeline(
        db=db,
        max_queue_size=100,
        flush_interval_ms=50.0,
    )
    await pipeline.start()

    # Burst 1000 messages into a queue of size 100
    for i in range(1000):
        pipeline.enqueue_tick({"symbol": "SPY", "price": 450 + i * 0.01, "ts": i})

    # Queue should never exceed max
    assert pipeline._queue.qsize() <= 100, f"Queue exceeded max: {pipeline._queue.qsize()}"

    # Wait for drain
    await asyncio.sleep(0.3)
    depth_after = pipeline._queue.qsize()
    assert depth_after < 50, f"queue did not drain: {depth_after}"

    await pipeline.stop()


@pytest.mark.asyncio
async def test_queue_full_drops_oldest():
    """When queue is bounded and full, oldest messages are dropped."""
    from services.ingestion_pipeline import IngestionPipeline

    db = MagicMock()
    db.conn = MagicMock()
    db.conn.executemany = MagicMock()

    pipeline = IngestionPipeline(
        db=db,
        max_queue_size=50,
        flush_interval_ms=10000,  # Never flushes during test
    )
    await pipeline.start()

    # Fill way past capacity
    for i in range(200):
        pipeline.enqueue_tick({"symbol": "SPY", "ts": i})

    metrics = pipeline.get_metrics()
    # Should have dropped at least some messages
    assert metrics["dropped"] > 0, f"Expected drops, got {metrics['dropped']}"
    # Queue should be at max
    assert pipeline._queue.qsize() <= 50

    await pipeline.stop()


@pytest.mark.asyncio
async def test_metrics_track_drops():
    """Drop counter should be accurate."""
    from services.ingestion_pipeline import IngestionPipeline

    db = MagicMock()
    db.conn = MagicMock()
    db.conn.executemany = MagicMock()

    pipeline = IngestionPipeline(
        db=db,
        max_queue_size=10,
        flush_interval_ms=10000,
    )
    await pipeline.start()

    for i in range(100):
        pipeline.enqueue_tick({"symbol": "SPY", "ts": i})

    metrics = pipeline.get_metrics()
    # 100 enqueued, queue size 10, so ~90 dropped
    assert metrics["enqueued"] == 100, f"Expected 100 enqueued, got {metrics['enqueued']}"
    assert metrics["dropped"] == 90, f"Expected 90 drops, got {metrics['dropped']}"

    await pipeline.stop()


@pytest.mark.asyncio
async def test_pipeline_restart_after_stop():
    """Pipeline should work after stop + restart cycle."""
    from services.ingestion_pipeline import IngestionPipeline

    db = MagicMock()
    db.conn = MagicMock()
    db.conn.executemany = MagicMock()

    pipeline = IngestionPipeline(
        db=db,
        max_queue_size=100,
        flush_interval_ms=50.0,
    )

    # First run
    await pipeline.start()
    for i in range(50):
        pipeline.enqueue_tick({"symbol": "SPY", "ts": i})
    await asyncio.sleep(0.1)
    await pipeline.stop()

    metrics1 = pipeline.get_metrics()
    assert metrics1["enqueued"] == 50

    # Second run
    pipeline._running = False  # Reset
    pipeline._queue = asyncio.Queue(maxsize=100)  # Fresh queue
    pipeline._metrics = {k: 0 for k in pipeline._metrics}  # Reset metrics

    await pipeline.start()
    for i in range(30):
        pipeline.enqueue_tick({"symbol": "QQQ", "ts": i})
    await asyncio.sleep(0.1)
    await pipeline.stop()

    metrics2 = pipeline.get_metrics()
    assert metrics2["enqueued"] == 30
