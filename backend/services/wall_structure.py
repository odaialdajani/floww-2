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


def _gross_of(r: dict[str, Any]) -> float:
    try:
        gross = abs(float(r.get("call_gex", 0) or 0)) + abs(float(r.get("put_gex", 0) or 0))
        if gross > 0:
            return gross
        return abs(float(r.get("gex", 0) or 0))
    except (TypeError, ValueError):
        return 0.0


def _median_step(strikes: list[float]) -> float:
    steps = sorted(b - a for a, b in zip(strikes, strikes[1:], strict=False) if b > a)
    if not steps:
        return 0.0
    mid = len(steps) // 2
    return steps[mid] if len(steps) % 2 else (steps[mid - 1] + steps[mid]) / 2


def _scope_key(scope: dict[str, Any] | None) -> str:
    if not isinstance(scope, dict):
        return "symbol=?|formula=gex.v2"
    return f"symbol={scope.get('symbol', '?')}|formula={scope.get('formula', 'gex.v2')}"


def discover_walls(strike_rows: list[dict[str, Any]], spot: float,
                   pct_threshold: float = 0.75, min_support: float = 0.0,
                   scope: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Find gross-gamma concentrations; cluster adjacent strikes into zones.

    R4-07/P03 + R5-C/R16 contract: zero-mass rows are excluded from membership
    AND the threshold population; a zero-mass strike between supported strikes
    BREAKS the zone (MAX_ZERO_BRIDGE = 0 — excluded rows are never proof of
    continuous support). Gaps wider than 2.5x the median supported step break
    zones; IDs bind symbol + scope + formula + boundaries. First-seen/
    persistence live in the recorder (heatmap_history). Thresholds are
    research config.
    """
    rows = _valid_rows(strike_rows)
    if not rows or not spot or spot <= 0:
        return []
    masses = [(r, _gross_of(r)) for r in rows]
    supported = [(r, g) for r, g in masses if g > 0]
    if not supported:
        return []
    gross = [g for _, g in supported]
    thresh = sorted(gross)[min(len(gross) - 1, int(len(gross) * pct_threshold))]
    thresh = max(thresh, min_support)
    if thresh <= 0:
        return []
    strikes_all = sorted(float(r.get("strike")) for r, _ in supported)
    gap_break = _median_step(strikes_all) * 2.5
    walls: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []
    prev_strike: float | None = None
    for r, g in masses:
        s = float(r.get("strike"))
        if prev_strike is not None and gap_break > 0 and (s - prev_strike) > gap_break and run:
            walls.append(_zone(run, spot, scope))
            run = []
        prev_strike = s
        if g <= 0:
            # Zero-mass strike: closes any open zone (no bridging).
            if run:
                walls.append(_zone(run, spot, scope))
                run = []
            continue
        if g >= thresh:
            run.append(r)
        elif run:
            walls.append(_zone(run, spot, scope))
            run = []
    if run:
        walls.append(_zone(run, spot, scope))
    # Rank by gross; keep stable ids independent of rank.
    walls.sort(key=lambda w: w["gross"], reverse=True)
    for i, w in enumerate(walls):
        w["rank"] = i + 1
    return walls


def _zone(members: list[dict[str, Any]], spot: float,
          scope: dict[str, Any] | None = None) -> dict[str, Any]:
    strikes = sorted(float(m.get("strike")) for m in members)
    lo, hi = strikes[0], strikes[-1]
    gross = sum(abs(float(m.get("call_gex", 0) or 0)) + abs(float(m.get("put_gex", 0) or 0))
                or abs(float(m.get("gex", 0) or 0)) for m in members)
    net = sum(float(m.get("gex", 0) or 0) for m in members)
    call = sum(float(m.get("call_gex", 0) or 0) for m in members)
    put = sum(float(m.get("put_gex", 0) or 0) for m in members)
    mid = (lo + hi) / 2
    wid = f"{lo:g}-{hi:g}"
    wid_hash = hashlib.sha256(
        f"wall:{_scope_key(scope)}:{wid}".encode()).hexdigest()[:12]
    dist = mid - spot
    # Wall-level OI effective dates (R5 holes): union of member-strike dates,
    # distinct/sorted/capped. Absent when no member carries OI metadata —
    # the inspector then renders unavailable instead of inventing a date.
    _wall_dates: list[str] = []
    for m in members:
        for _d in m.get("oi_dates") or []:
            if _d not in _wall_dates and len(_wall_dates) < 4:
                _wall_dates.append(_d)
    _wall_dates.sort()
    zone: dict[str, Any] = {
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
    if _wall_dates:
        zone["oi_effective_dates"] = _wall_dates
    return zone


def nearest_walls(walls: list[dict[str, Any]], spot: float, n: int = 2) -> list[dict[str, Any]]:
    """Nearest relevant walls by absolute distance (accessible context).

    Kept for compat; prefer nearest_by_side, which never returns two walls
    from the same side when both sides have coverage (R4-07).
    """
    return sorted(walls or [], key=lambda w: abs(float(w.get("mid", spot)) - spot))[:n]


def nearest_by_side(walls: list[dict[str, Any]], spot: float) -> dict[str, Any | None]:
    """Side-specific nearest walls: below (high <= spot), inside
    (low <= spot <= high), above (low >= spot). Each side independent —
    a missing side is None, never a same-side substitute."""
    below = [w for w in (walls or []) if float(w.get("high", spot)) <= spot]
    above = [w for w in (walls or []) if float(w.get("low", spot)) >= spot]
    inside = [w for w in (walls or [])
              if float(w.get("low", spot)) <= spot <= float(w.get("high", spot))]

    def _nearest(cands: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not cands:
            return None
        return min(cands, key=lambda w: abs(float(w.get("mid", spot)) - spot))

    return {"below": _nearest(below), "inside": _nearest(inside), "above": _nearest(above)}
