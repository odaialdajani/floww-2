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

    R5-F/R14 + R6-5/B10-B11 contract: the outcome horizon starts at the
    QUALIFYING ZONE ENCOUNTER — the decision window is
    [encounter_t, encounter_t + horizon_s]. Labels are CAUSALLY PREFIX
    STABLE: the scan proceeds forward and the first terminal event decides;
    later points (missing prices, later touches, opposing barrier) can never
    rewrite a decided label. A target hit before any encounter is not a
    target_hit. An observed touch with no barrier hit inside a fully covered
    window is indeterminate (a touch is not a decision), never no_touch.
    A consecutive observation gap longer than max_gap_s (default: horizon_s)
    censors the label — widely separated endpoints cannot prove first
    passage order.

    Returns {label, censored, detail}. Labels: target_hit | stop_hit | no_touch |
    indeterminate | data_gap | simultaneous_unknown.
    """
    lo, hi = zone
    if not path:
        return {"label": "data_gap", "censored": True, "version": LABEL_VERSION,
                "detail": "empty path"}
    gap_cap = horizon_s if max_gap_s is None else max_gap_s
    t0 = path[0][0]

    def _hit(price: float | None) -> tuple[bool, bool]:
        if price is None or not math.isfinite(price):
            return False, False
        _ht = (target >= hi and price >= target) or (target <= lo and price <= target)
        _hs = (stop >= hi and price >= stop) or (stop <= lo and price <= stop)
        return _ht, _hs

    # Phase 1 — encounter search over the arrival prefix. A corrupt point at
    # or before the encounter censors (continuity unprovable); points after
    # the encounter belong to phase 2 and never affect this step.
    encounter_t = None
    for t, p in path:
        if p is None or not math.isfinite(p):
            return {"label": "data_gap", "censored": True, "version": LABEL_VERSION}
        if lo <= p <= hi:
            encounter_t = t
            break
    duration = path[-1][0] - t0
    if encounter_t is None:
        # Same-timestamp dual-barrier contact without any zone encounter:
        # order unknown, never an assumed win (fill canary).
        _rt = _rs = None
        for t, p in path:
            _ht, _hs = _hit(p)
            if _rt is None and _ht:
                _rt = t
            if _rs is None and _hs:
                _rs = t
        if _rt is not None and _rs is not None and _rt == _rs:
            return {"label": "simultaneous_unknown", "censored": True, "version": LABEL_VERSION,
                    "detail": "both barriers inside same observation; order unknown"}
        if duration >= horizon_s:
            return {"label": "no_touch", "censored": False, "version": LABEL_VERSION}
        return {"label": "indeterminate", "censored": True, "version": LABEL_VERSION,
                "detail": "HORIZON_INCOMPLETE_no_encounter"}
    window_end = encounter_t + horizon_s
    # Phase 2 — single forward pass over the path. Gap spans are measured on
    # consecutive observations whenever the earlier point lies inside the
    # window (even if the later point falls beyond its edge). Points sharing
    # one timestamp form a single coarse observation. The first terminal event
    # decides; everything after it is causally irrelevant, so the scan stops.
    _prev: float | None = None
    _i = 0
    _n = len(path)
    while _i < _n:
        _t = path[_i][0]
        if _t < encounter_t:
            _i += 1
            continue
        if _t > window_end:
            break
        _group = []
        while _i < _n and path[_i][0] == _t:
            _group.append(path[_i][1])
            _i += 1
        for _p in _group:
            if _p is None or not math.isfinite(_p):
                return {"label": "data_gap", "censored": True, "version": LABEL_VERSION}
        if _prev is not None and (_t - _prev) > gap_cap:
            return {"label": "indeterminate", "censored": True, "version": LABEL_VERSION,
                    "detail": "OBSERVATION_GAP"}
        _prev = _t
        _hits = [_hit(_p) for _p in _group]
        if any(h for h, _ in _hits) and any(s for _, s in _hits):
            return {"label": "simultaneous_unknown", "censored": True, "version": LABEL_VERSION,
                    "detail": "both barriers inside same observation; order unknown"}
        if any(h for h, _ in _hits):
            return {"label": "target_hit", "censored": False, "version": LABEL_VERSION}
        if any(s for _, s in _hits):
            return {"label": "stop_hit", "censored": False, "version": LABEL_VERSION}
    # A consecutive pair straddling the window edge still censors: first
    # passage may have happened unseen in the unobserved span.
    for (_ta, _), (_tb, _) in zip(path, path[1:], strict=False):
        if _ta >= encounter_t and _ta < window_end and (_tb - _ta) > gap_cap:
            return {"label": "indeterminate", "censored": True, "version": LABEL_VERSION,
                    "detail": "OBSERVATION_GAP"}
    if path[-1][0] >= window_end:
        # Fully covered window. The encounter proves a touch happened, but no
        # barrier was hit: an undecided episode, never no_touch.
        return {"label": "indeterminate", "censored": False, "version": LABEL_VERSION,
                "detail": "TOUCH_NO_BARRIER"}
    return {"label": "indeterminate", "censored": True, "version": LABEL_VERSION,
            "detail": "HORIZON_INCOMPLETE_no_decision"}


def close_episodes(conn, paths_by_decision: dict[str, list],
                   default_horizon_s: float = 300) -> dict[str, Any]:
    """Deterministic pending→complete/censored outcome job (R6-5/B11).

    For each decision WITHOUT a recorded outcome, label its price path using
    the episode stored in decision features (zone/target/stop/horizon) and
    record the outcome. Idempotent across restart/catch-up: decisions that
    already have an outcome row are skipped and reported separately.
    Appending irrelevant future data cannot change an already recorded
    result (labels are prefix-stable; re-runs find the existing row first).
    Returns {closed, skipped_idempotent, results}.
    """
    from services.heatmap_history import record_outcome
    closed: list[str] = []
    skipped: list[str] = []
    results: dict[str, Any] = {}
    for did, path in (paths_by_decision or {}).items():
        try:
            existing = conn.execute(
                "SELECT COUNT(*) FROM outcome_labels_v1 WHERE decision_id = "
                f"'{str(did).replace(chr(39), chr(39) * 2)}'").fetchone()
            if existing and existing[0] > 0:
                skipped.append(did)
                continue
            dec = conn.execute(
                "SELECT ticker, features FROM scenario_decisions_v1 WHERE decision_id = "
                f"'{str(did).replace(chr(39), chr(39) * 2)}'").fetchall()
            if not dec:
                skipped.append(did)
                continue
            import json as _json
            ticker, features = dec[0][0], dec[0][1]
            try:
                feat = _json.loads(features) if isinstance(features, str) else (features or {})
            except (TypeError, ValueError):
                feat = {}
            if not isinstance(feat, dict):
                feat = {}
            zone = feat.get("zone") or [0, 0]
            horizon = feat.get("horizon_s", default_horizon_s)
            res = label_touch(
                path or [], (float(zone[0]), float(zone[1])),
                float(horizon), float(feat.get("target", 0)), float(feat.get("stop", 0)))
            record_outcome(conn, did, ticker, int(horizon),
                           res["label"], censored=bool(res.get("censored")),
                           detail={"detail": res.get("detail"), "version": res.get("version")})
            closed.append(did)
            results[did] = res
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("close_episodes %s failed: %s", did, e)
            skipped.append(did)
    return {"closed": closed, "skipped_idempotent": skipped, "results": results}


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
