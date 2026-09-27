"""
Volume-Synchronized Probability of Informed Trading (VPIN) Engine

Implementation based on:
    Easley, D., Lopez de Prado, M.M., & O'Hara, M. (2012).
    "Flow Toxicity and Liquidity in a High-frequency World."
    Review of Financial Studies, 25(5), 1457-1493.

VPIN measures the probability that a trade is information-based (toxic)
by classifying volume into buy and sell initiated trades using the
Bulk Volume Classification (BVC) method, then computing the imbalance
over a rolling window of volume-time buckets.

Key concepts:
    - Volume Clock: Time is measured in cumulative traded volume rather
      than wall-clock time. Each bucket contains a fixed amount of volume
      (bucket_size), making the measure robust to irregular trading intensity.
    - Bulk Volume Classification: Each trade's volume is split into
      buyer-initiated (V^B) and seller-initiated (V^S) components using
      the standard normal CDF applied to the normalized price change:
          V^B_tau = V * Phi(delta_P / (sigma * sqrt(dt)))
          V^S_tau = V - V^B_tau
    - VPIN: The rolling average absolute imbalance across n buckets:
          VPIN = sum(|V^B - V^S|) / sum(V)
      Values near 1 indicate high toxicity (informed trading); values
      near 0 indicate balanced flow.
    - Quote Imbalance (QI): A complementary signal derived from the
      bid/ask size imbalance at the top of book:
          QI = (bid_size - ask_size) / (bid_size + ask_size)
      Combined with VPIN, it provides a multi-dimensional toxicity signal.
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Any, cast

import numpy as np

import services.observability as obs_metrics
from services.quote_imbalance import QuoteImbalanceTracker
from services.volume_clock import VolumeBucket, VolumeClock
from services.vpin_cdf import VpinCdfCalculator


class VpinEngine:
    """Volume-Synchronized PIN (VPIN) engine with Bulk Volume Classification
    and Quote Imbalance tracking.

    Parameters
    ----------
    bucket_size : float
        Target volume per bucket (volume clock). Default 50,000 units.
    window : int
        Number of buckets in the rolling VPIN window. Default 50.
    ticker : str, optional
        Symbol tag for metrics + Mongo persistence.
    mongo_collection : pymongo collection, optional
        If provided, VPIN CDF values are persisted for backtesting.
    """

    def __init__(
        self,
        bucket_size: float = 50000.0,
        window: int = 50,
        ticker: str = "",
        mongo_collection: Any = None,
    ) -> None:
        if bucket_size <= 0:
            raise ValueError("bucket_size must be positive")
        if window <= 0:
            raise ValueError("window must be positive")

        self.bucket_size = float(bucket_size)
        self.window = int(window)
        self.ticker = ticker

        # Volume Clock for timestamp tracking and metadata
        self._clock = VolumeClock(bucket_size=self.bucket_size)

        # Current bucket accumulators (per-trade BVC)
        self._bucket_buy_volume: float = 0.0
        self._bucket_sell_volume: float = 0.0
        self._bucket_total_volume: float = 0.0
        self._bucket_start_time: float | None = None
        self._bucket_end_time: float = 0.0

        # Rolling finalized buckets (buy, sell, total)
        self._buy_buckets: deque[float] = deque(maxlen=self.window)
        self._sell_buckets: deque[float] = deque(maxlen=self.window)
        self._total_buckets: deque[float] = deque(maxlen=self.window)

        # Bucket metadata history
        self._bucket_meta: deque[dict[str, Any]] = deque(maxlen=500)

        # VPIN CDF calculator (with optional Mongo persistence)
        self._cdf_calc = VpinCdfCalculator(
            window=window,
            mongo_collection=mongo_collection,
            ticker=ticker,
        )

        # Quote Imbalance tracker
        self._qi_tracker = QuoteImbalanceTracker(window=100)

        # Latest values for signal output
        self._current_vpin: float = 0.0
        self._current_vpin_cdf: float = 0.0

        # Running sigma estimate (std of recent price changes)
        self._price_changes_buf: deque[float] = deque(maxlen=200)

    # ------------------------------------------------------------------
    # Bulk Volume Classification
    # ------------------------------------------------------------------

    @staticmethod
    def _norm_cdf(x: np.ndarray) -> np.ndarray:
        """Standard normal CDF: Phi(x) = 0.5 * (1 + erf(x / sqrt(2)))."""
        return cast(np.ndarray, 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0))))

    @classmethod
    def classify_volume(
        cls,
        price_changes: np.ndarray,
        volumes: np.ndarray,
        dt: float = 1.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Classify a sequence of trades into buy and sell volume using
        the Bulk Volume Classification (BVC) method.

        V^B_tau = V * Phi(delta_P / (sigma * sqrt(dt)))
        V^S_tau = V - V^B_tau

        Parameters
        ----------
        price_changes : np.ndarray
            Array of price changes (delta_P) per trade.
        volumes : np.ndarray
            Array of trade volumes.
        dt : float
            Time interval for the observation period. Default 1.0.

        Returns
        -------
        buy_volumes : np.ndarray
            Estimated buyer-initiated volume per trade.
        sell_volumes : np.ndarray
            Estimated seller-initiated volume per trade.
        """
        price_changes = np.asarray(price_changes, dtype=np.float64)
        volumes = np.asarray(volumes, dtype=np.float64)

        if price_changes.shape != volumes.shape:
            raise ValueError("price_changes and volumes must have the same shape")

        if dt <= 0:
            raise ValueError("dt must be positive")

        # Estimate sigma from price changes (realized volatility)
        sigma = float(np.std(price_changes))
        if sigma <= 0 or math.isnan(sigma):
            # No price variation: if all changes are zero, split evenly
            # If non-zero changes exist, use mean absolute value as fallback sigma
            mean_abs = float(np.mean(np.abs(price_changes)))
            if mean_abs <= 0:
                return volumes * 0.5, volumes * 0.5
            sigma = mean_abs

        z = price_changes / (sigma * math.sqrt(dt))
        phi = cls._norm_cdf(z)

        buy_volumes = volumes * phi
        sell_volumes = volumes - buy_volumes

        return buy_volumes, sell_volumes

    # ------------------------------------------------------------------
    # Incremental update (single trade)
    # ------------------------------------------------------------------

    def update(
        self,
        price_change: float,
        volume: float,
        sigma: float,
        dt: float = 1.0,
        timestamp: float | None = None,
    ) -> VolumeBucket | None:
        """Add a single trade to the current bucket. When the bucket's
        accumulated volume reaches bucket_size, the bucket is finalized
        and VPIN is recomputed.

        Parameters
        ----------
        price_change : float
            Price change for this trade.
        volume : float
            Trade volume.
        sigma : float
            Estimated return volatility (sigma) for normalization.
        dt : float
            Time interval. Default 1.0.
        timestamp : float, optional
            Epoch seconds.  Defaults to time.time().

        Returns
        -------
        VolumeBucket or None
            The finalized bucket if one was closed, else None.
        """
        if volume <= 0:
            return None

        # Update running sigma estimate
        self._price_changes_buf.append(price_change)

        ts = timestamp if timestamp is not None else time.time()

        # Classify this trade individually
        if sigma <= 0 or math.isnan(sigma) or math.isinf(sigma):
            buy_frac = 0.5
        else:
            z = price_change / (sigma * math.sqrt(dt))
            buy_frac = float(self._norm_cdf(np.array([z]))[0])

        buy_vol = volume * buy_frac
        sell_vol = volume - buy_vol

        # Feed the VolumeClock for boundary detection (tracks total volume only)
        self._clock.feed(price=price_change, size=volume, timestamp=ts)

        # Accumulate per-trade buy/sell
        self._bucket_buy_volume += buy_vol
        self._bucket_sell_volume += sell_vol
        self._bucket_total_volume += volume

        if self._bucket_start_time is None:
            self._bucket_start_time = ts
        self._bucket_end_time = ts

        # Check if bucket is full
        if self._bucket_total_volume >= self.bucket_size:
            return self._finalize_bucket(ts)
        return None

    def _finalize_bucket(self, ts: float) -> VolumeBucket | None:
        """Finalize the current bucket and push it into the rolling window."""
        if self._bucket_total_volume <= 0:
            return None

        buy = self._bucket_buy_volume
        sell = self._bucket_sell_volume
        total = self._bucket_total_volume

        self._buy_buckets.append(buy)
        self._sell_buckets.append(sell)
        self._total_buckets.append(total)

        avg_pc = 0.0
        if total > 0 and self._clock.finalized_buckets:
            # Use the clock's last finalized bucket for avg price change
            last = self._clock.finalized_buckets[-1]
            avg_pc = last.avg_price_change

        # Store metadata
        meta: dict[str, Any] = {
            "bucket_id": self._clock.num_finalized - 1,
            "start_time": self._bucket_start_time,
            "end_time": self._bucket_end_time,
            "total_volume": total,
            "buy_volume": buy,
            "sell_volume": sell,
            "avg_price_change": avg_pc,
        }
        self._bucket_meta.append(meta)

        # Reset accumulators
        self._bucket_buy_volume = 0.0
        self._bucket_sell_volume = 0.0
        self._bucket_total_volume = 0.0
        self._bucket_start_time = None
        self._bucket_end_time = 0.0

        # Recompute VPIN
        self._recompute_vpin()

        # Build a VolumeBucket for the return value
        vpin_val = abs(buy - sell) / total if total > 0 else 0.0
        return VolumeBucket(
            bucket_id=meta["bucket_id"],
            start_time=meta["start_time"] or ts,
            end_time=meta["end_time"] or ts,
            total_volume=total,
            buy_volume=buy,
            sell_volume=sell,
            avg_price_change=avg_pc,
            vpin=vpin_val,
        )

    def _recompute_vpin(self) -> None:
        """Recompute VPIN from finalized buckets and update CDF."""
        if len(self._total_buckets) == 0:
            self._current_vpin = 0.0
            self._current_vpin_cdf = 0.0
            return

        total_vol = sum(self._total_buckets)
        if total_vol <= 0:
            self._current_vpin = 0.0
            self._current_vpin_cdf = 0.0
            return

        imbalance = sum(
            abs(b - s)
            for b, s in zip(self._buy_buckets, self._sell_buckets, strict=False)
        )
        self._current_vpin = imbalance / total_vol

        # Update CDF calculator
        self._current_vpin_cdf = self._cdf_calc.update(self._current_vpin)

        # Emit Prometheus metrics
        if self.ticker:
            obs_metrics.vpin_current.labels(ticker=self.ticker).set(self._current_vpin)
            obs_metrics.ingestion_messages_total.labels(
                symbol=self.ticker, kind="vpin_bucket"
            ).inc()

    # ------------------------------------------------------------------
    # VPIN computation
    # ------------------------------------------------------------------

    def compute_vpin(self) -> float:
        """Return the current VPIN value.

        VPIN = sum(|V^B - V^S|) / sum(V) over the rolling window of n buckets.

        Returns
        -------
        float
            Current VPIN value in [0, 1].
        """
        return self._current_vpin

    # ------------------------------------------------------------------
    # VPIN empirical CDF
    # ------------------------------------------------------------------

    def compute_vpin_cdf(self) -> float:
        """CDF of the current VPIN value against the historical VPIN
        distribution.

        Returns
        -------
        float
            Empirical CDF value in [0, 1]. Higher values indicate the
            current VPIN is in the upper tail of the historical distribution.
        """
        return self._current_vpin_cdf

    @property
    def vpin_history_length(self) -> int:
        return len(self._cdf_calc.history)

    # ------------------------------------------------------------------
    # Quote Imbalance
    # ------------------------------------------------------------------

    def compute_quote_imbalance(self, bid_size: float, ask_size: float) -> float:
        """Compute the Quote Imbalance (QI).

        QI = (bid_size - ask_size) / (bid_size + ask_size)

        Parameters
        ----------
        bid_size : float
            Total size at the best bid.
        ask_size : float
            Total size at the best ask.

        Returns
        -------
        float
            QI in [-1, 1]. Positive values indicate bid-side pressure.
        """
        qi = self._qi_tracker.update(bid_size, ask_size)

        # Emit Prometheus metric
        if self.ticker:
            obs_metrics.qi_zscore_current.labels(ticker=self.ticker).set(
                self._qi_tracker.zscore
            )

        return qi

    def compute_qi_zscore(self) -> float:
        """Z-score of the current QI against the rolling QI history.

        Returns
        -------
        float
            Z-score. Values > 1.5 indicate significant bid-side pressure.
        """
        return self._qi_tracker.zscore

    # ------------------------------------------------------------------
    # Toxicity signal
    # ------------------------------------------------------------------

    def get_toxicity_signal(self) -> dict[str, Any]:
        """Return the composite toxicity signal.

        A market is considered toxic when:
            - VPIN CDF > 0.5  (VPIN is above its historical median)
            AND
            - QI z-score > 1.5  (significant bid-side pressure)

        Returns
        -------
        dict
            {
                "vpin": float,
                "vpin_cdf": float,
                "qi": float,
                "qi_zscore": float,
                "is_toxic": bool,
            }
        """
        qi_z = self._qi_tracker.zscore
        is_toxic = (self._current_vpin_cdf > 0.5) and (qi_z > 1.5)
        return {
            "vpin": self._current_vpin,
            "vpin_cdf": self._current_vpin_cdf,
            "qi": self._qi_tracker.qi,
            "qi_zscore": qi_z,
            "is_toxic": is_toxic,
        }

    # ------------------------------------------------------------------
    # Full state
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        """Return the full engine state for API serialization.

        Returns
        -------
        dict
            Complete state including configuration, current values,
            bucket counts, and history lengths.
        """
        return {
            "config": {
                "bucket_size": self.bucket_size,
                "window": self.window,
            },
            "current": {
                "vpin": self._current_vpin,
                "vpin_cdf": self._current_vpin_cdf,
                "qi": self._qi_tracker.qi,
                "qi_zscore": self._qi_tracker.zscore,
            },
            "toxicity": self.get_toxicity_signal(),
            "buckets": {
                "active": {
                    "volume": self._clock.current_volume,
                    "fill_ratio": self._clock.current_fill,
                },
                "finalized_count": self._clock.num_finalized,
            },
            "history": {
                "vpin_history_length": len(self._cdf_calc.history),
                "qi_history_length": len(self._qi_tracker._history),
            },
        }
