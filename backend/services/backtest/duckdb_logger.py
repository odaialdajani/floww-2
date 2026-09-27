"""Explicit, offline storage for BacktestResult snapshots.

Recovered from 999cda0e with exact run matching and separate fold records.
This module never runs a strategy, calculates missing performance metrics, or
promotes a model. A logger belongs to one caller/thread. Repeated writes replace
the requested run/fold; log_all replaces a whole run atomically.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import duckdb

from .report import BacktestResult


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any, name: str) -> int:
    number = _number(value)
    if number is None or number < 0 or not number.is_integer():
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(number)


class BacktestDuckDBLogger:
    def __init__(self, db_path: str = ":memory:"):
        self._conn = duckdb.connect(db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                run_id VARCHAR, fold INTEGER, ticker VARCHAR, trade_idx INTEGER,
                entry_idx INTEGER, exit_idx INTEGER, side VARCHAR, direction VARCHAR,
                entry_price DOUBLE, exit_price DOUBLE, quantity INTEGER,
                pnl DOUBLE, net_pnl DOUBLE, commission DOUBLE, slippage DOUBLE,
                PRIMARY KEY (run_id, fold, trade_idx));
            CREATE TABLE IF NOT EXISTS equity_curve (
                run_id VARCHAR, fold INTEGER, ticker VARCHAR, bar_idx INTEGER,
                equity DOUBLE, drawdown DOUBLE, PRIMARY KEY (run_id, fold, bar_idx));
            CREATE TABLE IF NOT EXISTS run_meta (
                run_id VARCHAR, fold INTEGER, ticker VARCHAR, n_splits INTEGER,
                embargo INTEGER, initial_capital DOUBLE, total_pnl DOUBLE,
                sharpe DOUBLE, sortino DOUBLE, calmar DOUBLE, max_dd_pct DOUBLE,
                n_trades INTEGER, total_bars INTEGER, PRIMARY KEY (run_id, fold));
        """)

    @staticmethod
    def _identity(run_id: str, fold: int) -> tuple[str, int]:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a nonempty string")
        return run_id, _integer(fold, "fold")

    def _trade_rows(self, result, run_id, fold, ticker):
        self._identity(run_id, fold)
        return [
            (run_id, fold, ticker or result.ticker or None, i,
             _integer(t.entry_bar_idx, "entry index"), _integer(t.exit_bar_idx, "exit index"),
             t.side, t.direction, _number(t.entry_price), _number(t.exit_price),
             _integer(t.quantity, "quantity"), _number(t.pnl), _number(t.net_pnl),
             _number(t.commission), _number(t.slippage))
            for i, t in enumerate(result.trades)
        ]

    def _equity_rows(self, result, run_id, fold, ticker):
        self._identity(run_id, fold)
        return [
            (run_id, fold, ticker or result.ticker or None, i, _number(value),
             _number(result.drawdown_curve[i]) if i < len(result.drawdown_curve) else None)
            for i, value in enumerate(result.equity_curve)
        ]

    def _meta_row(self, result, run_id, fold, ticker, n_splits, embargo):
        self._identity(run_id, fold)
        splits = _integer(n_splits, "n_splits")
        if splits < 1 or fold >= splits:
            raise ValueError("n_splits must include this fold")
        m = result.metrics or {}
        return (run_id, fold, ticker or result.ticker or None, splits, _integer(embargo, "embargo"),
                _number(result.initial_capital), _number(m.get("total_pnl")), _number(m.get("sharpe")),
                _number(m.get("sortino")), _number(m.get("calmar")), _number(m.get("max_drawdown_pct")),
                len(result.trades), _integer(result.total_bars, "total_bars"))

    def _insert(self, table: str, rows: list[tuple]) -> None:
        # table is a module-owned constant, never user input.
        if rows:
            placeholders = ",".join("?" for _ in rows[0])
            self._conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)

    def _replace_fold(self, table, rows, run_id, fold):
        self._identity(run_id, fold)
        self._conn.execute("BEGIN TRANSACTION")
        try:
            self._conn.execute(f"DELETE FROM {table} WHERE run_id = ? AND fold = ?", [run_id, fold])
            self._insert(table, rows)
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def log_trades(self, result: BacktestResult, run_id="default", fold=0, ticker="") -> int:
        rows = self._trade_rows(result, run_id, fold, ticker)
        self._replace_fold("trade_log", rows, run_id, fold)
        return len(rows)

    def log_equity_curve(self, result: BacktestResult, run_id="default", fold=0, ticker="") -> int:
        rows = self._equity_rows(result, run_id, fold, ticker)
        self._replace_fold("equity_curve", rows, run_id, fold)
        return len(rows)

    def log_run_meta(self, result: BacktestResult, run_id="default", ticker="",
                     n_splits=1, embargo=0, *, fold=0) -> None:
        row = self._meta_row(result, run_id, fold, ticker, n_splits, embargo)
        self._replace_fold("run_meta", [row], run_id, fold)

    def log_all(self, results: Sequence[BacktestResult], run_id="default", ticker="",
                n_splits: int | None = None, embargo=0) -> dict[str, int]:
        """Store folds separately; never invent a combined equity curve/Sharpe."""
        self._identity(run_id, 0)
        splits = len(results) if n_splits is None else _integer(n_splits, "n_splits")
        if splits != len(results):
            raise ValueError("n_splits must match the supplied fold results")
        _integer(embargo, "embargo")
        # Build and validate every row before changing any stored data.
        trades, equity, meta = [], [], []
        for fold, result in enumerate(results):
            trades.extend(self._trade_rows(result, run_id, fold, ticker))
            equity.extend(self._equity_rows(result, run_id, fold, ticker))
            meta.append(self._meta_row(result, run_id, fold, ticker, splits, embargo))
        self._conn.execute("BEGIN TRANSACTION")
        try:
            for table, rows in (("trade_log", trades), ("equity_curve", equity), ("run_meta", meta)):
                self._conn.execute(f"DELETE FROM {table} WHERE run_id = ?", [run_id])
                self._insert(table, rows)
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return {"trades_logged": len(trades), "equity_points_logged": len(equity), "folds_logged": len(meta)}

    def _query(self, sql: str, params: list) -> list[dict[str, Any]]:
        cursor = self._conn.execute(sql, params)
        names = [col[0] for col in cursor.description]
        return [dict(zip(names, (None if isinstance(v, float) and not math.isfinite(v) else v for v in row),
                         strict=True)) for row in cursor.fetchall()]

    def summary(self, run_id="default") -> dict[str, Any]:
        self._identity(run_id, 0)
        return {
            "run_id": run_id,
            "meta": self._query("SELECT * FROM run_meta WHERE run_id = ? ORDER BY fold", [run_id]),
            "trades": self._query("""
                SELECT COUNT(*) AS count, COUNT(net_pnl) AS known_pnl_count,
                    CASE WHEN COUNT(net_pnl) = COUNT(*) THEN SUM(net_pnl) END AS total_pnl,
                    CASE WHEN COUNT(net_pnl) = COUNT(*) THEN AVG(net_pnl) END AS avg_pnl,
                    COUNT(*) FILTER (WHERE net_pnl > 0) AS wins,
                    COUNT(*) FILTER (WHERE net_pnl < 0) AS losses
                FROM trade_log WHERE run_id = ?""", [run_id]),
        }

    def equity_curve(self, run_id="default") -> list[dict[str, Any]]:
        self._identity(run_id, 0)
        return self._query("SELECT * FROM equity_curve WHERE run_id = ? ORDER BY fold, bar_idx", [run_id])

    def leaderboard(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Rank individual folds with known Sharpe, not combined run performance."""
        return self._query("SELECT * FROM run_meta WHERE sharpe IS NOT NULL ORDER BY sharpe DESC, run_id, fold LIMIT ?",
                           [_integer(top_n, "top_n")])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
