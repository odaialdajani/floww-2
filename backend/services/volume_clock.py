"""
Volume Clock — bucketing engine for VPIN.

Implements the "volume clock" mechanism from Easley/López de Prado/O'Hara (2012):
instead of clock-time bars, trades are aggregated into fixed-volume buckets.
Each bucket contains exactly V units of volume (within float tolerance). When
a trade would overflow a bucket, the trade is split: the portion that fills
the current bucket is finalized, and the remainder carries over to the next.

Classes
-------
VolumeClock
    Accumulates trades into fixed-volume buckets, emitting bucket metadata
    whenever a bucket is finalized.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class VolumeBucket:
    """Metadata for a single finalized volume bucket."""
    bucket_id: int
    start_time: float          # epoch seconds of first trade in bucket
    end_time: float            # epoch seconds of last trade in bucket
    total_volume: float
    buy_volume: float
    sell_volume: float
    avg_price_change: float    # volume-weighted mean price change
    price_changes: List[float] = field(default_factory=list)  # raw changes
    vpin: float = 0.0         # |buy - sell| / total

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def imbalance(self) -> float:
        return abs(self.buy_volume - self.sell_volume)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bucket_id": self.bucket_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "total_volume": self.total_volume,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "avg_price_change": self.avg_price_change,
            "vpin": self.vpin,
        }


class VolumeClock:
    """Fixed-volume bucketing engine.

    Parameters
    ----------
    bucket_size : float
        Target volume per bucket (V).  Default 50 000.
    on_bucket_finalized : callable, optional
        Called with (VolumeBucket) each time a bucket closes.  Useful for
        streaming pipelines that need to forward the bucket immediately.
    """

    def __init__(
        self,
        bucket_size: float = 50_000.0,
        on_bucket_finalized: Optional[Callable[[VolumeBucket], None]] = None,
    ) -> None:
        if bucket_size <= 0:
            raise ValueError("bucket_size must be positive")

        self.bucket_size = float(bucket_size)
        self.on_bucket_finalized = on_bucket_finalized

        # Current bucket accumulators
        self._bucket_id: int = 0
        self._acc_volume: float = 0.0
        self._acc_buy: float = 0.0
        self._acc_sell: float = 0.0
        self._acc_wprice: float = 0.0       # volume-weighted price change sum
        self._start_time: Optional[float] = None
        self._end_time: float = 0.0
        self._price_changes: List[float] = []
        self._remainder: float = 0.0         # carry-over from split trade

        # History
        self._finalized: List[VolumeBucket] = []

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def feed(
        self,
        price: float,
        size: float,
        timestamp: Optional[float] = None,
    ) -> List[VolumeBucket]:
        """Feed a single trade.

        If the trade *exactly* fills or overflows the current bucket the
        trade is split: the portion that fits finalizes the bucket, the
        remainder starts (or continues) the next bucket.  This means one
        call can emit *multiple* buckets for very large trades.

        Parameters
        ----------
        price : float
            Signed price change (delta_P) for this trade.  Use the raw
            change from the previous trade; the engine only needs the
            sign + magnitude for BVC.
        size : float
            Trade volume (always positive).
        timestamp : float, optional
            Epoch seconds.  Defaults to time.time().

        Returns
        -------
        list of VolumeBucket
            Any buckets finalized by this trade (0, 1, or more).
        """
        if size <= 0:
            return []

        ts = timestamp if timestamp is not None else time.time()
        finalized: List[VolumeBucket] = []

        # Classify this trade's volume via a quick BVC estimate using the
        # raw price change; we pass the signed change so that aggressive
        # buys (positive dp) get ≈100 % buy, sells ≈0 %.
        # For the VolumeClock we just need buy/sell split — the full BVC
        # with sigma normalization happens upstream in VpinEngine.
        buy_frac = _price_classify(price)
        buy_vol = size * buy_frac
        sell_vol = size - buy_vol

        remaining = size
        # First, use any remainder carried over from a previous split
        if self._remainder > 0:
            space = self.bucket_size - self._acc_volume
            use = min(self._remainder, space)
            r_frac = use / size  # approximate: use same buy/sell ratio
            self._acc_volume += use
            self._acc_buy += buy_vol * r_frac
            self._acc_sell += sell_vol * r_frac
            self._acc_wprice += price * use
            self._price_changes.append(price)
            if self._start_time is None:
                self._start_time = ts
            self._end_time = ts
            self._remainder -= use
            remaining -= use
            if self._acc_volume >= self.bucket_size - 1e-12:
                finalized.append(self._finalize(ts))
            if remaining <= 0:
                return finalized

        # Now feed whole trades (or remaining portion)
        while remaining > 0:
            space = self.bucket_size - self._acc_volume
            if space <= 1e-12:
                finalized.append(self._finalize(ts))
                space = self.bucket_size - self._acc_volume
            use = min(remaining, space)
            u_frac = use / size  # fraction of original trade
            self._acc_volume += use
            self._acc_buy += buy_vol * u_frac
            self._acc_sell += sell_vol * u_frac
            self._acc_wprice += price * use
            self._price_changes.append(price)
            if self._start_time is None:
                self._start_time = ts
            self._end_time = ts
            remaining -= use
            if self._acc_volume >= self.bucket_size - 1e-12:
                finalized.append(self._finalize(ts))

        return finalized

    def feed_bulk(
        self,
        trades: List[Dict[str, Any]],
    ) -> List[VolumeBucket]:
        """Feed a list of trade dicts {"price_change": …, "size": …, "timestamp": …}.

        Convenience wrapper that calls :meth:`feed` for each trade and
        collects all finalized buckets.
        """
        all_finalized: List[VolumeBucket] = []
        for t in trades:
            buckets = self.feed(
                price=t["price_change"],
                size=t["size"],
                timestamp=t.get("timestamp"),
            )
            all_finalized.extend(buckets)
        return all_finalized

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _finalize(self, now: float) -> VolumeBucket:
        """Close the current bucket and start a new one."""
        if self._acc_volume <= 0:
            self._start_time = now

        avg_pc = self._acc_wprice / self._acc_volume if self._acc_volume > 0 else 0.0
        total = self._acc_volume
        vpin = abs(self._acc_buy - self._acc_sell) / total if total > 0 else 0.0

        bucket = VolumeBucket(
            bucket_id=self._bucket_id,
            start_time=self._start_time if self._start_time is not None else now,
            end_time=self._end_time if self._end_time > 0.0 else now,
            total_volume=total,
            buy_volume=self._acc_buy,
            sell_volume=self._acc_sell,
            avg_price_change=avg_pc,
            price_changes=list(self._price_changes),
            vpin=vpin,
        )
        self._finalized.append(bucket)
        self._bucket_id += 1

        # Reset accumulators
        self._acc_volume = 0.0
        self._acc_buy = 0.0
        self._acc_sell = 0.0
        self._acc_wprice = 0.0
        self._start_time = None
        self._end_time = 0.0
        self._price_changes = []

        if self.on_bucket_finalized:
            self.on_bucket_finalized(bucket)

        return bucket

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def current_fill(self) -> float:
        """Fraction of current bucket that is filled (0.0 – 1.0+)."""
        return self._acc_volume / self.bucket_size

    @property
    def current_volume(self) -> float:
        return self._acc_volume

    @property
    def finalized_buckets(self) -> List[VolumeBucket]:
        return list(self._finalized)

    @property
    def num_finalized(self) -> int:
        return len(self._finalized)

    def get_state(self) -> Dict[str, Any]:
        return {
            "bucket_size": self.bucket_size,
            "current": {
                "volume": self._acc_volume,
                "fill_ratio": self.current_fill,
                "bucket_id": self._bucket_id,
            },
            "finalized_count": len(self._finalized),
        }


# ----------------------------------------------------------------------
# Helper — naive price-direction classifier
# ----------------------------------------------------------------------

def _price_classify(price_change: float) -> float:
    """Map a signed price change to a buy-fraction in (0, 1).

    Uses the same normal-CDF trick as full BVC but with a *unit* sigma
    so that large |dp| → strong classification, small |dp| → ~0.5.
    This is only used for the VolumeClock's internal bookkeeping; the
    authoritative BVC happens in :class:`VpinEngine`.
    """
    z = price_change / 1.0  # unit sigma for the rough split
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
