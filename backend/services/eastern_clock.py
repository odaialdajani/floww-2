"""US Eastern clock with a tz-database-free fallback.

Several time gates (live window, trading window, OI prefetch, quiet hours)
depend on the current US Eastern wall clock. Each originally fell back to
`time.localtime().tm_isdst` when the tz database was unavailable, which
reports the HOST machine's timezone, not Eastern's.

Those disagree twice a year, because US and EU DST begin and end on different
dates:

  ~Mar 8-28   the US is on EDT, the EU is not
  ~Oct 25-31  the EU is back on CET, the US is still on EDT

On a non-Eastern host during those windows the fallback applied the wrong
offset and shifted every ET gate by an hour -- enough to open or close a
trading window at the wrong time, or to place a quiet-hours decision on the
wrong side of the boundary.

The fallback here applies the US rule directly (second Sunday in March 07:00
UTC -> first Sunday in November 06:00 UTC), needs no tz data, and produces the
same answer wherever the host is configured.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

__all__ = ["eastern_utc_offset_hours", "eastern_now", "eastern_at"]


def _nth_sunday(year: int, month: int, n: int, tzinfo) -> datetime:
    """The n-th Sunday of a month (n=1 is the first), matching `tzinfo`."""
    first_dow = datetime(year, month, 1).weekday()  # Monday == 0
    day = 1 + (6 - first_dow) % 7 + (n - 1) * 7
    return datetime(year, month, day, tzinfo=tzinfo)


def eastern_utc_offset_hours(utc_dt: datetime) -> int:
    """US Eastern UTC offset in hours for a given UTC instant.

    Negative during Eastern Daylight Time (-4) and Eastern Standard Time (-5).
    """
    tzinfo = utc_dt.tzinfo
    dst_start = _nth_sunday(utc_dt.year, 3, 2, tzinfo).replace(hour=7)
    dst_end = _nth_sunday(utc_dt.year, 11, 1, tzinfo).replace(hour=6)
    return -4 if dst_start <= utc_dt < dst_end else -5


def eastern_at(utc_dt: datetime) -> datetime:
    """Convert a UTC instant to Eastern wall-clock time.

    Prefers the tz database; falls back to the US rule above. Raises if both
    paths fail, so callers can fail closed rather than guess.
    """
    try:
        from zoneinfo import ZoneInfo

        return utc_dt.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return utc_dt + timedelta(hours=eastern_utc_offset_hours(utc_dt))


def eastern_now() -> datetime:
    """Current time in US Eastern. Raises if the clock cannot be determined."""
    return eastern_at(datetime.now(UTC))
