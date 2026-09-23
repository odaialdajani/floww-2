"""
backend/services/solstice_labels.py — outcome labeling + baselines/ablations (T11).

Pre-registered zone-touch horizons (1/3/5/15 min), first-passage labels with
simultaneous-barrier = unknown, walk-forward session splits with purge/embargo,
price-only and raw-wall baselines before added features. Costs + uncertainty.
"""

from __future__ import annotations

import math
from typing import Any

HORIZONS_S = (60, 180, 300, 900)
LABEL_VERSION = "outcome.v1"


def label_touch(path: list[tuple[float, float]], zone: tuple[float, float],
                horizon_s: float, target: float, stop: float) -> dict[str, Any]:
    """First-passage label over (t, price) path. Both-inside-same-bar → unknown order.

    Returns {label, censored, detail}. Labels: target_hit | stop_hit | no_touch |
    indeterminate | data_gap | simultaneous_unknown.
    """
    lo, hi = zone
    t0 = path[0][0] if path else 0
    hit_t = hit_s = None
    for t, p in path:
        if t - t0 > horizon_s:
            break
        if p is None or not math.isfinite(p):
            return {"label": "data_gap", "censored": True, "version": LABEL_VERSION}
        if hit_t is None and ((target >= hi and p >= target) or (target <= lo and p <= target)):
            hit_t = t
        if hit_s is None and ((stop >= hi and p >= stop) or (stop <= lo and p <= stop)):
            hit_s = t
    if hit_t is not None and hit_s is not None and hit_t == hit_s:
        return {"label": "simultaneous_unknown", "censored": True, "version": LABEL_VERSION,
                "detail": "both barriers inside same observation; order unknown"}
    if hit_t is not None and (hit_s is None or hit_t < hit_s):
        return {"label": "target_hit", "censored": False, "version": LABEL_VERSION}
    if hit_s is not None:
        return {"label": "stop_hit", "censored": False, "version": LABEL_VERSION}
    touched = any(lo <= p <= hi for _, p in path if p is not None)
    return {"label": "no_touch" if not touched else "indeterminate",
            "censored": False, "version": LABEL_VERSION}


def walk_forward_splits(sessions: list[str], n_folds: int = 3, embargo: int = 1) -> list[dict]:
    """Session-block splits with embargo; never split rows within a day."""
    n = len(sessions)
    folds = []
    size = max(1, n // (n_folds + 1))
    for i in range(n_folds):
        tr_end = (i + 1) * size
        te_start = tr_end + embargo
        te_end = te_start + size
        folds.append({"train": sessions[:tr_end], "test": sessions[te_start:te_end]})
    return folds


BASELINES = ("price_only_reclaim", "raw_wall_plus_confirmation", "plus_delta",
             "plus_window_activity", "plus_flow_proxy", "plus_classified_flow",
             "plus_vanna_charm_context")
