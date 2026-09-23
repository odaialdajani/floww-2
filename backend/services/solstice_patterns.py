"""
backend/services/solstice_patterns.py — numeric pattern library (T16).

Five heatmap patterns + distant-node relevance. Time-causal candidate →
confirmation → invalidation records with definition versions and
complete-coverage guards. Failures retained. No dealer-intent labels.
"""

from __future__ import annotations

import math
from typing import Any

VERSION = "patterns.v1"


def _coverage_ok(strike_rows: list[dict], spot: float, window_pct: float = 0.05) -> tuple[bool, str | None]:
    rows = [r for r in (strike_rows or []) if r.get("strike")]
    if len(rows) < 5:
        return False, "INSUFFICIENT_COVERAGE"
    near = [r for r in rows if abs(float(r["strike"]) - spot) / spot <= window_pct]
    if len(near) < 3:
        return False, "INCOMPLETE_WINDOW"
    return True, None


def _gross(r: dict) -> float:
    try:
        return abs(float(r.get("call_gex", 0) or 0)) + abs(float(r.get("put_gex", 0) or 0)) or abs(float(r.get("gex", 0) or 0))
    except (TypeError, ValueError):
        return 0.0


def detect_patterns_v1(strike_rows: list[dict], spot: float, walls: list[dict] | None = None) -> list[dict[str, Any]]:
    """Return ranked compatible pattern records (small set, separate evidence)."""
    out: list[dict[str, Any]] = []
    ok, reason = _coverage_ok(strike_rows, spot)
    if not ok:
        return [{"pattern_id": "insufficient_data", "pattern_version": VERSION,
                 "state": "INSUFFICIENT_DATA", "reason": reason, "evidence_ids": []}]
    rows = sorted(strike_rows, key=lambda r: float(r["strike"]))
    grosses = [_gross(r) for r in rows]
    total = sum(grosses) or 1.0
    top = max(grosses)
    # Mixed structure (rainbow road): dispersed, weak dominant route.
    if top / total < 0.15:
        out.append({"pattern_id": "mixed_structure", "pattern_version": VERSION,
                    "state": "CANDIDATE", "observed_features": {"top_share": round(top / total, 4)},
                    "evidence_ids": [], "contradictions": [],
                    "trigger_rule_id": "overlap_swings_then_chop",
                    "invalidation_rule_id": "persistent_route_and_acceptance"})
    # Range structure (whipsaw): strong bounding walls + thin interior.
    walls = walls or []
    above = [w for w in walls if float(w.get("mid", spot)) > spot]
    below = [w for w in walls if float(w.get("mid", spot)) < spot]
    if above and below:
        lo = max(below, key=lambda w: w.get("gross", 0))
        hi = max(above, key=lambda w: w.get("gross", 0))
        interior = [g for r, g in zip(rows, grosses)
                    if float(lo.get("high", lo.get("mid"))) < float(r["strike"]) < float(hi.get("low", hi.get("mid")))]
        if interior and (sum(interior) / total) < 0.25:
            out.append({"pattern_id": "range_structure", "pattern_version": VERSION,
                        "state": "CANDIDATE",
                        "observed_features": {"lower": [lo.get("low"), lo.get("high")],
                                              "upper": [hi.get("low"), hi.get("high")]},
                        "evidence_ids": [], "contradictions": [],
                        "trigger_rule_id": "repeated_bounded_traversal",
                        "invalidation_rule_id": "sustained_acceptance_outside"})
    # Intermediate wall (gatekeeper): significant wall between spot and destination.
    dest = max(rows, key=lambda r: _gross(r))
    d_strike = float(dest["strike"])
    between = [w for w in walls
               if min(spot, d_strike) < float(w.get("mid", 0)) < max(spot, d_strike)]
    if between:
        gk = max(between, key=lambda w: w.get("gross", 0))
        out.append({"pattern_id": "intermediate_wall", "pattern_version": VERSION,
                    "state": "CANDIDATE",
                    "observed_features": {"wall": [gk.get("low"), gk.get("high")], "destination": d_strike},
                    "evidence_ids": [], "contradictions": [],
                    "trigger_rule_id": "near_wall_rejection_or_acceptance",
                    "invalidation_rule_id": "none_presence_alone_predicts_nothing"})
    # Directional progression (trend): persistent side concentration + migration.
    side_gross_above = sum(g for r, g in zip(rows, grosses) if float(r["strike"]) > spot)
    side_gross_below = total - side_gross_above
    if max(side_gross_above, side_gross_below) / total > 0.65:
        out.append({"pattern_id": "directional_progression", "pattern_version": VERSION,
                    "state": "CANDIDATE",
                    "observed_features": {"dominant_side": "above" if side_gross_above > side_gross_below else "below"},
                    "evidence_ids": [], "contradictions": [],
                    "trigger_rule_id": "progression_pullback_hold_or_retest",
                    "invalidation_rule_id": "failed_progression_reclaim"})
    # Downside continuation watch (rug): overhead obstruction + thin lower corridor.
    if side_gross_above / total > 0.55:
        lower = sorted([w for w in below], key=lambda w: float(w.get("mid", 0)))
        if lower:
            nearest = lower[-1]
            corridor = [g for r, g in zip(rows, grosses)
                        if float(nearest.get("low", 0)) - (spot * 0.02) <= float(r["strike"]) <= float(nearest.get("high", 0))]
            if corridor and sum(corridor) / total < 0.15:
                out.append({"pattern_id": "downside_continuation_watch", "pattern_version": VERSION,
                            "state": "CANDIDATE",
                            "observed_features": {"overhead_gross_share": round(side_gross_above / total, 3)},
                            "evidence_ids": [], "contradictions": [],
                            "trigger_rule_id": "rejection_support_loss_failed_reclaim",
                            "invalidation_rule_id": "reclaim_acceptance_above"})
    return out


def distant_node_relevance(node_strike: float, spot: float, walls: list[dict],
                           sigma: float | None = None, horizon: str = "") -> dict[str, Any]:
    """Flag limited near-term relevance of remote/isolated concentrations.

    Never infers manipulation or 'proven decoy'. Standardized distance requires
    an explicit volatility/horizon input — otherwise invented sigma distances
    are invalid (T27 fixture).
    """
    dist = abs(node_strike - spot)
    intervening = sum(1 for w in (walls or [])
                     if min(spot, node_strike) < float(w.get("mid", 0)) < max(spot, node_strike))
    rec: dict[str, Any] = {"strike": node_strike, "distance": dist,
                           "intervening_walls": intervening,
                           "relevance": "limited" if (dist / max(spot, 1) > 0.05 or intervening > 0) else "near",
                           "version": VERSION}
    if sigma is not None and sigma > 0:
        rec["z"] = dist / (spot * sigma)
        rec["horizon"] = horizon
    else:
        rec["z"] = None
        rec["z_reason"] = "NO_VOL_HORIZON_INPUT"
    return rec
