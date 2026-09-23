"""
backend/services/wall_structure.py — Solstice wall registry (T05).

Stable wall IDs across refreshes; zones clustered from gross OI gamma with
call/put + net components. No invented OI trend, no calibrated probabilities.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any


def _valid_rows(strike_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in strike_rows or []:
        try:
            s = float(r.get("strike"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(s) or s <= 0:
            continue
        out.append(r)
    return sorted(out, key=lambda r: float(r["strike"]))


def discover_walls(strike_rows: list[dict[str, Any]], spot: float,
                   pct_threshold: float = 0.75, min_support: float = 0.0) -> list[dict[str, Any]]:
    """Find gross-gamma concentrations; cluster adjacent strikes into zones.

    Wall record: id (stable hash of boundaries+scope), boundaries, members,
    gross/net/call/put, distance, percentile, first-seen/persistence left to
    the recorder (heatmap_history). Thresholds are research config.
    """
    rows = _valid_rows(strike_rows)
    if not rows or not spot or spot <= 0:
        return []
    gross = [abs(float(r.get("call_gex", 0) or 0)) + abs(float(r.get("put_gex", 0) or 0))
             or abs(float(r.get("gex", 0) or 0)) for r in rows]
    if not gross or max(gross) <= 0:
        return []
    import statistics
    thresh = sorted(gross)[min(len(gross) - 1, int(len(gross) * pct_threshold))]
    thresh = max(thresh, min_support)
    walls: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []
    for r, g in zip(rows, gross):
        if g >= thresh:
            run.append(r)
        else:
            if run:
                walls.append(_zone(run, spot))
                run = []
    if run:
        walls.append(_zone(run, spot))
    # Rank by gross; keep stable ids independent of rank.
    walls.sort(key=lambda w: w["gross"], reverse=True)
    for i, w in enumerate(walls):
        w["rank"] = i + 1
    return walls


def _zone(members: list[dict[str, Any]], spot: float) -> dict[str, Any]:
    strikes = sorted(float(m.get("strike")) for m in members)
    lo, hi = strikes[0], strikes[-1]
    gross = sum(abs(float(m.get("call_gex", 0) or 0)) + abs(float(m.get("put_gex", 0) or 0))
                or abs(float(m.get("gex", 0) or 0)) for m in members)
    net = sum(float(m.get("gex", 0) or 0) for m in members)
    call = sum(float(m.get("call_gex", 0) or 0) for m in members)
    put = sum(float(m.get("put_gex", 0) or 0) for m in members)
    mid = (lo + hi) / 2
    wid = f"{lo:g}-{hi:g}"
    wid_hash = hashlib.sha256(f"wall:{wid}".encode()).hexdigest()[:12]
    dist = mid - spot
    return {
        "wall_id": f"w_{wid_hash}",
        "low": lo,
        "high": hi,
        "mid": mid,
        "members": strikes,
        "gross": gross,
        "net": net,
        "call": call,
        "put": put,
        "distance": dist,
        "distance_pct": dist / spot if spot else None,
        "exposure_basis": "OI",
        "formula_version": "gex.v2",
    }


def nearest_walls(walls: list[dict[str, Any]], spot: float, n: int = 2) -> list[dict[str, Any]]:
    """Nearest relevant walls by absolute distance (accessible context)."""
    return sorted(walls or [], key=lambda w: abs(float(w.get("mid", spot)) - spot))[:n]
