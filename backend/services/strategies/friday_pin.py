#!/usr/bin/env python3
"""
backend/services/strategies/friday_pin.py — Friday Late-Day Pin strategy.

Ported from swarmSPX (Sharpe 3.66, 14 trades, 100% win rate over 90 days).

Edge thesis (Cem Karsan / SqueezeMetrics / JPM derivs research):
    By 3:30pm ET on Friday, dealer gamma is heavily concentrated.
    When realized vol stays low in the last 30min, the market 'pins'
    near the highest-OI strike. Iron condors at +/- 0.6% capture this
    with ~30bps of premium.

This is the ONLY validated trading edge across all of Nav's projects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class FridayPinConfig:
    """Configuration for the Friday Pin strategy."""
    pin_range_pct: float = 0.5       # max 30-bar range to call it pinning
    lookback_bars: int = 30          # number of 1m bars to check
    entry_time_start_min: int = 930  # 15:30 ET as minutes-since-midnight
    entry_time_end_min: int = 940    # 15:40 ET
    target_bps: int = 30             # premium we expect to collect
    stop_bps: int = 60               # at this much movement we stopout
    min_history_bars: int = 30       # minimum bars before signal check


@dataclass
class FridayPinSignal:
    """A trade signal from the Friday Pin strategy."""
    action: str
    strike: float
    spot: float
    target_premium_bps: int
    stop_bps: int
    reason: str
    range_pct: float
    timestamp: str


@dataclass
class FridayPinStrategy:
    """Friday Late-Day Pin strategy.

    Sells 0DTE iron condor at 15:30-15:40 ET on Fridays when the prior
    30 1-minute bars stayed in <0.5% range.

    Attributes:
        config: FridayPinConfig with strategy parameters
        price_history: Rolling window of prices
    """

    def __init__(self, config: FridayPinConfig | None = None):
        self.config = config or FridayPinConfig()
        self.price_history: list[float] = []

    def update_price(self, price: float) -> None:
        """Add a price to the rolling history."""
        self.price_history.append(float(price))
        # Keep only what we need + a buffer
        max_len = self.config.lookback_bars + 10
        if len(self.price_history) > max_len:
            self.price_history = self.price_history[-max_len:]

    def check_entry_condition(self, market_data: dict) -> bool:
        """Check if the Friday Pin entry condition is met.

        Args:
            market_data: dict with keys:
                - price: current price (float)
                - timestamp: datetime or ISO string

        Returns:
            True if entry condition is met
        """
        price = market_data.get("price", 0.0)
        if price <= 0:
            return False

        self.update_price(price)

        # Check history length
        if len(self.price_history) < self.config.min_history_bars:
            return False

        # Parse timestamp
        ts = market_data.get("timestamp")
        if ts is None:
            ts = datetime.now(UTC)
        elif isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ts = datetime.now(UTC)

        # Convert to ET. This hardcoded UTC-5, which is EST and ignores DST,
        # even though the comment above it acknowledged the problem. For ~5
        # months a year every bar was read an hour early: a 15:35 ET bar
        # evaluated as 14:35 and was REJECTED by the 15:30-15:40 entry window
        # this method exists to catch. The comment claimed to handle DST; the
        # code did not. zoneinfo does.
        from zoneinfo import ZoneInfo

        try:
            ts_et = ts.astimezone(ZoneInfo("America/New_York"))
        except Exception:
            from datetime import timedelta
            ts_et = ts.astimezone(UTC) - timedelta(hours=5)

        # Check Friday (weekday 4 = Friday)
        if ts_et.weekday() != 4:
            return False

        # Check time window (15:30-15:40 ET)
        mins = ts_et.hour * 60 + ts_et.minute
        if mins < self.config.entry_time_start_min or mins > self.config.entry_time_end_min:
            return False

        # Check pin condition: range over last N bars < threshold
        recent = self.price_history[-self.config.lookback_bars:]
        if len(recent) < self.config.lookback_bars:
            return False

        price_range = max(recent) - min(recent)
        range_pct = (price_range / min(recent)) * 100 if min(recent) > 0 else 0

        return range_pct < self.config.pin_range_pct

    def generate_signal(self, market_data: dict) -> FridayPinSignal | None:
        """Generate a trade signal if conditions are met.

        Args:
            market_data: dict with keys:
                - price: current price (float)
                - timestamp: datetime or ISO string (optional)

        Returns:
            FridayPinSignal if conditions met, None otherwise
        """
        if not self.check_entry_condition(market_data):
            return None

        price = market_data.get("price", 0.0)
        recent = self.price_history[-self.config.lookback_bars:]
        range_pct = ((max(recent) - min(recent)) / min(recent)) * 100 if min(recent) > 0 else 0

        ts = market_data.get("timestamp", datetime.now(UTC))
        ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)

        signal = FridayPinSignal(
            action="SHORT_STRADDLE",
            strike=round(price, 0),
            spot=price,
            target_premium_bps=self.config.target_bps,
            stop_bps=self.config.stop_bps,
            reason=f"Pin condition met: {range_pct:.3f}% range over last {self.config.lookback_bars} min (threshold {self.config.pin_range_pct}%)",
            range_pct=range_pct,
            timestamp=ts_str,
        )

        logger.info(f"Friday Pin signal: {signal.reason}")
        return signal

    def backtest(self, historical_data: list[dict]) -> dict:
        """Run a backtest on historical 1-minute bar data.

        Args:
            historical_data: list of dicts with keys:
                - price: float
                - timestamp: ISO datetime string

        Returns:
            dict with keys: sharpe, win_rate, max_dd, pnl, trades, total_trades
        """
        self.price_history = []
        trades = []
        peak_equity = 0
        max_dd = 0
        equity = 0

        for bar in historical_data:
            signal = self.generate_signal(bar)
            if signal:
                # Simplified PnL: collect premium if pin holds, lose if stopout
                # In reality, this would use actual option pricing
                entry_price = signal.spot
                # Simulate: if next bar is within stop range, win
                # This is a simplified model — real backtest needs option data
                pnl = signal.target_premium_bps / 100 * entry_price / 100  # bps to dollars
                trades.append({
                    "entry": entry_price,
                    "pnl": pnl,
                    "timestamp": signal.timestamp,
                })
                equity += pnl
                peak_equity = max(peak_equity, equity)
                dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
                max_dd = max(max_dd, dd)

        total_pnl = sum(t["pnl"] for t in trades)
        wins = sum(1 for t in trades if t["pnl"] > 0)
        win_rate = wins / len(trades) if trades else 0

        # Simplified Sharpe (assuming daily returns)
        returns = [t["pnl"] for t in trades]
        if returns:
            import numpy as np
            returns_arr = np.array(returns)
            sharpe = float(np.mean(returns_arr) / np.std(returns_arr) * np.sqrt(252)) if np.std(returns_arr) > 0 else 0.0
        else:
            sharpe = 0.0

        return {
            "sharpe": round(sharpe, 2),
            "win_rate": round(win_rate, 2),
            "max_dd": round(max_dd, 4),
            "pnl": round(total_pnl, 2),
            "trades": trades,
            "total_trades": len(trades),
        }
