"""Deterministic strongest-wall assignment (Command Code C1.4).

Pure policy helper only. Raw gamma owns structural identity; this helper
assigns exactly one deterministic winner (or explicit ties when requested)
from already-computed adjusted magnitudes. It does not aggregate contracts,
infer behavior, emit probabilities, or call trades.

Tie policy:
- mode="single": stable input order breaks ties; exactly one winner.
- mode="explicit-ties": every wall sharing the top magnitude is returned.

Aggregation scope and stable ordering belong to the caller; the caller must
pass one magnitude per wall in canonical wall order.
"""

from __future__ import annotations

from typing import Any


def assign_strongest_wall(
    walls: list[dict[str, Any]],
    *,
    value_key: str = "adj_value",
    mode: str = "single",
) -> dict[str, Any]:
    """Assign strongest-wall identity without tolerance/equality ambiguity."""
    if mode not in ("single", "explicit-ties"):
        raise ValueError("mode must be 'single' or 'explicit-ties'")
    known = [
        (index, wall)
        for index, wall in enumerate(walls or [])
        if isinstance(wall, dict)
        and isinstance(wall.get(value_key), (int, float))
        and wall.get(value_key) == wall.get(value_key)
        and abs(wall.get(value_key)) != float("inf")
    ]
    if not known:
        return {"status": "unavailable", "reason": "NO_KNOWN_VALUES", "winners": []}
    top = max(abs(wall[value_key]) for _, wall in known)
    tied = [wall for _, wall in known if abs(wall[value_key]) == top]
    if mode == "explicit-ties":
        return {"status": "ok", "mode": mode, "top": top, "winners": tied}
    # Stable input order decides; equality alone never assigns identity.
    for _, wall in known:
        if abs(wall[value_key]) == top:
            return {"status": "ok", "mode": mode, "top": top, "winners": [wall]}
    raise AssertionError("unreachable: top came from known values")
