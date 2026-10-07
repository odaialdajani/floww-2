"""Fail-closed regular-session policy for background saved-market capture."""
from __future__ import annotations

from datetime import datetime, time

from services.solstice_calendar import ET, exchange_day_info


def capture_market_hours(now) -> bool:
    """True only inside a known regular XNYS session, excluding its close.

    The caller supplies an aware instant. Holidays, weekends, early closes,
    daylight-time changes and unavailable calendar data follow the maintained
    exchange schedule. No feed, account or order operation happens here.
    """
    try:
        if isinstance(now, str):
            current = datetime.fromisoformat(now.replace("Z", "+00:00"))
        elif isinstance(now, datetime):
            current = now
        else:
            return False
        if current.tzinfo is None or current.utcoffset() is None:
            return False
        local = current.astimezone(ET)
        day = local.date().isoformat()
        session = exchange_day_info(day)
        if (not isinstance(session, dict) or session.get("is_open") is not True
                or session.get("date") != day or session.get("reason") is not None):
            return False
        opening = datetime.strptime(session["open_et"], "%H:%M").time()
        closing = datetime.strptime(session["close_et"], "%H:%M").time()
        if opening >= closing:
            return False
        # Capture regular hours only, even if a malformed schedule starts early.
        opening = max(opening, time(9, 30))
        start = datetime.combine(local.date(), opening, tzinfo=ET)
        end = datetime.combine(local.date(), closing, tzinfo=ET)
        return start <= local < end
    except Exception:
        # Missing library, unknown date, malformed hours and calendar errors
        # must stop background capture rather than silently allow it.
        return False
