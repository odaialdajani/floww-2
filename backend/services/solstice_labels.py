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
                horizon_s: float, target: float, stop: float,
                max_gap_s: float | None = None) -> dict[str, Any]:
    """First-passage label over (t, price) path. Both-inside-same-bar → unknown order.

    R5-F/R14 contract: the outcome horizon starts at the QUALIFYING ZONE
    ENCOUNTER, not at the first supplied path point — an observation window
    [encounter_t, encounter_t + horizon_s] decides. A target hit before any
    encounter is not a target_hit. Event chronology enforced (only hits
    at/after encounter count). A consecutive observation gap longer than
    max_gap_s (default: horizon_s) censors the label — widely separated
    endpoints cannot prove first-passage order. Paths without a decision and
    without full window coverage are censored indeterminate, never no_touch.

    Returns {label, censored, detail}. Labels: target_hit | stop_hit | no_touch |
    indeterminate | data_gap | simultaneous_unknown.
    """
    lo, hi = zone
    if not path:
        return {"label": "data_gap", "censored": True, "version": LABEL_VERSION,
                "detail": "empty path"}
    t0 = path[0][0]
    for _t, p in path:
        if p is None or not math.isfinite(p):
            return {"label": "data_gap", "censored": True, "version": LABEL_VERSION}
    gap_cap = horizon_s if max_gap_s is None else max_gap_s
    # Same-observation dual-barrier hit blocks fills even without encounter
    # (order unknown — never an assumed win). Preserves the fill canary.
    raw_t = raw_s = None
    for t, p in path:
        if raw_t is None and ((target >= hi and p >= target) or (target <= lo and p <= target)):
            raw_t = t
        if raw_s is None and ((stop >= hi and p >= stop) or (stop <= lo and p <= stop)):
            raw_s = t
    if raw_t is not None and raw_s is not None and raw_t == raw_s:
        return {"label": "simultaneous_unknown", "censored": True, "version": LABEL_VERSION,
                "detail": "both barriers inside same observation; order unknown"}
    # Qualifying encounter: first zone touch anywhere in the supplied path.
    encounter_t = None
    for _t, _p in path:
        if lo <= _p <= hi:
            encounter_t = _t
            break
    duration = path[-1][0] - t0
    if encounter_t is None:
        if duration >= horizon_s:
            return {"label": "no_touch", "censored": False, "version": LABEL_VERSION}
        return {"label": "indeterminate", "censored": True, "version": LABEL_VERSION,
                "detail": "HORIZON_INCOMPLETE_no_encounter"}
    window_end = encounter_t + horizon_s
    # Gap model over the decision window: an unobserved stretch longer than
    # the cap means first passage may have happened unseen.
    for (ta, _), (tb, _) in zip(path, path[1:], strict=False):
        if ta >= encounter_t and ta < window_end and (tb - ta) > gap_cap:
            return {"label": "indeterminate", "censored": True, "version": LABEL_VERSION,
                    "detail": "OBSERVATION_GAP"}
    hit_t = hit_s = None
    for t, p in path:
        if t < encounter_t or t > window_end:
            continue  # chronology + horizon: only post-encounter window counts
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
    if path[-1][0] >= window_end:
        return {"label": "no_touch", "censored": False, "version": LABEL_VERSION}
    return {"label": "indeterminate", "censored": True, "version": LABEL_VERSION,
            "detail": "HORIZON_INCOMPLETE_no_decision"}


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
