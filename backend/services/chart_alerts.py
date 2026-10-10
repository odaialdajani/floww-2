"""B18 alert lines: server-owned evaluation, replay never emits live."""
from __future__ import annotations


def touch(price, target, tick=0.01) -> bool:
    """Tick-rounded touch predicate."""
    try:
        return abs(float(price) - float(target)) <= float(tick)
    except (TypeError, ValueError):
        return False


def evaluate(alert: dict, market: dict) -> dict:
    """Refuse stale/no-price/no-role; replay never enters live evaluation."""
    if (alert or {}).get("replay"):
        return {"fired": False, "reason": "replay-refused"}
    if (market or {}).get("stale"):
        return {"fired": False, "reason": "stale-gap-resets"}
    price, target = (market or {}).get("price"), (alert or {}).get("target")
    role = (market or {}).get("role")
    if price is None or target is None or role is None:
        return {"fired": False, "reason": "no-price-or-role"}
    if not touch(price, target, (alert or {}).get("tick", 0.01)):
        return {"fired": False, "reason": "no-touch"}
    return {"fired": True, "mode": (alert or {}).get("mode", "once")}
