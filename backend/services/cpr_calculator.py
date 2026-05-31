"""
Call/Put Volume Ratio (CPR) Calculator.

Computes the ratio of total call volume to total put volume per
expiry, with rolling-average tracking and anomaly flagging.

Interpretation:
    CPR > 2.0  -> Bullish flow (heavy call buying)
    CPR < 0.5  -> Bearish flow (heavy put buying)
    CPR ~ 1.0  -> Neutral

Usage:
    from services.cpr_calculator import CprCalculator

    calc = CprCalculator()
    result = calc.compute(call_volumes, put_volumes, expiries)
    # result = {"cpr": {"2026-07-06": 1.42}, "rolling_avg": {...}, "anomalies": [...]}
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

# Anomaly thresholds
CPR_BULLISH_THRESHOLD = 2.0
CPR_BEARISH_THRESHOLD = 0.5
ROLLING_WINDOW_DAYS = 5


@dataclass
class CprResult:
    """CPR for a single expiry."""
    expiry: str
    cpr: float
    call_volume: float
    put_volume: float
    label: str  # Bullish, Bearish, Neutral


@dataclass
class CprSnapshot:
    """CPR snapshot across expiries with rolling averages and anomalies."""
    current: Dict[str, CprResult] = field(default_factory=dict)
    rolling_avg: Dict[str, float] = field(default_factory=dict)
    anomalies: List[str] = field(default_factory=list)


def _float_or_zero(v) -> float:
    """Safe float conversion; returns 0.0 for NaN/None."""
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class CprCalculator:
    """Call/Put Volume Ratio calculator with rolling-average tracking.

    Maintains an internal deque of the last ``window_days`` CPR dicts
    so that rolling averages can be computed without external storage.

    Args:
        window_days: Rolling window size in trading days (default 5).
    """

    def __init__(self, window_days: int = ROLLING_WINDOW_DAYS) -> None:
        self.window_days = int(window_days)
        self._history: deque = deque(maxlen=window_days)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        call_volumes: Dict[str, float],
        put_volumes: Dict[str, float],
        expiries: Optional[List[str]] = None,
    ) -> CprSnapshot:
        """Compute CPR for each expiry and update rolling history.

        Args:
            call_volumes: Dict mapping expiry -> total call volume.
            put_volumes: Dict mapping expiry -> total put volume.
            expiries: Optional explicit list of expiries. If None,
                      uses the union of keys in call and put dicts.

        Returns:
            CprSnapshot with current values, rolling averages, and
            anomaly flags.
        """
        if expiries is None:
            expiries = sorted(set(list(call_volumes.keys()) + list(put_volumes.keys())))

        today_cpr: Dict[str, CprResult] = {}
        for exp in expiries:
            cv = _float_or_zero(call_volumes.get(exp, 0.0))
            pv = _float_or_zero(put_volumes.get(exp, 0.0))

            if pv == 0.0 and cv == 0.0:
                ratio = 0.0
            elif pv == 0.0:
                ratio = float("inf")
            else:
                ratio = cv / pv

            if ratio == float("inf") or ratio >= CPR_BULLISH_THRESHOLD:
                label = "Bullish"
            elif ratio <= CPR_BEARISH_THRESHOLD:
                label = "Bearish"
            else:
                label = "Neutral"

            today_cpr[exp] = CprResult(
                expiry=exp,
                cpr=ratio,
                call_volume=cv,
                put_volume=pv,
                label=label,
            )

        # Store today's CPR values (only the ratio, for rolling avg)
        self._history.append({exp: today_cpr[exp].cpr for exp in today_cpr})

        # Rolling average
        rolling_avg: Dict[str, float] = {}
        for exp in today_cpr:
            vals = [h[exp] for h in self._history if exp in h]
            if vals:
                filtered = [v for v in vals if v != float("inf")]
                rolling_avg[exp] = float(np.mean(filtered)) if filtered else float("inf")

        # Anomalies
        anomalies: List[str] = []
        for exp, res in today_cpr.items():
            if res.label == "Bullish":
                anomalies.append(f"{exp}: CPR={res.cpr:.2f} (Bullish)")
            elif res.label == "Bearish":
                anomalies.append(f"{exp}: CPR={res.cpr:.2f} (Bearish)")

        return CprSnapshot(
            current=today_cpr,
            rolling_avg=rolling_avg,
            anomalies=anomalies,
        )

    def compute_from_arrays(
        self,
        call_vols: np.ndarray,
        put_vols: np.ndarray,
        expiries: List[str],
    ) -> CprSnapshot:
        """NumPy-array convenience wrapper around :meth:`compute`.

        Args:
            call_vols: 1D array of call volumes per expiry.
            put_vols: 1D array of put volumes per expiry.
            expiries: List of expiry labels (same length as arrays).

        Returns:
            CprSnapshot.
        """
        cv_dict = {exp: float(call_vols[i]) for i, exp in enumerate(expiries)}
        pv_dict = {exp: float(put_vols[i]) for i, exp in enumerate(expiries)}
        return self.compute(cv_dict, pv_dict, expiries)

    @property
    def history_depth(self) -> int:
        """Number of days currently in the rolling buffer."""
        return len(self._history)
