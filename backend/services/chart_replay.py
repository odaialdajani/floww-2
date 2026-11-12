"""B15 single-cursor replay: known-at algebra, no live-cache feed."""
from __future__ import annotations

import math


def visible_snapshot(snapshots: list[dict], cursor):
    """Newest time-eligible reading at cursor R; late older never rewinds."""
    eligible = [s for s in (snapshots or [])
                if s.get("known_at") is not None and s["known_at"] <= cursor]
    if not eligible:
        return None
    eligible.sort(key=lambda s: (s["known_at"], str(s.get("id", ""))))
    return eligible[-1]


def age_ok(asof, cursor, limit=900) -> bool:
    """900s eligible, 901s absent."""
    try:
        return 0 <= float(cursor) - float(asof) <= limit
    except (TypeError, ValueError):
        return False


def _finite_number(value):
    """Convert a replay timestamp/duration like JS Number, refusing unknowns."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def partial_bar(events: list[dict], cursor, bar_seconds=900):
    """Aggregate the cursor-owning bucket with recorded availability only.

    ``event_time`` selects a leg's bucket. ``available_at`` controls whether
    that leg is known at the cursor. Unknown event times are excluded; unknown
    availability remains pending and is never fabricated.
    """
    c = _finite_number(cursor)
    duration = _finite_number(bar_seconds)
    if c is None or duration is None or duration <= 0:
        return None
    bucket_start = math.floor(c / duration) * duration
    bucket_end = bucket_start + duration
    in_bucket = []
    use = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        event_time = _finite_number(event.get("event_time"))
        if event_time is None or event_time < bucket_start or event_time >= bucket_end:
            continue
        in_bucket.append(event)
        available_at = _finite_number(event.get("available_at"))
        if available_at is not None and available_at <= c:
            use.append((event, available_at))
    if not in_bucket:
        return None
    opens = [event["open"] for event, _ in use if "open" in event]
    closes = [event["close"] for event, _ in use if "close" in event]
    return {
        "open": opens[0] if opens else None,
        "close": closes[-1] if closes else None,
        "complete": False,
        "count": len(use),
        "pending": len(in_bucket) - len(use),
        "lastAvailableAt": max((available_at for _, available_at in use), default=None),
        "bucketStart": bucket_start,
        "bucketEnd": bucket_end,
    }
