"""B15 single-cursor replay: known-at algebra, no live-cache feed."""
from __future__ import annotations


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


def partial_bar(events: list[dict], cursor):
    """Aggregate only base events with event_time<=R and available_at<=R."""
    use = [e for e in (events or [])
           if e.get("event_time", 1) <= cursor and e.get("available_at", 1) <= cursor]
    if not use:
        return None
    opens = [e["open"] for e in use if "open" in e]
    closes = [e["close"] for e in use if "close" in e]
    return {"open": opens[0] if opens else None, "close": closes[-1] if closes else None,
            "complete": False, "count": len(use)}
