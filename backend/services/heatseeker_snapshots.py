"""
backend/services/heatseeker_snapshots.py

Snapshot ingestion, OI delta computation, and top mover ranking for Heatseeker.

DuckDB table schema:
    heatseeker_snapshots (
        timestamp  TIMESTAMP,
        ticker     VARCHAR,
        expiry     VARCHAR,
        strike     DOUBLE,
        type       VARCHAR(4),
        oi         BIGINT,
        volume     BIGINT,
        iv         DOUBLE,
        delta_val  DOUBLE,
        gamma_val  DOUBLE
    )

All functions are NaN-safe (I-8 guards) and handle zero-OI without division errors.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pyarrow as pa

from services.connection_guard import guarded_connection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DuckDB table management
# ---------------------------------------------------------------------------

SNAPSHOT_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS heatseeker_snapshots (
        timestamp  TIMESTAMP,
        ticker     VARCHAR,
        expiry     VARCHAR,
        strike     DOUBLE,
        type       VARCHAR(4),
        oi         BIGINT,
        volume     BIGINT,
        iv         DOUBLE,
        double_val DOUBLE,
        gamma_val  DOUBLE
    )
"""

# Corrected schema (delta_val, not double_val)
SNAPSHOT_TABLE_SCHEMA_V2 = """
    CREATE TABLE IF NOT EXISTS heatseeker_snapshots (
        timestamp  TIMESTAMP,
        ticker     VARCHAR,
        expiry     VARCHAR,
        strike     DOUBLE,
        type       VARCHAR(4),
        oi         BIGINT,
        volume     BIGINT,
        iv         DOUBLE,
        delta_val  DOUBLE,
        gamma_val  DOUBLE
    )
"""

SNAPSHOT_COLUMNS = [
    "timestamp", "ticker", "expiry", "strike", "type",
    "oi", "volume", "iv", "delta_val", "gamma_val",
]

SNAPSHOT_COLUMN_TYPES = {
    "timestamp": pa.timestamp("us"),
    "ticker": pa.string(),
    "expiry": pa.string(),
    "strike": pa.float64(),
    "type": pa.string(),
    "oi": pa.int64(),
    "volume": pa.int64(),
    "iv": pa.float64(),
    "delta_val": pa.float64(),
    "gamma_val": pa.float64(),
}


@guarded_connection
def create_snapshot_table(conn) -> None:
    """Create the heatseeker_snapshots table if it doesn't exist.

    Also creates an index on (ticker, timestamp) for fast lookups.
    """
    conn.execute(SNAPSHOT_TABLE_SCHEMA_V2)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hs_ticker_ts "
        "ON heatseeker_snapshots(ticker, timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hs_contract "
        "ON heatseeker_snapshots(ticker, expiry, strike, type)"
    )


# ---------------------------------------------------------------------------
# PyArrow bulk insert (I-3: no Pandas)
# ---------------------------------------------------------------------------

@guarded_connection
def bulk_insert(conn, batch: pa.RecordBatch) -> int:
    """Insert a PyArrow RecordBatch into heatseeker_snapshots.

    Uses DuckDB's native Arrow integration for zero-copy bulk load.

    Args:
        conn: DuckDB connection.
        batch: PyArrow RecordBatch with columns matching SNAPSHOT_COLUMNS.

    Returns:
        Number of rows inserted.
    """
    # DuckDB can consume PyArrow tables directly via register + INSERT
    # For maximum performance we use the connection's arrow() method
    try:
        # Method 1: Direct Arrow table insert (fastest)
        if hasattr(conn, "register"):
            conn.register("snapshot_batch", batch)
            conn.execute(
                "INSERT INTO heatseeker_snapshots "
                "SELECT * FROM snapshot_batch"
            )
            conn.unregister("snapshot_batch")
        else:
            # Method 2: Fallback to executemany with dict rows
            rows = batch.to_pydict()
            n = batch.num_rows
            data = [
                tuple(rows[col][i] for col in SNAPSHOT_COLUMNS)
                for i in range(n)
            ]
            conn.executemany(
                "INSERT INTO heatseeker_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                data,
            )
        return batch.num_rows
    except Exception as e:
        logger.error(f"Bulk insert failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Chain → RecordBatch conversion
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safe float conversion. NaN → default (I-8 guard)."""
    if val is None:
        return default
    try:
        f = float(val)
        if f != f:  # NaN check without math import
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """Safe int conversion."""
    if val is None:
        return default
    try:
        i = int(val)
        return i
    except (TypeError, ValueError):
        return default


def contracts_to_recordbatch(chain: dict[str, Any]) -> pa.RecordBatch:
    """Convert a chain dict to a PyArrow RecordBatch for bulk insert.

    Expected chain format:
        {
            "ticker": "SPY",
            "spot": 500.0,
            "contracts": [
                {
                    "expiry": "2026-07-24",
                    "strike": 500.0,
                    "type": "C",
                    "oi": 1000,
                    "volume": 500,
                    "iv": 0.15,
                    "delta": 0.5,
                    "gamma": 0.02
                },
                ...
            ]
        }

    Missing fields default to 0 / 0.0 (I-8 NaN guards).
    """
    ticker = str(chain.get("ticker", "")).upper()
    contracts = chain.get("contracts") or []
    ts = datetime.now(UTC)

    arrays = {
        "timestamp": pa.array([ts] * len(contracts), type=pa.timestamp("us")),
        "ticker": pa.array([ticker] * len(contracts), type=pa.string()),
        "expiry": pa.array(
            [str(c.get("expiry", "")) for c in contracts],
            type=pa.string(),
        ),
        "strike": pa.array(
            [_safe_float(c.get("strike")) for c in contracts],
            type=pa.float64(),
        ),
        "type": pa.array(
            [str(c.get("type", "")).upper()[:4] for c in contracts],
            type=pa.string(),
        ),
        "oi": pa.array(
            [_safe_int(c.get("oi", c.get("open_interest", 0))) for c in contracts],
            type=pa.int64(),
        ),
        "volume": pa.array(
            [_safe_int(c.get("volume", 0)) for c in contracts],
            type=pa.int64(),
        ),
        "iv": pa.array(
            [_safe_float(c.get("iv")) for c in contracts],
            type=pa.float64(),
        ),
        "delta_val": pa.array(
            [_safe_float(c.get("delta")) for c in contracts],
            type=pa.float64(),
        ),
        "gamma_val": pa.array(
            [_safe_float(c.get("gamma")) for c in contracts],
            type=pa.float64(),
        ),
    }

    return pa.record_batch(arrays)


# ---------------------------------------------------------------------------
# OI Delta computation (I-8: NaN guards, zero-OI handling)
# ---------------------------------------------------------------------------

def _contract_key(c: dict[str, Any]) -> tuple[str, float, str]:
    """Unique key for a contract: (expiry, strike, type)."""
    return (
        str(c.get("expiry", "")),
        _safe_float(c.get("strike")),
        str(c.get("type", "")).upper(),
    )


def _get_oi(c: dict[str, Any]) -> float:
    """Extract OI from contract dict, trying 'oi' then 'open_interest'."""
    val = c.get("oi")
    if val is None:
        val = c.get("open_interest", 0)
    return _safe_float(val)


def _get_volume(c: dict[str, Any]) -> float:
    """Extract volume from contract dict."""
    return _safe_float(c.get("volume"))


def compute_oi_delta(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute OI delta between two snapshots.

    For each contract in the current snapshot, computes:
        oi_delta     = current_oi - previous_oi
        oi_delta_pct = oi_delta / previous_oi  (0.0 if both 0, inf if prev=0)
        volume_delta = current_volume - previous_volume

    Contracts only in previous (not in current) are included with
    current_oi=0 (full unwind).

    I-8: NaN values in OI/volume are treated as 0.
         Division by zero is handled: prev=0, cur>0 → inf; both 0 → 0.0.

    Args:
        current:  {"contracts": [...]} with current snapshot.
        previous: {"contracts": [...]} with previous snapshot.

    Returns:
        List of dicts with keys:
            ticker, expiry, strike, type, oi, volume, iv, delta, gamma,
            oi_delta, oi_delta_pct, volume_delta
    """
    cur_contracts = current.get("contracts") or []
    prev_contracts = previous.get("contracts") or []

    # Build lookup maps
    prev_map: dict[tuple, dict[str, Any]] = {}
    for c in prev_contracts:
        key = _contract_key(c)
        prev_map[key] = c

    cur_map: dict[tuple, dict[str, Any]] = {}
    for c in cur_contracts:
        key = _contract_key(c)
        cur_map[key] = c

    # Union of all contract keys
    all_keys = set(cur_map.keys()) | set(prev_map.keys())

    results: list[dict[str, Any]] = []
    for key in sorted(all_keys):
        expiry, strike, ctype = key
        cur = cur_map.get(key, {})
        prev = prev_map.get(key, {})

        cur_oi = _get_oi(cur)
        prev_oi = _get_oi(prev)
        cur_vol = _get_volume(cur)
        prev_vol = _get_volume(prev)

        oi_delta = cur_oi - prev_oi
        vol_delta = cur_vol - prev_vol

        # I-8: Division by zero guard
        if prev_oi == 0.0 and cur_oi == 0.0:
            oi_delta_pct = 0.0
        elif prev_oi == 0.0:
            oi_delta_pct = float("inf")
        else:
            oi_delta_pct = oi_delta / prev_oi

        # I-8: Guard against NaN in pct (shouldn't happen but defensive)
        if oi_delta_pct != oi_delta_pct:  # NaN check
            oi_delta_pct = 0.0

        results.append({
            "ticker": cur.get("ticker", prev.get("ticker", "")),
            "expiry": expiry,
            "strike": strike,
            "type": ctype,
            "oi": int(cur_oi),
            "volume": int(cur_vol),
            "iv": _safe_float(cur.get("iv", prev.get("iv"))),
            "delta": _safe_float(cur.get("delta", prev.get("delta"))),
            "gamma": _safe_float(cur.get("gamma", prev.get("gamma"))),
            "oi_delta": int(oi_delta),
            "oi_delta_pct": oi_delta_pct,
            "volume_delta": int(vol_delta),
        })

    return results


# ---------------------------------------------------------------------------
# Top Movers ranking
# ---------------------------------------------------------------------------

def rank_top_movers(
    deltas: list[dict[str, Any]],
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Rank contracts by absolute OI change, with volume spike as tiebreaker.

    Scoring:
        score = abs(oi_delta) + abs(volume_delta) * 0.1

    This prioritizes large OI changes but uses volume delta to break ties.

    Args:
        deltas: Output from compute_oi_delta().
        top_n: Maximum number of results to return.

    Returns:
        Sorted list of top movers, descending by score.
    """
    if not deltas:
        return []

    scored = []
    for d in deltas:
        oi_delta = abs(d.get("oi_delta", 0))
        vol_delta = abs(d.get("volume_delta", 0))
        score = oi_delta + vol_delta * 0.1
        scored.append({**d, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

@guarded_connection
def get_latest_snapshot(
    conn,
    ticker: str,
) -> list[dict[str, Any]]:
    """Get the most recent snapshot for a ticker.

    Returns all contracts from the latest timestamp for the given ticker.
    """
    try:
        result = conn.execute(
            """
            SELECT *
            FROM heatseeker_snapshots
            WHERE ticker = ?
              AND timestamp = (
                  SELECT MAX(timestamp)
                  FROM heatseeker_snapshots
                  WHERE ticker = ?
              )
            ORDER BY expiry, strike, type
            """,
            [ticker.upper(), ticker.upper()],
        ).fetchdf()
        # Convert NaN to None for JSON safety
        return result.where(result.notna(), None).to_dict("records")
    except Exception as e:
        logger.error(f"get_latest_snapshot error: {e}")
        return []


@guarded_connection
def get_history(
    conn,
    ticker: str,
    expiry: str,
    strike: float,
    ctype: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get time series for a specific contract.

    Returns historical snapshots ordered by timestamp ascending.
    """
    try:
        result = conn.execute(
            """
            SELECT timestamp, oi, volume, iv, delta_val, gamma_val
            FROM heatseeker_snapshots
            WHERE ticker = ? AND expiry = ? AND strike = ? AND type = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            [ticker.upper(), expiry, float(strike), ctype.upper(), limit],
        ).fetchdf()
        return result.where(result.notna(), None).to_dict("records")
    except Exception as e:
        logger.error(f"get_history error: {e}")
        return []


@guarded_connection
def get_top_movers_from_db(
    conn,
    ticker: str,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Compute top movers from the two most recent snapshots in DuckDB.

    Fetches the latest and previous snapshots, computes OI deltas,
    and returns the top N movers.
    """
    try:
        # Get the two most recent timestamps
        ts_rows = conn.execute(
            """
            SELECT DISTINCT timestamp
            FROM heatseeker_snapshots
            WHERE ticker = ?
            ORDER BY timestamp DESC
            LIMIT 2
            """,
            [ticker.upper()],
        ).fetchall()

        if not ts_rows:
            return []

        latest_ts = ts_rows[0][0]
        prev_ts = ts_rows[1][0] if len(ts_rows) > 1 else None

        # Fetch latest snapshot
        latest_rows = conn.execute(
            """
            SELECT ticker, expiry, strike, type, oi, volume, iv, delta_val, gamma_val
            FROM heatseeker_snapshots
            WHERE ticker = ? AND timestamp = ?
            """,
            [ticker.upper(), latest_ts],
        ).fetchdf()

        if latest_rows.empty:
            return []

        if prev_ts is None:
            # No previous snapshot — return all contracts with zero delta
            contracts = latest_rows.where(latest_rows.notna(), None).to_dict("records")
            return [
                {
                    "ticker": c["ticker"],
                    "expiry": c["expiry"],
                    "strike": c["strike"],
                    "type": c["type"],
                    "oi": c["oi"],
                    "volume": c["volume"],
                    "iv": c["iv"],
                    "delta": c.get("delta_val", 0),
                    "gamma": c.get("gamma_val", 0),
                    "oi_delta": 0,
                    "oi_delta_pct": 0.0,
                    "volume_delta": 0,
                    "score": 0.0,
                }
                for c in contracts
            ][:top_n]

        # Fetch previous snapshot
        prev_rows = conn.execute(
            """
            SELECT ticker, expiry, strike, type, oi, volume, iv, delta_val, gamma_val
            FROM heatseeker_snapshots
            WHERE ticker = ? AND timestamp = ?
            """,
            [ticker.upper(), prev_ts],
        ).fetchdf()

        # Convert to chain format for compute_oi_delta
        current = {"contracts": rows_to_contracts(latest_rows)}
        previous = {"contracts": rows_to_contracts(prev_rows)}

        deltas = compute_oi_delta(current, previous)
        return rank_top_movers(deltas, top_n=top_n)

    except Exception as e:
        logger.error(f"get_top_movers_from_db error: {e}")
        return []

def rows_to_contracts(df):
            records = df.where(df.notna(), None).to_dict("records")
            return [
                {
                    "ticker": r["ticker"],
                    "expiry": r["expiry"],
                    "strike": r["strike"],
                    "type": r["type"],
                    "oi": r["oi"],
                    "volume": r["volume"],
                    "iv": r["iv"],
                    "delta": r.get("delta_val", 0),
                    "gamma": r.get("gamma_val", 0),
                }
                for r in records
            ]

