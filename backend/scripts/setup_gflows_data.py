#!/usr/bin/env python3
"""
backend/scripts/setup_gflows_data.py

Seed DuckDB with deterministic gflows Greeks data.

Schema:
    gflows_greeks (
        ticker, expiry, strike, type,
        delta_absolute, gamma_total, vanna, charm
    )

Uses PyArrow bulk insert (I-3). Deterministic — safe to re-run (drops & recreates).

Usage:
    cd backend && source venv/bin/activate && python scripts/setup_gflows_data.py
    python scripts/setup_gflows_data.py --db-path /tmp/gflows.duckdb
    python scripts/setup_gflows_data.py --verify-only
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pyarrow as pa

log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gflows.duckdb"
TABLE_NAME = "gflows_greeks"

TICKERS = ["SPY", "QQQ", "SPX", "IWM"]

# Expiries: generate 4 weekly + 1 monthly from today
def _generate_expiries(n_weeks: int = 4) -> list[str]:
    """Generate deterministic expiry dates (Fridays only)."""
    today = date.today()
    expiries = []
    # Find next Friday
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # skip today if it's Friday, take next
    first_friday = today + timedelta(days=days_ahead)
    for i in range(n_weeks + 1):
        exp = first_friday + timedelta(weeks=i)
        expiries.append(exp.isoformat())
    return expiries


def _spot_price(ticker: str) -> float:
    """Deterministic spot prices for mock data."""
    spots = {"SPY": 530.0, "QQQ": 460.0, "SPX": 5900.0, "IWM": 225.0}
    return spots.get(ticker, 100.0)


def _generate_strikes(ticker: str) -> list[float]:
    """Generate deterministic strike ladder per ticker."""
    spot = _spot_price(ticker)
    # 21 strikes centered on spot, step = spot * 0.01
    step = round(spot * 0.01, 2)
    n = 10  # 10 below, spot, 10 above
    return [round(spot + (i - n) * step, 2) for i in range(n * 2 + 1)]


def _bs_delta(S: float, K: float, T: float, sigma: float, kind: str) -> float:
    """Simplified Black-Scholes delta for mock data."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        from scipy.stats import norm
        d1 = (math.log(S / K) + (0.05 + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        if kind == "call":
            return float(norm.cdf(d1))
        else:
            return float(norm.cdf(d1) - 1.0)
    except Exception:
        return 0.0


def _bs_gamma(S: float, K: float, T: float, sigma: float) -> float:
    """Simplified Black-Scholes gamma for mock data."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        from scipy.stats import norm
        d1 = (math.log(S / K) + (0.05 + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        return float(norm.pdf(d1) / (S * sigma * math.sqrt(T)))
    except Exception:
        return 0.0


def _bs_vanna(S: float, K: float, T: float, sigma: float) -> float:
    """Simplified Black-Scholes vanna for mock data."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        from scipy.stats import norm
        d1 = (math.log(S / K) + (0.05 + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return float(-norm.pdf(d1) * d2 / sigma)
    except Exception:
        return 0.0


def _bs_charm(S: float, K: float, T: float, sigma: float, kind: str) -> float:
    """Simplified Black-Scholes charm (delta decay) for mock data."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        from scipy.stats import norm
        d1 = (math.log(S / K) + (0.05 + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf = norm.pdf(d1)
        cdf = norm.cdf(d1)
        charm_val = -(pdf * (2 * 0.05 * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if kind == "put":
            charm_val = -( -0.05 * (1 - cdf) - pdf * (2 * 0.05 * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        return float(charm_val)
    except Exception:
        return 0.0


def bulk_insert(conn: duckdb.DuckDBPyConnection, table: pa.Table) -> int:
    """PyArrow bulk insert into DuckDB (I-3)."""
    # Register the PyArrow table as a DuckDB view, then INSERT
    conn.register("gflows_arrow", table)
    conn.execute(f"INSERT INTO {TABLE_NAME} SELECT * FROM gflows_arrow")
    conn.unregister("gflows_arrow")
    count = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    log.info("Bulk inserted %d rows via PyArrow", count)
    return count


def verify(conn: duckdb.DuckDBPyConnection) -> bool:
    """Verify data integrity."""
    try:
        # Check row count
        total = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
        assert total > 0, "Table is empty"

        # Check tickers
        tickers = {
            row[0]
            for row in conn.execute(f"SELECT DISTINCT ticker FROM {TABLE_NAME}").fetchall()
        }
        assert tickers == set(TICKERS), f"Tickers mismatch: {tickers}"

        # Check delta_absolute is non-zero for some rows
        nonzero_delta = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE delta_absolute > 0"
        ).fetchone()[0]
        assert nonzero_delta > 0, "All delta_absolute values are zero"

        # Check no NaN in critical columns
        nan_count = conn.execute(f"""
            SELECT COUNT(*) FROM {TABLE_NAME}
            WHERE delta_absolute IS NULL
               OR gamma_total IS NULL
               OR vanna IS NULL
               OR charm IS NULL
        """).fetchone()[0]
        assert nan_count == 0, f"Found {nan_count} rows with NULLs"

        # Per-ticker stats
        for ticker in TICKERS:
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE ticker = ?", [ticker]
            ).fetchone()[0]
            assert cnt > 0, f"No data for {ticker}"
            log.info("  %s: %d rows", ticker, cnt)

        log.info("Verification PASSED — %d total rows", total)
        return True

    except AssertionError as e:
        log.error("Verification FAILED: %s", e)
        return False


def seed_database(db_path: Path) -> bool:
    """Full pipeline: generate data → create table → bulk insert → verify."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Seeding gflows data into %s", db_path)
    conn = duckdb.connect(str(db_path))

    try:
        table = generate_mock_data()
        create_table(conn)
        bulk_insert(conn, table)
        return verify(conn)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed DuckDB with gflows Greeks data")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"DuckDB file path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing data, don't regenerate",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.verify_only:
        if not args.db_path.exists():
            log.error("Database not found: %s", args.db_path)
            return 1
        conn = duckdb.connect(str(args.db_path))
        ok = verify(conn)
        conn.close()
        return 0 if ok else 1

    ok = seed_database(args.db_path)
    return 0 if ok else 1


def generate_mock_data() -> pa.Table:
    """Generate deterministic mock gflows Greeks data as PyArrow Table."""
    expiries = _generate_expiries()

    tickers_list = []
    expiries_list = []
    strikes_list = []
    types_list = []
    delta_abs_list = []
    gamma_total_list = []
    vanna_list = []
    charm_list = []

    for ticker in TICKERS:
        spot = _spot_price(ticker)
        strikes = _generate_strikes(ticker)
        # IV varies by ticker
        base_iv = {"SPY": 0.16, "QQQ": 0.20, "SPX": 0.14, "IWM": 0.22}[ticker]

        for expiry in expiries:
            exp_date = date.fromisoformat(expiry)
            T = max((exp_date - date.today()).days, 1) / 365.0

            for strike in strikes:
                # IV skew: OTM puts higher IV, OTM calls lower IV
                moneyness = strike / spot
                iv = base_iv + 0.05 * (1.0 - moneyness)  # simple skew

                for opt_type in ("call", "put"):
                    delta = _bs_delta(spot, strike, T, iv, opt_type)
                    gamma = _bs_gamma(spot, strike, T, iv)
                    vanna = _bs_vanna(spot, strike, T, iv)
                    charm = _bs_charm(spot, strike, T, iv, opt_type)

                    tickers_list.append(ticker)
                    expiries_list.append(expiry)
                    strikes_list.append(strike)
                    types_list.append(opt_type)
                    delta_abs_list.append(round(abs(delta), 6))
                    gamma_total_list.append(round(gamma, 6))
                    vanna_list.append(round(vanna, 6))
                    charm_list.append(round(charm, 6))

    table = pa.table({
        "ticker": pa.array(tickers_list, type=pa.string()),
        "expiry": pa.array(expiries_list, type=pa.string()),
        "strike": pa.array(strikes_list, type=pa.float64()),
        "type": pa.array(types_list, type=pa.string()),
        "delta_absolute": pa.array(delta_abs_list, type=pa.float64()),
        "gamma_total": pa.array(gamma_total_list, type=pa.float64()),
        "vanna": pa.array(vanna_list, type=pa.float64()),
        "charm": pa.array(charm_list, type=pa.float64()),
    })

    log.info(
        "Generated %d rows (%d tickers x %d expiries x ~%d strikes x 2 types)",
        len(table), len(TICKERS), len(expiries),
        len(table) // (len(TICKERS) * len(expiries) * 2),
    )
    return table


def create_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the gflows_greeks table, dropping if exists."""
    conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    conn.execute(f"""
        CREATE TABLE {TABLE_NAME} (
            ticker        VARCHAR,
            expiry        VARCHAR,
            strike        DOUBLE,
            type          VARCHAR,
            delta_absolute DOUBLE,
            gamma_total   DOUBLE,
            vanna         DOUBLE,
            charm         DOUBLE
        )
    """)
    conn.execute(f"CREATE INDEX idx_gflows_ticker ON {TABLE_NAME}(ticker)")
    conn.execute(f"CREATE INDEX idx_gflows_expiry ON {TABLE_NAME}(expiry)")
    log.info("Table %s created with indexes", TABLE_NAME)


if __name__ == "__main__":
    sys.exit(main())
