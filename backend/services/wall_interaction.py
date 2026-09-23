"""
backend/services/wall_interaction.py — observable wall state machine (T07).

unobserved → approaching → testing → holding/rejecting/accepted_beyond →
retesting/invalidated/expired. Debounced by elapsed time + price thresholds,
never poll counts. Session/feed gaps break continuity (continuity=False).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

STATES = ("unobserved", "approaching", "testing", "holding", "rejecting",
          "accepted_beyond", "retesting", "invalidated", "expired")

# Versioned time/zone thresholds (research config, not financial truths).
TOUCH_TOL_PCT = 0.001       # within 0.1% of zone edge = touch
HOLD_S = 60                 # hold at/inside zone for 60s
ACCEPT_S = 120              # acceptance beyond boundary for 120s
RETEST_TOL_PCT = 0.002


def _parse_ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    try:
        s = str(v)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def transition(current: str, spot: float, wall: dict[str, Any],
               now: datetime | None = None, last: dict | None = None) -> dict[str, Any]:
    """One deterministic transition step. Returns {state, event, evidence}."""
    now_utc = now.astimezone(UTC) if isinstance(now, datetime) else datetime.now(UTC)
    lo = float(wall.get("low", 0))
    hi = float(wall.get("high", 0))
    if lo <= 0 or hi < lo or spot <= 0:
        return {"state": "unobserved", "event": None, "evidence": {"reason": "INVALID_WALL_OR_SPOT"}}
    if (last or {}).get("gap"):
        return {"state": "unobserved", "event": "continuity_break",
                "evidence": {"reason": "SESSION_OR_FEED_GAP"}, "at": now_utc.isoformat()}
    tol = hi * TOUCH_TOL_PCT
    inside = (lo - tol) <= spot <= (hi + tol)
    above = spot > hi + tol
    below = spot < lo - tol
    last_state = (last or {}).get("state", current or "unobserved")
    last_at = _parse_ts((last or {}).get("at"))
    elapsed = (now_utc - last_at).total_seconds() if last_at else 0.0

    if last_state in ("unobserved",):
        if inside:
            return {"state": "testing", "event": "first_touch",
                    "evidence": {"spot": spot, "zone": [lo, hi]}, "at": now_utc.isoformat()}
        if abs(spot - hi) / hi < 0.01 or abs(spot - lo) / lo < 0.01:
            return {"state": "approaching", "event": "approach",
                    "evidence": {"spot": spot, "zone": [lo, hi]}, "at": now_utc.isoformat()}
        return {"state": "unobserved", "event": None, "evidence": {"spot": spot}}
    if last_state == "approaching":
        if inside:
            return {"state": "testing", "event": "touch", "evidence": {"spot": spot},
                    "at": now_utc.isoformat()}
        return {"state": "approaching", "event": None, "evidence": {"spot": spot}}
    if last_state == "testing":
        if inside and elapsed >= HOLD_S:
            side = (last or {}).get("approach_side", "above" if spot >= (lo + hi) / 2 else "below")
            held = "holding" if side == "below" else "rejecting"
            # holding = lower wall supports (approached from above); rejecting = upper resists
            return {"state": held, "event": f"{held}_confirmed",
                    "evidence": {"spot": spot, "held_s": elapsed}, "at": now_utc.isoformat()}
        if (above or below) and elapsed >= ACCEPT_S:
            return {"state": "accepted_beyond", "event": "acceptance",
                    "evidence": {"spot": spot, "beyond_s": elapsed}, "at": now_utc.isoformat()}
        if inside:
            return {"state": "testing", "event": None, "evidence": {"spot": spot}}
        return {"state": "retesting", "event": "left_zone",
                "evidence": {"spot": spot}, "at": now_utc.isoformat()}
    if last_state in ("holding", "rejecting"):
        if (above and lo < hi <= spot) or (below and spot <= lo):
            # Acceptance beyond the held boundary invalidates the hold.
            if elapsed >= ACCEPT_S:
                return {"state": "invalidated", "event": "acceptance_beyond",
                        "evidence": {"spot": spot}, "at": now_utc.isoformat()}
            return {"state": "retesting", "event": "probe_beyond",
                    "evidence": {"spot": spot}, "at": now_utc.isoformat()}
        return {"state": last_state, "event": None, "evidence": {"spot": spot}}
    if last_state == "accepted_beyond":
        if inside:
            return {"state": "retesting", "event": "retest",
                    "evidence": {"spot": spot}, "at": now_utc.isoformat()}
        return {"state": "accepted_beyond", "event": None, "evidence": {"spot": spot}}
    if last_state == "retesting":
        if inside and elapsed >= HOLD_S:
            return {"state": "holding", "event": "reclaim_hold",
                    "evidence": {"spot": spot}, "at": now_utc.isoformat()}
        if (above or below) and elapsed >= ACCEPT_S:
            return {"state": "invalidated", "event": "failed_reclaim",
                    "evidence": {"spot": spot}, "at": now_utc.isoformat()}
        return {"state": "retesting", "event": None, "evidence": {"spot": spot}}
    return {"state": last_state if last_state in STATES else "unobserved",
            "event": None, "evidence": {"spot": spot}}


def scenario_for(wall: dict[str, Any], spot: float, side: str = "below") -> list[dict[str, Any]]:
    """Two-sided conditional paths with trigger + invalidation (never a trade order)."""
    lo, hi = float(wall.get("low", 0)), float(wall.get("high", 0))
    return [
        {"name": "Bounce watch" if side == "below" else "Rejection watch",
         "type": "reversal_watch", "zone": [lo, hi],
         "confirmation": f"reclaim and hold {'above ' + str(lo) if side == 'below' else 'below ' + str(hi)}",
         "invalidation": f"sustained acceptance {'below ' + str(lo) if side == 'below' else 'above ' + str(hi)}"},
        {"name": "Breakdown continuation" if side == "below" else "Breakout continuation",
         "type": "continuation", "zone": [lo, hi],
         "confirmation": "acceptance beyond zone + follow-through/retest",
         "invalidation": f"reclaim and hold {'above ' + str(lo) if side == 'below' else 'below ' + str(hi)}"},
    ]
