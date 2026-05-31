"""
Tests for RetailFlowSignal and RegimeFilter.

Validates:
  - Signal generates BUY_CALL/BUY_PUT/HOLD correctly.
  - Regime filter blocks counter-trend trades.
  - Exit logic closes positions at correct thresholds.
  - Score computation integrates CPR, OI change, IV skew.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import numpy as np

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.backtest.retail_flow_signal import (
    RegimeFilter,
    RetailFlowSignal,
)
from services.backtest.signals import Action, Position


def _make_snapshots_cpr(cprs: List[float], oi_changes=None, iv_skews=None):
    """Helper: create snapshot history from CPR values."""
    n = len(cprs)
    if oi_changes is None:
        oi_changes = [0.0] * n
    if iv_skews is None:
        iv_skews = [0.0] * n
    return [
        {"cpr": cprs[i], "oi_change_pct": oi_changes[i], "iv_skew": iv_skews[i]}
        for i in range(n)
    ]


def _make_bars(closes: List[float]):
    """Helper: create bar history from close prices."""
    return [{"close": c, "volume": 1_000_000} for c in closes]


def _uptrend_bars(n: int = 30, start: float = 400.0):
    """Generate uptrending close prices (above SMA)."""
    prices = [start]
    for i in range(1, n):
        prices.append(prices[-1] * (1 + np.random.default_rng(42 + i).uniform(0.001, 0.005)))
    return prices


def _downtrend_bars(n: int = 30, start: float = 400.0):
    """Generate downtrending close prices (below SMA)."""
    rng = np.random.default_rng(42)
    prices = [start]
    for i in range(1, n):
        prices.append(prices[-1] * (1 - rng.uniform(0.001, 0.005)))
    return prices


class TestRegimeFilter:
    """RegimeFilter trend detection."""

    def test_allow_bullish_above_sma(self):
        # Prices rising — current > SMA
        prices = list(np.cumprod([1.0 + 0.003] * 30)) * 100
        rf = RegimeFilter(sma_period=21, enabled=True)
        assert rf.allow_bullish(prices) == True

    def test_block_below_sma(self):
        # Prices falling — current < SMA
        rf = RegimeFilter(sma_period=21, enabled=True)
        prices = [100.0 - i * 0.5 for i in range(30)]
        assert rf.allow_bullish(prices) == False

    def test_allow_bearish_below_sma(self):
        rf = RegimeFilter(sma_period=21, enabled=True)
        prices = [100.0 - i * 0.5 for i in range(30)]
        assert rf.allow_bearish(prices) == True

    def test_block_bearish_above_sma(self):
        rf = RegimeFilter(sma_period=21, enabled=True)
        prices = list(np.cumprod([1.0 + 0.003] * 30)) * 100
        assert rf.allow_bearish(prices) == False

    def test_disabled_filter_allows_all(self):
        rf = RegimeFilter(sma_period=21, enabled=False)
        prices = [100.0 - i * 0.5 for i in range(30)]
        assert rf.allow_bullish(prices)
        assert rf.allow_bearish(prices)

    def test_short_history_always_allows(self):
        rf = RegimeFilter(sma_period=21, enabled=True)
        assert rf.allow_bullish([100.0])
        assert rf.allow_bearish([100.0])


class TestRetailFlowSignalEntries:
    """Entry signal generation."""

    def test_buy_call_on_bullish_score_uptrend(self):
        rf = RegimeFilter(sma_period=21, enabled=True)
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=rf)
        prices = _uptrend_bars(30)
        snapshots = _make_snapshots_cpr([2.5] * 30, [0.10] * 30, [-0.02] * 30)
        bars = _make_bars(prices)
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.BUY_CALL

    def test_hold_on_bullish_score_downtrend(self):
        """Bullish signal blocked by downtrend regime filter."""
        rf = RegimeFilter(sma_period=21, enabled=True)
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=rf)
        prices = _downtrend_bars(30)
        snapshots = _make_snapshots_cpr([2.5] * 30, [0.10] * 30, [-0.02] * 30)
        bars = _make_bars(prices)
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.HOLD

    def test_buy_put_on_bearish_score_downtrend(self):
        rf = RegimeFilter(sma_period=21, enabled=True)
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=rf)
        prices = _downtrend_bars(30)
        snapshots = _make_snapshots_cpr([0.4] * 30, [-0.10] * 30, [0.03] * 30)
        bars = _make_bars(prices)
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.BUY_PUT

    def test_hold_on_bearish_score_uptrend(self):
        """Bearish signal blocked by uptrend regime filter."""
        rf = RegimeFilter(sma_period=21, enabled=True)
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=rf)
        prices = _uptrend_bars(30)
        snapshots = _make_snapshots_cpr([0.4] * 30, [-0.10] * 30, [0.03] * 30)
        bars = _make_bars(prices)
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.HOLD

    def test_hold_below_threshold(self):
        signal = RetailFlowSignal(entry_threshold=30.0)
        prices = _uptrend_bars(30)
        snapshots = _make_snapshots_cpr([1.0] * 30)  # neutral CPR
        bars = _make_bars(prices)
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.HOLD

    def test_no_entry_when_position_open(self):
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=RegimeFilter(enabled=False))
        prices = _uptrend_bars(30)
        snapshots = _make_snapshots_cpr([2.5] * 30, [0.10] * 30, [-0.02] * 30)
        bars = _make_bars(prices)
        pos = Position(side="CALL", direction="LONG", entry_price=5.0, quantity=1)
        action = signal.evaluate(snapshots, bars, pos)
        assert action == Action.HOLD


class TestRetailFlowSignalExits:
    """Exit signal generation."""

    def test_exit_call_when_score_drops(self):
        signal = RetailFlowSignal(entry_threshold=30.0, exit_threshold=10.0,
                                  regime_filter=RegimeFilter(enabled=False))
        prices = _uptrend_bars(30)
        # Score will be neutral (CPR=1.0, OI=0, skew=0)
        snapshots = _make_snapshots_cpr([1.0] * 30)
        bars = _make_bars(prices)
        pos = Position(side="CALL", direction="LONG", entry_price=5.0, quantity=1)
        action = signal.evaluate(snapshots, bars, pos)
        assert action == Action.SELL_CALL

    def test_exit_put_when_score_rises(self):
        signal = RetailFlowSignal(entry_threshold=30.0, exit_threshold=10.0,
                                  regime_filter=RegimeFilter(enabled=False))
        prices = _downtrend_bars(30)
        snapshots = _make_snapshots_cpr([1.0] * 30)
        bars = _make_bars(prices)
        pos = Position(side="PUT", direction="LONG", entry_price=5.0, quantity=1)
        action = signal.evaluate(snapshots, bars, pos)
        assert action == Action.SELL_PUT


class TestRetailFlowSignalScoreIntegration:
    """Score computation integration."""

    def test_high_cpr_drives_score_up(self):
        rf = RegimeFilter(sma_period=21, enabled=True)
        signal = RetailFlowSignal(entry_threshold=20.0, regime_filter=rf)
        prices = _uptrend_bars(30)
        # Very bullish: CPR=3.5, positive OI change, negative IV skew (greedy)
        snapshots = _make_snapshots_cpr([3.5] * 30, [0.15] * 30, [-0.03] * 30)
        bars = _make_bars(prices)
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.BUY_CALL

    def test_extreme_bearish_drives_score_down(self):
        rf = RegimeFilter(sma_period=21, enabled=True)
        signal = RetailFlowSignal(entry_threshold=20.0, regime_filter=rf)
        prices = _downtrend_bars(30)
        # Very bearish: CPR=0.3, negative OI change, positive IV skew (fear)
        snapshots = _make_snapshots_cpr([0.3] * 30, [-0.15] * 30, [0.04] * 30)
        bars = _make_bars(prices)
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.BUY_PUT

    def test_empty_history_returns_hold(self):
        signal = RetailFlowSignal()
        assert signal.evaluate([], [], Position()) == Action.HOLD
        assert signal.evaluate([], [{"close": 100}], Position()) == Action.HOLD
        assert signal.evaluate([{"cpr": 2.0}], [], Position()) == Action.HOLD
