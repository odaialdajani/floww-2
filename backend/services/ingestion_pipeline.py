"""
backend/services/ingestion_pipeline.py

Bounded asyncio.Queue + batching writer for Schwab WebSocket data.
Drains queue every 50ms, bulk INSERTs into DuckDB.

Architecture:
  SchwabStreamer (or MockSchwabFeed)
    -> handlers push to bounded asyncio.Queue
    -> batching writer coroutine drains queue
    -> bulk INSERT into DuckDB tables (ticks, chains, lob_snapshots)

Backpressure: if queue fills, drop oldest messages and log.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.duckdb_engine import DuckDBEngine

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Bounded queue + batching writer for real-time market data.

    Usage:
        pipeline = IngestionPipeline(db=duckdb_engine, max_queue_size=10000)
        await pipeline.start()
        pipeline.enqueue_tick(tick_dict)
        pipeline.enqueue_chain(chain_dict)
        await pipeline.stop()
    """

    def __init__(
        self,
        db: DuckDBEngine,
        max_queue_size: int = 10000,
        flush_interval_ms: float = 50.0,
        tick_batch_size: int = 100,
        chain_batch_size: int = 50,
    ):
        self.db = db
        self.max_queue_size = max_queue_size
        self.flush_interval = flush_interval_ms / 1000.0
        self.tick_batch_size = tick_batch_size
        self.chain_batch_size = chain_batch_size

        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._writer_task: Optional[asyncio.Task] = None

        # Metrics
        self._last_drop_warning: float = 0.0
        self._metrics = {
            "enqueued": 0,
            "dequeued": 0,
            "dropped": 0,
            "ticks_inserted": 0,
            "chains_inserted": 0,
            "lob_inserted": 0,
            "lob_depth_inserted": 0,
            "flush_cycles": 0,
            "errors": 0,
            "last_flush_ms": 0,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the batching writer coroutine."""
        self._running = True
        self._writer_task = asyncio.create_task(self._writer_loop())
        logger.info(
            f"Ingestion pipeline started (queue={self.max_queue_size}, "
            f"flush={self.flush_interval*1000:.0f}ms)"
        )

    async def stop(self):
        """Drain remaining queue and stop."""
        self._running = False
        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
        # Final drain
        await self._drain_and_flush()
        logger.info(f"Ingestion pipeline stopped. Metrics: {self.get_metrics()}")

    # ------------------------------------------------------------------
    # Enqueue (called by streamer handlers)
    # ------------------------------------------------------------------

    def enqueue_tick(self, tick: Dict[str, Any]):
        """Enqueue an equity/underlying tick. Drops oldest if queue full."""
        self._enqueue(("tick", tick))

    def enqueue_chain(self, chain: Dict[str, Any]):
        """Enqueue an options chain update. Drops oldest if queue full."""
        self._enqueue(("chain", chain))

    def enqueue_lob(self, lob: Dict[str, Any]):
        """Enqueue a LOB snapshot. Drops oldest if queue full."""
        self._enqueue(("lob", lob))

    def enqueue_lob_depth(self, depth: Dict[str, Any]):
        """Enqueue a Level-2 LOB depth update. Drops oldest if queue full."""
        self._enqueue(("lob_depth", depth))

    def _enqueue(self, item: tuple):
        """Put item into queue, dropping oldest if full (backpressure)."""
        try:
            self._queue.put_nowait(item)
            self._metrics["enqueued"] += 1
        except asyncio.QueueFull:
            # Drop oldest
            try:
                self._queue.get_nowait()
                self._metrics["dropped"] += 1
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(item)
                self._metrics["enqueued"] += 1
            except asyncio.QueueFull:
                self._metrics["dropped"] += 1
            # Rate-limited warning log (max 1 per 10s)
            now = time.monotonic()
            if now - self._last_drop_warning > 10.0:
                self._last_drop_warning = now
                logger.warning(
                    f"Ingestion queue full ({self._queue.qsize()}/{self.max_queue_size}) — "
                    f"dropped {self._metrics['dropped']} messages total"
                )

    # ------------------------------------------------------------------
    # Writer loop
    # ------------------------------------------------------------------

    async def _writer_loop(self):
        """Main writer loop: drain queue every flush_interval."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._drain_and_flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._metrics["errors"] += 1
                logger.error(f"Writer loop error: {e}")

    async def _drain_and_flush(self):
        """Drain queue into buffers and bulk INSERT."""
        start = time.monotonic()
        ticks = []
        chains = []
        lob = []
        lob_depth = []

        # Drain queue (non-blocking)
        while not self._queue.empty():
            try:
                msg_type, data = self._queue.get_nowait()
                self._metrics["dequeued"] += 1
                if msg_type == "tick":
                    ticks.append(data)
                elif msg_type == "chain":
                    chains.append(data)
                elif msg_type == "lob":
                    lob.append(data)
                elif msg_type == "lob_depth":
                    lob_depth.append(data)
            except asyncio.QueueEmpty:
                break

        # Bulk INSERT into DuckDB
        try:
            if ticks:
                await self._insert_ticks(ticks)
                self._metrics["ticks_inserted"] += len(ticks)
            if chains:
                await self._insert_chains(chains)
                self._metrics["chains_inserted"] += len(chains)
            if lob:
                await self._insert_lob(lob)
                self._metrics["lob_inserted"] += len(lob)
            if lob_depth:
                await self._insert_lob_depth(lob_depth)
                self._metrics["lob_depth_inserted"] += len(lob_depth)
        except Exception as e:
            self._metrics["errors"] += 1
            logger.error(f"Bulk insert error: {e}")

        elapsed_ms = (time.monotonic() - start) * 1000
        self._metrics["last_flush_ms"] = round(elapsed_ms, 2)
        self._metrics["flush_cycles"] += 1

    # ------------------------------------------------------------------
    # DuckDB INSERTs
    # ------------------------------------------------------------------

    async def _insert_ticks(self, ticks: list):
        """Bulk INSERT ticks into DuckDB."""
        rows = []
        for t in ticks:
            rows.append((
                t.get("timestamp", datetime.now(timezone.utc).isoformat()),
                t.get("symbol", ""),
                t.get("bid", 0.0),
                t.get("ask", 0.0),
                t.get("last", 0.0),
                int(t.get("volume", 0)),
                int(t.get("oi", 0)),
                float(t.get("delta", 0.0)),
                float(t.get("gamma", 0.0)),
                float(t.get("theta", 0.0)),
                float(t.get("vega", 0.0)),
                float(t.get("vanna", 0.0)),
                float(t.get("charm", 0.0)),
                float(t.get("vomma", 0.0)),
                t.get("data_source", "Yahoo"),
                t.get("delay_seconds", 0),
            ))
        await asyncio.to_thread(
            lambda: self.db.conn.executemany(
                "INSERT INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        )

    async def _insert_chains(self, chains: list):
        """Bulk INSERT chain data into DuckDB chains table."""
        # Note: chains table may not exist in current schema; insert into ticks as fallback
        rows = []
        for c in chains:
            rows.append((
                c.get("timestamp", datetime.now(timezone.utc).isoformat()),
                c.get("symbol", ""),
                c.get("bid", 0.0),
                c.get("ask", 0.0),
                c.get("last", 0.0),
                c.get("volume", 0),
                c.get("oi", 0),
                c.get("delta", 0.0),
                c.get("gamma", 0.0),
                c.get("theta", 0.0),
                c.get("vega", 0.0),
                c.get("vanna", 0.0),
                c.get("charm", 0.0),
                c.get("vomma", 0.0),
                c.get("data_source", "Yahoo"),
                c.get("delay_seconds", 0),
            ))
        await asyncio.to_thread(
            lambda: self.db.conn.executemany(
                "INSERT INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        )

    async def _insert_lob(self, lob_snapshots: list):
        """Bulk INSERT LOB snapshots into DuckDB."""
        rows = []
        for l in lob_snapshots:
            rows.append((
                l.get("timestamp", datetime.now(timezone.utc).isoformat()),
                l.get("symbol", ""),
                l.get("bid_size", 0),
                l.get("ask_size", 0),
                l.get("bid_price", 0.0),
                l.get("ask_price", 0.0),
                l.get("level", 0),
            ))
        await asyncio.to_thread(
            lambda: self.db.conn.executemany(
                "INSERT INTO lob_snapshots VALUES (?,?,?,?,?,?,?)",
                rows,
            )
        )

    async def _insert_lob_depth(self, depth_rows: list):
        """Bulk INSERT Level-2 LOB depth into DuckDB."""
        rows = []
        for d in depth_rows:
            rows.append((
                d.get("timestamp", datetime.now(timezone.utc).isoformat()),
                d.get("symbol", ""),
                d.get("expiry", ""),
                d.get("strike", 0.0),
                d.get("option_type", "C"),
                d.get("level", 0),
                d.get("bid_size", 0),
                d.get("bid_price", 0.0),
                d.get("ask_size", 0),
                d.get("ask_price", 0.0),
            ))
        await asyncio.to_thread(
            lambda: self.db.conn.executemany(
                "INSERT INTO lob_depth VALUES (?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        )

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> Dict[str, Any]:
        return {
            **self._metrics,
            "queue_size": self._queue.qsize(),
            "queue_fill_pct": round(self._queue.qsize() / self.max_queue_size * 100, 1),
            "running": self._running,
        }
