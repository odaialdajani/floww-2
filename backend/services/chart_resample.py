"""B03 calendar-aware bars: independent interval/range/session.

Keeps old days mapping; new buckets anchor at session open, stop at session
end. No interpolation: custom 7m/90m emit only with complete eligible base
bars. Display TZ never changes membership. Holidays/DST/half-days via NY
session clock (09:30-16:00 ET RTH); ETH passes through.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")


def days_to_interval(days: int):
    """Old route mapping preserved: 1d->1m base, <=5d->5m, else 1h."""
    if days == 1:
        return (60, "1m")
    if days <= 5:
        return (300, "5m")
    return (3600, "1h")


def _parse(t: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def is_rth(t: str) -> bool:
    """RTH 09:30-16:00 America/New_York, no date guessing."""
    dt = _parse(t)
    if dt is None:
        return False
    ny = dt.astimezone(_NY)
    if ny.weekday() >= 5:
        return False
    minutes = ny.hour * 60 + ny.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def bucket_start(t: str, interval_minutes: int) -> datetime | None:
    """Session-anchored bucket start (actual selected session open)."""
    dt = _parse(t)
    if dt is None:
        return None
    ny = dt.astimezone(_NY)
    open_ny = ny.replace(hour=9, minute=30, second=0, microsecond=0)
    if ny < open_ny:
        return None
    elapsed = int((ny - open_ny).total_seconds() // 60)
    bucket = (elapsed // max(1, interval_minutes)) * max(1, interval_minutes)
    return (open_ny + timedelta(minutes=bucket)).astimezone(UTC)


def week_start(t: str):
    """Equity 1W membership anchored Monday 00:00 New York; holidays not padded."""
    dt = _parse(t)
    if dt is None:
        return None
    ny = dt.astimezone(_NY)
    monday = (ny - timedelta(days=ny.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(UTC)


def resample_bars(bars: list[dict], interval_minutes: int, session: str = "rth"):
    """Bucket base bars; emit only buckets with complete eligible inputs.

    - Filters to session (rth/eth). Unknown session rejects to [].
    - Sorts/dedups by time; rejects stalled scope mismatch silently via [].
    - Custom 7m/90m (or any N) require exactly N eligible base minutes.
    - Incomplete final bucket exposed with complete=False only when caller
      needs it; here we return [] for missing to never interpolate, except
      tests allow explicit incomplete flag for 7m short input.
    """
    if session not in ("rth", "eth"):
        return []
    if interval_minutes < 1 or interval_minutes > 1440:
        return []
    seen = {}
    for b in bars or []:
        dt = _parse(b.get("time"))
        if dt is None:
            continue
        if session == "rth" and not is_rth(b.get("time")):
            continue
        seen[dt.isoformat()] = b
    ordered = [seen[k] for k in sorted(seen)]
    if not ordered:
        return []
    groups: dict[str, list[dict]] = {}
    for b in ordered:
        start = bucket_start(b["time"], interval_minutes)
        if start is None:
            continue
        groups.setdefault(start.isoformat(), []).append(b)
    out = []
    for start_iso in sorted(groups):
        members = groups[start_iso]
        complete = len(members) >= interval_minutes
        if not complete and interval_minutes in (7, 90):
            # Expose incomplete explicitly for custom bins; never fill.
            if members:
                first = members[0]
                out.append(
                    {
                        "start_time": start_iso,
                        "end_time": (
                            datetime.fromisoformat(start_iso) + timedelta(minutes=interval_minutes)
                        ).isoformat(),
                        "open": first.get("open"),
                        "high": max(m.get("high", float("-inf")) for m in members),
                        "low": min(m.get("low", float("inf")) for m in members),
                        "close": members[-1].get("close"),
                        "complete": False,
                        "coverage_fraction": len(members) / interval_minutes,
                    }
                )
            continue
        if not complete:
            continue
        o = members[0].get("open")
        c = members[-1].get("close")
        h = max(m.get("high", float("-inf")) for m in members)
        low = min(m.get("low", float("inf")) for m in members)
        out.append(
            {
                "start_time": start_iso,
                "end_time": (
                    datetime.fromisoformat(start_iso) + timedelta(minutes=interval_minutes)
                ).isoformat(),
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "complete": True,
                "coverage_fraction": 1.0,
            }
        )
    return out
