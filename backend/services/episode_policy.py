"""
backend/services/episode_policy.py — versioned episode policy interface (R7-07).

Research episode policy (research_barriers.v1) and read-only setup-review
policy. Research policy is EXPERIMENTAL — it measures interaction outcomes,
not live trading advice. Setup-review policy is read-only preview.

Both policies freeze source facts at decision/encounter time; they never
invent barriers from future extrema or substitute one ticker's data for
another's.
"""

from __future__ import annotations

import math
from typing import Any

from services.solstice_labels import HORIZONS_S, LABEL_VERSION

POLICY_VERSION = "research_barriers.v1"
SETUP_REVIEW_VERSION = "setup_review.v1"

# Candidate research default: symmetric favorable/adverse excursions around
# the encounter price. zone_half_width is (high - low) / 2 of the zone that
# triggered the encounter. underlying_tick is the verified minimum price
# increment for the underlying (e.g. 0.01 for SPY, 1.0 for some indices).
#
# d = max(zone_half_width, 2 * underlying_tick) ensures barriers are never
# closer than 2 ticks (avoids false barrier hits from noise) and never wider
# than the zone that defined the encounter (avoids extrapolating beyond the
# observed structure).
#
# This is a RESEARCH DEFAULT — callers may override with documented rationale.
# Unknown tick or zone → policy_unavailable, not zero.


def default_barrier_distance(zone_half_width: float | None, underlying_tick: float | None) -> dict[str, Any]:
    """Compute the default symmetric barrier distance d.

    Returns {distance, source, status}. Unknown inputs → unavailable.
    """
    if zone_half_width is None or not math.isfinite(zone_half_width) or zone_half_width <= 0:
        zw = None
    else:
        zw = float(zone_half_width)
    if underlying_tick is None or not math.isfinite(underlying_tick) or underlying_tick <= 0:
        ut = None
    else:
        ut = float(underlying_tick)

    if zw is None and ut is None:
        return {"distance": None, "source": "max(zone_half_width, 2*underlying_tick)",
                "status": "policy_unavailable",
                "reason": "unknown_zone_and_tick"}
    if zw is None:
        return {"distance": 2.0 * ut, "source": "2*underlying_tick (zone unknown)",
                "status": "usable", "reason": None}
    if ut is None:
        return {"distance": zw, "source": "zone_half_width (tick unknown)",
                "status": "usable", "reason": None}

    d = max(zw, 2.0 * ut)
    return {"distance": d, "source": f"max({zw}, 2*{ut})",
            "status": "usable", "reason": None}


def research_default_features(zone: tuple[float, float], encounter_price: float,
                              underlying_tick: float | None = None) -> dict[str, Any]:
    """Build the research-default episode features from a zone encounter.

    Encounter must be a qualifying zone touch (price inside zone).
    Barriers are symmetric around encounter_price at distance d.

    Returns {zone, target, stop, horizon_s, policy_version, experimental,
    barrier_source, status} or {status: policy_unavailable, reason}.
    """
    lo, hi = zone
    if not (math.isfinite(lo) and math.isfinite(hi) and hi > lo):
        return {"status": "policy_unavailable",
                "reason": "invalid_zone",
                "policy_version": POLICY_VERSION}

    hw = (hi - lo) / 2.0
    db = default_barrier_distance(hw, underlying_tick)
    if db["status"] != "usable":
        return {"status": "policy_unavailable",
                "reason": db.get("reason", "unknown_barrier_distance"),
                "policy_version": POLICY_VERSION,
                "zone": [lo, hi],
                "encounter_price": encounter_price}

    d = db["distance"]
    target = encounter_price + d
    stop = encounter_price - d
    # Deduplicate: if target == stop (d == 0), use zone edges as fallback.
    if target == stop:
        target = hi
        stop = lo

    return {
        "zone": [lo, hi],
        "target": target,
        "stop": stop,
        "horizon_s": HORIZONS_S,  # all registered horizons evaluated
        "policy_version": POLICY_VERSION,
        "experimental": True,
        "barrier_source": db["source"],
        "barrier_distance": d,
        "status": "usable",
        "note": "research_default — symmetric excursions around encounter price; "
                "not live trading advice; validate against held-out sessions"
    }


def layout_from_features(features: dict[str, Any]) -> dict[str, Any]:
    """Extract the layout (zone, target, stop, horizon_s) from episode features.

    Validates that the features contain a complete, finite, non-degenerate
    layout. Returns {zone, target, stop, horizon_s, policy_version} or
    {status: NEED_EPISODE, reason} if incomplete.

    This is the gate used by close_episodes (via label_touch) — it mirrors
    the validation in solstice_labels.close_episodes so the policy and the
    job agree on what constitutes a complete episode.
    """
    if not isinstance(features, dict):
        return {"status": "NEED_EPISODE", "reason": "not_a_dict"}

    zone = features.get("zone")
    try:
        _lo, _hi = float(zone[0]), float(zone[1])
        _tgt = float(features.get("target"))
        _stp = float(features.get("stop"))
        _hor = features.get("horizon_s", HORIZONS_S)
        if isinstance(_hor, (int, float)):
            _hor = (_hor,)
        _hor = tuple(float(h) for h in _hor)
    except (TypeError, ValueError, IndexError):
        return {"status": "NEED_EPISODE", "reason": "non_numeric_layout"}

    if not (math.isfinite(_lo) and math.isfinite(_hi) and _hi > _lo
            and math.isfinite(_tgt) and math.isfinite(_stp)
            and _tgt != _stp and all(math.isfinite(h) and h > 0 for h in _hor)):
        return {"status": "NEED_EPISODE", "reason": "degenerate_or_infinite_layout"}

    pv = features.get("policy_version") or LABEL_VERSION
    return {"zone": [_lo, _hi], "target": _tgt, "stop": _stp,
            "horizon_s": _hor, "policy_version": pv, "status": "usable"}


def setup_review_features(zone: tuple[float, float], spot: float,
                          next_zone_above: dict | None = None,
                          next_zone_below: dict | None = None) -> dict[str, Any]:
    """Read-only setup-review policy: report the next loaded structural levels.

    This is NOT a research barrier policy — it does not define target/stop
    for outcome measurement. It reports the structural context a reviewer
    would use to set their own levels.

    Returns {zone, spot, next_above, next_below, policy_version, status}.
    No numeric target is invented; the next zones are descriptive, not
    predictive.
    """
    lo, hi = zone
    return {
        "zone": [lo, hi],
        "spot": spot,
        "next_above": next_zone_above,
        "next_below": next_zone_below,
        "policy_version": SETUP_REVIEW_VERSION,
        "status": "usable",
        "note": "read-only structural preview — no target/stop invented; "
                "reviewer sets their own levels"
    }


def episode_status_from_outcome(label: str, censored: bool) -> dict[str, Any]:
    """Map a label_touch result to an episode lifecycle status.

    Returns {status, label, censored, terminal}.
    - terminal outcomes (target_hit/stop_hit, not censored) → final_observed
    - censored outcomes (any label, censored=True) → pending (can complete)
    - indeterminate/not_censored → pending (open, undecided)
    """
    terminal_labels = ("target_hit", "stop_hit")
    if label in terminal_labels and not censored:
        return {"status": "final_observed", "label": label,
                "censored": False, "terminal": True}
    return {"status": "pending", "label": label,
            "censored": bool(censored), "terminal": False}
