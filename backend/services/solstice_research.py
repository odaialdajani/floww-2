"""
Q1/Q2/Q3 research annex + sizing ablation (T28). Frozen protocols, realistic
observability and costs. Public-only Q3 stays diagnostic. No auto-retuning.

Q1 wall activity/relevance: frozen structural baseline M (share-gamma units)
vs turnover Θ vs comparable activity A (dollar-GEX units) — never mixed units.
Q2 frozen-input regime sensitivity: dDelta/dElapsed vs dGamma/dElapsed vs
d/dRemaining (signs reverse); solver accuracy (a) ≠ realized value (b).
Q3 quote consistency: descriptive discrepancy vs anchored model + uncertainty;
NOT executable profit; needs full tape + sync + hedge latency to graduate.
ABL sizing: paired session/block diffs, frozen policy, unit vs portfolio.
"""

from __future__ import annotations

import math
from typing import Any

VERSION = "research.v1"


def q1_features(struct_units: float, turnover: float | None,
                activity_dollar: float | None) -> dict[str, Any]:
    """Keep M/Θ/A separate with units; thresholds are search candidates, not defaults."""
    return {"M_share_gamma": struct_units, "theta_turnover": turnover,
            "A_dollar_gex": activity_dollar, "version": VERSION,
            "thresholds": {"turnover": [0.8, 1.2], "activity": [0.1],
                           "neighbor": [0.3], "status": "UNVALIDATED_SEARCH_CANDIDATES"}}


def q2_timer(g: float, g_t_elapsed: float | None) -> dict[str, Any]:
    """Local timer −G/G_t defined only when derivative usable and time in domain."""
    if g_t_elapsed is None or g_t_elapsed == 0 or g <= 0:
        return {"timer": None, "reason": "DERIVATIVE_UNUSABLE", "version": VERSION}
    return {"timer": -g / g_t_elapsed, "version": VERSION,
            "note": "solver accuracy (a) is not realized value (b)"}


def q3_discrepancy(observed_mid: float | None, model_mid: float | None,
                   model_unc: float | None, spread: float | None) -> dict[str, Any]:
    """Descriptive quote-model discrepancy + uncertainty. rhat=2r/spread: |rhat|=1 = HALF spread."""
    if observed_mid is None or model_mid is None or spread is None or spread <= 0:
        return {"discrepancy": None, "reason": "INSUFFICIENT_QUOTE", "version": VERSION,
                "execution": "BLOCKED_public_only_diagnostic"}
    r = observed_mid - model_mid
    return {"discrepancy": r, "rhat": 2 * r / spread,
            "rhat_note": "|rhat|=1 means HALF a spread",
            "model_uncertainty": model_unc, "version": VERSION,
            "execution": "BLOCKED_public_only_diagnostic"}


def sizing_ablation(paired_diffs: list[float]) -> dict[str, Any]:
    """Paired session/block differences with effect size + uncertainty (no CI-overlap shortcut)."""
    n = len(paired_diffs)
    if n == 0:
        return {"n": 0, "mean": None, "version": VERSION}
    mean = sum(paired_diffs) / n
    var = sum((d - mean) ** 2 for d in paired_diffs) / max(n - 1, 1)
    return {"n": n, "mean": mean, "sd": math.sqrt(var),
            "version": VERSION, "policy": "frozen_offline_reviewed"}
