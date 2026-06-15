"""
Open Interest Change Detector.

Compares today's open interest (OI) against yesterday's for each
strike, computes percent change, and flags significant moves as
"New Positioning."

A change > 10% (absolute) is considered significant — this catches
both large new positions (increase) and large unwinds (decrease).

Usage:
    from services.oi_needle_detector import OiChangeDetector

    detector = OiChangeDetector()
    result = detector.detect(current_oi, previous_oi, strikes)
    # result = {"2026-07-06": {"strike": 450.0, "pct_change": 0.15, "flag": "New Positioning"}}
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np

# Significant change threshold (absolute %)
OI_CHANGE_THRESHOLD = 0.10  # 10%


@dataclass
class OiStrikeChange:
    """OI change for a single strike."""
    strike: float
    expiry: str
    current_oi: float
    previous_oi: float
    pct_change: float
    flag: str = ""


@dataclass
class OiChangeSnapshot:
    """Snapshot of OI changes across all strikes for one expiry."""
    changes: Dict[float, OiStrikeChange] = field(default_factory=dict)
    significant: List[float] = field(default_factory=list)
    max_increase: float = 0.0
    max_decrease: float = 0.0


@dataclass
class OiChangeDetector:
    """Detect significant day-over-day Open Interest changes.

    Args:
        threshold: Absolute % change to flag (default 0.10 = 10%).
    """

    def __init__(self, threshold: float = OI_CHANGE_THRESHOLD) -> None:
        self.threshold = float(threshold)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        current_oi: Dict[float, float],
        previous_oi: Dict[float, float],
        expiry: str,
    ) -> OiChangeSnapshot:
        """Compare current OI vs previous-day OI for one expiry.

        Args:
            current_oi: Dict mapping strike -> current open interest.
            previous_oi: Dict mapping strike -> prior-day open interest.
            expiry: Expiry date label.

        Returns:
            OiChangeSnapshot.
        """
        all_strikes = sorted(set(list(current_oi.keys()) + list(previous_oi.keys())))

        changes: Dict[float, OiStrikeChange] = {}
        significant: List[float] = []
        max_inc = 0.0
        max_dec = 0.0

        for K in all_strikes:
            cur = _safe_float(current_oi.get(K, 0.0))
            prev = _safe_float(previous_oi.get(K, 0.0))

            if prev == 0.0 and cur == 0.0:
                pct = 0.0
            elif prev == 0.0:
                pct = float("inf")  # brand new positioning
            else:
                pct = (cur - prev) / prev

            flag = "New Positioning" if _abs_pct(pct) > self.threshold else ""

            changes[K] = OiStrikeChange(
                strike=K,
                expiry=expiry,
                current_oi=cur,
                previous_oi=prev,
                pct_change=pct,
                flag=flag,
            )

            if flag:
                significant.append(K)
                if pct > 0:
                    max_inc = max(max_inc, pct)
                else:
                    max_dec = min(max_dec, pct)

        return OiChangeSnapshot(
            changes=changes,
            significant=significant,
            max_increase=max_inc,
            max_decrease=max_dec,
        )

    def detect_from_arrays(
        self,
        current_oi: np.ndarray,
        previous_oi: np.ndarray,
        strikes: np.ndarray,
        expiry: str,
    ) -> OiChangeSnapshot:
        """NumPy-array convenience wrapper.

        Args:
            current_oi: 1D array of current OI per strike.
            previous_oi: 1D array of prior-day OI per strike.
            strikes: 1D array of strike prices.
            expiry: Expiry date label.

        Returns:
            OiChangeSnapshot.
        """
        cur_dict = {float(strikes[i]): float(current_oi[i]) for i in range(len(strikes))}
        prev_dict = {float(strikes[i]): float(previous_oi[i]) for i in range(len(strikes))}
        return self.detect(cur_dict, prev_dict, expiry)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _safe_float(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        f = float(v)
        return 0.0 if math.isnan(f) else f
    except (TypeError, ValueError):
        return 0.0


def _abs_pct(pct: float) -> float:
    """Return absolute value, handling inf."""
    if pct == float("inf") or pct == float("-inf"):
        return float("inf")
    return abs(pct)
