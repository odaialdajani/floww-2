"""
backend/services/heatseeker.py

Skylit-parity Heatseeker.
    Wave 1: flip zones, node lifecycle, air pockets.
    Wave 2: beach ball, reverse rug, rainbow road, velocity mode, trinity.

Pure functions. No DB access — the route layer fetches the chain and passes
it in. Input shape mirrors backend/advanced_analytics.py: each contract is a
dict with at least `strike`, `type` ("C"/"CALL"/"call" or "P"/"PUT"/"put"),
`gamma`, `open_interest` (or `oi`). Robust to missing fields and empty input.

Formula references (mirroring `calc_gamma_flip_levels` in advanced_analytics.py
at line 633):
    gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
    signed_gex = gex_unit if type=="call" else -gex_unit

All functions return JSON-serializable dicts and never raise on empty or
degenerate input.
"""

from __future__ import annotations

import math
from datetime import datetime
from statistics import median
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _is_call(c: Dict[str, Any]) -> bool:
    """True if contract is a call. Accepts 'C', 'CALL', 'call' (any case)."""
    t = str(c.get("type", "")).upper()
    return t in ("C", "CALL")


def _oi(c: Dict[str, Any]) -> float:
    """Open interest, tolerant to 'open_interest' or 'oi' field names."""
    val = c.get("open_interest")
    if val is None:
        val = c.get("oi", 0)
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _strike(c: Dict[str, Any]) -> float:
    try:
        return float(c.get("strike", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _gamma(c: Dict[str, Any]) -> float:
    try:
        val = float(c.get("gamma", 0) or 0)
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return val
    except (TypeError, ValueError):
        return 0.0


def _gex_per_strike(spot: float, contracts: List[Dict[str, Any]]) -> Dict[float, float]:
    """
    Aggregate signed GEX per strike using the same convention as
    `calc_gamma_flip_levels` in advanced_analytics.py:

        gex_unit  = gamma * oi * 100 * spot * spot * 0.01
        signed    = +gex_unit for calls, -gex_unit for puts
    """
    out: Dict[float, float] = {}
    if not contracts or not spot or spot <= 0:
        return out
    for c in contracts:
        oi = _oi(c)
        if oi <= 0:
            continue
        gamma = _gamma(c)
        if gamma <= 0:
            continue
        strike = _strike(c)
        if strike <= 0:
            continue
        gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
        sign = 1.0 if _is_call(c) else -1.0
        out[strike] = out.get(strike, 0.0) + sign * gex_unit
    return out


# ---------------------------------------------------------------------------
# Function 1: Flip zones
# ---------------------------------------------------------------------------

def calc_flip_zones(
    spot: float,
    contracts: List[Dict[str, Any]],
    *,
    window_pct: float = 0.05,
) -> Dict[str, Any]:
    """
    All price levels where cumulative GEX changes sign, within
    ``spot * (1 ± window_pct)``.

    A flip zone is interpolated linearly between adjacent strikes where the
    running cumulative GEX crosses zero. ``strength`` is the magnitude of the
    cumulative-sum change at the crossing strike, which proxies dealer hedging
    urgency through that level.

    Returns
    -------
    dict with keys: ``flip_zones`` (list), ``window_low``, ``window_high``,
    ``count``. Empty list on degenerate input.
    """
    if not spot or spot <= 0:
        return {"flip_zones": [], "window_low": 0.0, "window_high": 0.0, "count": 0}

    window_low = spot * (1.0 - window_pct)
    window_high = spot * (1.0 + window_pct)

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return {
            "flip_zones": [],
            "window_low": round(window_low, 4),
            "window_high": round(window_high, 4),
            "count": 0,
        }

    strikes = sorted(gex.keys())
    cumulative: List[float] = []
    running = 0.0
    for k in strikes:
        running += gex[k]
        cumulative.append(running)

    zones: List[Dict[str, Any]] = []
    for i in range(1, len(strikes)):
        prev_c, curr_c = cumulative[i - 1], cumulative[i]
        # Only count true sign changes (excludes prev==0 to avoid duplicate
        # crossings when a strike has exactly zero net cumulative GEX).
        if prev_c == 0 or curr_c == 0:
            continue
        if (prev_c > 0) == (curr_c > 0):
            continue

        k1, k2 = strikes[i - 1], strikes[i]
        # Linear interpolation: f(k1)=prev_c, f(k2)=curr_c, find where f=0.
        denom = curr_c - prev_c
        if denom == 0:
            flip_price = (k1 + k2) / 2.0
        else:
            flip_price = k1 + (k2 - k1) * (-prev_c / denom)

        if not (window_low <= flip_price <= window_high):
            continue

        zones.append({
            "price": round(flip_price, 4),
            "from_sign": "positive" if prev_c > 0 else "negative",
            "to_sign": "positive" if curr_c > 0 else "negative",
            "strength": round(abs(curr_c - prev_c), 4),
        })

    return {
        "flip_zones": zones,
        "window_low": round(window_low, 4),
        "window_high": round(window_high, 4),
        "count": len(zones),
    }


# ---------------------------------------------------------------------------
# Function 2: Node lifecycle
# ---------------------------------------------------------------------------

def calc_node_lifecycle(
    spot: float,
    contracts: List[Dict[str, Any]],
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Classify the top 10 strikes by |GEX| as Fresh / Tested / Delivered /
    Decaying based on how many times spot has come within 0.1% of them in the
    supplied ``history`` (typically last 24h of spot snapshots).

    Tap-probability schedule (Skylit's documented decay curve):
        fresh      → 80
        tested     → 66
        delivered  → 33
        decaying   → 10

    ``history`` is a list of dicts with at least ``spot`` (and ``timestamp``,
    unused here but kept in the signature for the caller's contract).
    """
    if not spot or spot <= 0:
        return {"nodes": []}

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return {"nodes": []}

    # Top 10 strikes by absolute net GEX.
    ranked = sorted(gex.items(), key=lambda kv: abs(kv[1]), reverse=True)[:10]

    history = history or []
    history_spots: List[float] = []
    for h in history:
        try:
            history_spots.append(float(h.get("spot")))
        except (TypeError, ValueError):
            continue

    nodes: List[Dict[str, Any]] = []
    for strike, net_gex in ranked:
        if strike <= 0:
            continue
        taps = sum(
            1 for s in history_spots
            if abs(s - strike) / strike <= 0.001
        )
        if taps == 0:
            state, prob = "fresh", 80
        elif taps == 1:
            state, prob = "tested", 66
        elif taps == 2:
            state, prob = "delivered", 33
        else:
            state, prob = "decaying", 10
        nodes.append({
            "strike": round(strike, 4),
            "net_gex": round(net_gex, 4),
            "taps": taps,
            "state": state,
            "tap_probability": prob,
        })

    return {"nodes": nodes}


# ---------------------------------------------------------------------------
# Function 3: Air pockets
# ---------------------------------------------------------------------------

def calc_air_pockets(
    spot: float,
    contracts: List[Dict[str, Any]],
    *,
    min_gap_pct: float = 0.005,
) -> Dict[str, Any]:
    """
    Contiguous ranges of strikes where ``|GEX|`` is below 20% of the local
    median (median of ``|GEX|`` for strikes within ±5% of spot) AND the range
    spans at least ``spot * min_gap_pct`` in price.

    These zones tend to see fast price moves because dealer hedging is thin.

    Returns
    -------
    dict with key ``air_pockets`` — list of ``{low, high, span_pct,
    max_abs_gex_in_run}`` dicts. Empty list on degenerate input.
    """
    if not spot or spot <= 0:
        return {"air_pockets": []}

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return {"air_pockets": []}

    strikes = sorted(gex.keys())
    abs_gex: Dict[float, float] = {k: abs(gex[k]) for k in strikes}

    # Local median of |GEX| using strikes within ±5% of spot.
    near_window_low = spot * 0.95
    near_window_high = spot * 1.05
    near_vals = [abs_gex[k] for k in strikes if near_window_low <= k <= near_window_high]
    if not near_vals:
        return {"air_pockets": []}
    local_median = median(near_vals)
    if local_median <= 0:
        # Degenerate: everything is zero in the local window. No pockets to
        # report (a flat-zero band is technically a giant pocket but isn't
        # actionable signal).
        return {"air_pockets": []}

    threshold = 0.2 * local_median
    min_span = spot * min_gap_pct

    pockets: List[Dict[str, Any]] = []
    run_start_idx: Optional[int] = None
    run_max: float = 0.0

    def _flush(run_start_idx: int, run_end_idx: int, run_max_val: float) -> None:
        low_k = strikes[run_start_idx]
        high_k = strikes[run_end_idx]
        span = high_k - low_k
        if span < min_span:
            return
        pockets.append({
            "low": round(low_k, 4),
            "high": round(high_k, 4),
            "span_pct": round(span / spot, 6),
            "max_abs_gex_in_run": round(run_max_val, 4),
        })

    for i, k in enumerate(strikes):
        if abs_gex[k] < threshold:
            if run_start_idx is None:
                run_start_idx = i
                run_max = abs_gex[k]
            else:
                run_max = max(run_max, abs_gex[k])
        else:
            if run_start_idx is not None:
                _flush(run_start_idx, i - 1, run_max)
                run_start_idx = None
                run_max = 0.0
    # Trailing run.
    if run_start_idx is not None:
        _flush(run_start_idx, len(strikes) - 1, run_max)

    return {"air_pockets": pockets}


# ---------------------------------------------------------------------------
# Wave 2 — Function 4: Beach ball
# ---------------------------------------------------------------------------

def _king_node_strike(gex: Dict[float, float]) -> Optional[float]:
    """Strike with max |net_gex|. None if dict is empty."""
    if not gex:
        return None
    return max(gex.keys(), key=lambda k: abs(gex[k]))


def detect_beach_ball(
    spot: float,
    contracts: List[Dict[str, Any]],
    *,
    king_node: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Beach Ball: spot is stretched past the King Node (largest |GEX| strike).
    Overshoot/reversion setup.

    Active when ``abs(spot - king_node) / king_node > 0.005`` (50bps).
    Confidence = ``min(1.0, distance_pct / 0.02)`` — capped at 2% stretch.
    """
    inactive: Dict[str, Any] = {
        "pattern": "beach_ball",
        "active": False,
        "king_node": None,
        "spot_distance_pct": 0.0,
        "direction": "at",
        "confidence": 0.0,
    }

    if not spot or spot <= 0:
        return inactive

    if king_node is None:
        gex = _gex_per_strike(spot, contracts)
        king_node = _king_node_strike(gex)
    if king_node is None or king_node <= 0:
        return inactive

    raw_distance = (spot - king_node) / king_node
    distance_pct = abs(raw_distance)
    if raw_distance > 0:
        direction = "above"
    elif raw_distance < 0:
        direction = "below"
    else:
        direction = "at"

    active = distance_pct > 0.005
    confidence = min(1.0, distance_pct / 0.02)

    return {
        "pattern": "beach_ball",
        "active": active,
        "king_node": round(float(king_node), 4),
        "spot_distance_pct": round(distance_pct, 6),
        "direction": direction,
        "confidence": round(confidence, 4),
    }


# ---------------------------------------------------------------------------
# Wave 2 — Function 5: Reverse rug
# ---------------------------------------------------------------------------

def detect_reverse_rug(
    spot: float,
    contracts: List[Dict[str, Any]],
    *,
    min_strength: float = 0.0,
) -> Dict[str, Any]:
    """
    Reverse Rug: positive floor below spot, negative ceiling above.
    Support holds, bounce runs.

    Finds the largest positive-GEX strike below spot (the floor) and the
    largest negative-GEX strike above spot (the ceiling).

    Pattern active when both exist AND ``abs(floor_gex) > min_strength``
    AND ``abs(ceiling_gex) > min_strength``.
    """
    inactive: Dict[str, Any] = {
        "pattern": "reverse_rug",
        "active": False,
        "floor_strike": None,
        "floor_gex": 0.0,
        "ceiling_strike": None,
        "ceiling_gex": 0.0,
    }

    if not spot or spot <= 0:
        return inactive

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return inactive

    floor_strike: Optional[float] = None
    floor_gex: float = 0.0
    ceiling_strike: Optional[float] = None
    ceiling_gex: float = 0.0

    for strike, signed in gex.items():
        if strike < spot and signed > 0 and signed > floor_gex:
            floor_strike = strike
            floor_gex = signed
        elif strike > spot and signed < 0 and signed < ceiling_gex:
            ceiling_strike = strike
            ceiling_gex = signed

    active = (
        floor_strike is not None
        and ceiling_strike is not None
        and abs(floor_gex) > min_strength
        and abs(ceiling_gex) > min_strength
    )

    return {
        "pattern": "reverse_rug",
        "active": bool(active),
        "floor_strike": round(floor_strike, 4) if floor_strike is not None else None,
        "floor_gex": round(floor_gex, 4),
        "ceiling_strike": round(ceiling_strike, 4) if ceiling_strike is not None else None,
        "ceiling_gex": round(ceiling_gex, 4),
    }


# ---------------------------------------------------------------------------
# Wave 2 — Function 6: Rainbow road
# ---------------------------------------------------------------------------

def detect_rainbow_road(
    spot: float,
    contracts: List[Dict[str, Any]],
    *,
    max_dominant_share: float = 0.15,
    window_pct: float = 0.05,
) -> Dict[str, Any]:
    """
    Rainbow Road: no dominant structure within ±window_pct of spot. Chaos.

    Active when the top |GEX| strike's share of the local total is below
    ``max_dominant_share`` — i.e. GEX is spread across many strikes and
    no single node dominates.

    ``n_strikes_significant`` is the count of strikes with
    ``|gex| > 0.5 * mean(|gex|)`` in the same window.
    """
    inactive: Dict[str, Any] = {
        "pattern": "rainbow_road",
        "active": False,
        "top_strike_share": 0.0,
        "n_strikes_significant": 0,
    }

    if not spot or spot <= 0:
        return inactive

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return inactive

    low = spot * (1.0 - window_pct)
    high = spot * (1.0 + window_pct)
    local = {k: abs(v) for k, v in gex.items() if low <= k <= high}
    if not local:
        return inactive

    total = sum(local.values())
    if total <= 0:
        return inactive

    top_share = max(local.values()) / total
    mean_abs = total / len(local)
    n_significant = sum(1 for v in local.values() if v > 0.5 * mean_abs)

    active = top_share < max_dominant_share

    return {
        "pattern": "rainbow_road",
        "active": bool(active),
        "top_strike_share": round(top_share, 6),
        "n_strikes_significant": n_significant,
    }


# ---------------------------------------------------------------------------
# Wave 2 — Function 7: Velocity mode
# ---------------------------------------------------------------------------

def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse an iso8601 (or datetime) value. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        s = str(value)
        # Handle the trailing 'Z' since fromisoformat doesn't accept it pre-3.11.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def calc_velocity_mode(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Dealer urgency: rate at which the King Node is moving across the recent
    snapshots in ``history``. Caller passes the last ~30 minutes of data.

    Each entry: ``{"timestamp": iso8601, "king_node_strike": float, "spot": float}``.

    Velocity = ``(king_node[-1] - king_node[0]) / minutes_elapsed`` (signed,
    so an observer can tell which way the node is drifting).

    Mode bands (use ``abs(velocity)``):
        |v| < 0.5     → "calm"
        |v| < 2.0     → "active"
        |v| ≥ 2.0     → "urgent"
    """
    history = history or []
    n = len(history)
    if n < 2:
        return {
            "velocity_strikes_per_min": 0.0,
            "mode": "calm",
            "n_snapshots": n,
        }

    first = history[0]
    last = history[-1]
    try:
        kn0 = float(first.get("king_node_strike"))
        kn1 = float(last.get("king_node_strike"))
    except (TypeError, ValueError):
        return {
            "velocity_strikes_per_min": 0.0,
            "mode": "calm",
            "n_snapshots": n,
        }

    t0 = _parse_ts(first.get("timestamp"))
    t1 = _parse_ts(last.get("timestamp"))
    if t0 is None or t1 is None:
        return {
            "velocity_strikes_per_min": 0.0,
            "mode": "calm",
            "n_snapshots": n,
        }
    minutes = (t1 - t0).total_seconds() / 60.0
    if minutes <= 0:
        return {
            "velocity_strikes_per_min": 0.0,
            "mode": "calm",
            "n_snapshots": n,
        }

    velocity = (kn1 - kn0) / minutes
    mag = abs(velocity)
    if mag < 0.5:
        mode = "calm"
    elif mag < 2.0:
        mode = "active"
    else:
        mode = "urgent"

    return {
        "velocity_strikes_per_min": round(velocity, 6),
        "mode": mode,
        "n_snapshots": n,
    }


# ---------------------------------------------------------------------------
# Wave 2 — Function 8: Trinity confluence
# ---------------------------------------------------------------------------

def _side_of_flip(spot: Any, gamma_flip: Any) -> Optional[str]:
    """Return 'above', 'below', or None if either input is missing/invalid."""
    try:
        s = float(spot)
        gf = float(gamma_flip)
    except (TypeError, ValueError):
        return None
    if s <= 0 or gf <= 0:
        return None
    if s > gf:
        return "above"
    if s < gf:
        return "below"
    return "at"


def _all_equal_and_present(values: List[Any]) -> bool:
    """True when every value is non-None and they all compare equal."""
    if not values or any(v is None for v in values):
        return False
    first = values[0]
    return all(v == first for v in values)


def calc_trinity_confluence(
    spx_snapshot: Dict[str, Any],
    spy_snapshot: Dict[str, Any],
    qqq_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Cross-index alignment quantified.

    Each snapshot:
        {"gex_regime": "positive"|"negative"|"neutral"|"missing",
         "spot": float, "gamma_flip": float,
         "trend_direction": "up"|"down"|"flat"}

    Score 0–100:
        +33 if all three ``gex_regime`` agree (and none is 'missing')
        +33 if all three are on the same side of ``gamma_flip``
        +34 if all three ``trend_direction`` agree (and none is None)
        Missing fields contribute 0 — function does not crash.

    Verdict bands:
        score ≥ 66 → "high_confluence"
        33 ≤ score < 66 → "partial"
        score < 33 → "divergence"
    """
    snaps = [spx_snapshot or {}, spy_snapshot or {}, qqq_snapshot or {}]

    # gex_regime dimension
    regimes = [s.get("gex_regime") for s in snaps]
    regime_present = [r for r in regimes if r not in (None, "missing", "")]
    regime_aligned = (
        len(regime_present) == 3
        and _all_equal_and_present(regime_present)
    )

    # side_of_flip dimension
    sides = [_side_of_flip(s.get("spot"), s.get("gamma_flip")) for s in snaps]
    side_aligned = (
        all(side is not None for side in sides)
        and _all_equal_and_present(sides)
    )

    # trend dimension — exclude "missing" sentinel same as gex_regime above
    # (bug fix 2026-05-18: previously three "missing" trends scored +34 because
    # the `is not None` check accepted the literal string; CI agent surfaced
    # via test_heatseeker_routes.py::test_trinity_confluence_all_missing.)
    trends = [s.get("trend_direction") for s in snaps]
    trend_present = [t for t in trends if t not in (None, "missing", "")]
    trend_aligned = (
        len(trend_present) == 3
        and _all_equal_and_present(trend_present)
    )

    score = 0
    aligned: List[str] = []
    divergences: List[str] = []

    if regime_aligned:
        score += 33
        aligned.append("gex_regime")
    else:
        divergences.append("gex_regime")

    if side_aligned:
        score += 33
        aligned.append("side_of_flip")
    else:
        divergences.append("side_of_flip")

    if trend_aligned:
        score += 34
        aligned.append("trend")
    else:
        divergences.append("trend")

    if score >= 66:
        verdict = "high_confluence"
    elif score >= 33:
        verdict = "partial"
    else:
        verdict = "divergence"

    return {
        "score": int(score),
        "aligned_dimensions": aligned,
        "divergences": divergences,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Wave 3 — Function 9: Rolling floors/ceilings tracker
# ---------------------------------------------------------------------------

def _trend_direction(values: List[float]) -> str:
    """
    Classify a series as 'rising', 'falling', or 'flat'.
    Uses simple linear regression slope sign with a dead-zone of ±0.01
    per step to avoid noise triggering.
    """
    if len(values) < 2:
        return "flat"
    n = len(values)
    # Simple slope: (last - first) / (n - 1)
    slope = (values[-1] - values[0]) / (n - 1)
    # Dead-zone: if the per-step change is < 0.01 * first value, call it flat
    deadzone = abs(values[0]) * 0.005 if values[0] != 0 else 0.005
    if slope > deadzone:
        return "rising"
    elif slope < -deadzone:
        return "falling"
    return "flat"


def calc_rolling_floors_ceilings(
    spot: float,
    snapshots: List[Dict[str, Any]],
    ticker: str,
    *,
    lookback_days: int = 20,
) -> Dict[str, Any]:
    """
    Track how gamma flip points (floors/ceilings) move over time.

    Each snapshot: ``{"spot": float, "contracts": [...]}``.

    Floor = largest positive-GEX strike below the snapshot spot.
    Ceiling = largest (most negative) negative-GEX strike above the snapshot spot.

    Trend detection:
        rising floor  → bullish (dealers adding long gamma support higher)
        falling ceiling → bearish (dealers adding short gamma resistance lower)

    Returns
    -------
    dict with keys: ``ticker``, ``floor_series``, ``ceiling_series``,
    ``floor_trend``, ``ceiling_trend``, ``signal``.
    """
    if not snapshots or not spot or spot <= 0:
        return {
            "ticker": ticker.upper(),
            "floor_series": [],
            "ceiling_series": [],
            "floor_trend": "flat",
            "ceiling_trend": "flat",
            "signal": "neutral",
        }

    # Apply lookback: keep only the last ``lookback_days`` snapshots.
    # Each snapshot is assumed to be one day's worth of data; the caller
    # is responsible for supplying daily snapshots.
    usable = snapshots[-lookback_days:] if len(snapshots) > lookback_days else snapshots

    floor_series: List[float] = []
    ceiling_series: List[float] = []

    for snap in usable:
        snap_spot = snap.get("spot", spot)
        snap_contracts = snap.get("contracts", [])
        if not snap_spot or snap_spot <= 0:
            continue
        gex = _gex_per_strike(snap_spot, snap_contracts)
        if not gex:
            continue

        # Floor: largest positive-GEX strike below snap_spot
        floor_strike: Optional[float] = None
        floor_gex_val: float = 0.0
        for strike, signed in gex.items():
            if strike < snap_spot and signed > 0 and signed > floor_gex_val:
                floor_strike = strike
                floor_gex_val = signed

        # Ceiling: most negative-GEX strike above snap_spot
        ceiling_strike: Optional[float] = None
        ceiling_gex_val: float = 0.0
        for strike, signed in gex.items():
            if strike > snap_spot and signed < 0 and signed < ceiling_gex_val:
                ceiling_strike = strike
                ceiling_gex_val = signed

        if floor_strike is not None:
            floor_series.append(round(floor_strike, 4))
        if ceiling_strike is not None:
            ceiling_series.append(round(ceiling_strike, 4))

    floor_trend = _trend_direction(floor_series)
    ceiling_trend = _trend_direction(ceiling_series)

    # Signal logic
    if floor_trend == "rising":
        signal = "bullish"
    elif ceiling_trend == "falling":
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "ticker": ticker.upper(),
        "floor_series": floor_series,
        "ceiling_series": ceiling_series,
        "floor_trend": floor_trend,
        "ceiling_trend": ceiling_trend,
        "signal": signal,
    }


# ---------------------------------------------------------------------------
# Wave 3 — Function 10: Real-vs-hedge node classification
# ---------------------------------------------------------------------------

def classify_nodes(
    nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Distinguish between "real" dealer positioning nodes (growing gamma
    exposure) and "hedge" nodes (fading protection).

    Classification rules:
        - gamma_sign == "positive" AND oi_trend == "growing"  → "real"
        - gamma_sign == "negative" AND oi_trend == "fading"   → "hedge"
        - otherwise                                            → "unknown"

    Each node dict must contain at least ``strike``, ``gamma_sign``,
    ``oi_trend``. All other fields (``net_gex``, ``taps``, ``state``,
    ``tap_probability``) are passed through.

    Returns
    -------
    dict with keys: ``nodes`` (list with ``classification`` added),
    ``real_count``, ``hedge_count``.
    """
    nodes = nodes or []
    classified: List[Dict[str, Any]] = []
    real_count = 0
    hedge_count = 0

    for node in nodes:
        gamma_sign = str(node.get("gamma_sign", "")).lower()
        oi_trend = str(node.get("oi_trend", "")).lower()

        if gamma_sign == "positive" and oi_trend == "growing":
            classification = "real"
            real_count += 1
        elif gamma_sign == "negative" and oi_trend == "fading":
            classification = "hedge"
            hedge_count += 1
        else:
            classification = "unknown"

        classified.append({**node, "classification": classification})

    return {
        "nodes": classified,
        "real_count": real_count,
        "hedge_count": hedge_count,
    }


# ---------------------------------------------------------------------------
# Wave 3 — Function 11: Stacked nodes detection
# ---------------------------------------------------------------------------

def detect_stacked_nodes(
    contracts: List[Dict[str, Any]],
    *,
    threshold_pct: float = 0.3,
) -> Dict[str, Any]:
    """
    Detect strikes where both call and put GEX are significant — a
    "conflict zone" where dealers are active on both sides.

    A strike is stacked when:
        call_gex / total_abs_gex >= threshold_pct
      AND
        put_gex / total_abs_gex >= threshold_pct

    Returns
    -------
    dict with keys: ``stacked_nodes`` (list of ``{strike, call_gex, put_gex,
    conflict}``), ``count``.
    """
    if not contracts:
        return {"stacked_nodes": [], "count": 0}

    # Aggregate per-strike GEX, split by call/put
    call_gex: Dict[float, float] = {}
    put_gex: Dict[float, float] = {}
    for c in contracts:
        oi = _oi(c)
        if oi <= 0:
            continue
        gamma = _gamma(c)
        if gamma <= 0:
            continue
        strike = _strike(c)
        if strike <= 0:
            continue
        gex_unit = gamma * oi * 100.0  # spot^2*0.1 factor omitted — same for all
        if _is_call(c):
            call_gex[strike] = call_gex.get(strike, 0.0) + gex_unit
        else:
            put_gex[strike] = put_gex.get(strike, 0.0) + gex_unit

    # Total absolute GEX across all strikes (using the per-strike net)
    all_strikes = set(call_gex.keys()) | set(put_gex.keys())
    if not all_strikes:
        return {"stacked_nodes": [], "count": 0}

    total_abs = sum(
        abs(call_gex.get(s, 0.0)) + abs(put_gex.get(s, 0.0))
        for s in all_strikes
    )
    if total_abs <= 0:
        return {"stacked_nodes": [], "count": 0}

    stacked: List[Dict[str, Any]] = []
    for strike in sorted(all_strikes):
        cg = abs(call_gex.get(strike, 0.0))
        pg = abs(put_gex.get(strike, 0.0))
        if cg / total_abs >= threshold_pct and pg / total_abs >= threshold_pct:
            stacked.append({
                "strike": round(strike, 4),
                "call_gex": round(call_gex.get(strike, 0.0), 4),
                "put_gex": round(put_gex.get(strike, 0.0), 4),
                "conflict": True,
            })

    return {"stacked_nodes": stacked, "count": len(stacked)}


# ---------------------------------------------------------------------------
# Wave 3 — Function 12: Tug-of-war zones
# ---------------------------------------------------------------------------

def calc_tug_of_war_zones(
    contracts: List[Dict[str, Any]],
    spot: float,
    *,
    band_pct: float = 0.01,
) -> Dict[str, Any]:
    """
    Detect zones where positive and negative GEX are in conflict —
    within ``band_pct`` of spot (default 1%).

    When both signs of GEX exist near spot, price is in a tug-of-war
    between dealers hedging calls (buying support) and puts (selling
    resistance).

    Returns
    -------
    dict with keys: ``in_tug_of_war`` (bool), ``zone_low``, ``zone_high``,
    ``positive_strikes``, ``negative_strikes``, ``positive_gex``,
    ``negative_gex``, ``gex_balance``.
    """
    if not contracts or not spot or spot <= 0:
        return {
            "in_tug_of_war": False,
            "zone_low": 0.0,
            "zone_high": 0.0,
            "positive_strikes": 0,
            "negative_strikes": 0,
            "positive_gex": 0.0,
            "negative_gex": 0.0,
            "gex_balance": 0.0,
        }

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return {
            "in_tug_of_war": False,
            "zone_low": 0.0,
            "zone_high": 0.0,
            "positive_strikes": 0,
            "negative_strikes": 0,
            "positive_gex": 0.0,
            "negative_gex": 0.0,
            "gex_balance": 0.0,
        }

    low = spot * (1.0 - band_pct)
    high = spot * (1.0 + band_pct)

    pos_strikes: List[float] = []
    neg_strikes: List[float] = []
    pos_gex_total: float = 0.0
    neg_gex_total: float = 0.0

    for strike, signed in gex.items():
        if low <= strike <= high:
            if signed > 0:
                pos_strikes.append(strike)
                pos_gex_total += signed
            elif signed < 0:
                neg_strikes.append(strike)
                neg_gex_total += signed  # neg_gex_total is negative

    in_tug = len(pos_strikes) > 0 and len(neg_strikes) > 0

    zone_low = min(pos_strikes + neg_strikes) if in_tug else 0.0
    zone_high = max(pos_strikes + neg_strikes) if in_tug else 0.0

    # balance: +1 = all positive, -1 = all negative, 0 = perfectly balanced
    total_mag = pos_gex_total + abs(neg_gex_total)
    if total_mag > 0:
        gex_balance = (pos_gex_total - abs(neg_gex_total)) / total_mag
    else:
        gex_balance = 0.0

    return {
        "in_tug_of_war": in_tug,
        "zone_low": round(zone_low, 4),
        "zone_high": round(zone_high, 4),
        "positive_strikes": len(pos_strikes),
        "negative_strikes": len(neg_strikes),
        "positive_gex": round(pos_gex_total, 4),
        "negative_gex": round(neg_gex_total, 4),
        "gex_balance": round(gex_balance, 6),
    }
