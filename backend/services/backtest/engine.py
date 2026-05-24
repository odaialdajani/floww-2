"""
backend/services/backtest/engine.py

Event-driven backtest engine for the Confluence Decoder trading system.

Processes bars one at a time with strict no-lookahead: at bar i, only
data[0..i] is visible to the signal. Supports slippage, commission,
position tracking, and four evaluation modes:
  - IS_OUT_OF_SAMPLE_SPLIT: 70/30 temporal split
  - WALK_FORWARD_CV: walk-forward cross-validation
  - PURGED_K_FOLD_CV: purged K-fold with embargo gap (no train/test leakage)
  - MONTE_CARLO_BOOTSTRAP: Monte Carlo bootstrap on bar returns

Usage:
    engine = BacktestEngine(signal=MySignal(), initial_capital=100_000)
    result = engine.run(snapshots, bars)
    print(result.summary_text())

References:
    Marcos López de Prado (2018). "Advances in Financial Machine Learning."
    Chapter 12: Cross-Validation in Finance.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .signals import Action, Position, Signal
from .report import BacktestResult, TradeRecord

log = logging.getLogger("backtest.engine")

DEFAULT_SLIPPAGE_PCT = 0.0005   # 0.05%
DEFAULT_COMMISSION = 0.65       # $0.65 per contract


@dataclass
class EngineConfig:
    """Backtest engine configuration."""
    initial_capital: float = 100_000.0
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT
    commission_per_contract: float = DEFAULT_COMMISSION
    contracts_per_trade: int = 1
    price_per_contract: float = 5.0   # Simplified: fixed notional per contract
    allow_short: bool = False


class BacktestEngine:
    """Event-driven backtest engine.

    Processes one bar at a time. At each bar:
      1. Truncate history to current bar (no lookahead)
      2. Call signal.evaluate() with history + current position
      3. Execute the returned Action with slippage + commission
      4. Update position, equity, drawdown

    Args:
        signal: Signal instance that generates Actions.
        config: Engine configuration.
    """

    def __init__(self, signal: Signal, config: Optional[EngineConfig] = None):
        self.signal = signal
        self.config = config or EngineConfig()

    def run(
        self,
        snapshots: List[Dict[str, Any]],
        bars: List[Dict[str, Any]],
        ticker: str = "",
    ) -> BacktestResult:
        """Run the backtest over aligned snapshot and bar data.

        Args:
            snapshots: List of GEX snapshot dicts, sorted by date ascending.
            bars: List of OHLCV bar dicts, sorted by date ascending.
                   Must be the same length as snapshots (1:1 alignment).
            ticker: Ticker symbol for the result.

        Returns:
            BacktestResult with equity curve, trades, and metrics.
        """
        if len(snapshots) != len(bars):
            raise ValueError(
                f"snapshots ({len(snapshots)}) and bars ({len(bars)}) must have same length"
            )

        n = len(bars)
        if n == 0:
            return BacktestResult(ticker=ticker)

        cfg = self.config
        position = Position()
        result = BacktestResult(
            ticker=ticker,
            start_date=str(bars[0].get("date", "")),
            end_date=str(bars[-1].get("date", "")),
            initial_capital=cfg.initial_capital,
            slippage_pct=cfg.slippage_pct,
            commission_per_contract=cfg.commission_per_contract,
            total_bars=n,
        )

        equity = cfg.initial_capital
        peak_equity = equity
        result.equity_curve = [equity]
        result.drawdown_curve = [0.0]
        result.bar_returns = [0.0]

        for i in range(n):
            # No lookahead: only data up to index i
            snap_hist = snapshots[: i + 1]
            bar_hist = bars[: i + 1]

            # Get signal action
            action = self.signal.evaluate(snap_hist, bar_hist, position)

            # Execute action
            bar = bars[i]
            close_price = _safe_float(bar.get("close"))

            if action == Action.BUY_CALL:
                entry_price = close_price * (1.0 + cfg.slippage_pct)
                slippage_cost = close_price * cfg.slippage_pct * cfg.contracts_per_trade
                commission_cost = cfg.commission_per_contract * cfg.contracts_per_trade

                position.side = "CALL"
                position.direction = "LONG"
                position.entry_price = entry_price
                position.quantity = cfg.contracts_per_trade
                position.entry_bar_idx = i

                cost = (entry_price * cfg.contracts_per_trade) + commission_cost + slippage_cost
                equity -= cost
                result.total_buy_calls += 1

                # Record slippage/commission for the eventual trade close
                # We store them on the position and finalize at close
                position._pending_slippage = slippage_cost  # type: ignore[attr-defined]
                position._pending_commission = commission_cost  # type: ignore[attr-defined]

            elif action == Action.BUY_PUT:
                entry_price = close_price * (1.0 + cfg.slippage_pct)
                slippage_cost = close_price * cfg.slippage_pct * cfg.contracts_per_trade
                commission_cost = cfg.commission_per_contract * cfg.contracts_per_trade

                position.side = "PUT"
                position.direction = "LONG"
                position.entry_price = entry_price
                position.quantity = cfg.contracts_per_trade
                position.entry_bar_idx = i

                cost = (entry_price * cfg.contracts_per_trade) + commission_cost + slippage_cost
                equity -= cost
                result.total_buy_puts += 1

                position._pending_slippage = slippage_cost  # type: ignore[attr-defined]
                position._pending_commission = commission_cost  # type: ignore[attr-defined]

            elif action == Action.SELL_CALL:
                if position.is_open and position.side == "CALL":
                    exit_price = close_price * (1.0 - cfg.slippage_pct)
                    slippage_cost = close_price * cfg.slippage_pct * position.quantity
                    commission_cost = cfg.commission_per_contract * position.quantity

                    gross_pnl = (exit_price - position.entry_price) * position.quantity
                    entry_slippage = getattr(position, "_pending_slippage", 0.0)
                    entry_commission = getattr(position, "_pending_commission", 0.0)

                    trade = TradeRecord(
                        entry_bar_idx=position.entry_bar_idx,
                        exit_bar_idx=i,
                        side=position.side or "",
                        direction=position.direction or "",
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        quantity=position.quantity,
                        pnl=gross_pnl,
                        commission=entry_commission + commission_cost,
                        slippage=entry_slippage + slippage_cost,
                        net_pnl=gross_pnl - entry_commission - commission_cost - entry_slippage - slippage_cost,
                    )
                    result.trades.append(trade)
                    # Clean equity: cash tracks entry cost (deducted at buy),
                    # exit proceeds added at sell, net = initial + net_pnl
                    equity += trade.net_pnl

                    position.quantity = 0
                    position.side = None
                    position.direction = None
                    result.total_sell_calls += 1

            elif action == Action.SELL_PUT:
                if position.is_open and position.side == "PUT":
                    exit_price = close_price * (1.0 - cfg.slippage_pct)
                    slippage_cost = close_price * cfg.slippage_pct * position.quantity
                    commission_cost = cfg.commission_per_contract * position.quantity

                    gross_pnl = (exit_price - position.entry_price) * position.quantity
                    entry_slippage = getattr(position, "_pending_slippage", 0.0)
                    entry_commission = getattr(position, "_pending_commission", 0.0)

                    trade = TradeRecord(
                        entry_bar_idx=position.entry_bar_idx,
                        exit_bar_idx=i,
                        side=position.side or "",
                        direction=position.direction or "",
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        quantity=position.quantity,
                        pnl=gross_pnl,
                        commission=entry_commission + commission_cost,
                        slippage=entry_slippage + slippage_cost,
                        net_pnl=gross_pnl - entry_commission - commission_cost - entry_slippage - slippage_cost,
                    )
                    result.trades.append(trade)
                    equity += trade.net_pnl

                    position.quantity = 0
                    position.side = None
                    position.direction = None
                    result.total_sell_puts += 1

            # Update unrealized P&L for open positions
            if position.is_open and close_price > 0:
                position.update_unrealized(close_price)

            # Track equity and drawdown
            # equity = cash balance (initial capital - entry costs + exit proceeds)
            # total_equity = cash + unrealized P&L of open positions
            total_equity = equity + position.unrealized_pnl
            result.equity_curve.append(total_equity)

            if total_equity > peak_equity:
                peak_equity = total_equity
            dd = total_equity - peak_equity  # <= 0
            result.drawdown_curve.append(dd)

            # Bar return
            if len(result.equity_curve) >= 2:
                prev_eq = result.equity_curve[-2]
                if prev_eq != 0:
                    result.bar_returns.append((total_equity - prev_eq) / abs(prev_eq))
                else:
                    result.bar_returns.append(0.0)

        # Close any open position at the last bar
        if position.is_open:
            last_bar = bars[-1]
            exit_price = _safe_float(last_bar.get("close")) * (1.0 - cfg.slippage_pct)
            slippage_cost = _safe_float(last_bar.get("close")) * cfg.slippage_pct * position.quantity
            commission_cost = cfg.commission_per_contract * position.quantity

            gross_pnl = (exit_price - position.entry_price) * position.quantity
            entry_slippage = getattr(position, "_pending_slippage", 0.0)
            entry_commission = getattr(position, "_pending_commission", 0.0)

            trade = TradeRecord(
                entry_bar_idx=position.entry_bar_idx,
                exit_bar_idx=n - 1,
                side=position.side or "",
                direction=position.direction or "",
                entry_price=position.entry_price,
                exit_price=exit_price,
                quantity=position.quantity,
                pnl=gross_pnl,
                commission=entry_commission + commission_cost,
                slippage=entry_slippage + slippage_cost,
                net_pnl=gross_pnl - entry_commission - commission_cost - entry_slippage - slippage_cost,
            )
            result.trades.append(trade)
            equity += trade.net_pnl
            total_equity = equity
            result.equity_curve[-1] = total_equity
            result.drawdown_curve[-1] = total_equity - peak_equity

        result.compute_metrics()
        return result


# ============================================================================
# Evaluation modes
# ============================================================================

def run_is_oos_split(
    signal_factory: Callable[[], Signal],
    snapshots: List[Dict[str, Any]],
    bars: List[Dict[str, Any]],
    ticker: str = "",
    train_ratio: float = 0.7,
    config: Optional[EngineConfig] = None,
) -> Tuple[BacktestResult, BacktestResult]:
    """70/30 in-sample / out-of-sample temporal split.

    Args:
        signal_factory: Callable that returns a fresh Signal instance.
                        Called twice (train, test) to avoid state leakage.
        snapshots: Full snapshot history.
        bars: Full bar history.
        ticker: Ticker symbol.
        train_ratio: Fraction for in-sample (default 0.7).
        config: Engine configuration.

    Returns:
        (train_result, test_result) tuple.
    """
    n = len(bars)
    split_idx = int(n * train_ratio)
    if split_idx < 2 or split_idx > n - 2:
        raise ValueError(f"split_idx={split_idx} with n={n} leaves too few bars for one set")

    train_snap = snapshots[:split_idx]
    train_bars = bars[:split_idx]
    test_snap = snapshots[split_idx:]
    test_bars = bars[split_idx:]

    log.info(f"IS/OOS split: train={len(train_bars)} bars, test={len(test_bars)} bars")

    train_engine = BacktestEngine(signal=signal_factory(), config=config)
    train_result = train_engine.run(train_snap, train_bars, ticker=ticker)

    test_engine = BacktestEngine(signal=signal_factory(), config=config)
    test_result = test_engine.run(test_snap, test_bars, ticker=ticker)

    return train_result, test_result


def run_walk_forward_cv(
    signal_factory: Callable[[], Signal],
    snapshots: List[Dict[str, Any]],
    bars: List[Dict[str, Any]],
    ticker: str = "",
    n_splits: int = 5,
    min_train_size: int = 50,
    config: Optional[EngineConfig] = None,
) -> List[BacktestResult]:
    """Walk-forward cross-validation.

    For each fold k (0..n_splits-1):
      - Train period: bars[0 : min_train_size + k * step]
      - Test period:  next `step` bars after train

    Args:
        signal_factory: Callable returning a fresh Signal per fold.
        snapshots: Full snapshot history.
        bars: Full bar history.
        ticker: Ticker symbol.
        n_splits: Number of walk-forward folds.
        min_train_size: Minimum bars in the first training window.
        config: Engine configuration.

    Returns:
        List of BacktestResult, one per fold.
    """
    n = len(bars)
    usable = n - min_train_size
    if usable < n_splits:
        raise ValueError(
            f"n={n} with min_train_size={min_train_size} leaves {usable} bars, "
            f"need >= {n_splits} for {n_splits} splits"
        )

    step = usable // n_splits
    results: List[BacktestResult] = []

    for k in range(n_splits):
        train_end = min_train_size + k * step
        test_end = min(train_end + step, n)

        if test_end <= train_end:
            continue

        train_snap = snapshots[:train_end]
        train_bars = bars[:train_end]
        test_snap = snapshots[train_end:test_end]
        test_bars = bars[train_end:test_end]

        log.info(
            f"Walk-forward fold {k + 1}/{n_splits}: "
            f"train={len(train_bars)}, test={len(test_bars)}"
        )

        # Train signal on training data (signal_factory may use train data
        # to calibrate thresholds or fit models)
        signal = signal_factory()

        # Evaluate on test data
        engine = BacktestEngine(signal=signal, config=config)
        fold_result = engine.run(test_snap, test_bars, ticker=ticker)
        results.append(fold_result)

    return results


# ============================================================================
# Purged K-Fold Cross-Validation (López de Prado Ch. 12)
# ============================================================================

class PurgedKFold:
    """Purged K-Fold cross-validator with embargo gap for financial time series.

    Prevents train/test leakage by:
      1. Purging: removing from the training set any samples whose labels
         overlap temporally with the test set.
      2. Embargo: removing a gap of `embargo_size` samples immediately
         following the test set to eliminate serial correlation leakage.

    Args:
        n_splits: Number of folds (default 5).
        embargo_size: Number of samples to embargo after each test set
                       (default 5, or 0 to disable).
    """

    def __init__(self, n_splits: int = 5, embargo_size: int = 5):
        if n_splits < 2:
            raise ValueError(f"n_splits must be >= 2, got {n_splits}")
        if embargo_size < 0:
            raise ValueError(f"embargo_size must be >= 0, got {embargo_size}")
        self.n_splits = n_splits
        self.embargo_size = embargo_size

    def split(self, n_samples: int) -> List[Tuple[slice, slice]]:
        """Generate train/test indices for purged K-fold CV.

        Args:
            n_samples: Total number of samples (bars).

        Returns:
            List of (train_slice, test_slice) tuples. Each slice can be
            passed directly to list/slice operations like bars[train_slice].
        """
        fold_size = n_samples // self.n_splits
        folds: List[Tuple[slice, slice]] = []

        for k in range(self.n_splits):
            test_start = k * fold_size
            test_end = n_samples if k == self.n_splits - 1 else (k + 1) * fold_size

            # Training set: everything before test_start, minus embargo zone
            train_end = max(0, test_start - self.embargo_size)
            train_slice = slice(0, train_end)

            # Test set: current fold
            test_slice = slice(test_start, test_end)

            if train_end <= 0:
                # First fold may have no training data — skip or allow empty?
                # We still include it so that fold 0 acts as a "preview"
                pass

            folds.append((train_slice, test_slice))

        return folds

    def get_embargo_mask(self, n_samples: int) -> np.ndarray:
        """Return a boolean mask where True = sample is in an embargo zone.

        Samples in the embargo zone should be excluded from metric computation
        or used with caution, as they follow a test set.
        """
        mask = np.zeros(n_samples, dtype=bool)
        fold_size = n_samples // self.n_splits
        for k in range(self.n_splits):
            test_end = n_samples if k == self.n_splits - 1 else (k + 1) * fold_size
            embargo_start = test_end
            embargo_end = min(n_samples, embargo_start + self.embargo_size)
            if embargo_end > embargo_start:
                mask[embargo_start:embargo_end] = True
        return mask

    def __repr__(self) -> str:
        return f"PurgedKFold(n_splits={self.n_splits}, embargo_size={self.embargo_size})"


def run_purged_kfold_cv(
    signal_factory: Callable[[], Signal],
    snapshots: List[Dict[str, Any]],
    bars: List[Dict[str, Any]],
    ticker: str = "",
    n_splits: int = 5,
    embargo_size: int = 5,
    config: Optional[EngineConfig] = None,
) -> List[BacktestResult]:
    """Run purged K-fold CV with embargo.

    Each fold: train on data before the test set (minus embargo gap),
    test on a contiguous block. This is more robust than basic walk-forward
    because it prevents the model from seeing data that overlaps with or
    immediately follows the test period.

    Args:
        signal_factory: Callable returning a fresh Signal per fold.
        snapshots: Full snapshot history.
        bars: Full bar history.
        ticker: Ticker symbol.
        n_splits: Number of folds.
        embargo_size: Embargo gap after each test set.
        config: Engine configuration.

    Returns:
        List of BacktestResult, one per fold.
    """
    n = len(bars)
    if n < n_splits * 10:
        raise ValueError(
            f"n={n} too small for {n_splits}-fold purged CV "
            f"(need at least {n_splits * 10} bars)"
        )

    cv = PurgedKFold(n_splits=n_splits, embargo_size=embargo_size)
    folds = cv.split(n)
    results: List[BacktestResult] = []

    for k, (train_slice, test_slice) in enumerate(folds):
        test_snap = snapshots[test_slice]
        test_bars = bars[test_slice]
        train_bars = bars[train_slice]

        n_train = len(train_bars)
        if n_train < 5:
            log.warning(f"Fold {k + 1}/{n_splits}: skipping — only {n_train} training bars")
            continue

        log.info(
            f"Purged K-fold {k + 1}/{n_splits}: "
            f"train={n_train} (0..{n_train - 1} + embargo), "
            f"test={len(test_bars)} (embargo={embargo_size})"
        )

        signal = signal_factory()
        # Wire training data if signal has a .fit() method (ML signals)
        if callable(getattr(signal, "fit", None)):
            train_snap = snapshots[train_slice]
            signal.fit(train_snap, train_bars)  # type: ignore[union-attr]
        engine = BacktestEngine(signal=signal, config=config)
        fold_result = engine.run(test_snap, test_bars, ticker=ticker)
        results.append(fold_result)

    if not results:
        log.warning("Purged K-fold CV: no folds produced results")

    return results


def run_monte_carlo_bootstrap(
    signal: Signal,
    snapshots: List[Dict[str, Any]],
    bars: List[Dict[str, Any]],
    ticker: str = "",
    n_iterations: int = 1000,
    block_size: int = 21,
    config: Optional[EngineConfig] = None,
    seed: int = 42,
) -> List[BacktestResult]:
    """Monte Carlo bootstrap evaluation.

    Resamples bar returns in blocks (to preserve autocorrelation) and
    reconstructs price series, then runs the backtest on each synthetic path.

    Args:
        signal: Signal instance (reused across iterations).
        snapshots: Full snapshot history.
        bars: Full bar history.
        ticker: Ticker symbol.
        n_iterations: Number of bootstrap samples.
        block_size: Block length for stationary bootstrap (default 21 ≈ 1 month).
        config: Engine configuration.
        seed: Random seed for reproducibility.

    Returns:
        List of BacktestResult, one per bootstrap iteration.
    """
    rng = random.Random(seed)
    n = len(bars)

    if n < block_size:
        raise ValueError(f"n={n} < block_size={block_size}")

    # Compute bar returns
    closes = np.array([_safe_float(b.get("close")) for b in bars])
    returns = np.diff(closes) / closes[:-1]  # length n-1
    n_ret = len(returns)

    results: List[BacktestResult] = []

    for iteration in range(n_iterations):
        # Stationary block bootstrap on returns
        n_blocks = math.ceil(n_ret / block_size)
        block_starts = [rng.randint(0, n_ret - 1) for _ in range(n_blocks)]

        boot_returns = []
        for start in block_starts:
            for j in range(block_size):
                idx = (start + j) % n_ret
                boot_returns.append(returns[idx])
                if len(boot_returns) >= n_ret:
                    break
            if len(boot_returns) >= n_ret:
                break
        boot_returns = boot_returns[:n_ret]

        # Reconstruct price series from bootstrapped returns
        boot_closes = [closes[0]]
        for r in boot_returns:
            boot_closes.append(boot_closes[-1] * (1.0 + r))
        boot_closes = boot_closes[:n]

        # Create synthetic bars with bootstrapped closes
        boot_bars = []
        for i, b in enumerate(bars):
            synthetic = dict(b)
            synthetic["close"] = boot_closes[i]
            # Scale OHL proportionally
            orig_close = _safe_float(b.get("close"))
            if orig_close > 0:
                scale = boot_closes[i] / orig_close
                for field_name in ("open", "high", "low"):
                    if field_name in synthetic:
                        synthetic[field_name] = _safe_float(synthetic[field_name]) * scale
            boot_bars.append(synthetic)

        engine = BacktestEngine(signal=signal, config=config)
        iter_result = engine.run(snapshots, boot_bars, ticker=ticker)
        results.append(iter_result)

        if (iteration + 1) % 100 == 0:
            log.info(f"Monte Carlo: {iteration + 1}/{n_iterations} iterations done")

    return results


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        if f != f:  # NaN
            return default
        return f
    except (TypeError, ValueError):
        return default
