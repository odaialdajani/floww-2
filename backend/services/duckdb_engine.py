"""
backend/services/duckdb_engine.py

DuckDB OLAP engine for real-time options analytics.
In-memory instance with async batch writer for tick/LOB data.

Schema:
  ticks:       (timestamp, symbol, bid, ask, last, volume, oi, delta, gamma, theta, vega, data_source, delay_seconds)
  chains:      (timestamp, symbol, ticker, strike, expiry, type, bid, ask, last, volume, open_interest, iv, delta, gamma, theta, vega, data_source, delay_seconds)
  lob_snapshots: (timestamp, symbol, bid_size, ask_size, bid_price, ask_price, level)
  flow_prints:   (timestamp, ticker, strike, expiration, side, type, size, price,
                  premium, volume, oi, exchange, classification)
  vpin_buckets:  (timestamp, bucket_id, total_volume, buy_volume, sell_volume, vpin_value)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, List, Optional

import duckdb
import numpy as np

import services.observability as obs_metrics

logger = logging.getLogger(__name__)

def retry_on_failure(max_retries=3, base_delay=0.1):
    """Decorator that retries an async function on failure with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "%s failed (attempt %d/%d), retrying in %.2fs: %s",
                            func.__name__, attempt + 1, max_retries, delay, e,
                        )
                        await asyncio.sleep(delay)
            logger.error(
                "%s failed after %d attempts: %s",
                func.__name__, max_retries, last_exception,
            )
            raise last_exception
        return wrapper
    return decorator

# Default query timeout in seconds - prevents hanging on malformed queries or lock contention.
QUERY_TIMEOUT_S = 5.0


async def _execute_with_timeout(
    conn,
    fn,
    timeout: float = QUERY_TIMEOUT_S,
    operation: str = "query",
) -> Any:
    """Execute a DuckDB operation via asyncio.to_thread with a timeout.

    Args:
        conn: DuckDB connection object.
        fn: Callable that performs the DuckDB operation (runs in thread pool).
        timeout: Maximum seconds to wait before raising asyncio.TimeoutError.
        operation: Human-readable name for logging.

    Returns:
        Result of fn().

    Raises:
        asyncio.TimeoutError: If the operation exceeds the timeout.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"DuckDB {operation} timeout after {timeout}s")
        raise
    except Exception:
        raise


class DuckDBEngine:
    """Thread-safe DuckDB wrapper with async batch writer."""

    def __init__(self, db_path: str = ":memory:"):
        self._conn = duckdb.connect(db_path)
        self._lock = asyncio.Lock()
        self._tick_buffer: List[tuple] = []
        self._lob_buffer: List[tuple] = []
        self._flow_buffer: List[tuple] = []
        self._batch_size = 100
        self._flush_interval_ms = 50
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None
        self._init_schema()  # Ensure tables exist on creation

    def _init_schema(self):
        self._create_base_tables()
        self._create_chains_table()
        self._apply_delayed_data_migration()
        self._create_indexes()
        logger.info("DuckDB schema initialized with delayed-data support")

    def _create_base_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                timestamp    TIMESTAMP,
                symbol       VARCHAR,
                bid          DOUBLE,
                ask          DOUBLE,
                last         DOUBLE,
                volume       BIGINT,
                oi           BIGINT,
                delta_val    DOUBLE,
                gamma_val    DOUBLE,
                theta_val    DOUBLE,
                vega_val     DOUBLE,
                vanna_val    DOUBLE,
                charm_val    DOUBLE,
                vomma_val    DOUBLE
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS lob_snapshots (
                timestamp    TIMESTAMP,
                symbol       VARCHAR,
                bid_size     BIGINT,
                ask_size     BIGINT,
                bid_price    DOUBLE,
                ask_price    DOUBLE,
                level        INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS lob_depth (
                timestamp    TIMESTAMP,
                symbol       VARCHAR,
                expiry       DATE,
                strike       DOUBLE,
                option_type  VARCHAR(1),
                level        INTEGER,
                bid_size     BIGINT,
                bid_price    DOUBLE,
                ask_size     BIGINT,
                ask_price    DOUBLE
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS flow_prints (
                timestamp       TIMESTAMP,
                ticker          VARCHAR,
                strike          DOUBLE,
                expiration      VARCHAR,
                side            VARCHAR,
                type            VARCHAR,
                size            INTEGER,
                price           DOUBLE,
                premium         DOUBLE,
                volume          BIGINT,
                oi              BIGINT,
                exchange        VARCHAR,
                classification  VARCHAR,
                bid             DOUBLE,
                ask             DOUBLE,
                spot            DOUBLE
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vpin_buckets (
                timestamp    TIMESTAMP,
                bucket_id    INTEGER,
                total_volume DOUBLE,
                buy_volume   DOUBLE,
                sell_volume  DOUBLE,
                vpin_value   DOUBLE,
                qi_zscore    DOUBLE
            )
        """)

    def _create_chains_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS chains (
                timestamp     TIMESTAMP,
                symbol        VARCHAR,
                ticker        VARCHAR,
                strike        DOUBLE,
                expiry        DATE,
                type          VARCHAR(4),
                bid           DOUBLE,
                ask           DOUBLE,
                last          DOUBLE,
                volume        BIGINT,
                open_interest BIGINT,
                iv            DOUBLE,
                delta_val     DOUBLE,
                gamma_val     DOUBLE,
                theta_val     DOUBLE,
                vega_val      DOUBLE,
                data_source   VARCHAR DEFAULT 'Yahoo',
                delay_seconds INTEGER DEFAULT 0
            )
        """)

    def _apply_delayed_data_migration(self):
        for col, typ, default in [("data_source", "VARCHAR", "'Yahoo'"), ("delay_seconds", "INTEGER", "0")]:
            for table in ("ticks", "chains"):
                try:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col} {typ} DEFAULT {default}"
                    )
                    logger.info(f"Added {col} to {table}")
                except Exception:
                    pass

    def _create_indexes(self):
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_symbol ON ticks(symbol)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_ts ON ticks(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lob_symbol ON lob_snapshots(symbol)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lob_depth_symbol ON lob_depth(symbol)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lob_depth_ts ON lob_depth(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_flow_ticker ON flow_prints(ticker)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chains_ticker ON chains(ticker)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chains_ts ON chains(timestamp)")

    async def start(self):
        if self._running:
            return  # Already started — idempotent
        self._running = True
        # Guard against double-start: only create a new task if none is running
        existing = getattr(self, '_flush_task', None)
        if existing is not None and not existing.done():
            logger.warning("DuckDB _flush_loop task already running, not creating a new one")
        else:
            self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("DuckDB async writer started")

    async def stop(self):
        self._running = False
        task = getattr(self, '_flush_task', None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._flush_task = None
        await self._flush_all()

    async def insert_tick(self, symbol: str, bid: float, ask: float, last: float,
                          volume: int, oi: int, delta: float, gamma: float,
                          theta: float, vega: float, vanna: float = 0.0,
                          charm: float = 0.0, vomma: float = 0.0,
                          data_source: str = "Yahoo", delay_seconds: int = 0):
        ts = datetime.now(timezone.utc)
        self._tick_buffer.append((ts, symbol, bid, ask, last, volume, oi,
                                  delta, gamma, theta, vega, vanna, charm, vomma,
                                  data_source, delay_seconds))
        obs_metrics.duckdb_queue_depth.set(
            len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
        )
        if len(self._tick_buffer) >= self._batch_size:
            await self._flush_ticks()

    async def _flush_loop(self):
        while self._running:
            await asyncio.sleep(self._flush_interval_ms / 1000.0)
            await self._flush_all()

    async def _flush_all(self):
        await asyncio.gather(
            self._flush_ticks(),
            self._flush_lob(),
            self._flush_flow(),
        )

    @retry_on_failure(max_retries=3, base_delay=0.1)
    async def _flush_ticks(self):
        if not self._tick_buffer:
            return
        async with self._lock:
            buf = self._tick_buffer
            self._tick_buffer = []
        obs_metrics.duckdb_batch_size.observe(len(buf))
        obs_metrics.duckdb_queue_depth.set(
            len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
        )
        try:
            await _execute_with_timeout(
                self._conn,
                lambda: self._conn.executemany(
                    """INSERT INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    buf,
                ),
                operation="tick flush",
            )
        except asyncio.TimeoutError:
            logger.error(f"DuckDB tick flush timeout - {len(buf)} rows dropped")
        except Exception as e:
            logger.error(f"DuckDB tick flush error: {e}")

    @retry_on_failure(max_retries=3, base_delay=0.1)
    async def _flush_lob(self):
        if not self._lob_buffer:
            return
        async with self._lock:
            buf = self._lob_buffer
            self._lob_buffer = []
        obs_metrics.duckdb_batch_size.observe(len(buf))
        obs_metrics.duckdb_queue_depth.set(
            len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
        )
        try:
            await _execute_with_timeout(
                self._conn,
                lambda: self._conn.executemany(
                    """INSERT INTO lob_snapshots VALUES (?,?,?,?,?,?,?)""",
                    buf,
                ),
                operation="LOB flush",
            )
        except asyncio.TimeoutError:
            logger.error(f"DuckDB LOB flush timeout - {len(buf)} rows dropped")
        except Exception as e:
            logger.error(f"DuckDB LOB flush error: {e}")

    @retry_on_failure(max_retries=3, base_delay=0.1)
    async def _flush_flow(self):
        if not self._flow_buffer:
            return
        async with self._lock:
            buf = self._flow_buffer
            self._flow_buffer = []
        obs_metrics.duckdb_batch_size.observe(len(buf))
        obs_metrics.duckdb_queue_depth.set(
            len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
        )
        try:
            await _execute_with_timeout(
                self._conn,
                lambda: self._conn.executemany(
                    """INSERT INTO flow_prints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    buf,
                ),
                operation="flow flush",
            )
        except asyncio.TimeoutError:
            logger.error(f"DuckDB flow flush timeout - {len(buf)} rows dropped")
        except Exception as e:
            logger.error(f"DuckDB flow flush error: {e}")

    def query(self, sql: str, params: Optional[List] = None) -> List[Dict[str, Any]]:
        """Synchronous query returning list of dicts. Non-blocking wrapper available as query_async."""
        try:
            result = self._conn.execute(sql, params or []).fetchdf()
            return result.replace({np.nan: None}).to_dict("records")
        except Exception as e:
            logger.error(f"DuckDB query error: {e}")
            return []

    async def query_async(
        self,
        sql: str,
        params: Optional[List] = None,
        timeout: float = QUERY_TIMEOUT_S,
    ) -> List[Dict[str, Any]]:
        """Async wrapper for query - runs in thread pool with configurable timeout.

        Args:
            sql: SQL query string.
            params: Optional query parameters.
            timeout: Maximum seconds to wait (default QUERY_TIMEOUT_S=5).

        Returns:
            List of dicts from query result.

        Raises:
            asyncio.TimeoutError: If query exceeds timeout.
        """
        def _do_query():
            return self._conn.execute(sql, params or []).fetchdf()

        try:
            df = await _execute_with_timeout(
                self._conn, _do_query, timeout=timeout, operation="query"
            )
            return df.replace({np.nan: None}).to_dict("records")
        except asyncio.TimeoutError:
            logger.error(f"DuckDB query timeout after {timeout}s: {sql[:100]}")
            raise
        except Exception as e:
            logger.error(f"DuckDB query error: {e}")
            return []

    @property
    def conn(self):
        return self._conn


db = DuckDBEngine()
