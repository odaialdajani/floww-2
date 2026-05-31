"""
backend/services/replay_engine.py

Historical replay engine — reads ticks/chains from DuckDB + Mongo,
pushes to the same asyncio.Queue the live feed uses (drop-in replacement).

Supports multiple replay speeds: 1x, 10x, 100x, max.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from services.duckdb_engine import DuckDBEngine

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Replays historical market data from DuckDB and Mongo.

    Usage:
        engine = ReplayEngine(db=duckdb_engine, start=start_dt, end=end_dt, speed=10.0)
        engine.on_tick(pipeline.enqueue_tick)
        engine.on_chain(pipeline.enqueue_chain)
        await engine.start()
    """

    def __init__(
        self,
        db: DuckDBEngine,
        start: datetime,
        end: datetime,
        speed: float = 1.0,
        mongo_client=None,
    ):
        self.db = db
        self.start_dt = start
        self.end_dt = end
        self.speed = speed
        self.mongo_client = mongo_client

        self._running = False
        self._tick_handlers: List = []
        self._chain_handlers: List = []
        self._lob_handlers: List = []

        self._metrics = {
            "ticks_replayed": 0,
            "chains_replayed": 0,
            "start_time": None,
            "elapsed_wall_s": 0,
        }

    def on_tick(self, handler):
        self._tick_handlers.append(handler)

    def on_chain(self, handler):
        self._chain_handlers.append(handler)

    def on_lob(self, handler):
        self._lob_handlers.append(handler)

    async def start(self):
        """Start replaying data from start to end at the configured speed."""
        self._running = True
        self._metrics["start_time"] = time.monotonic()
        logger.info(
            f"Replay engine starting: {self.start_dt.isoformat()} -> {self.end_dt.isoformat()} "
            f"at {self.speed}x speed"
        )

        try:
            await self._replay_ticks()
            await self._replay_chains()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Replay error: {e}")
        finally:
            self._running = False
            self._metrics["elapsed_wall_s"] = round(
                time.monotonic() - self._metrics["start_time"], 2
            )
            logger.info(f"Replay complete: {self._metrics}")

    async def stop(self):
        self._running = False

    async def _replay_ticks(self):
        """Replay tick data from DuckDB."""
        rows = self.db.query(
            """
            SELECT * FROM ticks
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            [self.start_dt.isoformat(), self.end_dt.isoformat()],
        )
        if not rows:
            # Try Mongo if available
            rows = await self._fetch_ticks_from_mongo()

        if not rows:
            logger.warning("No tick data found for replay window")
            return

        prev_ts = None
        for row in rows:
            if not self._running:
                break

            ts = datetime.fromisoformat(row["timestamp"]) if isinstance(row["timestamp"], str) else row["timestamp"]

            # Speed control: wait proportional to time delta
            if prev_ts and self.speed > 0:
                delta = (ts - prev_ts).total_seconds()
                if delta > 0:
                    await asyncio.sleep(delta / self.speed)

            tick = {
                "timestamp": ts.isoformat(),
                "symbol": row["symbol"],
                "bid": row.get("bid", 0),
                "ask": row.get("ask", 0),
                "last": row.get("last", 0),
                "volume": row.get("volume", 0),
                "source": "replay",
            }

            for h in self._tick_handlers:
                try:
                    await h(tick) if asyncio.iscoroutinefunction(h) else h(tick)
                except Exception as e:
                    logger.error(f"Replay tick handler error: {e}")

            self._metrics["ticks_replayed"] += 1
            prev_ts = ts

    async def _replay_chains(self):
        """Replay chain data from DuckDB (stored in ticks table with chain fields)."""
        rows = self.db.query(
            """
            SELECT * FROM ticks
            WHERE timestamp >= ? AND timestamp <= ?
            AND delta_val != 0
            ORDER BY timestamp ASC
            LIMIT 1000
            """,
            [self.start_dt.isoformat(), self.end_dt.isoformat()],
        )

        for row in rows:
            if not self._running:
                break
            chain = {
                "timestamp": row["timestamp"],
                "symbol": row["symbol"],
                "bid": row.get("bid", 0),
                "ask": row.get("ask", 0),
                "last": row.get("last", 0),
                "volume": row.get("volume", 0),
                "oi": row.get("oi", 0),
                "delta": row.get("delta_val", 0),
                "gamma": row.get("gamma_val", 0),
                "theta": row.get("theta_val", 0),
                "vega": row.get("vega_val", 0),
                "source": "replay",
            }
            for h in self._chain_handlers:
                try:
                    await h(chain) if asyncio.iscoroutinefunction(h) else h(chain)
                except Exception as e:
                    logger.error(f"Replay chain handler error: {e}")
            self._metrics["chains_replayed"] += 1

    async def _fetch_ticks_from_mongo(self) -> List[Dict]:
        """Fetch ticks from Mongo if DuckDB has no data."""
        if not self.mongo_client:
            return []
        try:
            db = self.mongo_client.get_default_database()
            snapshots = db.snapshots
            cursor = snapshots.find({
                "timestamp": {
                    "$gte": self.start_dt.isoformat(),
                    "$lte": self.end_dt.isoformat(),
                }
            }).sort("timestamp", 1)
            results = []
            async for doc in cursor:
                results.append({
                    "timestamp": doc.get("timestamp", ""),
                    "symbol": doc.get("symbol", "SPY"),
                    "bid": doc.get("bid", 0),
                    "ask": doc.get("ask", 0),
                    "last": doc.get("last", 0),
                    "volume": doc.get("volume", 0),
                })
            return results
        except Exception as e:
            logger.warning(f"Mongo fetch failed: {e}")
            return []

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "start": self.start_dt.isoformat(),
            "end": self.end_dt.isoformat(),
            "speed": self.speed,
            **self._metrics,
        }
