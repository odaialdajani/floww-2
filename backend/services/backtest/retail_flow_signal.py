"""
backend/services/backtest/retail_flow_signal.py

Retail Flow backtest signal for the event-driven backtest engine.

Uses the composite Retail Flow Score (-100 to +100) as the primary signal,
with a regime filter (SMA-based trend) to avoid counter-trend trades.

Signal logic:
  - BUY_CALL:  flow_score > entry_threshold AND price > SMA_21 (bullish + trend up)
  - BUY_PUT:   flow_score < -entry_threshold AND price < SMA_21 (bearish + trend down)
  - SELL_CALL: close long call if flow_score drops below exit_threshold
  - SELL_PUT:  close long put if flow_score rises above -exit_threshold
  - HOLD:      otherwise

The regime filter (SMA_21) prevents:
  - Buying calls when price is below SMA (downtrend = counter-trend)
  - Buying puts when price is above SMA (uptrend = counter-trend)

This addresses the key finding from the 2024 backtest:
  "Short side is the problem — shorting a bull market kills the strategy"
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from services.retail_flow_score import RetailFlowScore

from .signals import Action, Position, Signal

log = logging.getLogger("backtest.retail_flow_signal")


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _sma(values: list, period: int) -> float:
    """Simple moving average of the last `period` values."""
    if len(values) < period:
        return float(np.mean(values)) if values else 0.0
    return float(np.mean(values[-period:]))


class RegimeFilter:
    """Trend-based regime filter using SMA.

    Prevents counter-trend trades:
      - Only allow long calls when price > SMA (uptrend)
      - Only allow long puts when price < SMA (downtrend)

    Args:
        sma_period: SMA lookback period (default 21).
        enabled: Whether the filter is active (default True).
    """

    def __init__(self, sma_period: int = 21, enabled: bool = True):
        self.sma_period = sma_period
        self.enabled = enabled

    def allow_bullish(self, close_prices: list) -> bool:
        """Return True if bullish trades are allowed (price > SMA or filter off)."""
        if not self.enabled or len(close_prices) < 2:
            return True
        price = close_prices[-1]
        sma = _sma(close_prices, self.sma_period)
        return price > sma

    def allow_bearish(self, close_prices: list) -> bool:
        """Return True if bearish trades are allowed (price < SMA or filter off)."""
        if not self.enabled or len(close_prices) < 2:
            return True
        price = close_prices[-1]
        sma = _sma(close_prices, self.sma_period)
        return price < sma


class RetailFlowSignal(Signal):
    """Backtest signal using the composite Retail Flow Score.

    Combines CPR, OI change, and IV skew into a single score,
    then applies a regime filter to avoid counter-trend trades.

    Args:
        entry_threshold: Minimum absolute flow score to enter a trade (default 30).
        exit_threshold: Flow score level to exit (default 10).
        regime_filter: RegimeFilter instance (default: SMA 21, enabled).
        scorer: RetailFlowScore instance (default: standard weights).
    """

    def __init__(
        self,
        entry_threshold: float = 30.0,
        exit_threshold: float = 10.0,
        regime_filter: Optional[RegimeFilter] = None,
        scorer: Optional[RetailFlowScore] = None,
    ):
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.regime_filter = regime_filter or RegimeFilter()
        self.scorer = scorer or RetailFlowScore()

    def evaluate(
        self,
        snapshot_history: List[Dict[str, Any]],
        bar_history: List[Dict[str, Any]],
        position: Position,
    ) -> Action:
        """Evaluate the retail flow signal at the current bar.

        Expected snapshot keys:
            - cpr: float (Call/Put Volume Ratio)
            - oi_change_pct: float (OI % change)
            - iv_skew: float (Put IV - Call IV)

        Expected bar keys:
            - close: float (closing price, used for regime filter)
        """
        if not snapshot_history or not bar_history:
            return Action.HOLD

        snap = snapshot_history[-1]
        _bar = bar_history[-1]

        # Extract flow metrics from snapshot
        cpr = _safe_float(snap.get("cpr"), 1.0)
        oi_change = _safe_float(snap.get("oi_change_pct"), 0.0)
        iv_skew = _safe_float(snap.get("iv_skew"), 0.0)

        # Compute composite flow score
        flow_result = self.scorer.compute(
            cpr=cpr,
            oi_change_pct=oi_change,
            iv_skew=iv_skew,
        )
        score = flow_result.value

        # Build close price history for regime filter
        close_prices = [_safe_float(b.get("close")) for b in bar_history]

        # Exit logic: close existing positions when score reverts
        if position.is_open and position.side == "CALL" and position.direction == "LONG":
            if score < self.exit_threshold:
                return Action.SELL_CALL

        if position.is_open and position.side == "PUT" and position.direction == "LONG":
            if score > -self.exit_threshold:
                return Action.SELL_PUT

        # Entry logic: only if flat
        if not position.is_open:
            # Bullish: score above threshold + regime filter allows
            if score > self.entry_threshold:
                if self.regime_filter.allow_bullish(close_prices):
                    return Action.BUY_CALL
                else:
                    log.debug(f"Bullish flow score {score:.1f} blocked by regime filter")

            # Bearish: score below negative threshold + regime filter allows
            if score < -self.entry_threshold:
                if self.regime_filter.allow_bearish(close_prices):
                    return Action.BUY_PUT
                else:
                    log.debug(f"Bearish flow score {score:.1f} blocked by regime filter")

        return Action.HOLD
