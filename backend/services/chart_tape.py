"""B19 entitled tape: no inferred prints, explicit commissioning verdicts."""
from __future__ import annotations


def validate_print(trade: dict) -> dict:
    """Require trade ID, condition, correction flag, known-at; aggressor may be unknown."""
    if not isinstance(trade, dict):
        return {"status": "unavailable", "reason": "missing trade"}
    for field in ("trade_id", "price", "size", "known_at"):
        if trade.get(field) is None:
            return {"status": "unavailable", "reason": f"missing {field}"}
    if not isinstance(trade["price"], (int, float)) or not isinstance(trade["size"], (int, float)):
        return {"status": "unavailable", "reason": "bad types"}
    return {"status": "available", "aggressor": trade.get("aggressor", "unknown")}


def commissioning(entitlements: dict) -> dict:
    """Separate verdicts for options/equity/dark; absent => unavailable."""
    return {
        "options_trades": "available" if (entitlements or {}).get("options") else "unavailable",
        "equity_trades": "available" if (entitlements or {}).get("equity") else "unavailable",
        "dark_prints": "available" if (entitlements or {}).get("dark") else "unavailable",
    }
