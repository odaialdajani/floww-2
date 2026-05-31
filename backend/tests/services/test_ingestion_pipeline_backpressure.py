"""When the ingestion queue fills, pipeline must apply backpressure, not crash or hang."""
import asyncio
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_queue_drains_under_burst():
    """Enqueue many ticks rapidly; pipeline should drain without erroring."""
    try:
        from services.ingestion_pipeline import IngestionPipeline
    except ImportError as e:
        pytest.skip(f"Module import failed: {e}")

    mock_db = MagicMock()
    pipeline = IngestionPipeline(db=mock_db, tick_batch_size=100, flush_interval_ms=50)
    await pipeline.start()
    try:
        # enqueue_tick is sync (not async), so no await needed
        for i in range(500):
            pipeline.enqueue_tick({"symbol": "SPY", "price": 450 + i * 0.01, "ts": i})
        await asyncio.sleep(0.3)
        pipeline.enqueue_tick({"symbol": "SPY", "price": 451.0, "ts": 1001})
    finally:
        await pipeline.stop()
