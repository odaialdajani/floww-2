"""
Composite Retail Flow Score.

Combines Call/Put Volume Ratio (CPR), Open Interest Change, and
Implied Volatility Skew into a single -100 to +100 score.

    +100 = Extreme Bullish Flow
       0 = Neutral
    -100 = Extreme Bearish Flow

This score acts as a VPIN-CDF replacement for flow toxicity
when tick-level data is unavailable.

Components:
    1. CPR subscore (weight 40%)  — bullish when >> 1, bearish when << 1
    2. OI Change subscore (weight 30%)  — bullish when call OI grows
    3. IV Skew subscore (weight 30%)  — bullish when put IV >> call IV
       (high put IV = fear) => negative score

Usage:
    from services.retail_flow_score import RetailFlowScore

    scorer = RetailFlowScore()
    score = scorer.compute(cpr=1.5, oi_change_pct=0.12, iv_skew=0.03)
    # score.value -> float in [-100, 100]
"""

from dataclasses import dataclass

import numpy as np

# Component weights (must sum to 1.0)
WEIGHT_CPR = 0.40
WEIGHT_OI = 0.30
WEIGHT_IV_SKEW = 0.30

assert abs(WEIGHT_CPR + WEIGHT_OI + WEIGHT_IV_SKEW - 1.0) < 1e-9


@dataclass
@dataclass
class FlowScoreResult:
    """Result of a composite retail flow score computation."""
    value: float
    cpr_score: float = 0.0
    oi_score: float = 0.0
    iv_skew_score: float = 0.0
    label: str = "Neutral"


def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def compute_cpr_subscore(cpr: float) -> float:
    """Map CPR to a [-100, +100] subscore.

    CPR is typically 0.3–3.0.  We use a log-ratio mapping so that
    CPR=1 maps to 0, CPR=2 maps to ~+50, CPR=3 maps to ~+75, etc.
    Symmetric: CPR=0.5 maps to ~-46.

    Args:
        cpr: Call/Put Volume Ratio (positive finite number).

    Returns:
        Subscore in [-100, +100].
    """
    cpr = _safe_float(cpr, 1.0)
    if cpr <= 0:
        cpr = 1e-6
    # log2 maps: 1->0, 2->1, 0.5->-1, 4->2, 0.25->-2
    log_val = np.log2(cpr)
    # Scale: log2(4)=2 -> +100, log2(0.25)=-2 -> -100
    raw = log_val * 50.0
    return float(_clamp(raw))


def compute_oi_subscore(oi_change_pct: float) -> float:
    """Map OI % change to a [-100, +100] subscore.

    Positive OI change (new positioning) is bullish.
    We use a sigmoid-like mapping: 10% -> ~+50, 25% -> ~+80.

    Args:
        oi_change_pct: Fractional OI change (0.10 = +10%).

    Returns:
        Subscore in [-100, +100].
    """
    pct = _safe_float(oi_change_pct, 0.0)
    # Linear-ish with soft clamp: 0.20 -> 100, -0.20 -> -100
    raw = pct * 500.0
    return float(_clamp(raw))


def compute_iv_skew_subscore(iv_skew: float) -> float:
    """Map IV skew to a [-100, +100] subscore.

    IV skew = avg_put_iv - avg_call_iv (positive = put IV higher = fear).
    Positive skew (fear) => negative score (bearish signal).
    Negative skew (call IV higher) => positive score (bullish/greedy).

    Args:
        iv_skew: Put IV minus Call IV (e.g., 0.02 = put IV 2pts higher).

    Returns:
        Subscore in [-100, +100].
    """
    skew = _safe_float(iv_skew, 0.0)
    # Invert: positive skew (fear) -> negative score
    # 0.05 skew -> -100, -0.05 skew -> +100
    raw = -skew * 2000.0
    return float(_clamp(raw))


class RetailFlowScore:
    """Composite retail flow toxicity score.

    Combines three proxy metrics into a single -100 to +100 score
    that can be used in place of VPIN CDF for trading signals.

    Args:
        weight_cpr: Weight for CPR subscore (default 0.40).
        weight_oi: Weight for OI change subscore (default 0.30).
        weight_iv_skew: Weight for IV skew subscore (default 0.30).
    """

    def __init__(
        self,
        weight_cpr: float = WEIGHT_CPR,
        weight_oi: float = WEIGHT_OI,
        weight_iv_skew: float = WEIGHT_IV_SKEW,
    ) -> None:
        self.w_cpr = weight_cpr
        self.w_oi = weight_oi
        self.w_iv = weight_iv_skew

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        cpr: float,
        oi_change_pct: float,
        iv_skew: float,
    ) -> FlowScoreResult:
        """Compute the composite retail flow score.

        Args:
            cpr: Call/Put Volume Ratio (scalar, today's value).
            oi_change_pct: Fractional OI change (scalar, e.g. 0.12 = +12%).
            iv_skew: Put IV minus Call IV (scalar, e.g. 0.03 = put IV 3pts higher).

        Returns:
            FlowScoreResult with composite value and subscores.
        """
        cpr_sc = compute_cpr_subscore(cpr)
        oi_sc = compute_oi_subscore(oi_change_pct)
        iv_sc = compute_iv_skew_subscore(iv_skew)

        composite = _clamp(
            self.w_cpr * cpr_sc + self.w_oi * oi_sc + self.w_iv * iv_sc
        )

        label = self._label(composite)

        return FlowScoreResult(
            value=composite,
            cpr_score=cpr_sc,
            oi_score=oi_sc,
            iv_skew_score=iv_sc,
            label=label,
        )

    def compute_batch(
        self,
        cprs: np.ndarray,
        oi_changes: np.ndarray,
        iv_skews: np.ndarray,
    ) -> np.ndarray:
        """Vectorized batch computation for multiple expiries.

        Args:
            cprs: 1D array of CPR values.
            oi_changes: 1D array of OI % changes.
            iv_skews: 1D array of IV skew values.

        Returns:
            1D array of composite scores.
        """
        cprs = np.asarray(cprs, dtype=np.float64)
        oi_changes = np.asarray(oi_changes, dtype=np.float64)
        iv_skews = np.asarray(iv_skews, dtype=np.float64)

        cpr_scores = np.log2(np.clip(cprs, 1e-6, None)) * 50.0
        oi_scores = oi_changes * 500.0
        iv_scores = -iv_skews * 2000.0

        composite = (
            self.w_cpr * cpr_scores
            + self.w_oi * oi_scores
            + self.w_iv * iv_scores
        )
        return np.clip(composite, -100.0, 100.0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _label(value: float) -> str:
        if value >= 60:
            return "Extreme Bullish"
        elif value >= 30:
            return "Bullish"
        elif value <= -60:
            return "Extreme Bearish"
        elif value <= -30:
            return "Bearish"
        else:
            return "Neutral"
