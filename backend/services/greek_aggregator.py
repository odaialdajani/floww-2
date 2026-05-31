"""
Greek Aggregator with Fallback.

Orchestrates the full Greek computation pipeline:
  1. Pull latest chain data ( strikes, expiries, IVs, OI, types ).
  2. Accept upstream Greeks (from yoptions / MarketData.app).
  3. Detect NaN / missing values in upstream Vanna, Charm, etc.
  4. Fill missing values via Numba Black-Scholes (bs_calculator).
  5. Compute derived metrics: GEX, VEX, Vanna Exposure, Charm Exposure.
  6. Return a unified Greek snapshot with no NaN values.

This is the primary service that other modules (dashboard, signals, etc.)
should call — never call the BS calculator directly unless you need
raw Greeks only.

Usage:
    from services.greek_aggregator import GreekAggregator

    agg = GreekAggregator(spot=450.0, r=0.05)
    snapshot = agg.aggregate(
        upstream_greeks={"delta": [...], "gamma": [...], ...},
        strikes=np.array([...]),
        expiries=np.array([...]),
        ivs=np.array([...]),
        ois=np.array([...]),
        types=np.array([...]),
    )
    logger.info(snapshot.vanna_exposure)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from services.bs_calculator import BSCalculator
from services.gex_aggregator import GexAggregator

logger = logging.getLogger(__name__)


@dataclass
class GreekSnapshot:
    """Unified Greek snapshot for an entire option chain.

    All arrays are 1D numpy float64 of length N (number of contracts).

    Attributes:
        delta: Option delta.
        gamma: Option gamma.
        theta: Option theta (per day).
        vega: Option vega (per 1 vol point).
        vanna: Option vanna (dDelta/dVol).
        charm: Option charm (dDelta/dTime per day).
        vomma: Option vomma (dVega/dVol).
        zomma: Option zomma (dGamma/dVol).
        gex_1d: Net gamma exposure per strike (aggregated across expiries).
        vex_1d: Net vomma exposure per strike.
        vanna_exposure: Vanna * OI * spot * 0.01 per contract.
        charm_exposure: Charm * OI * spot * 0.01 per contract.
        total_gex: Scalar total GEX (positive - negative).
        net_gex: Scalar net GEX.
        max_gex_strike: Strike with highest positive GEX.
        min_gex_strike: Strike with most negative GEX.
        zero_gamma_levels: Strikes where net GEX crosses zero.
        n_filled: Number of contracts where BS fallback was used.
        strikes: Strike array (for reference).
        expiries: Expiry array (for reference).
        types: Option type array (0=call, 1=put).
    """
    delta: np.ndarray = field(default_factory=lambda: np.array([]))
    gamma: np.ndarray = field(default_factory=lambda: np.array([]))
    theta: np.ndarray = field(default_factory=lambda: np.array([]))
    vega: np.ndarray = field(default_factory=lambda: np.array([]))
    vanna: np.ndarray = field(default_factory=lambda: np.array([]))
    charm: np.ndarray = field(default_factory=lambda: np.array([]))
    vomma: np.ndarray = field(default_factory=lambda: np.array([]))
    zomma: np.ndarray = field(default_factory=lambda: np.array([]))
    gex_1d: List[float] = field(default_factory=list)
    vex_1d: List[float] = field(default_factory=list)
    vanna_exposure: np.ndarray = field(default_factory=lambda: np.array([]))
    charm_exposure: np.ndarray = field(default_factory=lambda: np.array([]))
    total_gex: float = 0.0
    net_gex: float = 0.0
    max_gex_strike: float = 0.0
    min_gex_strike: float = 0.0
    zero_gamma_levels: List[float] = field(default_factory=list)
    n_filled: int = 0
    strikes: np.ndarray = field(default_factory=lambda: np.array([]))
    expiries: np.ndarray = field(default_factory=lambda: np.array([]))
    types: np.ndarray = field(default_factory=lambda: np.array([]))


class GreekAggregator:
    """Orchestrate Greek computation with NaN-fallback and exposure metrics.

    Args:
        spot: Current underlying price.
        r: Risk-free rate (default 0.05).
        q: Continuous dividend yield (default 0.0).
    """

    def __init__(self, spot: float, r: float = 0.05, q: float = 0.0) -> None:
        self.spot = float(spot)
        self.r = float(r)
        self.q = float(q)
        self._bs = BSCalculator(spot=spot, r=r, q=q)
        self._gex_agg = GexAggregator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def aggregate(
        self,
        upstream_greeks: Dict[str, np.ndarray],
        strikes: np.ndarray,
        expiries: np.ndarray,
        ivs: np.ndarray,
        ois: np.ndarray,
        types: np.ndarray,
    ) -> GreekSnapshot:
        """Full Greek aggregation pipeline.

        Steps:
          1. Fill NaN Greeks via BS fallback.
          2. Compute GEX/VEX via GexAggregator.
          3. Compute Vanna/Charm exposure.
          4. Return unified snapshot.

        Args:
            upstream_greeks: Dict with keys like 'delta', 'gamma', etc.
                Arrays may contain NaN for missing values.
            strikes: 1D array of strike prices.
            expiries: 1D array of times-to-expiry in years.
            ivs: 1D array of implied volatilities.
            ois: 1D array of open interest per contract.
            types: 1D array of option types (0=call, 1=put).

        Returns:
            GreekSnapshot with all fields populated, no NaN values.
        """
        K = np.asarray(strikes, dtype=np.float64)
        T = np.asarray(expiries, dtype=np.float64)
        IV = np.asarray(ivs, dtype=np.float64)
        OI = np.asarray(ois, dtype=np.float64)
        kind = np.asarray(types, dtype=np.int32)

        # Step 1: Fill NaN Greeks
        cleaned, n_filled = self._fill_greeks(upstream_greeks, K, T, IV, kind)

        # Step 2: GEX / VEX
        contracts = self._build_contracts(K, T, cleaned, OI, kind)
        gex_result = self._gex_agg.compute(self.spot, contracts)

        # Step 3: Vanna / Charm exposure
        vanna_exp = self._compute_vanna_exposure(
            cleaned["vanna"], OI, cleaned["delta"]
        )
        charm_exp = self._compute_charm_exposure(
            cleaned["charm"], OI, cleaned["delta"]
        )

        return GreekSnapshot(
            delta=cleaned["delta"],
            gamma=cleaned["gamma"],
            theta=cleaned["theta"],
            vega=cleaned["vega"],
            vanna=cleaned["vanna"],
            charm=cleaned["charm"],
            vomma=cleaned.get("vomma", np.zeros_like(K)),
            zomma=cleaned.get("zomma", np.zeros_like(K)),
            gex_1d=gex_result["gex_1d"],
            vex_1d=gex_result["vex_1d"] if "vex_1d" in gex_result else [],
            vanna_exposure=vanna_exp,
            charm_exposure=charm_exp,
            total_gex=gex_result["total_gex"],
            net_gex=gex_result["net_gex"],
            max_gex_strike=gex_result["max_gex_strike"],
            min_gex_strike=gex_result["min_gex_strike"],
            zero_gamma_levels=gex_result["zero_gamma_levels"],
            n_filled=n_filled,
            strikes=K,
            expiries=T,
            types=kind,
        )

    def aggregate_simple(
        self,
        strikes: np.ndarray,
        expiries: np.ndarray,
        ivs: np.ndarray,
        ois: np.ndarray,
        types: np.ndarray,
    ) -> GreekSnapshot:
        """Compute all Greeks from scratch (no upstream data).

        Useful when no data provider is available — everything is
        computed via the Numba BS calculator.
        """
        n = len(strikes)
        empty = {
            "delta": np.full(n, np.nan),
            "gamma": np.full(n, np.nan),
            "theta": np.full(n, np.nan),
            "vega": np.full(n, np.nan),
            "vanna": np.full(n, np.nan),
            "charm": np.full(n, np.nan),
            "vomma": np.full(n, np.nan),
            "zomma": np.full(n, np.nan),
        }
        return self.aggregate(empty, strikes, expiries, ivs, ois, types)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fill_greeks(
        self,
        upstream: Dict[str, np.ndarray],
        K: np.ndarray,
        T: np.ndarray,
        IV: np.ndarray,
        kind: np.ndarray,
    ) -> tuple:
        """Fill NaN values in upstream Greeks via BS fallback.

        Returns:
            (cleaned_dict, n_filled_count)
        """
        computed = self._bs.compute_chain(K, T, IV, kind)
        cleaned: Dict[str, np.ndarray] = {}
        n_filled = 0

        for key in ["delta", "gamma", "theta", "vega", "vanna", "charm", "vomma", "zomma"]:
            if key in upstream:
                arr = np.array(upstream[key], dtype=np.float64).copy()
                nan_mask = np.isnan(arr)
                n_nan = int(np.sum(nan_mask))
                if n_nan > 0:
                    arr[nan_mask] = computed[key][nan_mask]
                    n_filled += n_nan
                    logger.debug(
                        "BS fallback filled %d NaN values for %s", n_nan, key
                    )
                cleaned[key] = arr
            else:
                cleaned[key] = computed[key]
                n_filled += len(K)  # All values were missing

        return cleaned, n_filled

    @staticmethod
    def _build_contracts(
        K: np.ndarray,
        T: np.ndarray,
        greeks: Dict[str, np.ndarray],
        OI: np.ndarray,
        kind: np.ndarray,
    ) -> List[Dict]:
        """Build contract dicts for GexAggregator."""
        contracts: List[Dict] = []
        for i in range(len(K)):
            contracts.append({
                "strike": float(K[i]),
                "gamma": float(greeks["gamma"][i]),
                "oi": float(OI[i]),
                "type": int(kind[i]),
                "expiry": float(T[i]),
                "vomma": float(greeks.get("vomma", np.zeros_like(K))[i]),
            })
        return contracts

    @staticmethod
    def _compute_vanna_exposure(
        vanna: np.ndarray, oi: np.ndarray, delta: np.ndarray
    ) -> np.ndarray:
        """Vanna exposure = vanna * OI * spot * 0.01.

        Represents the dollar impact of a 1 vol point change on delta
        positioning across all open contracts.
        """
        return vanna * oi * 0.01

    @staticmethod
    def _compute_charm_exposure(
        charm: np.ndarray, oi: np.ndarray, delta: np.ndarray
    ) -> np.ndarray:
        """Charm exposure = charm * OI * spot * 0.01.

        Represents the daily delta decay across all open contracts.
        """
        return charm * oi * 0.01
