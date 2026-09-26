"""
backend/services/wall_interaction.py — observable wall state machine (T07).

R4-05/P04 contract:
- Distinct side vocabulary: `wall_position` (wall below/inside/above spot)
  vs `approach_side` (price arrived from above/below, from history).
  A lower wall approached from above that holds is HOLDING (support);
  an upper wall approached from below that holds is REJECTING (resistance).
  Never reversed.
- Continuous dwell: HOLD needs continuous HOLD_S inside; ACCEPTANCE needs
  continuous ACCEPT_S beyond the SAME boundary. Time-since-testing never
  counts. Side flips and gaps reset the clock (continuity=False).
- Session/feed gaps break continuity (unobserved + continuity_break).

R4-06/P04: states persist by scoped wall ID (ticker + scope + wall_id);
server joins history instead of restarting at unobserved. Scenarios carry
the same scoped wall ID. Selection retention lives in the payload
(first_seen=False when history exists).
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

# Adverse invalidation sides: a confirmed hold (support) is only invalidated
# by sustained acceptance BELOW; a confirmed rejection (resistance) only by
# sustained acceptance ABOVE. Favorable-side excursions never invalidate.
ADVERSE_SIDE = {"holding": "below", "rejecting": "above"}

# Feed-gap policy: no usable observation for this long breaks continuity.
# 900s = 3x the 5-minute structural capture cadence; session-day rollover
# and provider switches always break regardless of elapsed time.
FEED_GAP_S = 900.0

# Scope identity binds expiry dimensions (R5-C/R16): same strikes at a
# different DTE/mode/expiry count are a different analytical scope.
def scope_id_for(ticker: str, scope: dict[str, Any] | None) -> str:
    scope = scope or {}
    return "|".join(str(v) for v in (
        str(ticker or ""), "gex.v2", scope.get("mode", "day"),
        scope.get("dte"), scope.get("scalp", False), scope.get("expiries", 4)))

# Minimal in-memory interaction store keyed by (ticker, scope, wall_id).
# Non-durable by design: P07 hardens to DuckDB wall_events_v1 with restart/
# gap receipts. Callers must mark durable=False when served from here.
INTERACTION_STORE: dict[tuple[str, str, str], dict[str, Any]] = {}


def _key(ticker: str, scope: str, wall_id: str) -> tuple[str, str, str]:
    return (str(ticker or ""), str(scope or ""), str(wall_id or ""))


def save_last(ticker: str, scope: str, wall_id: str, state: dict[str, Any]) -> None:
    if not wall_id:
        return
    INTERACTION_STORE[_key(ticker, scope, wall_id)] = dict(state or {})


def load_last(ticker: str, scope: str, wall_id: str) -> dict[str, Any] | None:
    if not wall_id:
        return None
    got = INTERACTION_STORE.get(_key(ticker, scope, wall_id))
    return dict(got) if got is not None else None


def wall_position(wall: dict[str, Any], spot: float) -> str:
    """Where the wall lies relative to spot (not where price came from)."""
    try:
        lo = float(wall.get("low", 0))
        hi = float(wall.get("high", 0))
        s = float(spot)
    except (TypeError, ValueError):
        return "unknown"
    if lo <= 0 or hi < lo or s <= 0:
        return "unknown"
    if hi <= s:
        return "below"
    if lo >= s:
        return "above"
    return "inside"


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


def _dwell(now_utc: datetime, since_iso: Any, fallback_iso: Any = None) -> float:
    since = _parse_ts(since_iso) or _parse_ts(fallback_iso)
    if since is None:
        return 0.0
    return max(0.0, (now_utc - since).total_seconds())


def transition(current: str, spot: float, wall: dict[str, Any],
               now: datetime | None = None, last: dict | None = None) -> dict[str, Any]:
    """One deterministic transition step. Returns {state, event, evidence}."""
    now_utc = now.astimezone(UTC) if isinstance(now, datetime) else datetime.now(UTC)
    now_iso = now_utc.isoformat()
    lo = float(wall.get("low", 0)) if wall.get("low") is not None else 0.0
    hi = float(wall.get("high", 0)) if wall.get("high") is not None else 0.0
    try:
        lo = float(wall.get("low", 0))
        hi = float(wall.get("high", 0))
        s = float(spot)
    except (TypeError, ValueError):
        return {"state": "unobserved", "event": None, "evidence": {"reason": "INVALID_WALL_OR_SPOT"}}
    if lo <= 0 or hi < lo or s <= 0:
        return {"state": "unobserved", "event": None, "evidence": {"reason": "INVALID_WALL_OR_SPOT"}}
    if (last or {}).get("gap"):
        return {"state": "unobserved", "event": "continuity_break",
                "evidence": {"reason": "SESSION_OR_FEED_GAP"}, "at": now_iso,
                "continuity": False}
    tol = hi * TOUCH_TOL_PCT
    inside = (lo - tol) <= s <= (hi + tol)
    above = s > hi + tol
    below = s < lo - tol
    cur_side = "inside" if inside else ("above" if above else "below")
    wpos = wall_position(wall, s)
    last = dict(last or {})
    last_state = last.get("state", current or "unobserved")
    if last_state not in STATES:
        last_state = "unobserved"
    approach = last.get("approach_side")  # where price came from (history only)
    inside_since = last.get("inside_since")
    beyond_since = last.get("beyond_since")
    beyond_side = last.get("beyond_side")
    adverse_side = last.get("adverse_side")  # side whose acceptance invalidates
    reclaim_state = last.get("reclaim_state")  # hold/reject to resume after favorable excursion

    def _base(state: str, event: Any, evidence: dict[str, Any]) -> dict[str, Any]:
        ev = dict(evidence or {})
        ev.setdefault("spot", s)
        ev.setdefault("zone", [lo, hi])
        ev["wall_position"] = wpos
        if approach is not None:
            ev["approach_side"] = approach
        out = {"state": state, "event": event, "evidence": ev, "at": now_iso,
               "continuity": True, "wall_position": wpos,
               "approach_side": approach, "inside_since": inside_since,
               "beyond_since": beyond_since, "beyond_side": beyond_side,
               "adverse_side": adverse_side, "reclaim_state": reclaim_state}
        return out

    if last_state in ("unobserved",):
        if inside:
            inside_since = now_iso
            out = _base("testing", "first_touch", {"spot": s, "zone": [lo, hi]})
            out["inside_since"] = now_iso
            out["beyond_since"] = None
            out["beyond_side"] = None
            return out
        if abs(s - hi) / hi < 0.01 or abs(s - lo) / lo < 0.01:
            # Price near zone: record which side it sits on as approach context.
            approach = "below" if below or s < lo else "above"
            out = _base("approaching", "approach", {"spot": s, "zone": [lo, hi]})
            out["approach_side"] = approach
            out["evidence"]["approach_side"] = approach
            return out
        return _base("unobserved", None, {"spot": s})
    if last_state == "approaching":
        if inside:
            inside_since = inside_since or now_iso
            out = _base("testing", "touch", {"spot": s})
            out["inside_since"] = inside_since
            out["beyond_since"] = None
            out["beyond_side"] = None
            return out
        # Update approach side from current position while still outside.
        approach = "below" if below or s < lo else "above"
        out = _base("approaching", None, {"spot": s})
        out["approach_side"] = approach
        out["evidence"]["approach_side"] = approach
        return out
    if last_state == "testing":
        if inside:
            dwell = _dwell(now_utc, inside_since, last.get("at"))
            if dwell >= HOLD_S:
                if approach == "above":
                    out = _base("holding", "holding_confirmed",
                                {"spot": s, "held_s": dwell, "dwell_s": dwell})
                    out["inside_since"] = inside_since or last.get("at")
                    return out
                if approach == "below":
                    out = _base("rejecting", "rejecting_confirmed",
                                {"spot": s, "held_s": dwell, "dwell_s": dwell})
                    out["inside_since"] = inside_since or last.get("at")
                    return out
                # Unknown approach: cannot label hold vs reject yet.
                out = _base("testing", None, {"spot": s, "dwell_s": dwell,
                                              "reason": "APPROACH_UNKNOWN"})
                out["inside_since"] = inside_since or last.get("at")
                return out
            out = _base("testing", None, {"spot": s, "dwell_s": dwell})
            out["inside_since"] = inside_since or last.get("at") or now_iso
            out["beyond_since"] = None
            out["beyond_side"] = None
            return out
        # Outside: track continuous beyond dwell on the SAME side.
        if beyond_since and (beyond_side is None or beyond_side == cur_side):
            dwell_b = _dwell(now_utc, beyond_since)
        else:
            beyond_since = now_iso
            beyond_side = cur_side
            dwell_b = 0.0
        if dwell_b >= ACCEPT_S:
            out = _base("accepted_beyond", "acceptance",
                        {"spot": s, "beyond_s": dwell_b, "dwell_s": dwell_b,
                         "beyond_side": cur_side})
            out["beyond_since"] = beyond_since
            out["beyond_side"] = beyond_side
            return out
        # Leaving the zone clears inside dwell (R5-C/R10): a later return
        # restarts the hold clock instead of confirming immediately.
        inside_since = None
        out = _base("retesting", "left_zone", {"spot": s, "dwell_s": dwell_b,
                                               "beyond_side": cur_side})
        out["inside_since"] = None
        out["beyond_since"] = beyond_since
        out["beyond_side"] = beyond_side
        out["adverse_side"] = None
        out["reclaim_state"] = None
        return out
    if last_state in ("holding", "rejecting"):
        adverse = ADVERSE_SIDE[last_state]
        if above or below:
            if cur_side == adverse:
                if beyond_since and (beyond_side is None or beyond_side == cur_side):
                    dwell_b = _dwell(now_utc, beyond_since)
                else:
                    beyond_since = now_iso
                    beyond_side = cur_side
                    dwell_b = 0.0
                if dwell_b >= ACCEPT_S:
                    out = _base("invalidated", "acceptance_beyond",
                                {"spot": s, "dwell_s": dwell_b, "beyond_side": cur_side,
                                 "adverse_side": adverse})
                    out["beyond_since"] = beyond_since
                    out["beyond_side"] = beyond_side
                    return out
                inside_since = None
                out = _base("retesting", "probe_beyond",
                            {"spot": s, "dwell_s": dwell_b,
                             "beyond_side": cur_side, "adverse_side": adverse})
                out["inside_since"] = None
                out["beyond_since"] = beyond_since
                out["beyond_side"] = beyond_side
                out["adverse_side"] = adverse
                out["reclaim_state"] = last_state
                return out
            # Favorable-side excursion: the confirmed hold/rejection stands;
            # no invalidation clock runs on this side.
            out = _base(last_state, None, {"spot": s, "excursion_side": cur_side})
            out["beyond_since"] = None
            out["beyond_side"] = None
            out["adverse_side"] = adverse
            out["reclaim_state"] = None
            return out
        out = _base(last_state, None, {"spot": s})
        out["beyond_since"] = None
        out["beyond_side"] = None
        return out
    if last_state == "accepted_beyond":
        if inside:
            inside_since = now_iso
            out = _base("retesting", "retest", {"spot": s})
            out["inside_since"] = inside_since
            out["beyond_since"] = None
            out["beyond_side"] = None
            return out
        return _base("accepted_beyond", None, {"spot": s})
    if last_state == "retesting":
        if inside:
            if inside_since is None:
                inside_since = now_iso
            dwell = _dwell(now_utc, inside_since, last.get("at"))
            if dwell >= HOLD_S:
                out = _base("holding", "reclaim_hold",
                            {"spot": s, "dwell_s": dwell})
                out["inside_since"] = inside_since
                out["adverse_side"] = None
                out["reclaim_state"] = None
                return out
            out = _base("retesting", None, {"spot": s, "dwell_s": dwell})
            out["inside_since"] = inside_since
            return out
        # Outside while retesting: only the adverse side can invalidate. A
        # favorable-side excursion resumes the pre-probe hold/rejection.
        if adverse_side is not None and cur_side != adverse_side:
            if reclaim_state in ("holding", "rejecting"):
                out = _base(reclaim_state, "excursion_cleared", {"spot": s})
                out["beyond_since"] = None
                out["beyond_side"] = None
                out["adverse_side"] = ADVERSE_SIDE[reclaim_state]
                out["reclaim_state"] = None
                return out
            out = _base("retesting", None, {"spot": s, "dwell_s": 0.0,
                                            "beyond_side": cur_side})
            out["beyond_since"] = None
            out["beyond_side"] = None
            return out
        if beyond_since and (beyond_side is None or beyond_side == cur_side):
            dwell_b = _dwell(now_utc, beyond_since)
        else:
            beyond_since = now_iso
            beyond_side = cur_side
            dwell_b = 0.0
        if dwell_b >= ACCEPT_S:
            out = _base("invalidated", "failed_reclaim",
                        {"spot": s, "dwell_s": dwell_b, "beyond_side": cur_side})
            out["beyond_since"] = beyond_since
            out["beyond_side"] = beyond_side
            return out
        out = _base("retesting", None, {"spot": s, "dwell_s": dwell_b,
                                        "beyond_side": cur_side})
        out["beyond_since"] = beyond_since
        out["beyond_side"] = beyond_side
        return out
    return _base(last_state if last_state in STATES else "unobserved",
                 None, {"spot": s})


def is_newer_state(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """True when stored state a is strictly newer than b (R5-C newest-wins).

    An event-only database row must not override more recent in-memory dwell
    continuity. Unparseable timestamps lose (never treated as newer).
    """
    if a is None:
        return False
    if b is None:
        return True
    ta, tb = _parse_ts(a.get("at")), _parse_ts(b.get("at"))
    if ta is None:
        return False
    if tb is None:
        return True
    return ta > tb


def detect_wall_gap(last: dict[str, Any] | None, now: datetime,
                    data_source: str | None) -> bool:
    """Source-time gap detector (R5-C): session-day rollover, provider switch
    or a feed gap beyond FEED_GAP_S breaks continuity."""
    if not last or last.get("gap"):
        return bool(last and last.get("gap"))
    at = _parse_ts(last.get("at"))
    if at is None:
        return True  # unknown last observation time: continuity unprovable
    now_utc = now.astimezone(UTC) if isinstance(now, datetime) else datetime.now(UTC)
    if at.date() != now_utc.date():
        return True
    if data_source is not None and last.get("data_source") is not None:
        if last.get("data_source") != data_source:
            return True
    return (now_utc - at).total_seconds() > FEED_GAP_S


def scenario_for(wall: dict[str, Any], spot: float,
                 wall_position: str | None = None,
                 wall_id: str | None = None, scope: str = "",
                 side: str | None = None) -> list[dict[str, Any]]:
    """Two-sided conditional paths with trigger + invalidation (never a trade order).

    R4-06/P04: every scenario carries the same scoped wall ID so grid,
    inspector, AI and recorder resolve the same wall. `wall_position`
    is where the wall lies vs spot (below/inside/above); legacy `side`
    is accepted as an alias for backward compat but wall_position wins.
    """
    try:
        lo, hi = float(wall.get("low", 0)), float(wall.get("high", 0))
    except (TypeError, ValueError):
        lo, hi = 0.0, 0.0
    wpos = wall_position or side or "below"
    if wpos not in ("below", "above", "inside"):
        wpos = "below"
    wid = wall_id or wall.get("wall_id")
    if wpos == "above":
        paths = [
            {"name": "Rejection watch",
             "type": "reversal_watch", "zone": [lo, hi],
             "confirmation": f"fail acceptance above {hi}; return and hold below",
             "invalidation": f"sustained acceptance above {hi}"},
            {"name": "Breakout continuation",
             "type": "continuation", "zone": [lo, hi],
             "confirmation": "acceptance beyond zone + follow-through/retest",
             "invalidation": f"reclaim and hold below {hi}"},
        ]
    elif wpos == "inside":
        paths = [
            {"name": "Hold watch",
             "type": "reversal_watch", "zone": [lo, hi],
             "confirmation": f"hold inside [{lo}, {hi}] with continuous dwell",
             "invalidation": f"sustained acceptance beyond [{lo}, {hi}]"},
            {"name": "Acceptance/retest watch",
             "type": "continuation", "zone": [lo, hi],
             "confirmation": "acceptance beyond zone + follow-through/retest",
             "invalidation": f"reclaim and hold inside [{lo}, {hi}]"},
        ]
    else:  # below
        paths = [
            {"name": "Bounce watch",
             "type": "reversal_watch", "zone": [lo, hi],
             "confirmation": f"reclaim and hold above {lo}",
             "invalidation": f"sustained acceptance below {lo}"},
            {"name": "Breakdown continuation",
             "type": "continuation", "zone": [lo, hi],
             "confirmation": "acceptance beyond zone + follow-through/retest",
             "invalidation": f"reclaim and hold above {lo}"},
        ]
    for p in paths:
        p["wall_id"] = wid
        p["wall_position"] = wpos
        p["scope"] = scope
    return paths
