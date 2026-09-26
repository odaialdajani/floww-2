"""
backend/services/solstice_session.py — 0DTE session/permission/playbook orchestration (T19).

Entry/management/data-quality permissions are separate. Blocking new entries
never abandons positions. Reason codes with severity + recovery.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
VERSION = "session.v1"

REASONS = ("WARMUP_INCOMPLETE", "MODEL_SIGN_UNSTABLE", "PARTIAL_CHAIN",
           "PRICE_NOT_CONFIRMED", "MID_RANGE_LOCATION", "PATTERN_CONFLICT",
           "EVENT_CONTEXT_UNAVAILABLE", "COST_EXCEEDS_POLICY", "NO_ELIGIBLE_SIDE",
           "RISK_BUDGET_EXHAUSTED", "ACCOUNT_STATE_STALE", "SERIES_CUTOFF_UNKNOWN",
           "ORDER_STATE_UNKNOWN", "PROTECTION_UNCONFIRMED", "RECONCILIATION_REQUIRED",
           "NO_0DTE_LISTING", "STALE_BID", "STALE_ASK", "LATE_SESSION_CUTOFF",
           "MARKET_CLOSED", "QUALITY_UNKNOWN", "EXCHANGE_HOLIDAY", "CALENDAR_UNKNOWN")

# Versioned late-session policy: no new entries within 30 min of 16:00 ET.
LATE_CUTOFF_MIN = 30


def session_state(now: datetime | None = None, quality: dict | None = None,
                  positions_open: bool = False) -> dict[str, Any]:
    """Return entry/management/data permissions + reasons + recovery.

    R6-3: maintained XNYS calendar drives open/close (holidays closed,
    half-days 13:00 ET, DST-safe). Unknown calendar fails closed
    (CALENDAR_UNKNOWN). 16:00 ET remains the regular-session default only
    when the calendar is unreachable — and then entry is blocked anyway.
    Series last-trade vs settlement (AM/PM) stay series-metadata owned
    (solstice_time.last_trading_utc). Blocking entries never abandons
    positions.
    """
    now_utc = now.astimezone(UTC) if isinstance(now, datetime) else datetime.now(UTC)
    et = now_utc.astimezone(ET)
    reasons: list[str] = []
    cal_hint = "regular 16:00 ET close"
    if et.weekday() >= 5:
        reasons.append("MARKET_CLOSED")
        close = et.replace(hour=16, minute=0, second=0, microsecond=0)
        market_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
    else:
        from services.solstice_calendar import exchange_day_info
        day = exchange_day_info(et.date().isoformat())
        if not day["is_open"]:
            reasons.append(day["reason"] or "MARKET_CLOSED")
            cal_hint = f"{day.get('calendar', 'XNYS')} {day['date']} closed ({day['reason']})"
            close = et.replace(hour=16, minute=0, second=0, microsecond=0)
            market_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
        else:
            try:
                _oh, _om = (int(x) for x in day["open_et"].split(":"))
                _ch, _cm = (int(x) for x in day["close_et"].split(":"))
            except (TypeError, ValueError, AttributeError):
                reasons.append("CALENDAR_UNKNOWN")
                close = et.replace(hour=16, minute=0, second=0, microsecond=0)
                market_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
            else:
                market_open = et.replace(hour=_oh, minute=_om, second=0, microsecond=0)
                close = et.replace(hour=_ch, minute=_cm, second=0, microsecond=0)
                cal_hint = (f"{day.get('calendar', 'XNYS')} {day['date']} "
                            f"{day['open_et']}-{day['close_et']} ET"
                            f"{' (half day)' if day['half_day'] else ''}")
    if not reasons and et < market_open:
        # Pre-open: last trading time has not arrived today.
        reasons.append("MARKET_CLOSED")
    mins_left = (close - et).total_seconds() / 60.0
    if mins_left < 0:
        reasons.append("SERIES_CUTOFF_UNKNOWN")
    elif mins_left < LATE_CUTOFF_MIN:
        reasons.append("LATE_SESSION_CUTOFF")
    q = quality or {}
    qstate = q.get("state", "unknown")
    if qstate not in ("usable", "partial"):
        reasons.append("QUALITY_UNKNOWN")
    if not q.get("setupEligible", q.get("setup_eligible", True)):
        # Data says no setup is eligible: session permission agrees (entry
        # blocked, management never abandoned).
        reasons.append("NO_ELIGIBLE_SIDE")
    reasons.extend([r for r in q.get("reasonCodes", []) if r in REASONS])
    if "EVENT_CONTEXT_UNAVAILABLE" in reasons:
        # Configured dependency policy: optional context missing blocks only
        # strategies that declare the dependency (handled by caller).
        pass
    entry_allowed = not reasons
    return {
        "version": VERSION,
        "minutes_to_close": round(mins_left, 1),
        "entry_allowed": entry_allowed,
        "management_allowed": True,  # blocking entries never abandons positions
        "data_state": q.get("state", "unknown"),
        "reasons": reasons,
        "positions_open": positions_open,
        "recovery": {r: "re-evaluate on material state change" for r in reasons},
        "note": "entry block does not stop monitoring or position management",
        "calendar": cal_hint,
    }


def playbook_for(wall: dict | None, spot: float, quality: dict | None) -> dict[str, Any]:
    """Select wall rejection/reclaim vs break-retest vs range vs no-setup."""
    if not wall or (quality or {}).get("state") in ("stale", "unavailable"):
        return {"playbook": "no_setup", "reason": "INSUFFICIENT_EVIDENCE"}
    lo, hi = float(wall.get("low", 0)), float(wall.get("high", 0))
    if lo <= spot <= hi:
        return {"playbook": "range_edge_rotation",
                "trigger": "edge hold with usable net payoff",
                "invalidation": "range break"}
    if spot < lo:
        return {"playbook": "wall_rejection_reclaim",
                "trigger": "causal rejection or reclaim after test",
                "invalidation": f"acceptance above {hi}"}
    return {"playbook": "wall_rejection_reclaim",
            "trigger": "causal rejection or reclaim after test",
            "invalidation": f"acceptance below {lo}"}
