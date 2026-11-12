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
from datetime import UTC, datetime
from statistics import median
from typing import Any

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _finite(value: Any) -> float | None:
    """Coerce a value to a finite float, or None when it is missing/invalid."""
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _is_call(c: dict[str, Any]) -> bool:
    """True if contract is a call. Accepts 'C', 'CALL', 'call' (any case)."""
    t = str(c.get("type", "")).upper()
    return t in ("C", "CALL")


def _oi(c: dict[str, Any]) -> float:
    """Open interest, tolerant to 'open_interest' or 'oi' field names."""
    val = c.get("open_interest")
    if val is None:
        val = c.get("oi", 0)
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _strike(c: dict[str, Any]) -> float:
    try:
        return float(c.get("strike", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _gamma(c: dict[str, Any]) -> float:
    try:
        val = float(c.get("gamma", 0) or 0)
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return val
    except (TypeError, ValueError):
        return 0.0


def _gex_per_strike(spot: float, contracts: list[dict[str, Any]]) -> dict[float, float]:
    """
    Aggregate signed GEX per strike using the same convention as
    `calc_gamma_flip_levels` in advanced_analytics.py:

        gex_unit  = gamma * oi * 100 * spot * spot * 0.01
        signed    = +gex_unit for calls, -gex_unit for puts
    """
    out: dict[float, float] = {}
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


def _gross_per_strike(spot: float, contracts: list[dict[str, Any]]) -> dict[float, float | None]:
    """
    GROSS (unsigned) exposure per OBSERVED strike: ``|call| + |put|``.

    Net signed GEX cancels to zero at a strike that carries large offsetting
    call and put exposure. Thin-area detection must therefore measure gross
    exposure: a zero net sum is not a thin strike.

    Measured zero OI/gamma stays zero. Missing or invalid inputs leave the
    entire strike unknown, including when another leg has usable exposure:
    a partial sum cannot establish that the strike is thin.
    """
    out: dict[float, float | None] = {}
    if not contracts or not spot or spot <= 0:
        return out
    for c in contracts:
        strike = _finite(c.get("strike"))
        if strike is None or strike <= 0:
            continue
        out.setdefault(strike, 0.0)
        oi = _finite(c.get("open_interest") if c.get("open_interest") is not None else c.get("oi"))
        gamma = _finite(c.get("gamma"))
        if oi is None or gamma is None or oi < 0 or gamma < 0:
            out[strike] = None
            continue
        if out[strike] is not None:
            exposure = gamma * oi * 100.0 * spot * spot * 0.01
            out[strike] = out[strike] + exposure if math.isfinite(exposure) else None
    return out


def _adjacent_gaps(strikes: list[float]) -> list[float]:
    """Positive gaps between adjacent strikes in an ascending ladder."""
    return [b - a for a, b in zip(strikes, strikes[1:], strict=False) if b > a]


# A gap wider than 1.5x the expected strike spacing hides at least one listed
# strike between two observed strikes: continuity is broken there.
_SPACING_TOLERANCE = 0.5


def _expected_strike_step(
    strikes: list[float],
    *,
    expected_step: float | None = None,
    expected_strikes: list[float] | None = None,
) -> float | None:
    """
    Expected spacing between listed strikes, carried from the SAME loaded
    observation — never a hardcoded constant.

    Preference order:
      1. an explicit ``expected_step`` supplied by the caller,
      2. the listed ladder in ``expected_strikes`` when the observation
         declares one,
      3. the median adjacent gap of the observed strike ladder.

    Returns ``None`` when no spacing can be derived. The caller must then
    leave continuity UNVERIFIED instead of assuming it, because an assumed
    ladder would bridge strikes that were never loaded.
    """
    supplied = _finite(expected_step)
    if supplied is not None and supplied > 0:
        return supplied
    declared = sorted({
        s for s in (_finite(k) for k in (expected_strikes or []))
        if s is not None and s > 0
    })
    if len(declared) >= 2:
        gaps = _adjacent_gaps(declared)
        if gaps:
            return float(median(gaps))
    observed = sorted(s for s in strikes if s > 0)
    if len(observed) >= 2:
        gaps = _adjacent_gaps(observed)
        if gaps:
            return float(median(gaps))
    return None


def _omitted_steps(gap: float, step: float) -> int:
    """How many listed strikes are missing inside one ladder gap."""
    if step <= 0:
        return 0
    return max(0, int(round(gap / step)) - 1)


# ---------------------------------------------------------------------------
# Function 1: Flip zones
# ---------------------------------------------------------------------------

def calc_flip_zones(
    spot: float,
    contracts: list[dict[str, Any]],
    *,
    window_pct: float = 0.05,
) -> dict[str, Any]:
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
    cumulative: list[float] = []
    running = 0.0
    for k in strikes:
        running += gex[k]
        cumulative.append(running)

    zones: list[dict[str, Any]] = []
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
        flip_price = (k1 + k2) / 2.0 if denom == 0 else k1 + (k2 - k1) * (-prev_c / denom)

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

def _history_samples(
    history: list[dict[str, Any]],
) -> tuple[list[tuple[datetime, float]], int, int]:
    """
    Reduce timestamped spot history to ordered, DISTINCT samples.

    Repeated identical timestamps are ONE sample: a replayed, re-sent or
    de-duplicated row is not a second observation, so it can never add a tap.
    Rows without a usable timestamp (or with a missing/invalid spot) are
    dropped and counted, never guessed. Samples come back in time order so a
    sustained visit can be told apart from the visit that follows it.
    """
    seen: dict[str, tuple[datetime, float]] = {}
    duplicates = 0
    unusable = 0
    for h in history or []:
        if not isinstance(h, dict):
            unusable += 1
            continue
        spot = _finite(h.get("spot"))
        ts = _parse_ts(h.get("timestamp"))
        if spot is None or ts is None:
            unusable += 1
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        key = ts.astimezone(UTC).isoformat()
        if key in seen:
            duplicates += 1
            continue
        seen[key] = (ts, spot)
    ordered = sorted(seen)
    return [seen[k] for k in ordered], duplicates, unusable


def _visit_episodes(
    samples: list[tuple[datetime, float]],
    strike: float,
    band_pct: float,
) -> tuple[int, int]:
    """
    Count visit episodes at ``strike`` over time-ordered samples.

    An episode is a maximal run of consecutive samples inside the tap band.
    Spot resting on the strike for many samples is ONE sustained visit; only
    leaving the band and returning starts another episode.
    """
    episodes = 0
    visit_samples = 0
    inside = False
    for _ts, spot in samples:
        if abs(spot - strike) / strike <= band_pct:
            visit_samples += 1
            if not inside:
                episodes += 1
                inside = True
        else:
            inside = False
    return episodes, visit_samples


def calc_node_lifecycle(
    spot: float,
    contracts: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    tap_band_pct: float = 0.001,
    min_history_samples: int = 2,
) -> dict[str, Any]:
    """
    Classify the top 10 strikes by |GEX| as Fresh / Tested / Delivered /
    Decaying from VISIT EPISODES in the supplied timestamped history.

    F08/F09/F10: unknown history MUST stay unknown. Missing history, rows
    without a usable timestamp, and fewer than ``min_history_samples``
    DISTINCT samples all resolve to state 'unknown' — an untouched label
    needs adequate same-scope price history, and one sample cannot support
    it. ``tap_probability`` stays None with reason 'UNCALIBRATED' (outcome
    probabilities are not hardcoded here), and the legacy schedule is kept
    only as ``legacy_tap_schedule`` for compatibility, explicitly
    uncalibrated.

    Duplicate timestamps are one sample, so a replayed row, a repeated poll
    or a sustained dwell on the strike can never inflate the tap count.

    ``min_history_samples`` guards the UNTOUCHED label only: with fewer
    distinct samples the history cannot support "fresh", so such a node is
    reported as 'unknown' with reason HISTORY_INSUFFICIENT while its measured
    zero-visit count stays visible. Observed visits need no such guard.
    """
    def _unknown_nodes(reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "strike": round(strike, 4),
                    "net_gex": round(net_gex, 4),
                    "taps": None,
                    "visit_episodes": None,
                    "state": "unknown",
                    "tap_probability": None,
                    "tap_probability_reason": "UNCALIBRATED",
                    "reason": reason,
                    "legacy_tap_schedule": None,
                }
                for strike, net_gex in ranked if strike > 0
            ],
            "history_status": "unknown",
            "reason": reason,
            **extra,
        }

    if not spot or spot <= 0:
        return {"nodes": [], "history_status": "unknown", "reason": "INVALID_SPOT"}

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return {"nodes": [], "history_status": "unknown", "reason": "NO_GEX"}

    # Top 10 strikes by absolute net GEX.
    ranked = sorted(gex.items(), key=lambda kv: abs(kv[1]), reverse=True)[:10]

    samples, duplicates, unusable = _history_samples(history)
    n_samples = len(samples)
    ledger = {
        "history_samples": n_samples,
        "duplicate_timestamps_dropped": duplicates,
        "unusable_rows": unusable,
    }

    if n_samples == 0:
        return _unknown_nodes("HISTORY_UNKNOWN", **ledger)

    # The untouched ("fresh") label needs adequate same-scope history; an
    # observed visit does not.
    adequate = n_samples >= min_history_samples

    nodes: list[dict[str, Any]] = []
    for strike, net_gex in ranked:
        if strike <= 0:
            continue
        episodes, visit_samples = _visit_episodes(samples, strike, tap_band_pct)
        if episodes == 0 and not adequate:
            nodes.append({
                "strike": round(strike, 4),
                "net_gex": round(net_gex, 4),
                "taps": 0,
                "visit_episodes": 0,
                "visit_samples": 0,
                "state": "unknown",
                "tap_probability": None,
                "tap_probability_reason": "UNCALIBRATED",
                "reason": "HISTORY_INSUFFICIENT",
                "legacy_tap_schedule": None,
            })
            continue
        if episodes == 0:
            state = "fresh"
        elif episodes == 1:
            state = "tested"
        elif episodes == 2:
            state = "delivered"
        else:
            state = "decaying"
        legacy = {0: 80, 1: 66, 2: 33}.get(min(episodes, 3), 10)
        nodes.append({
            "strike": round(strike, 4),
            "net_gex": round(net_gex, 4),
            "taps": episodes,
            "visit_episodes": episodes,
            "visit_samples": visit_samples,
            "state": state,
            "tap_probability": None,
            "tap_probability_reason": "UNCALIBRATED",
            "legacy_tap_schedule": legacy,
        })

    return {
        "nodes": nodes,
        "history_status": "ok",
        "min_history_samples": min_history_samples,
        **ledger,
    }


# ---------------------------------------------------------------------------
# Function 3: Air pockets
# ---------------------------------------------------------------------------

def _air_pockets_empty(reason: str) -> dict[str, Any]:
    """Degenerate air-pocket answer with the coverage fields still explicit."""
    return {
        "air_pockets": [],
        "basis": "gross_exposure",
        "coverage_status": "unknown",
        "reason": reason,
        "strikes_observed": 0,
        "strikes_unknown_exposure": 0,
        "expected_step": None,
        "n_omitted_strikes": 0,
    }


def calc_air_pockets(
    spot: float,
    contracts: list[dict[str, Any]],
    *,
    min_gap_pct: float = 0.005,
    expected_step: float | None = None,
    expected_strikes: list[float] | None = None,
    spacing_tolerance: float = _SPACING_TOLERANCE,
) -> dict[str, Any]:
    """
    Contiguous ranges of strikes where GROSS exposure is below 20% of the
    local median (median of gross exposure for strikes within ±5% of spot)
    AND the range spans at least ``spot * min_gap_pct`` in price.

    Two semantics the legacy ``|net GEX|`` version got wrong:

    1. **Gross, not net.** Large offsetting call and put exposure at one
       strike nets to zero. Net magnitude would read that strike as thin;
       gross exposure keeps it dense, so a cancellation is never mistaken
       for an air pocket.
    2. **Measured continuity.** The expected strike spacing is carried from
       the SAME loaded observation (an explicit step, the declared ladder,
       or the median adjacent gap of the observed strikes). A gap wider than
       that spacing hides at least one listed strike, so a thin run BREAKS
       there instead of bridging strikes that were never loaded. When no
       spacing can be derived, ``coverage_status`` is 'unknown' and
       continuity is left unverified — never assumed.

    Returns
    -------
    dict with keys ``air_pockets`` (list of ``{low, high, span_pct,
    max_abs_gex_in_run, max_gross_gex_in_run}``), plus the coverage
    disclosure: ``basis``, ``coverage_status``, ``strikes_observed``,
    ``expected_step``, ``n_omitted_strikes``. Empty list on degenerate input.
    """
    if not spot or spot <= 0:
        return _air_pockets_empty("INVALID_SPOT")

    gross = _gross_per_strike(spot, contracts)
    if not gross:
        return _air_pockets_empty("NO_OBSERVED_STRIKES")

    strikes = sorted(gross.keys())
    step = _expected_strike_step(
        strikes, expected_step=expected_step, expected_strikes=expected_strikes,
    )
    spacing_known = step is not None and step > 0
    unknown_exposure = sum(value is None for value in gross.values())
    coverage_ok = spacing_known and unknown_exposure == 0
    # Continuity is only enforceable when the ladder spacing is known.
    max_step = step * (1.0 + spacing_tolerance) if spacing_known else None

    # Local median of gross exposure using strikes within ±5% of spot.
    near_window_low = spot * 0.95
    near_window_high = spot * 1.05
    near_vals = [gross[k] for k in strikes if near_window_low <= k <= near_window_high and gross[k] is not None]
    if not near_vals:
        empty = _air_pockets_empty("NO_STRIKES_NEAR_SPOT")
        empty["strikes_observed"] = len(strikes)
        empty["strikes_unknown_exposure"] = unknown_exposure
        empty["expected_step"] = round(step, 6) if step else None
        return empty
    local_median = median(near_vals)
    if local_median <= 0:
        # Degenerate: everything is zero in the local window. An observed
        # flat-zero band is not actionable signal, so no pocket is reported.
        empty = _air_pockets_empty("FLAT_ZERO_LOCAL_EXPOSURE")
        empty["strikes_observed"] = len(strikes)
        empty["strikes_unknown_exposure"] = unknown_exposure
        empty["expected_step"] = round(step, 6) if step else None
        return empty

    threshold = 0.2 * local_median
    min_span = spot * min_gap_pct

    pockets: list[dict[str, Any]] = []
    run_idx: list[int] = []
    omitted = 0

    def _flush() -> None:
        if not run_idx:
            return
        low_k = strikes[run_idx[0]]
        high_k = strikes[run_idx[-1]]
        span = high_k - low_k
        if span < min_span:
            run_idx.clear()
            return
        run_max = max(gross[strikes[i]] for i in run_idx)
        pockets.append({
            "low": round(low_k, 4),
            "high": round(high_k, 4),
            "span_pct": round(span / spot, 6),
            "max_abs_gex_in_run": round(run_max, 4),
            "max_gross_gex_in_run": round(run_max, 4),
        })
        run_idx.clear()

    for i, k in enumerate(strikes):
        if i and max_step is not None:
            gap = k - strikes[i - 1]
            if gap > max_step:
                # An unobserved (or anomalously spaced) listed strike sits
                # between two observed strikes: a thin run cannot bridge it.
                omitted += _omitted_steps(gap, step)
                _flush()
        if gross[k] is not None and gross[k] < threshold:
            run_idx.append(i)
        else:
            _flush()
    # Trailing run.
    _flush()

    return {
        "air_pockets": pockets,
        "basis": "gross_exposure",
        "coverage_status": "ok" if coverage_ok else "unknown",
        "strikes_observed": len(strikes),
        "strikes_unknown_exposure": unknown_exposure,
        "expected_step": round(step, 6) if step else None,
        "n_omitted_strikes": omitted,
    }


# ---------------------------------------------------------------------------
# Wave 2 — Function 4: Beach ball
# ---------------------------------------------------------------------------

def _king_node_strike(gex: dict[float, float]) -> float | None:
    """Strike with max |net_gex|. None if dict is empty."""
    if not gex:
        return None
    return max(gex.keys(), key=lambda k: abs(gex[k]))


def detect_beach_ball(
    spot: float,
    contracts: list[dict[str, Any]],
    *,
    king_node: float | None = None,
) -> dict[str, Any]:
    """
    Beach Ball: spot is stretched past the King Node (largest |GEX| strike).
    Overshoot/reversion setup.

    Active when ``abs(spot - king_node) / king_node > 0.005`` (50bps).

    The ONLY supported reading is the measured distance — in points
    (``spot_distance_points``, signed) and in percent
    (``spot_distance_pct``). The legacy probability-like ``confidence``
    (``min(1.0, distance_pct / 0.02)``) is retired: a distance ratio is not
    a calibrated outcome probability, and no time series exists here to
    support one. Overshoot, unwind and squeeze stay unverified hypotheses.
    """
    inactive: dict[str, Any] = {
        "pattern": "beach_ball",
        "active": False,
        "king_node": None,
        "spot_distance_points": None,
        "spot_distance_pct": None,
        "direction": "at",
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

    return {
        "pattern": "beach_ball",
        "active": active,
        "king_node": round(float(king_node), 4),
        "spot_distance_points": round(spot - float(king_node), 4),
        "spot_distance_pct": round(distance_pct, 6),
        "direction": direction,
    }


# ---------------------------------------------------------------------------
# Wave 2 — Function 5: Reverse rug
# ---------------------------------------------------------------------------

def detect_reverse_rug(
    spot: float,
    contracts: list[dict[str, Any]],
    *,
    min_strength: float = 0.0,
) -> dict[str, Any]:
    """
    Reverse Rug: positive floor below spot, negative ceiling above.
    Support holds, bounce runs.

    Finds the largest positive-GEX strike below spot (the floor) and the
    largest negative-GEX strike above spot (the ceiling).

    Pattern active when both exist AND ``abs(floor_gex) > min_strength``
    AND ``abs(ceiling_gex) > min_strength``.
    """
    inactive: dict[str, Any] = {
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

    floor_strike: float | None = None
    floor_gex: float = 0.0
    ceiling_strike: float | None = None
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
    contracts: list[dict[str, Any]],
    *,
    max_dominant_share: float = 0.15,
    window_pct: float = 0.05,
) -> dict[str, Any]:
    """
    Rainbow Road: no dominant structure within ±window_pct of spot. Chaos.

    Active when the top |GEX| strike's share of the local total is below
    ``max_dominant_share`` — i.e. GEX is spread across many strikes and
    no single node dominates.

    ``n_strikes_significant`` is the count of strikes with
    ``|gex| > 0.5 * mean(|gex|)`` in the same window.
    """
    inactive: dict[str, Any] = {
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

def _parse_ts(value: Any) -> datetime | None:
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


def _node_exposure(row: dict[str, Any]) -> float | None:
    """Stored exposure of the king node, when the owning history carries it."""
    for key in ("king_node_gex", "king_gex", "king_node_exposure"):
        val = _finite(row.get(key))
        if val is not None:
            return val
    return None


def calc_velocity_mode(history: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Dealer urgency: rate at which the King Node is migrating across the recent
    snapshots in ``history``. Caller passes the last ~30 minutes of data.

    Each entry: ``{"timestamp": iso8601, "king_node_strike": float, "spot": float}``.

    Velocity = ``(king_node[-1] - king_node[0]) / minutes_elapsed`` (signed,
    so an observer can tell which way the node is drifting).

    Mode bands (use ``abs(velocity)``):
        |v| < 0.5     → "calm"
        |v| < 2.0     → "active"
        |v| ≥ 2.0     → "urgent"

    The measured quantity is named: ``quantity`` is strike MIGRATION in
    points per minute. Same-node exposure change (dollars per minute) is a
    DIFFERENT quantity — a node can stay at one strike while its exposure
    grows or shrinks. It is reported separately in ``exposure_change`` and is
    never folded into, or inferred from, the migration rate. When the owning
    history does not carry node exposure, exposure change is 'unknown' with
    reason EXPOSURE_HISTORY_NOT_SUPPLIED rather than a fabricated zero.
    """
    history = history or []
    n = len(history)
    if n < 2:
        return {
            "velocity_strikes_per_min": None,
            "mode": "unknown",
            "n_snapshots": n,
            "quantity": "strike_migration",
            "unit": "points_per_min",
            "reason": "INSUFFICIENT_HISTORY",
        }

    first = history[0]
    last = history[-1]
    try:
        kn0 = float(first.get("king_node_strike"))
        kn1 = float(last.get("king_node_strike"))
    except (TypeError, ValueError):
        return {
            "velocity_strikes_per_min": None,
            "mode": "unknown",
            "n_snapshots": n,
            "quantity": "strike_migration",
            "unit": "points_per_min",
            "reason": "INVALID_KING_NODE",
        }

    t0 = _parse_ts(first.get("timestamp"))
    t1 = _parse_ts(last.get("timestamp"))
    if t0 is None or t1 is None:
        return {
            "velocity_strikes_per_min": None,
            "mode": "unknown",
            "n_snapshots": n,
            "quantity": "strike_migration",
            "unit": "points_per_min",
            "reason": "TIMESTAMP_UNKNOWN",
        }
    minutes = (t1 - t0).total_seconds() / 60.0
    if minutes <= 0:
        return {
            "velocity_strikes_per_min": None,
            "mode": "unknown",
            "n_snapshots": n,
            "quantity": "strike_migration",
            "unit": "points_per_min",
            "reason": "NONPOSITIVE_WINDOW",
        }

    velocity = (kn1 - kn0) / minutes
    mag = abs(velocity)
    if mag < 0.5:
        mode = "calm"
    elif mag < 2.0:
        mode = "active"
    else:
        mode = "urgent"

    exposure_change: dict[str, Any] = {
        "measured": False,
        "reason": "EXPOSURE_HISTORY_NOT_SUPPLIED",
    }
    e0 = _node_exposure(first)
    e1 = _node_exposure(last)
    if e0 is not None and e1 is not None and kn0 != kn1:
        exposure_change = {"measured": False, "reason": "NODE_CHANGED"}
    elif e0 is not None and e1 is not None:
        exposure_change = {
            "measured": True,
            "unit": "dollars_per_min",
            "value": round((e1 - e0) / minutes, 4),
        }

    return {
        "velocity_strikes_per_min": round(velocity, 6),
        "mode": mode,
        "n_snapshots": n,
        "quantity": "strike_migration",
        "unit": "points_per_min",
        "exposure_change": exposure_change,
    }


# ---------------------------------------------------------------------------
# Wave 2 — Function 8: Trinity confluence
# ---------------------------------------------------------------------------

def _side_of_flip(spot: Any, gamma_flip: Any) -> str | None:
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


def _all_equal_and_present(values: list[Any]) -> bool:
    """True when every value is non-None and they all compare equal."""
    if not values or any(v is None for v in values):
        return False
    first = values[0]
    return all(v == first for v in values)


def calc_trinity_confluence(
    spx_snapshot: dict[str, Any],
    spy_snapshot: dict[str, Any],
    qqq_snapshot: dict[str, Any],
) -> dict[str, Any]:
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
    aligned: list[str] = []
    divergences: list[str] = []

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

def _trend_direction(values: list[float]) -> str:
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
    snapshots: list[dict[str, Any]],
    ticker: str,
    *,
    lookback_days: int = 20,
) -> dict[str, Any]:
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

    floor_series: list[float] = []
    ceiling_series: list[float] = []

    for snap in usable:
        snap_spot = snap.get("spot", spot)
        snap_contracts = snap.get("contracts", [])
        if not snap_spot or snap_spot <= 0:
            continue
        gex = _gex_per_strike(snap_spot, snap_contracts)
        if not gex:
            continue

        # Floor: largest positive-GEX strike below snap_spot
        floor_strike: float | None = None
        floor_gex_val: float = 0.0
        for strike, signed in gex.items():
            if strike < snap_spot and signed > 0 and signed > floor_gex_val:
                floor_strike = strike
                floor_gex_val = signed

        # Ceiling: most negative-GEX strike above snap_spot
        ceiling_strike: float | None = None
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
    nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    F08: lifecycle-derived `oi_trend` is NOT an OI observation. This function
    now requires explicit OI evidence: nodes must carry `oi_observations`
    (list of {oi, effective_date}) or `oi_trend_source == 'observed'`.
    Lifecycle-only trends → classification 'unknown' with reason
    OI_TREND_UNOBSERVED. Dealer-intent labels ('real'/'hedge') are deprecated
    proxies; they describe observed OI direction only, never intent.

    Classification rules (observed OI only):
        - gamma_sign == "positive" AND oi_trend == "growing"  → "real"
        - gamma_sign == "negative" AND oi_trend == "fading"   → "hedge"
        - otherwise                                            → "unknown"
    """
    nodes = nodes or []
    classified: list[dict[str, Any]] = []
    real_count = 0
    hedge_count = 0

    for node in nodes:
        gamma_sign = str(node.get("gamma_sign", "")).lower()
        oi_trend = str(node.get("oi_trend", "")).lower()
        trend_source = str(node.get("oi_trend_source", "")).lower()
        observations = {}
        observed_rows = node.get("oi_observations")
        for obs in observed_rows if isinstance(observed_rows, list) else []:
            if not isinstance(obs, dict):
                continue
            try:
                from datetime import date
                day = date.fromisoformat(obs["effective_date"])
                oi = obs["oi"]
                if isinstance(oi, bool) or not isinstance(oi, (int, float)) or not math.isfinite(oi) or oi < 0:
                    continue
                observations[day] = oi
            except (KeyError, ValueError, TypeError):
                continue
        has_obs = len(observations) >= 2
        if has_obs:
            before, after = [observations[d] for d in sorted(observations)[-2:]]
            oi_trend = "growing" if after > before else "fading" if after < before else "unchanged"

        if not oi_trend or (trend_source not in ("observed", "oi_history") and not has_obs):
            # Unobserved trend (e.g. derived from lifecycle state) → unknown.
            classified.append({**node, "classification": "unknown",
                               "classification_reason": "OI_TREND_UNOBSERVED"})
            continue

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
    contracts: list[dict[str, Any]],
    *,
    threshold_pct: float = 0.3,
) -> dict[str, Any]:
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
    call_gex: dict[float, float] = {}
    put_gex: dict[float, float] = {}
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

    stacked: list[dict[str, Any]] = []
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

# ---------------------------------------------------------------------------
# Replay session manifest — scope-aware grouping
# ---------------------------------------------------------------------------

def _session_gaps(asofs: list[str], expected_cadence_s: float | None) -> list[dict[str, Any]]:
    """
    Declared gaps inside ONE scope's ordered snapshots.

    Same rule the owning store manifest uses: an interval beyond 1.5x the
    expected cadence is an explicit gap (never silently interpolated).
    Gaps are only measurable when a cadence was supplied.
    """
    if not expected_cadence_s or expected_cadence_s <= 0 or len(asofs) < 2:
        return []
    gaps: list[dict[str, Any]] = []
    for a, b in zip(asofs, asofs[1:], strict=False):
        ta, tb = _parse_ts(a), _parse_ts(b)
        if ta is None or tb is None:
            continue
        gap_s = (tb - ta).total_seconds()
        if gap_s <= expected_cadence_s * 1.5:
            continue
        gaps.append({
            "from": a,
            "to": b,
            "gap_s": round(gap_s, 1),
            "missing_beats": max(0, round(gap_s / expected_cadence_s) - 1),
        })
    return gaps


def group_replay_sessions(
    rows: list[dict[str, Any]] | None,
    *,
    expected_cadence_s: float | None = None,
    day: str = "",
    ticker: str = "",
) -> dict[str, Any]:
    """
    Group one UTC day's stored replay rows by QUERY SCOPE, and refuse to
    certify one session across scopes.

    A ticker/day row list is not one market session when the rows were
    produced by different query scopes (different expiry sets, expiries
    counts, or query keys): the snapshots describe different observations,
    and gap or heartbeat arithmetic across them would silently mix them.
    So the rows are grouped per scope, each scope keeps its own snapshot
    list and its own gap accounting, and the day-level certification is
    explicitly refused with ``MIXED_QUERY_SCOPES``.

    A single-scope day still certifies one session. A day with no usable
    rows is an empty state. A day whose rows carry no scope lands in a
    disclosed 'unknown' scope bucket rather than being dropped. Rows without
    a usable ``asof`` timestamp are excluded and counted — never dated.

    Day attribution is the caller's stored-timestamp prefix (the same key
    the owning manifest matches with ``LIKE day%``); ``day`` is echoed for
    disclosure, not re-derived here.
    """
    groups: dict[str, dict[str, Any]] = {}
    n_snapshots = 0
    rows_without_timestamp = 0
    for row in rows or []:
        if not isinstance(row, dict):
            rows_without_timestamp += 1
            continue
        asof = row.get("asof") or row.get("asof_ts") or row.get("as_of")
        observed_at = _parse_ts(asof) if isinstance(asof, str) else None
        if observed_at is None or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            rows_without_timestamp += 1
            continue
        n_snapshots += 1
        scope = (
            row.get("scope")
            or row.get("query_key")
            or row.get("scope_id")
            or ""
        )
        scope = str(scope).strip() or "unknown"
        bucket = groups.setdefault(scope, {
            "scope": scope,
            "n_snapshots": 0,
            "snapshots": [],
            "gaps": [],
        })
        bucket["snapshots"].append({
            "snapshot_id": row.get("snapshot_id") or row.get("id"),
            "asof": asof.strip(),
            "n_contracts": row.get("n_contracts"),
        })
        bucket["n_snapshots"] += 1

    for bucket in groups.values():
        bucket["snapshots"].sort(key=lambda s: _parse_ts(s["asof"]).astimezone(UTC))
        bucket["gaps"] = _session_gaps(
            [s["asof"] for s in bucket["snapshots"]], expected_cadence_s,
        )

    sessions = [groups[k] for k in sorted(groups)]
    out: dict[str, Any] = {
        "ticker": (ticker or "").upper() or None,
        "day": day or None,
        "n_scopes": len(sessions),
        "n_snapshots": n_snapshots,
        "rows_without_timestamp": rows_without_timestamp,
        "gap_coverage": "ok" if expected_cadence_s and expected_cadence_s > 0 and sessions and not rows_without_timestamp else "unknown",
        "sessions": sessions,
    }

    if not sessions:
        out["status"] = "unavailable" if rows_without_timestamp else "empty"
        out["reason"] = "INVALID_TIMESTAMPS" if rows_without_timestamp else "NO_STORED_ROWS"
    elif len(sessions) == 1:
        out["status"] = "partial" if rows_without_timestamp else "ok"
        if rows_without_timestamp:
            out["reason"] = "INVALID_TIMESTAMPS"
    else:
        out["status"] = "refused"
        out["reason"] = "MIXED_QUERY_SCOPES"
        out["note"] = (
            "A UTC-day list of rows across query scopes cannot certify one "
            "market session; each scope keeps its own rows and gap accounting."
        )
    return out


# ---------------------------------------------------------------------------
# Wave 3 — Function 12: Tug-of-war zones
# ---------------------------------------------------------------------------

def calc_tug_of_war_zones(
    contracts: list[dict[str, Any]],
    spot: float,
    *,
    band_pct: float = 0.01,
) -> dict[str, Any]:
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

    pos_strikes: list[float] = []
    neg_strikes: list[float] = []
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
    gex_balance = (pos_gex_total - abs(neg_gex_total)) / total_mag if total_mag > 0 else 0.0

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
