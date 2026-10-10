"""B21 dark-pool: exact single prints, equities only, no direction."""
from __future__ import annotations


def top_levels(prints: list[dict], top_n=3):
    """Return largest notional single prints with venue/price/size/event/receipt."""
    rows = [p for p in (prints or [])
            if isinstance(p, dict) and p.get("asset_class", "equity") == "equity"
            and all(p.get(k) is not None for k in ("price", "size", "event_time", "venue"))]
    rows.sort(key=lambda p: p["price"] * p["size"], reverse=True)
    return [{"price": p["price"], "size": p["size"], "venue": p["venue"],
             "event_time": p["event_time"], "notional": p["price"] * p["size"],
             "direction": "unknown"} for p in rows[:top_n]]
