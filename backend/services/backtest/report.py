"""
backend/services/backtest/report.py

Report generation for backtest results.

Computes and formats:
  - Sharpe ratio (annualized)
  - Maximum drawdown
  - Hit rate
  - Profit factor
  - Win/loss ratio
  - Per-trade and per-bar summaries
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

log = logging.getLogger("backtest.report")


@dataclass
class TradeRecord:
    """Completed round-trip trade."""
    entry_bar_idx: int = 0
    exit_bar_idx: int = 0
    side: str = ""          # "CALL" or "PUT"
    direction: str = ""     # "LONG" or "SHORT"
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 0
    pnl: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    net_pnl: float = 0.0    # pnl - commission - slippage


@dataclass
class BacktestResult:
    """Full backtest result container."""
    # Configuration
    ticker: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 0.0
    slippage_pct: float = 0.0
    commission_per_contract: float = 0.0

    # Time series
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)
    bar_returns: List[float] = field(default_factory=list)

    # Trades
    trades: List[TradeRecord] = field(default_factory=list)

    # Counters
    total_bars: int = 0
    total_buy_calls: int = 0
    total_buy_puts: int = 0
    total_sell_calls: int = 0
    total_sell_puts: int = 0

    # Computed metrics (populated by compute_metrics)
    metrics: Dict[str, float] = field(default_factory=dict)

    def compute_metrics(self) -> Dict[str, float]:
        """Compute all summary metrics from the result data."""
        m: Dict[str, float] = {}

        n_trades = len(self.trades)
        m["n_trades"] = float(n_trades)
        m["total_bars"] = float(self.total_bars)

        if n_trades == 0:
            m["sharpe"] = 0.0
            m["max_drawdown"] = 0.0
            m["max_drawdown_pct"] = 0.0
            m["hit_rate"] = 0.0
            m["profit_factor"] = 0.0
            m["win_loss_ratio"] = 0.0
            m["avg_trade_pnl"] = 0.0
            m["avg_win"] = 0.0
            m["avg_loss"] = 0.0
            m["total_pnl"] = 0.0
            m["total_commission"] = 0.0
            m["total_slippage"] = 0.0
            m["final_equity"] = self.initial_capital
            m["net_return_pct"] = 0.0
            self.metrics = m
            return m

        pnls = np.array([t.net_pnl for t in self.trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        m["total_pnl"] = float(np.sum(pnls))
        m["avg_trade_pnl"] = float(np.mean(pnls))
        m["avg_win"] = float(np.mean(wins)) if len(wins) > 0 else 0.0
        m["avg_loss"] = float(np.mean(losses)) if len(losses) > 0 else 0.0
        m["n_wins"] = float(len(wins))
        m["n_losses"] = float(len(losses))
        m["hit_rate"] = float(len(wins) / n_trades) if n_trades > 0 else 0.0

        # Win/loss ratio (avg win / |avg_loss|)
        if len(losses) > 0 and np.mean(losses) != 0:
            m["win_loss_ratio"] = float(np.mean(wins) / abs(np.mean(losses))) if len(wins) > 0 else 0.0
        else:
            m["win_loss_ratio"] = float("inf") if len(wins) > 0 else 0.0

        # Profit factor: gross wins / |gross losses|
        gross_wins = float(np.sum(wins)) if len(wins) > 0 else 0.0
        gross_losses = float(abs(np.sum(losses))) if len(losses) > 0 else 0.0
        if gross_losses > 0:
            m["profit_factor"] = gross_wins / gross_losses
        elif gross_wins > 0:
            m["profit_factor"] = float("inf")
        else:
            m["profit_factor"] = 0.0

        # Total costs
        m["total_commission"] = float(sum(t.commission for t in self.trades))
        m["total_slippage"] = float(sum(t.slippage for t in self.trades))

        # Equity curve metrics
        if self.equity_curve:
            m["final_equity"] = float(self.equity_curve[-1])
            m["net_return_pct"] = (m["final_equity"] / self.initial_capital - 1.0) * 100.0 if self.initial_capital > 0 else 0.0
        else:
            m["final_equity"] = self.initial_capital
            m["net_return_pct"] = 0.0

        # Sharpe ratio (annualized, from bar returns)
        if self.bar_returns:
            rets = np.array(self.bar_returns)
            if len(rets) > 1 and np.std(rets) > 0:
                m["sharpe"] = float(np.mean(rets) / np.std(rets) * math.sqrt(252))
            else:
                m["sharpe"] = 0.0
        else:
            m["sharpe"] = 0.0

        # Max drawdown
        if self.drawdown_curve:
            m["max_drawdown"] = float(min(self.drawdown_curve))
            peak = max(self.equity_curve) if self.equity_curve else self.initial_capital
            m["max_drawdown_pct"] = (m["max_drawdown"] / peak * 100.0) if peak > 0 else 0.0
        else:
            m["max_drawdown"] = 0.0
            m["max_drawdown_pct"] = 0.0

        self.metrics = m
        log.info(
            f"Metrics: sharpe={m['sharpe']:.3f} max_dd={m['max_drawdown_pct']:.2f}% "
            f"hit_rate={m['hit_rate']:.3f} pf={m['profit_factor']:.3f} "
            f"wl={m['win_loss_ratio']:.3f} n_trades={n_trades}"
        )
        return m

    def summary_text(self) -> str:
        """Return a human-readable summary string."""
        m = self.metrics if self.metrics else self.compute_metrics()
        lines = [
            f"=== Backtest Report: {self.ticker} ===",
            f"Period: {self.start_date} -> {self.end_date}",
            f"Bars: {self.total_bars}  Trades: {int(m.get('n_trades', 0))}",
            "",
            "--- Performance ---",
            f"Initial Capital:  ${self.initial_capital:,.2f}",
            f"Final Equity:     ${m.get('final_equity', 0):,.2f}",
            f"Net Return:       {m.get('net_return_pct', 0):.2f}%",
            f"Total P&L:        ${m.get('total_pnl', 0):,.2f}",
            "",
            "--- Risk ---",
            f"Sharpe (ann.):    {m.get('sharpe', 0):.3f}",
            f"Max Drawdown:     ${m.get('max_drawdown', 0):,.2f} ({m.get('max_drawdown_pct', 0):.2f}%)",
            "",
            "--- Trade Stats ---",
            f"Hit Rate:         {m.get('hit_rate', 0):.3f}",
            f"Profit Factor:    {m.get('profit_factor', 0):.3f}",
            f"Win/Loss Ratio:   {m.get('win_loss_ratio', 0):.3f}",
            f"Avg Trade P&L:    ${m.get('avg_trade_pnl', 0):,.2f}",
            f"Avg Win:          ${m.get('avg_win', 0):,.2f}",
            f"Avg Loss:         ${m.get('avg_loss', 0):,.2f}",
            f"Wins:             {int(m.get('n_wins', 0))}  Losses: {int(m.get('n_losses', 0))}",
            "",
            "--- Costs ---",
            f"Commission:       ${m.get('total_commission', 0):,.2f}",
            f"Slippage:         ${m.get('total_slippage', 0):,.2f}",
        ]
        return "\n".join(lines)


