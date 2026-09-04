"""
backend/services/vpin_toxicity.py

VPIN (Volume-Synchronized Probability of Informed Trading) toxicity detector.

Implements paper #5 in the Blademap bibliography, "Volume-Synchronized
Probability of Informed Trading" by Easley, López de Prado, O'Hara (2013).
Pure-Python only — no torch / numba / scipy (Round-9 freeze rule).

VPIN estimates the probability that the order flow is toxic / informed by
computing the absolute imbalance between buy-side volume and sell-side
volume across N consecutive volume-clock buckets:

    VPIN_N = (1/N) * sum_{i=1..N} |buy_vol_i - sell_vol_i| / (buy_vol_i + sell_vol_i)

The original Easley implementation uses a *tick-driven volume clock*
(BVC) to size each bucket.  We don't have access to per-trade data in the
Flowseeker pipeline, so we substitute a **bulk-volume proxy** at the
chain-snapshot resolution:

    OF_i = |call_vol_i - put_vol_i| / (call_vol_i + put_vol_i)

This is conceptually a low-frequency approximation of the original VPIN —
it correlates with classical VPIN because both measure relative directional
imbalance in the flow, but loses the per-trade timing resolution that the
original captures (caller-supplied ticks would give a sharper toxicity
reading). The docstring is explicit about this trade-off.

Output schema (snake_case for consistency with multi_level_ofi.py
+ hmm_regime.py)::

    {
        "vpin":            float,  # 0..1
        "label":           "LOW_TOXICITY" | "MODERATE_TOXICITY"
                          | "HIGH_TOXICITY" | "EXTREME_TOXICITY",
        "label_color":     "#94a3b8" | "#fbbf24" | "#fb923c" | "#ef4444",
        "n_buckets":       int,    # count of buckets in the rolling window
        "is_warming":      bool,   # True until history_total >= bucket_count,
        "history_total":   int,    # total buckets ever pushed (capped at history),
        "last_bucket_of":  float,  # OF_i of the most recent bucket,
    }

Label thresholds (per Easley 2013 calibration + common practitioner usage):

  * ``VPIN < 0.30``     → LOW_TOXICITY    (sparse informed flow)
  * ``0.30 ≤ VPIN < 0.50`` → MODERATE_TOXICITY
  * ``0.50 ≤ VPIN < 0.70`` → HIGH_TOXICITY
  * ``VPIN ≥ 0.70``     → EXTREME_TOXICITY (informed-dominated)

Usage::

    vpin = VPINToxicity(buckets=20, history=240)
    for chain_snapshot in chains_iter:
        call_vol, put_vol, total_oi = aggregate(chain_snapshot)
        vpin.push_bucket(call_vol, put_vol, call_vol + put_vol, total_oi)
    out = vpin.compute()
"""

from __future__ import annotations

from collections import deque
from typing import Any

LABEL_LOW = "LOW_TOXICITY"
LABEL_MODERATE = "MODERATE_TOXICITY"
LABEL_HIGH = "HIGH_TOXICITY"
LABEL_EXTREME = "EXTREME_TOXICITY"

# Brand colours: slate → amber → orange → red mirrors the existing OFI / HMM
# brand chips in FlowseekerProTab.jsx.
LABEL_COLORS: dict[str, str] = {
    LABEL_LOW:      "#94a3b8",
    LABEL_MODERATE: "#fbbf24",
    LABEL_HIGH:     "#fb923c",
    LABEL_EXTREME:  "#ef4444",
}


def _classify_vpin(vpin: float) -> str:
    """Map a VPIN value to a 4-band label."""
    if vpin < 0.3:
        return LABEL_LOW
    if vpin < 0.5:
        return LABEL_MODERATE
    if vpin < 0.7:
        return LABEL_HIGH
    return LABEL_EXTREME


class VPINToxicity:
    """Pure-Python bulk-volume VPIN over a sliding window of buckets.

    The ``history`` buffer stores the per-bucket OF_i values; the actual
    VPIN statistic uses the LAST ``buckets`` entries only.  Default
    ``history=240`` = 12x the rolling window so the buffer can absorb
    short stalls (failed fetches / paused feeds) without starvating the
    statistic.
    """

    def __init__(self, buckets: int = 20, history: int = 240):
        if buckets < 2:
            raise ValueError("buckets must be >= 2 to compute a meaningful mean")
        if history < buckets:
            raise ValueError("history must be >= buckets")
        self.buckets = int(buckets)
        self.history = int(history)
        self._ofs: deque = deque(maxlen=self.history)

    def push_bucket(
        self,
        call_vol: float,
        put_vol: float,
        total_vol: float,
        total_oi: float,  # noqa: ARG002 — accepted for forward compat
    ) -> None:
        """Append a bucket using the bulk-volume proxy.

        Buckets with ``total_vol <= 0`` are silently skipped — they would
        pollute the rolling window with a fake OF=0 sentinel that doesn't
        represent an actual no-flow state.
        """
        if total_vol is None or total_vol <= 0:
            return
        of_i = abs(call_vol - put_vol) / float(total_vol)
        # Defensive clamp to [0, 1] — should never trip but cheap insurance.
        if of_i < 0.0:
            of_i = 0.0
        elif of_i > 1.0:
            of_i = 1.0
        self._ofs.append(float(of_i))

    def compute(self) -> dict[str, Any]:
        """Return current VPIN dict per the snake_case schema above."""
        n_total = len(self._ofs)
        if n_total < self.buckets:
            return {
                "vpin": 0.0,
                "label": LABEL_LOW,
                "label_color": LABEL_COLORS[LABEL_LOW],
                "n_buckets": n_total,
                "is_warming": True,
                "history_total": n_total,
                "last_bucket_of": (
                    float(round(self._ofs[-1], 4)) if self._ofs else 0.0
                ),
            }
        # Mean of the LAST N buckets.
        recent = list(self._ofs)[-self.buckets:]
        vpin = sum(recent) / float(len(recent))
        if vpin < 0.0:
            vpin = 0.0
        elif vpin > 1.0:
            vpin = 1.0
        # Classify the SAME value we report. Classifying the raw mean while
        # reporting round(mean, 4) let the two disagree at a band edge: ten
        # buckets of OF=0.3 sum to 0.2999999999999999 on some numpy builds and
        # to 0.3 on others, so the payload read {"vpin": 0.3, "label": "LOW"}
        # on one machine and {"vpin": 0.3, "label": "MODERATE"} on another.
        vpin = float(round(vpin, 4))
        label = _classify_vpin(vpin)
        return {
            "vpin": vpin,
            "label": label,
            "label_color": LABEL_COLORS[label],
            "n_buckets": int(len(recent)),
            "is_warming": False,
            "history_total": int(n_total),
            "last_bucket_of": float(round(self._ofs[-1], 4)),
        }


__all__ = [
    "VPINToxicity",
    "LABEL_LOW",
    "LABEL_MODERATE",
    "LABEL_HIGH",
    "LABEL_EXTREME",
    "LABEL_COLORS",
]
