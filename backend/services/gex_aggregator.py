"""
GEX/VEX Aggregator Module
==========================

Computes Gamma Exposure (GEX) and Vomma Exposure (VEX) per strike and per
strike×expiry for options chains, using Numba JIT compilation for performance.

Gamma Exposure (GEX) Formula
-----------------------------
    GEX_per_unit = gamma * OI * 100 * spot^2 * 0.01

Where:
    - gamma: option gamma (second derivative of price w.r.t. spot)
    - OI: open interest (number of contracts)
    - 100: shares per contract multiplier
    - spot^2 * 0.01: scaling to dollar gamma per 1% move in spot

    SCALE CONVENTION (S^2 -- DISPLAY). This module uses the spot^2 (dollar-GEX)
    scale: the human-facing magnitude shown in the heatmap/UI. It is DISTINCT
    from the S^1 (single spot factor) scale in ``services/gex_history.py`` and
    ``scripts/compute_gex_features.py``, which is the FROZEN ML-feature
    convention. The two differ by EXACTLY a factor of ``spot`` and are NOT
    interchangeable -- do not feed a display-scale value where a feature-scale
    value is expected. The relationship is pinned by
    ``tests/services/test_gex_aggregator_oracle.py``. Audit:
    ``docs/superpowers/specs/2026-06-13-gex-gamma-correctness-audit-design.md``.

Dealer Positioning Convention
-----------------------------
    Calls (+): Customers are long calls → dealers are short calls → dealers
               have negative gamma → GEX contribution is positive (dealers
               must buy into rallies / sell into declines = stabilizing).

    Puts  (-): Customers are long puts → dealers are short puts → dealers
               have negative gamma → GEX contribution is negative (dealers
               must sell into declines / buy into rallies = destabilizing).

    Net GEX > 0: Dealer gamma exposure is net positive (stabilizing).
    Net GEX < 0: Dealer gamma exposure is net negative (destabilizing / "gamma squeeze" risk).

Vomma Exposure (VEX)
--------------------
    VEX_per_unit = vomma * OI * 100 * spot^2 * 0.01

Signed identically to GEX. VEX measures sensitivity of gamma to changes in
implied volatility — important for vol-of-vol and skew dynamics.
"""

from typing import Any, Dict, List, Tuple

import numba
import numpy as np


@numba.njit
def compute_gex_surface(
    spot: float,
    strikes: np.ndarray,
    gammas: np.ndarray,
    ois: np.ndarray,
    types: np.ndarray,
    expiries: np.ndarray,
    vommas: np.ndarray,
    unique_strikes: np.ndarray,
    unique_expiries: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute the 2D GEX and VEX surfaces (strikes x expiries).

    Parameters
    ----------
    spot : float
        Current underlying price.
    strikes : np.ndarray
        Strike price for each contract (1D, length N).
    gammas : np.ndarray
        Gamma for each contract (1D, length N).
    ois : np.ndarray
        Open interest for each contract (1D, length N).
    types : np.ndarray
        Option type per contract: 0 = call, 1 = put (1D, length N).
    expiries : np.ndarray
        Time-to-expiry in years for each contract (1D, length N).
    vommas : np.ndarray
        Vomma for each contract (1D, length N).
    unique_strikes : np.ndarray
        Sorted array of unique strike values (1D, length S).
    unique_expiries : np.ndarray
        Sorted array of unique expiry values (1D, length E).

    Returns
    -------
    gex_surface : np.ndarray
        2D array of shape (S, E) with signed GEX per strike×expiry.
    vex_surface : np.ndarray
        2D array of shape (S, E) with signed VEX per strike×expiry.
    """
    n_strikes = len(unique_strikes)
    n_expiries = len(unique_expiries)
    gex_surface = np.zeros((n_strikes, n_expiries), dtype=np.float64)
    vex_surface = np.zeros((n_strikes, n_expiries), dtype=np.float64)

    spot_sq_scale = spot * spot * 0.01 * 100.0

    n = len(strikes)
    for i in range(n):
        # Find strike index
        si = -1
        for s in range(n_strikes):
            if unique_strikes[s] == strikes[i]:
                si = s
                break
        if si < 0:
            continue

        # Find expiry index
        ei = -1
        for e in range(n_expiries):
            if unique_expiries[e] == expiries[i]:
                ei = e
                break
        if ei < 0:
            continue

        # Signed GEX: + for calls, - for puts
        sign = 1.0 if types[i] == 0 else -1.0
        gex_surface[si, ei] += sign * gammas[i] * ois[i] * spot_sq_scale
        vex_surface[si, ei] += sign * vommas[i] * ois[i] * spot_sq_scale

    return gex_surface, vex_surface


@numba.njit
def aggregate_gex_1d(
    spot: float,
    strikes: np.ndarray,
    gammas: np.ndarray,
    ois: np.ndarray,
    types: np.ndarray,
    unique_strikes: np.ndarray,
) -> np.ndarray:
    """
    Aggregate GEX across all expiries for each strike (1D).

    Parameters
    ----------
    spot : float
        Current underlying price.
    strikes : np.ndarray
        Strike price for each contract (1D, length N).
    gammas : np.ndarray
        Gamma for each contract (1D, length N).
    ois : np.ndarray
        Open interest for each contract (1D, length N).
    types : np.ndarray
        Option type per contract: 0 = call, 1 = put (1D, length N).
    unique_strikes : np.ndarray
        Sorted array of unique strike values (1D, length S).

    Returns
    -------
    np.ndarray
        1D array of length S with net GEX per strike.
    """
    n_strikes = len(unique_strikes)
    result = np.zeros(n_strikes, dtype=np.float64)

    spot_sq_scale = spot * spot * 0.01 * 100.0

    n = len(strikes)
    for i in range(n):
        si = -1
        for s in range(n_strikes):
            if unique_strikes[s] == strikes[i]:
                si = s
                break
        if si < 0:
            continue

        sign = 1.0 if types[i] == 0 else -1.0
        result[si] += sign * gammas[i] * ois[i] * spot_sq_scale

    return result


class GexAggregator:
    """
    High-level wrapper that accepts contract dictionaries, normalises fields,
    and returns a comprehensive GEX/VEX analysis dictionary.
    """

    # Acceptable key aliases for contract dicts
    _STRIKE_KEYS = ("strike", "strike_price", "K")
    _GAMMA_KEYS = ("gamma", "gamma_val", "g")
    _OI_KEYS = ("oi", "open_interest", "openInterest")
    _TYPE_KEYS = ("type", "option_type", "opt_type")
    _EXPIRY_KEYS = ("expiry", "T", "time_to_expiry", "tte", "expiration")
    _VOMMA_KEYS = ("vomma", "vomma_val", "v")

    @staticmethod
    def _resolve(contract: Dict, key_aliases: tuple, default: Any = None) -> Any:
        """Resolve a value from a dict using multiple possible key names."""
        for key in key_aliases:
            if key in contract:
                return contract[key]
        if default is not None:
            return default
        raise KeyError(
            f"None of {key_aliases} found in contract: {contract}"
        )

    @staticmethod
    def _parse_option_type(val) -> int:
        """
        Parse option type to 0 (call) or 1 (put).
        Accepts: 'C', 'c', 'call', 'CALL', 'P', 'p', 'put', 'PUT', 0, 1.
        """
        if isinstance(val, (int, float, np.integer)):
            return int(val)
        s = str(val).strip().lower()
        if s in ("c", "call"):
            return 0
        if s in ("p", "put"):
            return 1
        raise ValueError(f"Unrecognised option type: {val!r}")

    def compute(self, spot: float, contracts: List[Dict]) -> Dict[str, Any]:
        """
        Compute GEX/VEX surfaces and summary metrics from a list of contract dicts.

        Parameters
        ----------
        spot : float
            Current underlying price.
        contracts : list of dict
            Each dict must contain (by any accepted alias):
                - strike: float
                - gamma: float
                - oi / open_interest: float or int
                - type: 'C'/'call'/'P'/put' or 0/1
                - expiry / T: float (time to expiry in years)
                - vomma: float (optional, defaults to 0.0)

        Returns
        -------
        dict with keys:
            strikes, expiries, gex_surface, vex_surface, gex_1d,
            total_gex, total_negative_gex, net_gex,
            max_gex_strike, min_gex_strike,
            zero_gamma_levels, gex_ratio
        """
        # Handle empty input
        if not contracts:
            return {
                "strikes": [],
                "expiries": [],
                "gex_surface": [],
                "vex_surface": [],
                "gex_1d": [],
                "total_gex": 0.0,
                "total_negative_gex": 0.0,
                "net_gex": 0.0,
                "max_gex_strike": 0.0,
                "min_gex_strike": 0.0,
                "zero_gamma_levels": [],
                "gex_ratio": 0.0,
            }

        n = len(contracts)

        strikes = np.empty(n, dtype=np.float64)
        gammas = np.empty(n, dtype=np.float64)
        ois = np.empty(n, dtype=np.float64)
        types = np.empty(n, dtype=np.int64)
        expiries = np.empty(n, dtype=np.float64)
        vommas = np.empty(n, dtype=np.float64)

        for i, c in enumerate(contracts):
            strikes[i] = float(self._resolve(c, self._STRIKE_KEYS))
            gammas[i] = float(self._resolve(c, self._GAMMA_KEYS))
            ois[i] = float(self._resolve(c, self._OI_KEYS))
            types[i] = self._parse_option_type(self._resolve(c, self._TYPE_KEYS))
            expiries[i] = float(self._resolve(c, self._EXPIRY_KEYS))
            vommas[i] = float(self._resolve(c, self._VOMMA_KEYS, default=0.0))

        unique_strikes = np.unique(strikes)
        unique_expiries = np.unique(expiries)

        # 2D surfaces
        gex_surface, vex_surface = compute_gex_surface(
            spot, strikes, gammas, ois, types, expiries, vommas,
            unique_strikes, unique_expiries,
        )

        # 1D aggregation
        gex_1d = aggregate_gex_1d(spot, strikes, gammas, ois, types, unique_strikes)

        # Summary metrics
        total_gex = float(np.sum(gex_surface[gex_surface > 0]))
        total_negative_gex = float(np.sum(gex_surface[gex_surface < 0]))
        net_gex = float(np.sum(gex_surface))

        # King Node: strike with highest positive GEX
        if len(gex_1d) > 0:
            max_idx = int(np.argmax(gex_1d))
            min_idx = int(np.argmin(gex_1d))
            max_gex_strike = float(unique_strikes[max_idx])
            min_gex_strike = float(unique_strikes[min_idx])
        else:
            max_gex_strike = 0.0
            min_gex_strike = 0.0

        # Zero crossings
        zero_gamma_levels = self.find_zero_crossings(unique_strikes, gex_1d)

        # GEX ratio
        if total_negative_gex != 0.0:
            gex_ratio = total_gex / abs(total_negative_gex)
        else:
            gex_ratio = float("inf") if total_gex > 0 else 0.0

        return {
            "strikes": unique_strikes.tolist(),
            "expiries": unique_expiries.tolist(),
            "gex_surface": gex_surface.tolist(),
            "vex_surface": vex_surface.tolist(),
            "gex_1d": gex_1d.tolist(),
            "total_gex": total_gex,
            "total_negative_gex": total_negative_gex,
            "net_gex": net_gex,
            "max_gex_strike": max_gex_strike,
            "min_gex_strike": min_gex_strike,
            "zero_gamma_levels": zero_gamma_levels,
            "gex_ratio": gex_ratio,
        }

    def find_zero_crossings(
        self, strikes: np.ndarray, gex_1d: np.ndarray
    ) -> List[float]:
        """
        Find strikes where net GEX crosses zero using linear interpolation.

        Parameters
        ----------
        strikes : np.ndarray
            Sorted array of unique strike values (1D).
        gex_1d : np.ndarray
            Net GEX per strike (1D, same length as strikes).

        Returns
        -------
        list of float
            Interpolated strike prices where GEX crosses zero.
        """
        crossings: List[float] = []
        n = len(strikes)
        if n < 2:
            return crossings

        for i in range(n - 1):
            a = gex_1d[i]
            b = gex_1d[i + 1]
            if (a > 0 and b < 0) or (a < 0 and b > 0):
                # Linear interpolation: find x where gex = 0
                # t = a / (a - b)  →  crossing = strikes[i] + t * (strikes[i+1] - strikes[i])
                denom = a - b
                if denom == 0:
                    continue
                t = a / denom
                crossing = float(strikes[i] + t * (strikes[i + 1] - strikes[i]))
                crossings.append(crossing)

        return crossings
