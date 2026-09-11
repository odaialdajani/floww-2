"""
backend/routes/backtest.py

Backtest engine API routes — Phase 6.2.

Exposes the BacktestEngine via REST so the frontend and scripts can run
IS/OOS splits, walk-forward CV, and Monte Carlo bootstrap evaluations.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from services.backtest.engine import (
    BacktestEngine,
    EngineConfig,
    run_is_oos_split,
    run_monte_carlo_bootstrap,
    run_walk_forward_cv,
)
from services.backtest.report import BacktestResult
from services.backtest.signals import RuleBasedSignal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

# In-memory per-ticker store of the last /run report (2026-09-04).
# Process-local by design (matches the heatmap SWR cache pattern);
# a restart simply returns not_found until the next run.
_reports: dict[str, dict[str, Any]] = {}


def _result_to_dict(result: BacktestResult) -> dict[str, Any]:
    """Serialize a BacktestResult for JSON transport."""
    m = result.metrics if result.metrics else result.compute_metrics()
    return {
        "ticker": result.ticker,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_capital": result.initial_capital,
        "slippage_pct": result.slippage_pct,
        "commission_per_contract": result.commission_per_contract,
        "total_bars": result.total_bars,
        "n_trades": len(result.trades),
        "equity_curve": result.equity_curve,
        "drawdown_curve": result.drawdown_curve,
        "bar_returns": result.bar_returns,
        "trades": [
            {
                "entry_bar_idx": t.entry_bar_idx,
                "exit_bar_idx": t.exit_bar_idx,
                "side": t.side,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": t.pnl,
                "commission": t.commission,
                "slippage": t.slippage,
                "net_pnl": t.net_pnl,
            }
            for t in result.trades
        ],
        "metrics": m,
    }


def _bars_to_simple(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce bar dicts to the engine's expected shape."""
    out: list[dict[str, Any]] = []
    for b in bars:
        out.append({
            "date": b.get("date", b.get("timestamp", "")),
            "open": b.get("open", 0.0),
            "high": b.get("high", 0.0),
            "low": b.get("low", 0.0),
            "close": b.get("close", 0.0),
            "volume": b.get("volume", 0),
        })
    return out


def _snaps_to_simple(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce snapshot dicts to the engine's expected shape (keep GEX fields)."""
    out: list[dict[str, Any]] = []
    for s in snapshots:
        d: dict[str, Any] = {
            "date": s.get("date", s.get("ts", "")),
        }
        for key in (
            "net_gex", "net_gex_zscore_60d", "total_call_gex", "total_put_gex",
            "king_strike", "max_pain", "spot",
        ):
            if key in s:
                d[key] = s[key]
        out.append(d)
    return out


@router.post("/run")
async def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a single backtest over aligned snapshot + bar data.

    Body:
        ticker: str
        snapshots: list[dict]  — GEX snapshot per bar
        bars: list[dict]       — OHLCV bar per bar (must match snapshots length)
        config: dict           — optional EngineConfig overrides
    """
    ticker = payload.get("ticker", "")
    snapshots = _snaps_to_simple(payload.get("snapshots", []))
    bars = _bars_to_simple(payload.get("bars", []))
    cfg_dict = payload.get("config", {})

    config = EngineConfig(
        initial_capital=cfg_dict.get("initial_capital", 100_000.0),
        slippage_pct=cfg_dict.get("slippage_pct", 0.0005),
        commission_per_contract=cfg_dict.get("commission_per_contract", 0.65),
        contracts_per_trade=cfg_dict.get("contracts_per_trade", 1),
        allow_short=cfg_dict.get("allow_short", False),
    )

    signal = RuleBasedSignal()
    engine = BacktestEngine(signal=signal, config=config)
    result = engine.run(snapshots, bars, ticker=ticker)
    report = {"status": "ok", "result": _result_to_dict(result)}
    _reports[ticker.upper()] = report
    return report


@router.get("/report/{ticker}")
async def get_backtest_report(ticker: str) -> dict[str, Any]:
    """Retrieve the last /run report for a ticker (case-insensitive).

    Returns ``{"status": "not_found", "ticker": ...}`` (HTTP 200 — honest
    empty, not an error) when no run has been stored yet.
    """
    report = _reports.get(ticker.upper())
    if report is None:
        return {"status": "not_found", "ticker": ticker.upper()}
    return report


@router.post("/is-oos")
async def run_is_oos(payload: dict[str, Any]) -> dict[str, Any]:
    """Run 70/30 in-sample / out-of-sample temporal split.

    Returns both train and test results for comparison.
    """
    ticker = payload.get("ticker", "")
    snapshots = _snaps_to_simple(payload.get("snapshots", []))
    bars = _bars_to_simple(payload.get("bars", []))
    train_ratio = payload.get("train_ratio", 0.7)
    cfg_dict = payload.get("config", {})

    config = EngineConfig(
        initial_capital=cfg_dict.get("initial_capital", 100_000.0),
        slippage_pct=cfg_dict.get("slippage_pct", 0.0005),
        commission_per_contract=cfg_dict.get("commission_per_contract", 0.65),
        contracts_per_trade=cfg_dict.get("contracts_per_trade", 1),
    )

    train_result, test_result = run_is_oos_split(
        signal_factory=lambda: RuleBasedSignal(),
        snapshots=snapshots,
        bars=bars,
        ticker=ticker,
        train_ratio=train_ratio,
        config=config,
    )
    return {
        "status": "ok",
        "train": _result_to_dict(train_result),
        "test": _result_to_dict(test_result),
    }


@router.post("/walk-forward")
async def run_walk_forward(payload: dict[str, Any]) -> dict[str, Any]:
    """Run walk-forward cross-validation.

    Body:
        ticker, snapshots, bars
        n_splits: int (default 5)
        min_train_size: int (default 50)
        config: dict
    """
    ticker = payload.get("ticker", "")
    snapshots = _snaps_to_simple(payload.get("snapshots", []))
    bars = _bars_to_simple(payload.get("bars", []))
    n_splits = payload.get("n_splits", 5)
    min_train_size = payload.get("min_train_size", 50)
    cfg_dict = payload.get("config", {})

    config = EngineConfig(
        initial_capital=cfg_dict.get("initial_capital", 100_000.0),
        slippage_pct=cfg_dict.get("slippage_pct", 0.0005),
        commission_per_contract=cfg_dict.get("commission_per_contract", 0.65),
        contracts_per_trade=cfg_dict.get("contracts_per_trade", 1),
    )

    results = run_walk_forward_cv(
        signal_factory=lambda: RuleBasedSignal(),
        snapshots=snapshots,
        bars=bars,
        ticker=ticker,
        n_splits=n_splits,
        min_train_size=min_train_size,
        config=config,
    )
    return {
        "status": "ok",
        "n_folds": len(results),
        "folds": [_result_to_dict(r) for r in results],
    }


@router.post("/monte-carlo")
async def run_monte_carlo(payload: dict[str, Any]) -> dict[str, Any]:
    """Run Monte Carlo bootstrap evaluation.

    Body:
        ticker, snapshots, bars
        n_iterations: int (default 1000)
        block_size: int (default 21)
        seed: int (default 42)
        config: dict
    """
    ticker = payload.get("ticker", "")
    snapshots = _snaps_to_simple(payload.get("snapshots", []))
    bars = _bars_to_simple(payload.get("bars", []))
    n_iterations = payload.get("n_iterations", 1000)
    block_size = payload.get("block_size", 21)
    seed = payload.get("seed", 42)
    cfg_dict = payload.get("config", {})

    config = EngineConfig(
        initial_capital=cfg_dict.get("initial_capital", 100_000.0),
        slippage_pct=cfg_dict.get("slippage_pct", 0.0005),
        commission_per_contract=cfg_dict.get("commission_per_contract", 0.65),
        contracts_per_trade=cfg_dict.get("contracts_per_trade", 1),
    )

    signal = RuleBasedSignal()
    results = run_monte_carlo_bootstrap(
        signal=signal,
        snapshots=snapshots,
        bars=bars,
        ticker=ticker,
        n_iterations=n_iterations,
        block_size=block_size,
        seed=seed,
        config=config,
    )
    # Aggregate bootstrap distribution stats
    if results:
        sharpe_vals = [r.metrics.get("sharpe", 0) for r in results if r.metrics]
        pnl_vals = [r.metrics.get("total_pnl", 0) for r in results if r.metrics]
        return {
            "status": "ok",
            "n_iterations": len(results),
            "distribution": {
                "sharpe_mean": float(sum(sharpe_vals) / len(sharpe_vals)) if sharpe_vals else 0.0,
                "sharpe_median": float(sorted(sharpe_vals)[len(sharpe_vals) // 2]) if sharpe_vals else 0.0,
                "sharpe_p10": float(sorted(sharpe_vals)[max(0, int(len(sharpe_vals) * 0.1))]) if sharpe_vals else 0.0,
                "sharpe_p90": float(sorted(sharpe_vals)[min(len(sharpe_vals) - 1, int(len(sharpe_vals) * 0.9))]) if sharpe_vals else 0.0,
                "pnl_mean": float(sum(pnl_vals) / len(pnl_vals)) if pnl_vals else 0.0,
                "pnl_median": float(sorted(pnl_vals)[len(pnl_vals) // 2]) if pnl_vals else 0.0,
                "pnl_p10": float(sorted(pnl_vals)[max(0, int(len(pnl_vals) * 0.1))]) if pnl_vals else 0.0,
                "pnl_p90": float(sorted(pnl_vals)[min(len(pnl_vals) - 1, int(len(pnl_vals) * 0.9))]) if pnl_vals else 0.0,
            },
        }
    return {"status": "ok", "n_iterations": 0, "distribution": {}}
