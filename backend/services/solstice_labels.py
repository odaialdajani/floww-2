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
        # R7-07: no_touch requires gap-free coverage. A large observation gap
        # in the pre-encounter prefix censors — we cannot prove no touch
        # happened during the unobserved span, even if duration >= horizon_s.
        for (_ta, _), (_tb, _) in zip(path, path[1:], strict=False):
            if (_tb - _ta) > gap_cap:
                return {"label": "indeterminate", "censored": True,
                        "version": LABEL_VERSION, "detail": "OBSERVATION_GAP"}
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
    """Deterministic pending→complete/censored outcome job (R6-5/B11, R8-05).

    For each decision WITHOUT a recorded outcome, label its price path using
    the episode stored in decision features (zone/target/stop/horizon) and
    record the outcome. Idempotent across restart/catch-up: a decision with
    a TERMINAL (non-censored target_hit/stop_hit) outcome for the same
    (horizon, policy, label version) is skipped and reported separately —
    irrelevant future data cannot rewrite a decided label (labels are
    prefix-stable). Terminal means any NON-CENSORED label for its closed
    window (hit, no-touch, or touch-without-barrier): later points outside
    the window cannot change it, so re-runs skip without rewriting.

    Censored/indeterminate outcomes are INCOMPLETE: they are re-processed
    when a longer path is supplied, replacing the old censored result. A
    re-run with the same (or shorter) path is skipped — no new data.

    Horizons expand: features may carry one horizon or a list (the research
    policy emits all registered horizons). Each horizon closes and stores
    independently; results[did] is the single result for scalar episodes
    and {horizon: result} for lists (backward compatible).

    Fail-closed: a decision WITHOUT a complete episode (zone with high >
    low, finite distinct target/stop, positive horizon) is NEVER labeled —
    missing inputs are not zero (a zero-default zone/target/stop would
    "hit" on any positive price). Such decisions are reported in
    skipped_pending with reason NEED_EPISODE and no outcome row is written.
    Returns {closed, skipped_idempotent, skipped_pending, pending_reasons,
    results}.
    """
    from services.heatmap_history import record_outcome
    closed: list[str] = []
    skipped: list[str] = []
    pending: list[str] = []
    pending_reasons: dict[str, str] = {}
    results: dict[str, Any] = {}

    def _rows(did: str) -> list:
        try:
            return conn.execute(
                "SELECT horizon_s, policy_version, label, censored, detail, label_version "
                "FROM outcome_labels_v1 WHERE decision_id = "
                f"'{str(did).replace(chr(39), chr(39) * 2)}'").fetchall() or []
        except Exception:
            return []

    for did, path in (paths_by_decision or {}).items():
        try:
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
            zone = feat.get("zone")
            try:
                _lo, _hi = float(zone[0]), float(zone[1])
                _tgt, _stp = float(feat.get("target")), float(feat.get("stop"))
            except (TypeError, ValueError, IndexError):
                _lo = _hi = _tgt = _stp = float("nan")
            _raw_hor = feat.get("horizon_s", default_horizon_s)
            _hors = list(_raw_hor) if isinstance(_raw_hor, (list, tuple)) else [_raw_hor]
            _policy = str(feat.get("policy_version") or "legacy")
            if not (math.isfinite(_lo) and math.isfinite(_hi) and _hi > _lo
                    and math.isfinite(_tgt) and math.isfinite(_stp) and _tgt != _stp):
                pending.append(did)
                pending_reasons[did] = "NEED_EPISODE"
                continue
            _valid_hors = []
            for _h in _hors:
                try:
                    _hf = float(_h)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(_hf) and _hf > 0:
                    _valid_hors.append(_hf)
            if not _valid_hors:
                pending.append(did)
                pending_reasons[did] = "NEED_EPISODE"
                continue
            _existing = _rows(did)
            _did_results: dict[str, Any] = {}
            _did_closed = False
            for _hor in _valid_hors:
                _match = None
                for r in _existing:
                    try:
                        _rh = float(r[0])
                    except (TypeError, ValueError):
                        continue
                    if (_rh == _hor and str(r[1] or "legacy") == _policy
                            and str(r[5] or "") == LABEL_VERSION):
                        _match = r
                        break
                if _match is not None:
                    _mlabel, _mcens = str(_match[2]), bool(_match[3])
                    if not _mcens:
                        # Terminal for its closed window (hit, no-touch, or
                        # touch-without-barrier): later points fall outside
                        # the window, so there is nothing to reprocess.
                        continue
                    _old_detail = {}
                    try:
                        import json as _json2
                        _old_detail = _json2.loads(str(_match[4])) if _match[4] else {}
                    except (TypeError, ValueError):
                        pass
                    _old_end = _old_detail.get("path_end_t", 0.0)
                    _new_end = path[-1][0] if path else 0.0
                    if _new_end <= _old_end:
                        continue
                    conn.execute(
                        "DELETE FROM outcome_labels_v1 WHERE decision_id = "
                        f"'{str(did).replace(chr(39), chr(39) * 2)}' AND horizon_s = {_hor} "
                        f"AND COALESCE(policy_version, 'legacy') = '{_policy}'")
                res = label_touch(path or [], (_lo, _hi), _hor, _tgt, _stp)
                _detail = {"detail": res.get("detail"), "version": res.get("version")}
                if path:
                    _detail["path_end_t"] = path[-1][0]
                record_outcome(conn, did, ticker, int(_hor),
                               res["label"], censored=bool(res.get("censored")),
                               detail=_detail, policy_version=_policy)
                _did_results[str(_hor)] = res
                _did_closed = True
            if not _did_results:
                skipped.append(did)
                continue
            if _did_closed and did not in closed:
                closed.append(did)
            if len(_valid_hors) == 1 and not isinstance(_raw_hor, (list, tuple)):
                results[did] = _did_results[str(_valid_hors[0])]
            else:
                results[did] = _did_results
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("close_episodes %s failed: %s", did, e)
            skipped.append(did)
    return {"closed": closed, "skipped_idempotent": skipped,
            "skipped_pending": pending, "pending_reasons": pending_reasons,
            "results": results}


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
