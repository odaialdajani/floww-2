"""
backend/services/backtest/duckdb_logger.py

DuckDB P&L logging adapter for paper trading backtest results.

Logs completed trades, equity curves, and portfolio snapshots to DuckDB
for post-hoc analysis, dashboards, and ML training data.

Schema:
  trade_log:    (run_id, fold, ticker, entry_idx, exit_idx, side, direction,
                 entry_price, exit_price, quantity, pnl, net_pnl, commission,
                 slippage, timestamp)

  equity_curve: (run_id, fold, ticker, bar_idx, equity, drawdown, timestamp)

  run_meta:     (run_id, ticker, n_splits, embargo, initial_capital,
                 total_pnl, sharpe, sortino, calmar, max_dd_pct,
                 timestamp)

Usage:
    from services.backtest.duckdb_logger import BacktestDuckDBLogger

    logger = BacktestDuckDBLogger(":memory:")  # or a file path
    logger.log_trades(result, run_id="wf_001", fold=0, ticker="SPY")
    logger.log_equity_curve(result, run_id="wf_001", fold=0, ticker="SPY")
    logger.log_run_meta(result, run_id="wf_001", ticker="SPY", n_splits=5, embargo=5)
    report = logger.summary(run_id="wf_001")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import duckdb
import numpy as np

from .report import BacktestResult

logger = logging.getLogger("backtest.duckdb_logger")


class BacktestDuckDBLogger:
    """DuckDB-backed logger for backtest results.

    Creates and manages a DuckDB database with tables for trade logs,
    equity curves, and run metadata. Supports in-memory and file-backed modes.

    Args:
        db_path: Path to DuckDB file, or ":memory:" for in-memory (default).
    """

    def __init__(self, db_path: str = ":memory:"):
        self._conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        """Create tables if they don't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                run_id        VARCHAR,
                fold          INTEGER,
                ticker        VARCHAR,
                entry_idx     INTEGER,
                exit_idx      INTEGER,
                side          VARCHAR,
                direction     VARCHAR,
                entry_price   DOUBLE,
                exit_price    DOUBLE,
                quantity      INTEGER,
                pnl           DOUBLE,
                net_pnl       DOUBLE,
                commission    DOUBLE,
                slippage      DOUBLE,
                logged_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS equity_curve (
                run_id        VARCHAR,
                fold          INTEGER,
                ticker        VARCHAR,
                bar_idx       INTEGER,
                equity        DOUBLE,
                drawdown      DOUBLE,
                logged_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS run_meta (
                run_id          VARCHAR PRIMARY KEY,
                ticker          VARCHAR,
                n_splits        INTEGER,
                embargo         INTEGER,
                initial_capital DOUBLE,
                total_pnl       DOUBLE,
                sharpe          DOUBLE,
                sortino         DOUBLE,
                calmar          DOUBLE,
                max_dd_pct      DOUBLE,
                n_trades        INTEGER,
                total_bars      INTEGER,
                timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trade_run ON trade_log(run_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_equity_run ON equity_curve(run_id)
        """)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_trades(
        self,
        result: BacktestResult,
        run_id: str = "default",
        fold: int = 0,
        ticker: str = "",
    ) -> int:
        """Log all trades from a BacktestResult to DuckDB.

        Args:
            result: Completed BacktestResult.
            run_id: Unique run identifier (e.g. "purged_cv_001").
            fold: Fold index within the run.
            ticker: Ticker symbol.

        Returns:
            Number of trades logged.
        """
        ticker = ticker or result.ticker or "UNKNOWN"
        trades = result.trades

        if not trades:
            return 0

        rows = [
            (
                run_id,
                fold,
                ticker,
                t.entry_bar_idx,
                t.exit_bar_idx,
                t.side,
                t.direction,
                float(t.entry_price),
                float(t.exit_price),
                int(t.quantity),
                float(t.pnl),
                float(t.net_pnl),
                float(t.commission),
                float(t.slippage),
            )
            for t in trades
        ]

        self._conn.executemany(
            """INSERT INTO trade_log
               (run_id, fold, ticker, entry_idx, exit_idx, side, direction,
                entry_price, exit_price, quantity, pnl, net_pnl, commission, slippage)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

        logger.info(f"Logged {len(rows)} trades for run_id={run_id}, fold={fold}")
        return len(rows)

    def log_equity_curve(
        self,
        result: BacktestResult,
        run_id: str = "default",
        fold: int = 0,
        ticker: str = "",
    ) -> int:
        """Log equity curve from a BacktestResult to DuckDB.

        Args:
            result: Completed BacktestResult.
            run_id: Unique run identifier.
            fold: Fold index.
            ticker: Ticker symbol.

        Returns:
            Number of equity points logged.
        """
        ticker = ticker or result.ticker or "UNKNOWN"
        curve = result.equity_curve
        dd = result.drawdown_curve

        if not curve:
            return 0

        # Pad drawdown curve if shorter
        dd = dd + [0.0] * (len(curve) - len(dd))

        rows = [
            (run_id, fold, ticker, i, float(eq), float(dd[i]))
            for i, eq in enumerate(curve)
        ]

        self._conn.executemany(
            """INSERT INTO equity_curve
               (run_id, fold, ticker, bar_idx, equity, drawdown)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )

        return len(rows)

    def log_run_meta(
        self,
        result: BacktestResult,
        run_id: str = "default",
        ticker: str = "",
        n_splits: int = 1,
        embargo: int = 0,
    ) -> None:
        """Log run-level metadata to DuckDB.

        Args:
            result: Completed BacktestResult (metrics must be computed).
            ticker: Ticker symbol.
            run_id: Unique run identifier.
            n_splits: Number of CV folds.
            embargo: Embargo size used.
        """
        ticker = ticker or result.ticker or "UNKNOWN"
        m = result.metrics if result.metrics else result.compute_metrics()

        # Upsert: replace if run_id exists
        self._conn.execute("""
            INSERT OR REPLACE INTO run_meta
            (run_id, ticker, n_splits, embargo, initial_capital,
             total_pnl, sharpe, sortino, calmar, max_dd_pct,
             n_trades, total_bars, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            run_id,
            ticker,
            n_splits,
            embargo,
            float(result.initial_capital),
            float(m.get("total_pnl", 0.0)),
            float(m.get("sharpe", 0.0)),
            float(m.get("sortino", 0.0)),
            float(m.get("calmar", 0.0)),
            float(m.get("max_drawdown_pct", 0.0)),
            int(m.get("n_trades", 0)),
            int(result.total_bars),
        ))

        logger.info(
            f"Run meta logged: {run_id} ticker={ticker} "
            f"sharpe={m.get('sharpe', 0):.3f} sortino={m.get('sortino', 0):.3f} "
            f"max_dd={m.get('max_drawdown_pct', 0):.2f}% "
            f"trades={int(m.get('n_trades', 0))}"
        )

    def log_all(
        self,
        results: List[BacktestResult],
        run_id: str = "default",
        ticker: str = "",
        n_splits: int = 1,
        embargo: int = 0,
    ) -> Dict[str, int]:
        """Log trades, equity curves, and metadata for a list of results.

        Args:
            results: List of BacktestResult (one per fold).
            run_id: Base run identifier (fold suffix appended).
            ticker: Ticker symbol.
            n_splits: Number of CV folds.
            embargo: Embargo size used.

        Returns:
            Dict with counts: trades_logged, equity_points_logged, folds_logged.
        """
        total_trades = 0
        total_equity = 0

        for fold, result in enumerate(results):
            trades = self.log_trades(result, run_id=f"{run_id}_f{fold}", fold=fold, ticker=ticker)
            eq_points = self.log_equity_curve(result, run_id=f"{run_id}_f{fold}", fold=fold, ticker=ticker)
            total_trades += trades
            total_equity += eq_points

        # Aggregate run meta (average across folds)
        if results:
            agg = BacktestResult(ticker=ticker)
            agg.trades = [t for r in results for t in r.trades]
            agg.equity_curve = results[-1].equity_curve  # Last fold equity
            agg.drawdown_curve = results[-1].drawdown_curve
            agg.total_bars = max(r.total_bars for r in results)
            agg.initial_capital = results[0].initial_capital
            agg.compute_metrics()
            self.log_run_meta(agg, run_id=run_id, ticker=ticker, n_splits=n_splits, embargo=embargo)

        return {
            "trades_logged": total_trades,
            "equity_points_logged": total_equity,
            "folds_logged": len(results),
        }

    # ------------------------------------------------------------------
    # Analysis queries
    # ------------------------------------------------------------------

    def summary(self, run_id: str = "default") -> Dict[str, Any]:
        """Return a summary dict for a run.

        Args:
            run_id: Run identifier.

        Returns:
            Dict with metadata, trade stats, and equity curve.
        """
        meta = self._conn.execute(
            "SELECT * FROM run_meta WHERE run_id = ?", [run_id]
        ).fetchdf()

        trades = self._conn.execute(
            "SELECT COUNT(*) as count, SUM(net_pnl) as total_pnl, "
            "AVG(net_pnl) as avg_pnl, "
            "SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins, "
            "SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losses "
            "FROM trade_log WHERE run_id LIKE ?",
            [f"{run_id}%"],
        ).fetchdf()

        return {
            "meta": meta.replace({np.nan: None}).to_dict("records") if len(meta) > 0 else [],
            "trades": trades.replace({np.nan: None}).to_dict("records") if len(trades) > 0 else [],
            "run_id": run_id,
        }

    def equity_curve(self, run_id: str = "default") -> List[Dict[str, Any]]:
        """Return equity curve for a run."""
        df = self._conn.execute(
            "SELECT * FROM equity_curve WHERE run_id LIKE ? ORDER BY bar_idx",
            [f"{run_id}%"],
        ).fetchdf()
        return df.replace({np.nan: None}).to_dict("records")

    def leaderboard(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Return top-N runs by Sharpe ratio."""
        df = self._conn.execute("""
            SELECT run_id, ticker, n_splits, embargo, sharpe, sortino,
                   calmar, max_dd_pct, total_pnl, n_trades
            FROM run_meta
            ORDER BY sharpe DESC
            LIMIT ?
        """, [top_n]).fetchdf()
        return df.replace({np.nan: None}).to_dict("records")

    def close(self):
        """Close the DuckDB connection."""
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
