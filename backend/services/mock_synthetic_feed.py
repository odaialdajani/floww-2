"""
backend/services/mock_synthetic_feed.py

Synthetic tick feed for local development and CI.
Generates realistic Level 1 options and equities data using GBM spot dynamics
with chain Greeks computed via services/numba_greeks.py.

RENAMED from mock_schwab_feed.py on 2026-09-27. It was never a Schwab
connection: it opens no socket, reads no credential, and contacts no host. It
is a pure in-process random generator that happens to emit a message shape
modelled on the (now deleted) Schwab streamer. The name was the only Schwab
thing about it, and it was actively misleading — this feed stands in for the
Public.com ingestion path, not for a retired broker.

Enabled only by FLOWW_ENABLE_MOCK_FEED=1; never a live data source.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np
from scipy.stats import norm

from services.numba_greeks import compute_all_greeks

logger = logging.getLogger(__name__)


# Default spot parameters for underlyINGS
DEFAULT_SPOTS = {
    "SPY": {"price": 500.0, "vol": 0.15, "drift": 0.05},
    "QQQ": {"price": 440.0, "vol": 0.18, "drift": 0.06},
    "DIA": {"price": 400.0, "vol": 0.12, "drift": 0.04},
    "IWM": {"price": 220.0, "vol": 0.20, "drift": 0.05},
}

# Option chain parameters
OPTION_EXPIRIES = [7, 14, 21, 30, 45, 60]  # days to expiry
STRIKE_STEP = 5.0
NUM_STRIKES = 20  # strikes above and below ATM


class MockSyntheticFeed:
    """Synthetic market data feed that mimics Schwab WebSocket streamer.

    Generates:
      - Equity ticks (bid/ask/last/volume) for SPY/QQQ/DIA/IWM
      - Options chain updates with full Greeks
      - LOB snapshots

    Usage:
        feed = MockSyntheticFeed(rate=100)  # 100 msg/sec
        feed.on_tick(handle_tick)
        feed.on_chain(handle_chain)
        await feed.start()
    """

    def __init__(
        self,
        rate: float = 100.0,  # messages per second
        symbols: list[str] | None = None,
        spots: dict[str, dict[str, float]] | None = None,
        seed: int = 42,
    ):
        self.rate = rate
        self.symbols = symbols or ["SPY", "QQQ"]
        self.spots = spots or DEFAULT_SPOTS
        self.rng = np.random.default_rng(seed)

        self._running = False
        self._tick_handlers: list = []
        self._chain_handlers: list = []
        self._lob_handlers: list = []
        self._lob_depth_handlers: list = []

        # Current state
        self._current_prices: dict[str, float] = {
            s: self.spots.get(s, {}).get("price", 100.0) for s in self.symbols
        }
        self._current_volume: dict[str, int] = {s: 0 for s in self.symbols}
        self._tick_count = 0
        self._start_time = 0.0

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def on_tick(self, handler: Callable[[dict[str, Any]], Any]):
        self._tick_handlers.append(handler)

    def on_chain(self, handler: Callable[[dict[str, Any]], Any]):
        self._chain_handlers.append(handler)

    def on_lob(self, handler: Callable[[dict[str, Any]], Any]):
        self._lob_handlers.append(handler)

    def on_lob_depth(self, handler: Callable[[dict[str, Any]], Any]):
        self._lob_depth_handlers.append(handler)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start generating synthetic data."""
        self._running = True
        self._start_time = time.monotonic()
        interval = 1.0 / self.rate
        logger.info(f"Mock Schwab feed starting: {self.rate} msg/s, symbols={self.symbols}")

        while self._running:
            try:
                await self._generate_tick()
                self._tick_count += 1
                # Generate chain updates less frequently (every 10 ticks)
                if self._tick_count % 10 == 0:
                    await self._generate_chain()
                # Generate LOB snapshots (every 5 ticks)
                if self._tick_count % 5 == 0:
                    await self._generate_lob()
                # Generate Level-2 depth (every 20 ticks)
                if self._tick_count % 20 == 0:
                    await self._generate_lob_depth()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Mock feed error: {e}")
                await asyncio.sleep(interval)

    async def stop(self):
        """Stop the feed."""
        self._running = False
        elapsed = time.monotonic() - self._start_time
        rate = self._tick_count / elapsed if elapsed > 0 else 0
        logger.info(
            f"Mock feed stopped: {self._tick_count} ticks in {elapsed:.1f}s "
            f"({rate:.0f} msg/s)"
        )

    # ------------------------------------------------------------------
    # Tick generation
    # ------------------------------------------------------------------

    async def _generate_tick(self):
        """Generate a single equity tick for a random symbol."""
        symbol = self.rng.choice(self.symbols)
        spot_config = self.spots.get(symbol, {"price": 100.0, "vol": 0.15, "drift": 0.05})
        current_price = self._current_prices[symbol]

        # GBM step
        dt = 1.0 / (252 * 6.5 * 3600)  # 1 second in trading years
        vol = spot_config["vol"]
        drift = spot_config["drift"]
        shock = self.rng.normal(0, 1)
        price_change = current_price * (drift * dt + vol * math.sqrt(dt) * shock)
        new_price = max(current_price + price_change, 1.0)

        self._current_prices[symbol] = new_price
        self._current_volume[symbol] += int(self.rng.integers(100, 10000))

        spread = max(0.01, new_price * 0.0001)  # 1 basis point spread
        tick = {
            "timestamp": datetime.now(UTC).isoformat(),
            "symbol": symbol,
            "bid": round(new_price - spread / 2, 2),
            "ask": round(new_price + spread / 2, 2),
            "last": round(new_price, 2),
            "volume": self._current_volume[symbol],
            "bid_size": int(self.rng.integers(100, 5000)),
            "ask_size": int(self.rng.integers(100, 5000)),
            "source": "mock",
        }

        for h in self._tick_handlers:
            try:
                await h(tick) if asyncio.iscoroutinefunction(h) else h(tick)
            except Exception as e:
                logger.error(f"Tick handler error: {e}")

    async def _generate_chain(self):
        """Generate options chain updates for all symbols.

        Vectorized: builds the whole strike×type×expiry grid as arrays and
        computes Greeks in ONE compute_all_greeks call per symbol (the old
        per-contract numpy-of-size-1 loop burned ~117% CPU and saturated
        the ingestion queue).
        """
        now = datetime.now(UTC)
        for symbol in self.symbols:
            spot = self._current_prices[symbol]
            spot_config = self.spots.get(symbol, {"vol": 0.15})
            base_iv = spot_config["vol"]

            # Build the full contract grid as flat arrays (vectorized)
            atm_strike = round(spot / STRIKE_STEP) * STRIKE_STEP
            strikes_list = [atm_strike + (i - NUM_STRIKES // 2) * STRIKE_STEP for i in range(NUM_STRIKES)]
            dtes = OPTION_EXPIRIES[:3]  # nearest 3 expiries

            rows: list[tuple[float, float, float, int, str, float]] = []
            # (strike, T, iv, type_code, opt_type, expiry_str)
            moneyness = [s / spot for s in strikes_list]
            for dte in dtes:
                T = dte / 365.0
                expiry_str = (now.replace(hour=0, minute=0, second=0) + __import__("datetime").timedelta(days=dte)).strftime("%Y-%m-%d")
                for strike, mn in zip(strikes_list, moneyness, strict=True):
                    iv_skew = base_iv * (1 + 0.1 * (mn - 1) ** 2)
                    for type_code, opt_type in [(0, "call"), (1, "put")]:
                        rows.append((strike, T, iv_skew, type_code, opt_type, expiry_str))

            n = len(rows)
            strikes_arr = np.array([r[0] for r in rows])
            ts_arr = np.array([r[1] for r in rows])
            ivs_arr = np.array([r[2] for r in rows])
            types_arr = np.array([r[3] for r in rows])

            # ONE vectorized Greeks call for the entire symbol grid
            greeks = compute_all_greeks(spot, strikes_arr, ts_arr, ivs_arr, types_arr)
            deltas = np.asarray(greeks["delta"])
            gammas = np.asarray(greeks["gamma"])
            thetas = np.asarray(greeks["theta"])
            vegas = np.asarray(greeks["vega"])

            # Vectorized Black-Scholes theoretical price
            sq_t = np.sqrt(ts_arr)
            d1 = (np.log(spot / strikes_arr) + (0.05 + 0.5 * ivs_arr**2) * ts_arr) / (ivs_arr * sq_t)
            d2 = d1 - ivs_arr * sq_t
            is_call = types_arr == 0
            theo = np.where(
                is_call,
                spot * norm.cdf(d1) - strikes_arr * np.exp(-0.05 * ts_arr) * norm.cdf(d2),
                strikes_arr * np.exp(-0.05 * ts_arr) * norm.cdf(-d2) - spot * norm.cdf(-d1),
            )
            theo = np.maximum(theo, 0.01)
            spreads = np.maximum(0.05, theo * 0.02)

            volumes = self.rng.integers(0, 500, size=n)
            ois = self.rng.integers(1000, 50000, size=n)

            for i, (strike, _T, _iv, type_code, opt_type, expiry_str) in enumerate(rows):
                spread_i = float(spreads[i])
                chain = {
                    "timestamp": now.isoformat(),
                    "symbol": symbol,
                    "option_symbol": f"{symbol} {expiry_str[-5:].replace('-', '')}{'C' if type_code == 0 else 'P'}{int(strike*1000):08d}",
                    "expiry": expiry_str,
                    "strike": strike,
                    "type": opt_type,
                    "bid": round(float(theo[i]) - spread_i / 2, 2),
                    "ask": round(float(theo[i]) + spread_i / 2, 2),
                    "last": round(float(theo[i]) + self.rng.normal(0, spread_i * 0.3), 2),
                    "volume": int(volumes[i]),
                    "oi": int(ois[i]),
                    "delta": round(float(deltas[i]), 6),
                    "gamma": round(float(gammas[i]), 6),
                    "theta": round(float(thetas[i]), 6),
                    "vega": round(float(vegas[i]), 6),
                    "source": "mock",
                }

                for h in self._chain_handlers:
                    try:
                        await h(chain) if asyncio.iscoroutinefunction(h) else h(chain)
                    except Exception as e:
                        logger.error(f"Chain handler error: {e}")

    async def _generate_lob(self):
        """Generate a top-of-book LOB snapshot."""
        for symbol in self.symbols:
            spot = self._current_prices[symbol]
            spread = max(0.01, spot * 0.0001)
            lob = {
                "timestamp": datetime.now(UTC).isoformat(),
                "symbol": symbol,
                "bid_size": int(self.rng.integers(100, 10000)),
                "ask_size": int(self.rng.integers(100, 10000)),
                "bid_price": round(spot - spread / 2, 2),
                "ask_price": round(spot + spread / 2, 2),
                "level": 0,
                "source": "mock",
            }
            for h in self._lob_handlers:
                try:
                    await h(lob) if asyncio.iscoroutinefunction(h) else h(lob)
                except Exception as e:
                    logger.error(f"LOB handler error: {e}")

    async def _generate_lob_depth(self):
        """Generate Level-2 order book depth (top 5 levels) for each symbol."""
        for symbol in self.symbols:
            spot = self._current_prices[symbol]
            spread = max(0.01, spot * 0.0001)
            for level in range(5):
                level_spread = spread * (1 + level * 0.5)
                depth = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "symbol": symbol,
                    "expiry": (datetime.now(UTC) + __import__("datetime").timedelta(days=7)).strftime("%Y-%m-%d"),
                    "strike": 0.0,
                    "option_type": "C",
                    "level": level,
                    "bid_size": int(self.rng.integers(50, 5000) / (level + 1)),
                    "bid_price": round(spot - level_spread / 2, 2),
                    "ask_size": int(self.rng.integers(50, 5000) / (level + 1)),
                    "ask_price": round(spot + level_spread / 2, 2),
                    "source": "mock",
                }
                for h in self._lob_depth_handlers:
                    try:
                        await h(depth) if asyncio.iscoroutinefunction(h) else h(depth)
                    except Exception as e:
                        logger.error(f"LOB depth handler error: {e}")

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self._start_time
        return {
            "tick_count": self._tick_count,
            "elapsed_s": round(elapsed, 1),
            "actual_rate": round(self._tick_count / elapsed, 1) if elapsed > 0 else 0,
            "target_rate": self.rate,
            "current_prices": {s: round(p, 2) for s, p in self._current_prices.items()},
        }
