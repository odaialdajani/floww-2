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

__all__ = [
    "eastern_utc_offset_hours", "eastern_now", "eastern_at", "eastern_at_safe",
    "eastern_now_safe", "eastern_at_safe_provenance", "US_DST_RULE_VALID_FROM",
    "US_DST_RULE_VALID_UNTIL",
]

# Validity window of the tz-database-free rule below. US DST was redefined by
# the Energy Policy Act of 2005: from 2007 DST starts on the SECOND Sunday in
# March (not the first Sunday in April). Before 2007 the rule's boundaries are
# wrong by up to an hour, which is measured, not theoretical:
#   2003-04-05  rule says 13:00 -04:00, reality is 12:00 -05:00
#   2006-04-01  rule says 13:00 -04:00, reality is 12:00 -05:00
# So the fallback refuses to answer for those instants rather than returning
# a confident wrong hour. Current time is always inside the window.
US_DST_RULE_VALID_FROM = 2007
# Upper bound is open-ended: no announced change, but the value is declared so
# a future rule change has an obvious place to break the fallback.
US_DST_RULE_VALID_UNTIL = None


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


def eastern_at_safe_provenance(utc_dt: datetime) -> tuple[datetime, dict]:
    """Aware Eastern conversion plus HOW it was derived (S5/R10-11).

    Returns (aware_datetime, provenance). provenance["source"] is
    "tzdata" when the database answered, or "us_dst_rule" when the
    tz-database-free rule did. The rule path is only valid for
    US_DST_RULE_VALID_FROM .. US_DST_RULE_VALID_UNTIL; outside that window
    it RAISES rather than returning a wrong hour by up to 60 minutes.
    """
    from datetime import timezone as _tz

    if utc_dt.tzinfo is None:
        raise ValueError("eastern_at_safe requires a timezone-aware UTC instant")
    try:
        from zoneinfo import ZoneInfo

        got = utc_dt.astimezone(ZoneInfo("America/New_York"))
        return got, {"source": "tzdata", "offset_hours": eastern_utc_offset_hours(utc_dt),
                     "rule_valid": True,
                     "note": "tz database answered; the DST-rule fallback was not used"}
    except Exception as exc:
        # Distinguish "no tz database" from any other failure. A broken
        # ZoneInfo must not be silently downgraded to a rule guess.
        # ImportError (not just ModuleNotFoundError) is the missing-tzdata
        # signal: a host with no tzdata, a stripped zoneinfo module and the
        # existing DST-fallback tests all surface it that way, and narrowing
        # this to two exact class names broke them. ZoneInfoNotFoundError
        # derives from KeyError, so it is matched by name.
        if not isinstance(exc, ImportError) and exc.__class__.__name__ != "ZoneInfoNotFoundError":
            raise
        year = utc_dt.year
        if year < US_DST_RULE_VALID_FROM or (
            US_DST_RULE_VALID_UNTIL is not None and year > US_DST_RULE_VALID_UNTIL
        ):
            raise ValueError(
                "no tz database available and the US DST rule is only valid from "
                f"{US_DST_RULE_VALID_FROM}; refusing to guess for {year}"
            ) from exc
        offset = eastern_utc_offset_hours(utc_dt)
        got = utc_dt.astimezone(_tz(timedelta(hours=offset), name="US-Eastern-rule"))
        return got, {"source": "us_dst_rule", "offset_hours": offset, "rule_valid": True,
                     "note": "tz database unavailable; the post-2007 US DST rule was "
                             "applied directly. Correct wall hour and instant, but DST "
                             "fold disambiguation metadata is absent"}


def eastern_at_safe(utc_dt: datetime) -> datetime:
    """Convert a UTC instant to aware Eastern wall-clock time (R10-11 repair).

    Unlike eastern_at's legacy fallback (`utc_dt + offset` preserving UTC
    tzinfo, which shifts the instant by 4-5h while reading the right wall
    hour), this always returns an AWARE datetime whose UTC timestamp equals
    the input instant. See eastern_at_safe_provenance for how it was
    derived and for the rule's validity window.
    """
    return eastern_at_safe_provenance(utc_dt)[0]


def eastern_now_safe() -> datetime:
    """Current time via the instant-preserving boundary. Raises when unknown."""
    return eastern_at_safe(datetime.now(UTC))
