"""B02 exposure grids: archived GEX + canonical VANNA VEX only.

Missing stays unknown, never zero. Newer malformed/incomplete observation
supersedes prior valid display with degraded/unavailable, never silent carry.
"""
from __future__ import annotations


def parse_grid(channel: dict) -> dict:
    """Validate one metric channel with model/basis/unit identity."""
    if not isinstance(channel, dict):
        return {"status": "unknown", "reason": "missing channel"}
    metric = channel.get("metric")
    values = channel.get("values")
    if metric not in ("gex", "vex") or not isinstance(values, list) or not values:
        return {"status": "unknown", "reason": "missing inputs"}
    requested = channel.get("requested_expiries")
    observed = channel.get("observed_expiries", channel.get("actual_expiries"))
    coverage = {"inputs": len(values)}
    if isinstance(requested, list) and isinstance(observed, list):
        coverage = {"requested": len(requested), "observed": len(observed),
                    "ratio": (len(observed) / len(requested)) if requested else 0.0}
    if metric == "gex":
        if channel.get("basis") != "gex.v2":
            return {"status": "unavailable", "reason": "basis mismatch"}
        return {"status": "available", "metric": "gex", "values": values,
                "coverage": coverage}
    # VANNA VEX requires canonical triple together; parent formula alone insufficient.
    if not (channel.get("model") == "VEX_1VOLPT"
            and channel.get("basis") == "local-bs-vanna.v1"
            and channel.get("unit") == "USD-per-volpt"):
        return {"status": "unavailable", "reason": "non-VANNA identity"}
    return {"status": "available", "metric": "vex", "values": values,
            "coverage": coverage}


def select_display(readings: list[dict]) -> dict:
    """Choose newest observed source-asof before validating display.

    A newer malformed/incomplete observation supersedes prior valid display.
    """
    if not readings:
        return {"status": "unknown", "reason": "no readings"}
    ordered = sorted(readings, key=lambda r: (r.get("asof", 0), str(r.get("id", ""))))
    newest = ordered[-1]
    grid = newest.get("grid", {})
    status = grid.get("status", "unknown")
    if status == "available":
        return {"status": "available", "values": grid.get("values"),
                "asof": newest.get("asof"), "scope": newest.get("scope")}
    if status == "malformed":
        return {"status": "degraded", "reason": "newer malformed supersedes",
                "asof": newest.get("asof"), "scope": newest.get("scope")}
    return {"status": "unavailable", "reason": "newer incomplete supersedes",
            "asof": newest.get("asof"), "scope": newest.get("scope")}
