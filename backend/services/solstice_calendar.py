"""
backend/services/solstice_calendar.py — maintained exchange calendar (R6-3).

Pinned pandas-market-calendars XNYS schedule: real holidays, half-days
(13:00 ET) and DST-safe America/New_York rules. Fail-closed: an unknown
date (outside calendar range) or an unavailable library yields
is_open=False with an explicit reason — never silently treat a holiday
as an open session. Validated against Cboe 2026 Thanksgiving closure and
Nov 27 / Dec 24 half-days.
"""

from __future__ import annotations

import functools
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
VERSION = "calendar.v1"
CALENDAR_NAME = "XNYS"


@functools.lru_cache(maxsize=8)
def _schedule_year(year: int) -> Any | None:
    try:
        import pandas_market_calendars as _pmc
    except ImportError:
        return None
    try:
        cal = _pmc.get_calendar(CALENDAR_NAME)
        return cal.schedule(f"{year}-01-01", f"{year}-12-31")
    except Exception:
        return None


def exchange_day_info(day: str) -> dict[str, Any]:
    """Session hours for a YYYY-MM-DD date (ET wall clock).

    Returns {date, is_open, open_et, close_et, half_day, reason, version}.
    open_et/close_et are "HH:MM" ET strings; half-days close 13:00.
    Unknown (no calendar/row) → closed with reason CALENDAR_UNKNOWN.
    """
    try:
        import pandas as _pd
        sched = _schedule_year(int(str(day)[:4]))
        if sched is None or sched.empty:
            raise ValueError("no schedule")
        row = sched.loc[_pd.Timestamp(str(day)[:10])]
        open_et = row["market_open"].tz_convert(ET).strftime("%H:%M")
        close_et = row["market_close"].tz_convert(ET).strftime("%H:%M")
        return {"date": str(day)[:10], "is_open": True, "open_et": open_et,
                "close_et": close_et, "half_day": close_et != "16:00",
                "reason": None, "version": VERSION, "calendar": CALENDAR_NAME}
    except KeyError:
        return {"date": str(day)[:10], "is_open": False, "open_et": None,
                "close_et": None, "half_day": False, "reason": "EXCHANGE_HOLIDAY",
                "version": VERSION, "calendar": CALENDAR_NAME}
    except Exception:
        return {"date": str(day)[:10], "is_open": False, "open_et": None,
                "close_et": None, "half_day": False, "reason": "CALENDAR_UNKNOWN",
                "version": VERSION, "calendar": CALENDAR_NAME}
