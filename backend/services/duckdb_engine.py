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
import contextlib
import logging
import os
from datetime import UTC, datetime
from functools import wraps
from typing import Any

import duckdb
import numpy as np

import services.observability as obs_metrics
from services.connection_guard import connection_lock

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
    except TimeoutError:
        logger.error(f"DuckDB {operation} timeout after {timeout}s")
        raise
    except Exception:
        raise


# ── Versioned schema migrations (GSD 3.1) ─────────────────────────────
#
# Each entry: (version, name, fn(conn)). Append-only — a migration that
# shipped must never be edited or reordered; add the next version instead.
# Migration 1 formalizes the pre-migration-era baseline (tables + indexes
# are created unconditionally in _init_schema before this runs).


def _mig_002_chains_expiry_index(conn) -> None:
    """Speed up expiry-filtered chain reads (outcome/heatmap queries)."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chains_expiry ON chains(expiry)")


def _mig_003_ticks_symbol_ts_composite(conn) -> None:
    """Composite for per-symbol time-window scans (VPIN / replay)."""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts ON ticks(symbol, timestamp)"
    )


MIGRATIONS: list[tuple[int, str, Any]] = [
    (2, "idx_chains_expiry", _mig_002_chains_expiry_index),
    (3, "idx_ticks_symbol_ts", _mig_003_ticks_symbol_ts_composite),
]


class DuckDBEngine:
    """Thread-safe DuckDB wrapper with async batch writer."""

    # Test-teardown registry: tests/conftest.py closes these after each test
    # so leaked connections don't leave ~ncores spinning DuckDB scheduler
    # threads behind (long pytest runs ground to a halt without this).
    _live_instances: list = []

    def __init__(self, db_path: str = ":memory:"):
        self._conn = duckdb.connect(db_path)
        self._is_shared_singleton = False
        DuckDBEngine._live_instances.append(self)
        self._lock = asyncio.Lock()
        # DuckDB connections are NOT thread-safe (threadsafety==1). The async
        # flush loop, the ingestion pipeline, and synchronous readers (e.g. the
        # vpin history route) all touch this one connection from different OS
        # threads. This lock serializes EVERY raw connection access — reads and
        # writes — so two threads never share the connection's pending result.
        self._conn_lock = connection_lock(self._conn)
        self._tick_buffer: list[tuple] = []
        self._lob_buffer: list[tuple] = []
        self._flow_buffer: list[tuple] = []
        self._batch_size = 100
        self._flush_interval_ms = 50
        self._running = False
        self._flush_task: asyncio.Task | None = None
        self._init_schema()  # Ensure tables exist on creation

    def _init_schema(self):
        self._create_base_tables()
        self._create_chains_table()
        self._apply_delayed_data_migration()
        self._create_indexes()
        self._run_migrations()
        logger.info("DuckDB schema initialized with delayed-data support")

    # ------------------------------------------------------------------
    # Versioned migrations (GSD 3.1)
    #
    # DuckDB has no PRAGMA user_version, so applied migrations are tracked
    # in a schema_migrations table. Each migration runs once, under the
    # conn lock. Append new migrations to the END of MIGRATIONS — never
    # edit or reorder an applied one.
    # ------------------------------------------------------------------

    def _applied_versions(self) -> set[int]:
        with self._conn_lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version    INTEGER PRIMARY KEY,
                    name       VARCHAR,
                    applied_at TIMESTAMP DEFAULT now()
                )
            """)
            rows = self._conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {r[0] for r in rows}

    def _run_migrations(self) -> None:
        applied = self._applied_versions()
        ran = False
        for version, name, fn in MIGRATIONS:
            if version in applied:
                continue
            logger.info(f"duckdb migration {version}: applying {name}")
            with self._conn_lock:
                fn(self._conn)
                self._conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations (version, name) VALUES (?, ?)",
                    [version, name],
                )
            ran = True
        if ran:
            logger.info(f"duckdb migrations complete (schema at v{MIGRATIONS[-1][0]})")

    def _create_base_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                timestamp     TIMESTAMP,
                symbol        VARCHAR,
                bid           DOUBLE,
                ask           DOUBLE,
                last          DOUBLE,
                volume        BIGINT,
                oi            BIGINT,
                delta_val     DOUBLE,
                gamma_val     DOUBLE,
                theta_val     DOUBLE,
                vega_val      DOUBLE,
                vanna_val     DOUBLE,
                charm_val     DOUBLE,
                vomma_val     DOUBLE,
                data_source   VARCHAR DEFAULT 'Yahoo',
                delay_seconds INTEGER DEFAULT 0
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
                except Exception as e:
                    msg = str(e).lower()
                    if "already exists" not in msg and "duplicate" not in msg:
                        logger.warning(
                            f"duckdb_engine: reserved-slot-write: {e}",
                            exc_info=True,
                        )
                    pass  # idempotent ADD COLUMN ok

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
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._flush_task = None
        await self._flush_all()

    def close(self) -> None:
        """Synchronous teardown: drop the connection so DuckDB's per-connection
        thread pool is released. Tests create many short-lived engines; without
        this each leaked connection leaves ~ncores spinning scheduler threads
        and long pytest runs grind to a halt. Safe to call twice."""
        conn = getattr(self, '_conn', None)
        if conn is not None:
            with self._conn_lock:
                with contextlib.suppress(Exception):
                    conn.close()
                self._conn = None

    async def insert_tick(self, symbol: str, bid: float, ask: float, last: float,
                          volume: int, oi: int, delta: float, gamma: float,
                          theta: float, vega: float, vanna: float = 0.0,
                          charm: float = 0.0, vomma: float = 0.0,
                          data_source: str = "Yahoo", delay_seconds: int = 0):
        ts = datetime.now(UTC)
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
            if not buf:
                return
            obs_metrics.duckdb_batch_size.observe(len(buf))
            obs_metrics.duckdb_queue_depth.set(
                len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
            )
            try:
                await _execute_with_timeout(
                    self._conn,
                    lambda: self.execute_write(
                        """INSERT INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        buf,
                    ),
                    operation="tick flush",
                )
            except TimeoutError:
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
            if not buf:
                return
            obs_metrics.duckdb_batch_size.observe(len(buf))
            obs_metrics.duckdb_queue_depth.set(
                len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
            )
            try:
                await _execute_with_timeout(
                    self._conn,
                    lambda: self.execute_write(
                        """INSERT INTO lob_snapshots VALUES (?,?,?,?,?,?,?)""",
                        buf,
                    ),
                    operation="LOB flush",
                )
            except TimeoutError:
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
            if not buf:
                return
            obs_metrics.duckdb_batch_size.observe(len(buf))
            obs_metrics.duckdb_queue_depth.set(
                len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
            )
            try:
                await _execute_with_timeout(
                    self._conn,
                    lambda: self.execute_write(
                        """INSERT INTO flow_prints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        buf,
                    ),
                    operation="flow flush",
                )
            except TimeoutError:
                logger.error(f"DuckDB flow flush timeout - {len(buf)} rows dropped")
            except Exception as e:
                logger.error(f"DuckDB flow flush error: {e}")

    def query_strict(self, sql: str, params: list | None = None) -> list[dict]:
        """Read with explicit failure, for callers distinguishing outage from empty."""
        with self._conn_lock:
            cursor = self._conn.execute(sql, params or [])
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def execute_write(self, sql: str, params_seq: list | None = None) -> None:
        """Serialized write against the shared connection. Pass a sequence of
        row tuples for executemany, or None for a parameterless statement.
        All concurrent writers (ingestion pipeline, flush loop) MUST go through
        this so writes never race a read on the same connection."""
        with self._conn_lock:
            if params_seq is None:
                self._conn.execute(sql)
            else:
                self._conn.executemany(sql, params_seq)

    def execute_write_bulk(self, table: str, columns: list[str], df) -> int:
        """Columnar bulk insert: register a pandas DataFrame and INSERT..SELECT.
        ~65x faster than executemany for large batches (executemany is
        row-by-row inside DuckDB). Serialized under the same conn lock."""
        import pandas as pd  # local: only needed on the bulk write path

        with self._conn_lock:
            n = len(df)
            if n == 0:
                return 0
            self._conn.register("_bulk_batch_df", pd.DataFrame(df, columns=columns))
            try:
                cols = ", ".join(columns)
                self._conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _bulk_batch_df")
            finally:
                self._conn.unregister("_bulk_batch_df")
        return n

    def query(self, sql: str, params: list | None = None) -> list[dict[str, Any]]:
        """Synchronous query returning list of dicts. Non-blocking wrapper available as query_async."""
        try:
            with self._conn_lock:
                result = self._conn.execute(sql, params or []).fetchdf()
            return result.replace({np.nan: None}).to_dict("records")
        except Exception as e:
            logger.error(f"DuckDB query error: {e}")
            return []

    async def query_async(
        self,
        sql: str,
        params: list | None = None,
        timeout: float = QUERY_TIMEOUT_S,
    ) -> list[dict[str, Any]]:
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
            with self._conn_lock:
                return self._conn.execute(sql, params or []).fetchdf()

        try:
            df = await _execute_with_timeout(
                self._conn, _do_query, timeout=timeout, operation="query"
            )
            return df.replace({np.nan: None}).to_dict("records")
        except TimeoutError:
            logger.error(f"DuckDB query timeout after {timeout}s: {sql[:100]}")
            raise
        except Exception as e:
            logger.error(f"DuckDB query error: {e}")
            return []

    @property
    def conn(self):
        return self._conn


def _open_shared_db() -> DuckDBEngine:
    # T09 persistence: file-backed storage when DUCKDB_PATH is set so the
    # research recorder survives restarts; default :memory: (no behavior
    # change). An unusable path must never prevent startup — fall back.
    path = os.environ.get("DUCKDB_PATH", ":memory:") or ":memory:"
    if path != ":memory:":
        try:
            return DuckDBEngine(path)
        except Exception as e:
            logger.warning("DUCKDB_PATH=%s unusable (%s) — falling back to :memory:", path, e)
    return DuckDBEngine()


db = _open_shared_db()
# Never let test teardown close the shared app singleton.
db._is_shared_singleton = True
DuckDBEngine._live_instances.remove(db)
