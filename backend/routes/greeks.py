"""
backend/routes/greeks.py

Greeks API routes.

GET /api/greeks/profile/{ticker}
  → Aggregated Greeks by strike from gflows_greeks DuckDB table.
  → Validates ticker ∈ {SPY, QQQ, SPX, IWM}
  → Returns delta_absolute, gamma_total, vanna, charm arrays
  → NaN guards on all Greek fields (I-8)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from fastapi import APIRouter, HTTPException

from services.store_executor import run_store

log = logging.getLogger(__name__)

router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────

VALID_TICKERS = {"SPY", "QQQ", "SPX", "IWM"}
TABLE_NAME = "gflows_greeks"


def _get_db_path() -> Path:
    """Resolve the gflows DuckDB path from env or default."""
    env_path = os.environ.get("GFLOWS_DUCKDB_PATH")
    if env_path:
        return Path(env_path)
    # Default: backend/data/gflows.duckdb
    return Path(__file__).resolve().parent.parent / "data" / "gflows.duckdb"


def _require_db(db_path: Path) -> None:
    """The store must exist before a read-only connection can be opened."""
    if not db_path.exists():
        log.error("Gflows DuckDB not found: %s", db_path)
        raise HTTPException(
            status_code=503,
            detail="Greeks data not available — run setup_gflows_data.py first",
        )


def _query_greeks(db_path: Path, ticker: str,
                  conn: duckdb.DuckDBPyConnection | None = None) -> list[dict[str, Any]]:
    """Query aggregated Greeks by strike for a given ticker.

    Joins gflows_greeks data, aggregates by strike across expiries.
    Returns list of dicts with strike, delta_absolute, gamma_total, vanna, charm.
    """
    _require_db(db_path)

    owned = conn is None
    if owned:
        conn = duckdb.connect(str(db_path), read_only=True)
    try:
        # Aggregate by strike across all expiries
        # delta_absolute: sum of |delta| * OI proxy (use count as weight)
        # gamma_total: sum of gamma
        # vanna: sum of vanna
        # charm: sum of charm
        rows = conn.execute(f"""
            SELECT
                strike,
                SUM(delta_absolute) AS delta_absolute,
                SUM(gamma_total)   AS gamma_total,
                SUM(vanna)         AS vanna,
                SUM(charm)         AS charm,
                COUNT(DISTINCT expiry) AS n_expiries
            FROM {TABLE_NAME}
            WHERE ticker = ?
            GROUP BY strike
            ORDER BY strike ASC
        """, [ticker]).fetchall()

        if not rows:
            return []

        result = []
        for row in rows:
            # NaN guards (I-8): replace NaN/Inf with 0.0
            delta_abs = float(row[1]) if row[1] is not None else 0.0
            gamma_tot = float(row[2]) if row[2] is not None else 0.0
            vanna_val = float(row[3]) if row[3] is not None else 0.0
            charm_val = float(row[4]) if row[4] is not None else 0.0

            # Guard against NaN/Inf
            if not np.isfinite(delta_abs):
                delta_abs = 0.0
            if not np.isfinite(gamma_tot):
                gamma_tot = 0.0
            if not np.isfinite(vanna_val):
                vanna_val = 0.0
            if not np.isfinite(charm_val):
                charm_val = 0.0

            result.append({
                "strike": float(row[0]),
                "delta_absolute": round(delta_abs, 6),
                "gamma_total": round(gamma_tot, 6),
                "vanna": round(vanna_val, 6),
                "charm": round(charm_val, 6),
                "n_expiries": int(row[5]),
            })

        return result
    finally:
        if owned:
            conn.close()


def _get_expiries(db_path: Path, ticker: str,
                  conn: duckdb.DuckDBPyConnection | None = None) -> list[str]:
    """Get distinct expiry dates for a ticker."""
    if not db_path.exists():
        return []
    owned = conn is None
    if owned:
        conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute(f"""
            SELECT DISTINCT expiry
            FROM {TABLE_NAME}
            WHERE ticker = ?
            ORDER BY expiry ASC
        """, [ticker]).fetchall()
        return [row[0] for row in rows]
    finally:
        if owned:
            conn.close()


def _read_greeks_profile(db_path: Path, ticker: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Read the whole profile over one read-only handle.

    The handle is opened and closed inside this call: DuckDB refuses a
    read-write open of the same file while a read-only handle is held, and a
    cancelled request must never leak one.

    The store is checked before the handle is opened, inside the worker. The
    route checks it too, but the file can disappear between that check and
    this one; without the second check the open would raise a bare DuckDB
    error and answer 500 instead of the documented 503.
    """
    _require_db(db_path)
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = _query_greeks(db_path, ticker, conn)
        expiries = _get_expiries(db_path, ticker, conn) if rows else []
        return rows, expiries
    finally:
        conn.close()


# ── Routes ────────────────────────────────────────────────────────────


@router.get("/profile/{ticker}")
async def get_greeks_profile(ticker: str):
    """Get aggregated Greeks profile for a ticker.

    Returns per-strike aggregated Greeks (delta_absolute, gamma_total,
    vanna, charm) from the gflows_greeks DuckDB table.

    Path Parameters:
        ticker: any symbol (case-insensitive). Seeded tickers return rows;
        unseeded tickers return 404.

    Returns:
        JSON with ticker, strikes array, and Greek arrays.
    """
    # Open universe (2026-09-03): no allowlist — unseeded tickers fall
    # through to the 404 below with a clear message.
    upper_ticker = ticker.upper().strip()

    db_path = _get_db_path()
    _require_db(db_path)
    # One read-only connection for the whole read, opened, used and closed
    # off the request thread. It is closed there: DuckDB refuses a read-write
    # open of the same file while a read-only handle is held, and the
    # documented setup script must keep working against a live backend.
    rows, expiries = await run_store(_read_greeks_profile, db_path, upper_ticker)

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No Greeks data found for {upper_ticker}. Run setup_gflows_data.py to seed the database.",
        )

    # Unpack into columnar arrays for the response
    strikes = [r["strike"] for r in rows]
    delta_absolute = [r["delta_absolute"] for r in rows]
    gamma_total = [r["gamma_total"] for r in rows]
    vanna = [r["vanna"] for r in rows]
    charm = [r["charm"] for r in rows]

    return {
        "ticker": upper_ticker,
        "strikes": strikes,
        "expiries": expiries,
        "delta_absolute": delta_absolute,
        "gamma_total": gamma_total,
        "vanna": vanna,
        "charm": charm,
        "n_strikes": len(strikes),
    }
