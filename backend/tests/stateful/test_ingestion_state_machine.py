"""Stateful queue conservation, oldest-drop order and real flush persistence.

A private event loop drives actual drain/start/stop methods deterministically.
Only synchronous storage writes are mocked; conversion and queue logic are real.
"""

import asyncio
from collections import deque
from unittest.mock import Mock

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from services.ingestion_pipeline import IngestionPipeline


class IngestionPipelineMachine(RuleBasedStateMachine):
    @initialize()
    def setup(self):
        self.runner = asyncio.Runner()
        self.pending = deque()
        self.written = []
        self.expected_written = []
        self.arrivals = 0
        self.dropped = 0
        self.storage = Mock()
        self.storage.execute_write_bulk.side_effect = self.record_write
        self.pipeline = IngestionPipeline(db=self.storage, max_queue_size=3,
                                          flush_interval_ms=60000)

    def record_write(self, table, columns, rows):
        assert table == "ticks"
        assert columns[1] == "symbol" and columns[4] == "last"
        self.written.extend((row[1], row[4], row[5]) for row in rows)

    @rule(symbol=st.sampled_from(["SPY", "QQQ", "IWM", "DIA", "TLT"]),
          price=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
          count=st.integers(min_value=1, max_value=8))
    def ticks_arrive(self, symbol, price, count):
        for _ in range(count):
            self.arrivals += 1
            # Unique volume identifies arrival order even for duplicate prices.
            item = (symbol, price, self.arrivals)
            if len(self.pending) == 3:
                self.pending.popleft()
                self.dropped += 1
            self.pending.append(item)
            self.pipeline.enqueue_tick({"symbol": symbol, "last": price,
                                        "volume": self.arrivals,
                                        "timestamp": "2026-09-11T14:00:00+00:00"})

    def record_expected_flush(self):
        self.expected_written.extend(self.pending)
        self.pending.clear()

    @rule()
    def queue_flushes(self):
        self.record_expected_flush()
        self.runner.run(self.pipeline._drain_and_flush())
        assert self.written == self.expected_written

    @rule()
    def start_and_stop_drains_remaining(self):
        async def cycle():
            await self.pipeline.start()
            assert self.pipeline.get_metrics()["running"] is True
            await self.pipeline.stop()
        self.record_expected_flush()
        self.runner.run(cycle())
        assert self.pipeline.get_metrics()["running"] is False
        assert self.pipeline._writer_task.done()
        assert self.written == self.expected_written

    @invariant()
    def conservation_and_storage_order(self):
        metrics = self.pipeline.get_metrics()
        assert metrics["errors"] == 0
        assert metrics["enqueued"] == self.arrivals
        assert metrics["dropped"] == self.dropped
        assert metrics["queue_size"] == len(self.pending) <= 3
        assert metrics["dequeued"] == metrics["ticks_inserted"] == len(self.written)
        assert self.arrivals == len(self.written) + self.dropped + len(self.pending)
        assert self.written == self.expected_written
        assert self.storage.execute_write_bulk.call_count <= metrics["flush_cycles"]

    def teardown(self):
        try:
            self.record_expected_flush()
            self.runner.run(self.pipeline.stop())
            self.conservation_and_storage_order()
        finally:
            self.runner.close()


TestIngestionPipeline = IngestionPipelineMachine.TestCase
TestIngestionPipeline.settings = settings(max_examples=200, stateful_step_count=20,
                                         deadline=None, derandomize=True)
