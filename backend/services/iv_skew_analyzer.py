"""
Implied Volatility (IV) Skew Analyzer.

Computes the volatility skew across strikes and expiries:
  - IV Skew = average put IV - average call IV (ATM)
  - Term structure (short-dated vs long-dated skew)
  - Skew percentile ranking vs historical
  - Call/Put IV spread per strike

The skew is a proxy for fear/greed:
  Positive skew (put IV > call IV) = fear / tail-risk hedging
  Negative skew (call IV > put IV)  = greed / speculative call buying

Usage:
    from services.iv_skew_analyzer import IvSkewAnalyzer

    analyzer = IvSkewAnalyzer()
    result = analyzer.analyze(
        call_ivs={"450": 0.16, "455": 0.15},
        put_ivs={"450": 0.18, "455": 0.17},
        spot=450.0,
    )
    logger.info(result.skew_atm)  # 0.02 = put IV 2pts higher
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)
@dataclass
class IvSkewResult:
    """Container for IV skew analysis results.

    Attributes:
        skew_atm: ATM IV skew (put IV - call IV), positive = fear.
        call_iv_atm: Interpolated ATM call IV.
        put_iv_atm: Interpolated ATM put IV.
        call_iv_weighted: Open-interest-weighted average call IV.
        put_iv_weighted: OI-weighted average put IV.
        skew_weighted: OI-weighted skew (put - call).
        term_structure_ratio: Short-dated skew / long-dated skew. >1 means
            near-term fear exceeds longer-term.
        skew_percentile: Percentile rank of current skew vs historical
            (0-100, >80 = extreme fear).
        call_ivs_by_strike: Dict mapping strike -> call IV.
        put_ivs_by_strike: Dict mapping strike -> put IV.
        flags: List of human-readable anomaly flags.
    """
    skew_atm: float = 0.0
    call_iv_atm: float = 0.0
    put_iv_atm: float = 0.0
    call_iv_weighted: float = 0.0
    put_iv_weighted: float = 0.0
    skew_weighted: float = 0.0
    term_structure_ratio: float = 1.0
    skew_percentile: float = 50.0
    call_ivs_by_strike: Dict[str, float] = field(default_factory=dict)
    put_ivs_by_strike: Dict[str, float] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)


class IvSkewAnalyzer:
    """Analyze implied volatility skew from option chain data.

    Args:
        fear_threshold: Skew level above which we flag "fear" (default 0.03 = 3 vol points).
        extreme_fear_threshold: Skew level for "extreme fear" flag (default 0.06).
        history_window: Number of days of skew history to track (default 20).
    """

    def __init__(
        self,
        fear_threshold: float = 0.03,
        extreme_fear_threshold: float = 0.06,
        history_window: int = 20,
    ) -> None:
        self.fear_threshold = fear_threshold
        self.extreme_fear_threshold = extreme_fear_threshold
        self.history_window = history_window
        self._skew_history: List[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        call_ivs: Dict[str, float],
        put_ivs: Dict[str, float],
        spot: float,
        call_oi: Optional[Dict[str, float]] = None,
        put_oi: Optional[Dict[str, float]] = None,
    ) -> IvSkewResult:
        """Run full IV skew analysis.

        Args:
            call_ivs: Dict mapping strike string -> call IV (e.g. {"450": 0.16}).
            put_ivs: Dict mapping strike string -> put IV.
            spot: Current underlying price.
            call_oi: Optional dict of call open interest per strike.
            put_oi: Optional dict of put open interest per strike.

        Returns:
            IvSkewResult with all computed metrics.
        """
        result = IvSkewResult()
        result.call_ivs_by_strike = dict(call_ivs)
        result.put_ivs_by_strike = dict(put_ivs)

        if not call_ivs or not put_ivs:
            result.flags.append("INSUFFICIENT_DATA")
            return result

        # ATM interpolation
        call_iv_atm = self._interpolate_atm(call_ivs, spot)
        put_iv_atm = self._interpolate_atm(put_ivs, spot)
        result.call_iv_atm = call_iv_atm
        result.put_iv_atm = put_iv_atm
        result.skew_atm = put_iv_atm - call_iv_atm

        # OI-weighted IV
        if call_oi:
            result.call_iv_weighted = self._weighted_avg(call_ivs, call_oi)
        else:
            result.call_iv_weighted = float(np.mean(list(call_ivs.values()))) if call_ivs else 0.0
        if put_oi:
            result.put_iv_weighted = self._weighted_avg(put_ivs, put_oi)
        else:
            result.put_iv_weighted = float(np.mean(list(put_ivs.values()))) if put_ivs else 0.0
        result.skew_weighted = result.put_iv_weighted - result.call_iv_weighted

        # Skew percentile vs history
        self._skew_history.append(result.skew_atm)
        if len(self._skew_history) > self.history_window:
            self._skew_history = self._skew_history[-self.history_window:]
        result.skew_percentile = self._compute_percentile(result.skew_atm)

        # Flags
        result.flags = self._generate_flags(result.skew_atm)

        return result

    def analyze_term_structure(
        self,
        short_call_ivs: Dict[str, float],
        short_put_ivs: Dict[str, float],
        long_call_ivs: Dict[str, float],
        long_put_ivs: Dict[str, float],
        spot: float,
    ) -> IvSkewResult:
        """Analyze short-dated vs long-dated skew (term structure).

        Returns result with term_structure_ratio populated.
        """
        short = self.analyze(short_call_ivs, short_put_ivs, spot)
        long = self.analyze(long_call_ivs, long_put_ivs, spot)

        # Combine into single result
        short.term_structure_ratio = (
            short.skew_atm / long.skew_atm if long.skew_atm != 0.0 else 1.0
        )
        return short

    def compute_skew_surface(
        self,
        call_ivs_by_expiry: Dict[str, Dict[str, float]],
        put_ivs_by_expiry: Dict[str, Dict[str, float]],
        spot: float,
    ) -> Dict[str, float]:
        """Compute ATM skew for each expiry (skew surface).

        Args:
            call_ivs_by_expiry: Dict of expiry -> {strike -> IV}.
            put_ivs_by_expiry: Dict of expiry -> {strike -> IV}.
            spot: Current underlying price.

        Returns:
            Dict mapping expiry -> ATM skew.
        """
        surface: Dict[str, float] = {}
        for expiry in call_ivs_by_expiry:
            if expiry in put_ivs_by_expiry:
                call_atm = self._interpolate_atm(call_ivs_by_expiry[expiry], spot)
                put_atm = self._interpolate_atm(put_ivs_by_expiry[expiry], spot)
                surface[expiry] = put_atm - call_atm
        return surface

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _interpolate_atm(ivs: Dict[str, float], spot: float) -> float:
        """Linearly interpolate IV at the ATM strike.

        Finds the two strikes bracketing `spot` and linearly interpolates.
        If spot is outside the range, returns the nearest strike's IV.
        """
        if not ivs:
            return 0.0

        strikes_ivs: List[Tuple[float, float]] = []
        for k_str, iv in ivs.items():
            try:
                k = float(k_str)
                strikes_ivs.append((k, float(iv)))
            except (ValueError, TypeError):
                continue

        if not strikes_ivs:
            return 0.0

        strikes_ivs.sort(key=lambda x: x[0])
        strikes_arr = np.array([s[0] for s in strikes_ivs])
        ivs_arr = np.array([s[1] for s in strikes_ivs])

        # Exact match
        exact = np.where(strikes_arr == spot)[0]
        if len(exact) > 0:
            return float(ivs_arr[exact[0]])

        # Bracketing interpolation
        below = strikes_arr[strikes_arr <= spot]
        above = strikes_arr[strikes_arr >= spot]

        if len(below) == 0:
            return float(ivs_arr[0])  # spot below all strikes
        if len(above) == 0:
            return float(ivs_arr[-1])  # spot above all strikes

        k_low = float(below[-1])
        k_high = float(above[0])
        if k_low == k_high:
            idx = np.where(strikes_arr == k_low)[0][0]
            return float(ivs_arr[idx])

        iv_low = float(ivs_arr[np.where(strikes_arr == k_low)[0][0]])
        iv_high = float(ivs_arr[np.where(strikes_arr == k_high)[0][0]])

        # Linear interpolation
        t = (spot - k_low) / (k_high - k_low)
        return iv_low + t * (iv_high - iv_low)

    @staticmethod
    def _weighted_avg(
        ivs: Dict[str, float], ois: Dict[str, float]
    ) -> float:
        """Compute open-interest-weighted average IV."""
        total_oi = 0.0
        weighted_sum = 0.0
        for k_str, iv in ivs.items():
            try:
                iv_val = float(iv)
            except (ValueError, TypeError):
                continue
            oi_val = 0.0
            if k_str in ois:
                try:
                    oi_val = float(ois[k_str])
                except (ValueError, TypeError):
                    oi_val = 0.0
            weighted_sum += iv_val * oi_val
            total_oi += oi_val
        if total_oi <= 0:
            # Fall back to simple average
            vals = [float(v) for v in ivs.values() if _is_float(v)]
            return float(np.mean(vals)) if vals else 0.0
        return weighted_sum / total_oi

    def _compute_percentile(self, current_skew: float) -> float:
        """Compute percentile rank of current skew vs history.

        Uses (rank - 1) / (n - 1) * 100 for n > 1, so:
          - First observation (n=1) = 50th percentile
          - Highest value (n>1) = 100th percentile
          - Lowest value (n>1) = 0th percentile
        """
        n = len(self._skew_history)
        if n <= 1:
            return 50.0
        hist = np.array(self._skew_history)
        # rank = number of observations strictly below + 0.5 * number equal
        below = int(np.sum(hist < current_skew))
        equal = int(np.sum(hist == current_skew))
        rank = below + 0.5 * equal
        return float(rank / (n - 1) * 100.0)

    def _generate_flags(self, skew: float) -> List[str]:
        """Generate human-readable flags based on skew level."""
        flags: List[str] = []
        if skew >= self.extreme_fear_threshold:
            flags.append("EXTREME_FEAR")
        elif skew >= self.fear_threshold:
            flags.append("FEAR")
        elif skew <= -self.fear_threshold:
            flags.append("GREED")
        return flags

    @property
    def history_size(self) -> int:
        """Number of skew observations in history."""
        return len(self._skew_history)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _is_float(v) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False
