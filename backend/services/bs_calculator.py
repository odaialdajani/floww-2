"""
Black-Scholes Greek Calculator with Numba JIT fallback.

This module provides a clean-high-level interface on top of the
low-level vectorized numba functions in numba_greeks.py.  It is
intended as the **fallback** when the upstream data provider
(``yoptions`` / yfinance) returns NaN for any Greek.

Fast calculation target: <1ms per option chain (hundreds of strikes).

Usage:
    from services.bs_calculator import BSCalculator

    calc = BSCalculator(spot=450.0, r=0.05, q=0.0)
    greeks = calc.compute_chain(
        strikes=np.array([440., 445., 450., 455., 460.]),
        expiries=np.array([0.25, 0.25, 0.25, 0.25, 0.25]),
        ivs=np.array([0.18, 0.17, 0.16, 0.17, 0.18]),
        kinds=np.array([0, 0, 1, 1, 0]),  # 0=call, 1=put
    )
    logger.info(greeks["delta"])
"""

from __future__ import annotations

import logging
import time
from typing import Dict

import numpy as np

from services.numba_greeks import compute_all_greeks

logger = logging.getLogger(__name__)
class BSCalculator:
    """Vectorized Black-Scholes Greek calculator (Numba-backed).

    Accepts scalar spot + vectorized strikes/expiries/ivs/kinds and
    returns all first-order and second-order Greeks for the entire
    chain in a single call.

    Args:
        spot: Current underlying price.
        r: Risk-free rate (annualized, default 0.05).
        q: Continuous dividend yield (default 0.0).
    """

    def __init__(self, spot: float, r: float = 0.05, q: float = 0.0) -> None:
        self.spot = float(spot)
        self.r = float(r)
        self.q = float(q)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_chain(
        self,
        strikes: np.ndarray,
        expiries: np.ndarray,
        ivs: np.ndarray,
        kinds: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """Compute the full Greek surface for an option chain.

        Args:
            strikes: 1D array of strike prices.
            expiries: 1D array of times-to-expiry in years.
            ivs: 1D array of implied volatilities.
            kinds: 1D array of option types (0=call, 1=put).

        Returns:
            Dictionary with keys: delta, gamma, theta, vega, vanna,
            charm, vomma, zomma.  Each maps to a 1D np.ndarray.
        """
        K = np.asarray(strikes, dtype=np.float64)
        T = np.asarray(expiries, dtype=np.float64)
        IV = np.asarray(ivs, dtype=np.float64)
        kind = np.asarray(kinds, dtype=np.int32)

        return compute_all_greeks(
            spot=self.spot,
            strikes=K,
            expiries=T,
            ivs=IV,
            types=kind,
            r=self.r,
            q=self.q,
        )

    def fill_nan_greeks(
        self,
        upstream: Dict[str, np.ndarray],
        strikes: np.ndarray,
        expiries: np.ndarray,
        ivs: np.ndarray,
        kinds: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """Replace NaN entries in an upstream Greek dict with BS values.

        This is the primary integration point for the fallback pattern::

            raw = yoptions.get_greeks()           # may contain NaNs
            clean = calc.fill_nan_greeks(raw, K, T, IV, kinds)

        Args:
            upstream: Dict possibly containing NaN values for any key.
            strikes: 1D array of strike prices.
            expiries: 1D array of times-to-expiry in years.
            ivs: 1D array of implied volatilities.
            kinds: 1D array of option types (0=call, 1=put).

        Returns:
            Same dict with NaN elements replaced by Black-Scholes values.
        """
        computed = self.compute_chain(strikes, expiries, ivs, kinds)
        cleaned: Dict[str, np.ndarray] = {}
        for key in computed:
            if key in upstream:
                arr = np.array(upstream[key], dtype=np.float64).copy()
                nan_mask = np.isnan(arr)
                if np.any(nan_mask):
                    arr[nan_mask] = computed[key][nan_mask]
                cleaned[key] = arr
            else:
                cleaned[key] = computed[key]
        return cleaned

    def benchmark(self, n_options: int = 500) -> float:
        """Time one full chain computation (for sanity checks).

        Returns:
            Elapsed time in milliseconds.
        """
        rng = np.random.default_rng(42)
        lo = self.spot * 0.8
        hi = self.spot * 1.2
        K = np.sort(rng.uniform(lo, hi, n_options))
        T = np.full(n_options, 0.25)
        IV = rng.uniform(0.10, 0.50, n_options)
        kinds = rng.integers(0, 2, n_options).astype(np.int32)

        # warm-up JIT
        self.compute_chain(K[:5], T[:5], IV[:5], kinds[:5])

        t0 = time.perf_counter()
        self.compute_chain(K, T, IV, kinds)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return elapsed_ms
