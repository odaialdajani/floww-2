"""
Advanced Options Analytics Module
Implements institutional-grade analytics from the floe library:

- Implied PDF (Breeden-Litzenberger)
- Hedge Impulse Curve (gamma + vanna combined)
- Pressure Cloud (stability/acceleration zones)
- Charm Integral (time-decay pressure)
- Market Regime Detection (from IV surface)
- Enhanced opportunity detection
"""

import math
from collections import defaultdict
from typing import Any, Dict, List

import numpy as np

from bs_greeks import bs_call_price, bs_charm, bs_gamma, bs_vanna

# ============================================================================
# Implied PDF (Breeden-Litzenberger)
# ============================================================================

def calc_implied_pdf(spot: float, contracts: List[Dict[str, Any]],
                     risk_free_rate: float = 0.045) -> Dict[str, Any]:
    """
    Compute implied probability density function using Breeden-Litzenberger.
    Uses numerical second derivative of call prices w.r.t. strike.

    Returns strike-level PDF with summary statistics:
    - most_likely_price (mode)
    - median_price
    - expected_value (mean)
    - expected_move (std dev)
    - tail_skew
    - cumulative probabilities
    """
    if spot <= 0 or not contracts:
        return {"error": "No data", "strike_probabilities": []}

    # Group calls by expiry
    by_expiry = defaultdict(list)
    for c in contracts:
        if c["type"] == "call" and c.get("iv", 0) > 0 and c.get("strike", 0) > 0:
            by_expiry[c["expiry"]].append(c)

    if not by_expiry:
        return {"error": "No call options", "strike_probabilities": []}

    # Use the nearest expiry with enough data
    best_expiry = None
    best_calls = []
    for exp in sorted(by_expiry.keys()):
        calls = by_expiry[exp]
        if len(calls) >= 5:
            best_expiry = exp
            best_calls = calls
            break

    if not best_calls or len(best_calls) < 5:
        return {"error": "Insufficient call data", "strike_probabilities": []}

    # Sort by strike
    sorted_calls = sorted(best_calls, key=lambda c: c["strike"])
    len(sorted_calls)

    # Compute call prices using BS at each strike
    # Use mid-price approximation: since we don't have bid/ask, use BS price from IV
    call_prices = []
    strikes = []
    for c in sorted_calls:
        strike = c["strike"]
        iv = c["iv"]
        T = c.get("T", 1/365)
        if iv <= 0 or T <= 0:
            continue
        price = bs_call_price(spot, strike, T, iv, r=risk_free_rate)
        call_prices.append(price)
        strikes.append(strike)

    if len(strikes) < 5:
        return {"error": "Insufficient valid prices", "strike_probabilities": []}

    # Compute second derivative numerically (central difference)
    strike_probs = []
    for i in range(len(strikes)):
        if i == 0 or i == len(strikes) - 1:
            strike_probs.append({"strike": strikes[i], "probability": 0.0})
            continue

        k_prev = strikes[i - 1]
        k_curr = strikes[i]
        k_next = strikes[i + 1]

        c_prev = call_prices[i - 1]
        c_curr = call_prices[i]
        c_next = call_prices[i + 1]

        dk = k_next - k_prev
        if abs(dk) < 1e-9:
            strike_probs.append({"strike": k_curr, "probability": 0.0})
            continue

        # Second derivative: d2C/dK2
        d2 = (c_next - 2 * c_curr + c_prev) / (dk * dk)
        prob = max(d2, 0.0)  # probability must be non-negative
        strike_probs.append({"strike": k_curr, "probability": prob})

    # Normalize to sum to 1
    total_prob = sum(sp["probability"] for sp in strike_probs)
    if total_prob < 1e-12:
        return {"error": "Zero probability mass", "strike_probabilities": []}

    for sp in strike_probs:
        sp["probability"] = sp["probability"] / total_prob

    # Summary statistics
    # Mode (most likely price)
    most_likely = max(strike_probs, key=lambda sp: sp["probability"])

    # Median (50th percentile)
    cum = 0.0
    median_price = strike_probs[len(strike_probs) // 2]["strike"]
    for sp in strike_probs:
        cum += sp["probability"]
        if cum >= 0.5:
            median_price = sp["strike"]
            break

    # Expected value (mean)
    expected_value = sum(sp["strike"] * sp["probability"] for sp in strike_probs)

    # Variance and std dev
    variance = sum((sp["strike"] - expected_value) ** 2 * sp["probability"] for sp in strike_probs)
    expected_move = math.sqrt(variance)

    # Tail skew
    left_tail = sum(sp["probability"] for sp in strike_probs if sp["strike"] < expected_value)
    right_tail = sum(sp["probability"] for sp in strike_probs if sp["strike"] >= expected_value)
    tail_skew = right_tail / max(left_tail, 1e-9)

    # Cumulative probabilities relative to spot
    cum_below = sum(sp["probability"] for sp in strike_probs if sp["strike"] < spot)
    cum_above = sum(sp["probability"] for sp in strike_probs if sp["strike"] > spot)

    # Probability within 1 standard deviation
    lower_1sd = spot - expected_move
    upper_1sd = spot + expected_move
    prob_1sd = sum(sp["probability"] for sp in strike_probs if lower_1sd <= sp["strike"] <= upper_1sd)

    return {
        "expiry": best_expiry,
        "strike_probabilities": strike_probs,
        "most_likely_price": most_likely["strike"],
        "median_price": median_price,
        "expected_value": round(expected_value, 2),
        "expected_move": round(expected_move, 2),
        "expected_move_pct": round(expected_move / spot * 100, 2),
        "tail_skew": round(tail_skew, 4),
        "cumulative_below_spot": round(cum_below, 4),
        "cumulative_above_spot": round(cum_above, 4),
        "prob_within_1sd": round(prob_1sd, 4),
        "interpretation": {
            "skew": "bullish" if tail_skew > 1.1 else "bearish" if tail_skew < 0.9 else "symmetric",
            "conviction": "high" if most_likely["probability"] > 0.15 else "moderate" if most_likely["probability"] > 0.08 else "low",
        }
    }


# ============================================================================
# Market Regime Detection (from IV surface)
# ============================================================================

def calc_market_regime(spot: float, contracts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Derive market regime from IV surface characteristics.
    Uses ATM IV, skew, and curvature to classify regime.
    """
    if spot <= 0 or not contracts:
        return {"regime": "unknown", "atm_iv": 0}

    # Get ATM IV
    atm_contract = min(contracts, key=lambda c: abs(c["strike"] - spot))
    atm_iv = atm_contract.get("iv", 0.2)

    # Compute skew (slope of IV across strikes)
    otm_puts = [c for c in contracts if c["type"] == "put" and c["strike"] < spot * 0.95]
    otm_calls = [c for c in contracts if c["type"] == "call" and c["strike"] > spot * 1.05]

    avg_put_iv = np.mean([c["iv"] for c in otm_puts]) if otm_puts else atm_iv
    avg_call_iv = np.mean([c["iv"] for c in otm_calls]) if otm_calls else atm_iv

    # Skew: put IV - call IV (positive = put skew = fear)
    skew = avg_put_iv - avg_call_iv

    # Curvature (butterfly): average wing IV - ATM IV
    curvature = (avg_put_iv + avg_call_iv) / 2 - atm_iv

    # Spot-vol correlation estimate from skew
    implied_spot_vol_corr = max(-0.95, min(0.5, skew * 0.15))

    # Vol-of-vol from curvature
    implied_vol_of_vol = math.sqrt(abs(curvature)) * 2.0 * atm_iv if curvature > 0 else atm_iv * 0.5

    # Regime classification
    if atm_iv < 0.15:
        regime = "calm"
    elif atm_iv < 0.20:
        regime = "normal"
    elif atm_iv < 0.35:
        regime = "stressed"
    else:
        regime = "crisis"

    # Expected daily moves
    expected_daily_spot_move = atm_iv / math.sqrt(252)
    expected_daily_vol_move = implied_vol_of_vol / math.sqrt(252)

    return {
        "regime": regime,
        "atm_iv": round(atm_iv, 4),
        "atm_strike": atm_contract["strike"],
        "skew": round(skew, 4),
        "curvature": round(curvature, 4),
        "implied_spot_vol_corr": round(implied_spot_vol_corr, 4),
        "implied_vol_of_vol": round(implied_vol_of_vol, 4),
        "expected_daily_spot_move": round(expected_daily_spot_move, 4),
        "expected_daily_spot_move_pct": round(expected_daily_spot_move * 100, 2),
        "expected_daily_vol_move": round(expected_daily_vol_move, 4),
        "interpretation": {
            "fear_greed": "extreme_fear" if skew > 0.05 else "fear" if skew > 0.02 else "greed" if skew < -0.02 else "neutral",
            "tail_risk": "elevated" if curvature > 0.03 else "normal",
            "environment": regime,
        }
    }


# ============================================================================
# Hedge Impulse Curve (gamma + vanna combined response)
# ============================================================================

def calc_hedge_impulse_curve(spot: float, contracts: List[Dict[str, Any]],
                              ticker: str = "",
                              range_pct: float = 3.0,
                              step_pct: float = 0.5) -> Dict[str, Any]:
    """
    Compute the hedge impulse curve H(S) = Gamma(S) - (k/S) * Vanna(S)
    across a price grid. Shows where dealers amplify vs dampen price moves.
    """
    if spot <= 0 or not contracts:
        return {"curve": [], "regime": "neutral"}

    q = {"SPY": 0.013, "QQQ": 0.006, "^SPX": 0.013, "IWM": 0.012}.get(ticker, 0.0)

    # Extract strike-space exposures
    strikes = []
    gex_values = []
    vex_values = []
    for c in contracts:
        s = c["strike"]
        oi = c.get("oi", 0) or 0
        if oi <= 0 or math.isnan(oi) or math.isinf(oi):
            continue
        gamma = bs_gamma(spot, s, c["T"], c["iv"], q=q)
        vanna = bs_vanna(spot, s, c["T"], c["iv"], q=q)
        if math.isnan(gamma) or math.isinf(gamma) or math.isnan(vanna) or math.isinf(vanna):
            continue
        gex = gamma * oi * 100.0 * spot * spot * 0.01
        vex = vanna * oi * 100.0 * spot * 0.01
        strikes.append(s)
        gex_values.append(gex)
        vex_values.append(vex)

    if not strikes:
        return {"curve": [], "regime": "neutral"}

    # Detect strike spacing
    gaps = [abs(strikes[i] - strikes[i-1]) for i in range(1, len(strikes)) if abs(strikes[i] - strikes[i-1]) > 0]
    strike_spacing = min(gaps) if gaps else 1.0
    kernel_width = 2.0 * strike_spacing

    # Derive spot-vol coupling from skew
    otm_puts = [c for c in contracts if c["type"] == "put" and c["strike"] < spot * 0.95]
    otm_calls = [c for c in contracts if c["type"] == "call" and c["strike"] > spot * 1.05]
    avg_put_iv = np.mean([c["iv"] for c in otm_puts]) if otm_puts else 0.2
    avg_call_iv = np.mean([c["iv"] for c in otm_calls]) if otm_calls else 0.2
    skew = avg_put_iv - avg_call_iv
    implied_corr = max(-0.95, min(0.5, skew * 0.15))
    k = max(2, min(20, -implied_corr * 0.2 * math.sqrt(252)))

    # Build price grid
    grid_min = spot * (1 - range_pct / 100)
    grid_max = spot * (1 + range_pct / 100)
    grid_step = spot * (step_pct / 100)

    curve = []
    price = grid_min
    while price <= grid_max:
        # Kernel smoothing
        gamma_smooth = _kernel_smooth(strikes, gex_values, price, kernel_width)
        vanna_smooth = _kernel_smooth(strikes, vex_values, price, kernel_width)

        # H(S) = Gamma(S) - (k/S) * Vanna(S)
        impulse = gamma_smooth - (k / price) * vanna_smooth

        curve.append({
            "price": round(price, 2),
            "gamma": round(gamma_smooth, 2),
            "vanna": round(vanna_smooth, 2),
            "impulse": round(impulse, 2),
        })
        price += grid_step

    # Find zero crossings
    zero_crossings = []
    for i in range(len(curve) - 1):
        a = curve[i]["impulse"]
        b = curve[i + 1]["impulse"]
        if a * b < 0:
            t = abs(a) / (abs(a) + abs(b))
            cross_price = curve[i]["price"] + t * (curve[i + 1]["price"] - curve[i]["price"])
            zero_crossings.append({
                "price": round(cross_price, 2),
                "direction": "rising" if b > a else "falling",
            })

    # Find extrema
    extrema = []
    for i in range(1, len(curve) - 1):
        prev = curve[i - 1]["impulse"]
        curr = curve[i]["impulse"]
        next_val = curve[i + 1]["impulse"]
        if curr > prev and curr > next_val and curr > 0:
            extrema.append({"price": curve[i]["price"], "impulse": curr, "type": "basin"})
        elif curr < prev and curr < next_val and curr < 0:
            extrema.append({"price": curve[i]["price"], "impulse": curr, "type": "peak"})

    # Impulse at spot
    impulse_at_spot = _interp_impulse(curve, spot)

    # Classify regime
    regime = _classify_impulse_regime(impulse_at_spot, curve, spot)

    # Nearest attractors
    basins_above = [e for e in extrema if e["type"] == "basin" and e["price"] > spot]
    basins_below = [e for e in extrema if e["type"] == "basin" and e["price"] < spot]
    nearest_above = min(basins_above, key=lambda e: e["price"])["price"] if basins_above else None
    nearest_below = max(basins_below, key=lambda e: e["price"])["price"] if basins_below else None

    return {
        "spot": spot,
        "spot_vol_coupling": round(k, 4),
        "kernel_width": round(kernel_width, 2),
        "strike_spacing": round(strike_spacing, 2),
        "curve": curve,
        "zero_crossings": zero_crossings,
        "extrema": extrema,
        "impulse_at_spot": round(impulse_at_spot, 2),
        "regime": regime,
        "nearest_attractor_above": nearest_above,
        "nearest_attractor_below": nearest_below,
    }


def _kernel_smooth(strikes: List[float], values: List[float],
                   eval_price: float, lambda_width: float) -> float:
    """Gaussian kernel smoothing."""
    weighted_sum = 0.0
    weight_sum = 0.0
    for i in range(len(strikes)):
        dist = (strikes[i] - eval_price) / lambda_width
        weight = math.exp(-(dist * dist))
        weighted_sum += values[i] * weight
        weight_sum += weight
    result = weighted_sum / weight_sum if weight_sum > 0 else 0.0
    if math.isnan(result) or math.isinf(result):
        return 0.0
    return result


def _interp_impulse(curve: List[Dict], price: float) -> float:
    """Interpolate impulse at a given price."""
    if not curve:
        return 0.0
    if price <= curve[0]["price"]:
        return curve[0]["impulse"]
    if price >= curve[-1]["price"]:
        return curve[-1]["impulse"]
    for i in range(len(curve) - 1):
        if curve[i]["price"] <= price <= curve[i + 1]["price"]:
            t = (price - curve[i]["price"]) / (curve[i + 1]["price"] - curve[i]["price"])
            return curve[i]["impulse"] + t * (curve[i + 1]["impulse"] - curve[i]["impulse"])
    return 0.0


def _classify_impulse_regime(impulse_at_spot: float, curve: List[Dict], spot: float) -> str:
    """Classify the impulse curve regime."""
    if not curve:
        return "neutral"
    abs_values = [abs(p["impulse"]) for p in curve]
    mean_abs = sum(abs_values) / len(abs_values) if abs_values else 0
    if mean_abs == 0:
        return "neutral"
    normalized = impulse_at_spot / mean_abs
    if normalized > 0.5:
        return "pinned"
    if normalized < -0.3:
        return "expansion"
    return "neutral"


# ============================================================================
# Pressure Cloud (stability/acceleration zones from impulse curve)
# ============================================================================

def calc_pressure_cloud(spot: float, contracts: List[Dict[str, Any]],
                        ticker: str = "") -> Dict[str, Any]:
    """
    Compute pressure cloud: stability zones, acceleration zones, and regime edges.
    Translates the impulse curve into actionable trading zones.
    """
    impulse_data = calc_hedge_impulse_curve(spot, contracts, ticker)
    curve = impulse_data.get("curve", [])
    extrema = impulse_data.get("extrema", [])
    zero_crossings = impulse_data.get("zero_crossings", [])

    if not curve:
        return {"stability_zones": [], "acceleration_zones": [], "regime_edges": [], "price_levels": []}

    # Expected daily move for reachability weighting
    atm_contract = min(contracts, key=lambda c: abs(c["strike"] - spot)) if contracts else {"iv": 0.2}
    atm_iv = atm_contract.get("iv", 0.2)
    expected_move = atm_iv / math.sqrt(252) * spot
    reach_range = expected_move * 2.0

    # Per-price-level scores
    price_levels = []
    for point in curve:
        distance = abs(point["price"] - spot)
        proximity = math.exp(-((distance / max(reach_range, 1)) ** 2)) if reach_range > 0 else 0

        stability = point["impulse"] * proximity if point["impulse"] > 0 else 0
        acceleration = abs(point["impulse"]) * proximity if point["impulse"] < 0 else 0

        # Convert to contract estimates (ES multiplier = 50)
        es_mult = 50
        contract_denom = es_mult * spot * 0.01
        expected_contracts = point["impulse"] / contract_denom if contract_denom > 0 else 0

        price_levels.append({
            "price": point["price"],
            "stability_score": round(stability, 2),
            "acceleration_score": round(acceleration, 2),
            "expected_hedge_contracts": round(expected_contracts, 2),
            "hedge_type": "passive" if point["impulse"] >= 0 else "aggressive",
        })

    # Stability zones from positive impulse basins
    basins = [e for e in extrema if e["type"] == "basin"]
    max_basin = max(abs(b["impulse"]) for b in basins) if basins else 1
    stability_zones = []
    for basin in basins:
        proximity = math.exp(-((abs(basin["price"] - spot) / max(reach_range, 1)) ** 2)) if reach_range > 0 else 0
        strength = min(1.0, (abs(basin["impulse"]) / max(max_basin, 1e-10)) * proximity)
        side = "above-spot" if basin["price"] >= spot else "below-spot"
        trade_type = "long" if side == "below-spot" else "short"
        stability_zones.append({
            "center": basin["price"],
            "strength": round(strength, 4),
            "side": side,
            "trade_type": trade_type,
            "hedge_type": "passive",
        })

    # Acceleration zones from negative impulse peaks
    peaks = [e for e in extrema if e["type"] == "peak"]
    max_peak = max(abs(p["impulse"]) for p in peaks) if peaks else 1
    acceleration_zones = []
    for peak in peaks:
        proximity = math.exp(-((abs(peak["price"] - spot) / max(reach_range, 1)) ** 2)) if reach_range > 0 else 0
        strength = min(1.0, (abs(peak["impulse"]) / max(max_peak, 1e-10)) * proximity)
        side = "above-spot" if peak["price"] >= spot else "below-spot"
        trade_type = "short" if side == "below-spot" else "long"
        acceleration_zones.append({
            "center": peak["price"],
            "strength": round(strength, 4),
            "side": side,
            "trade_type": trade_type,
            "hedge_type": "aggressive",
        })

    # Regime edges from zero crossings
    regime_edges = []
    for crossing in zero_crossings:
        is_below = crossing["price"] < spot
        if crossing["direction"] == "falling":
            transition = "stable-to-unstable" if is_below else "unstable-to-stable"
        else:
            transition = "unstable-to-stable" if is_below else "stable-to-unstable"
        regime_edges.append({
            "price": crossing["price"],
            "transition_type": transition,
        })

    return {
        "spot": spot,
        "stability_zones": sorted(stability_zones, key=lambda z: z["strength"], reverse=True)[:5],
        "acceleration_zones": sorted(acceleration_zones, key=lambda z: z["strength"], reverse=True)[:5],
        "regime_edges": regime_edges,
        "price_levels": price_levels,
    }


# ============================================================================
# Charm Integral (time-decay pressure)
# ============================================================================

def calc_charm_integral(spot: float, contracts: List[Dict[str, Any]],
                        ticker: str = "") -> Dict[str, Any]:
    """
    Compute charm integral: cumulative expected delta change from time decay.
    Shows the unconditional pressure from options expiring.
    """
    empty_response = {
        "total_charm_to_close": 0.0,
        "total_charm": 0.0,
        "direction": "neutral",
        "buckets": [],
        "minutes_remaining": 0,
    }

    if spot <= 0 or not contracts:
        return empty_response

    q = {"SPY": 0.013, "QQQ": 0.006, "^SPX": 0.013, "IWM": 0.012}.get(ticker, 0.0)

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()

    # Find nearest expiry
    expiries = sorted(set(c["expiry"] for c in contracts))
    if not expiries:
        return empty_response

    nearest = expiries[0]
    try:
        exp_date = datetime.strptime(nearest, "%Y-%m-%d").date()
        days_remaining = max((exp_date - today).days, 0)
    except Exception:
        days_remaining = 0

    if days_remaining == 0:
        return empty_response

    minutes_remaining = days_remaining * 390  # trading minutes

    # Total charm exposure
    total_charm = 0.0
    for c in contracts:
        oi = c.get("oi", 0) or 0
        if oi <= 0 or math.isnan(oi) or math.isinf(oi):
            continue
        charm = bs_charm(spot, c["strike"], c["T"], c["iv"], q=q, kind=c["type"])
        if math.isnan(charm) or math.isinf(charm):
            continue
        charm_unit = charm * oi * 100.0 * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        total_charm += sign * charm_unit

    # Build time buckets (every 30 minutes)
    buckets = []
    cumulative = 0.0
    time_step = 30

    for t in range(minutes_remaining, 0, -time_step):
        if t < 1:
            break
        # Charm accelerates as 1/sqrt(T)
        time_scaling = math.sqrt(minutes_remaining / t)
        instant_charm = total_charm * time_scaling
        bucket_fraction = time_step / 390.0
        bucket_contribution = instant_charm * bucket_fraction
        cumulative += bucket_contribution
        buckets.append({
            "minutes_remaining": t,
            "instantaneous_charm": round(instant_charm, 2),
            "cumulative_charm": round(cumulative, 2),
        })

    direction = "buying" if cumulative > 0 else "selling" if cumulative < 0 else "neutral"
    if math.isnan(total_charm) or math.isinf(total_charm):
        total_charm = 0.0
        direction = "neutral"
        buckets = []

    return {
        "spot": spot,
        "expiry": nearest,
        "minutes_remaining": minutes_remaining,
        "days_remaining": days_remaining,
        "total_charm_to_close": round(cumulative, 2) if not (math.isnan(cumulative) or math.isinf(cumulative)) else 0.0,
        "direction": direction,
        "buckets": buckets[::3],  # every 90 min for performance
    }


# ============================================================================
# Gamma Flip & Key Levels (from FlashAlpha gex-explained research)
# ============================================================================

def calc_gamma_flip_levels(spot: float, contracts: List[Dict[str, Any]],
                            ticker: str = "") -> Dict[str, Any]:
    """
    Compute gamma flip, call wall, put wall, max pain, 0DTE magnet, hedging flows.

    The gamma flip is the single most important level from GEX analysis.
    Above it = positive gamma (mean-reverting). Below it = negative gamma (momentum).
    """
    if not spot or spot <= 0 or spot != spot:  # spot != spot catches NaN
        return {"gamma_flip": None, "call_wall": None, "put_wall": None,
                "max_pain": None, "zero_dte_magnet": None, "total_gex": 0,
                "regime": "unknown", "hedging_flow": {}}

    from datetime import datetime, timezone
    q = {"SPY": 0.013, "QQQ": 0.006, "^SPX": 0.013, "IWM": 0.012}.get(ticker, 0.0)
    today = datetime.now(timezone.utc).date()

    gex_by_strike: Dict[float, float] = {}
    oi_by_strike: Dict[float, int] = {}
    zero_dte_oi: Dict[float, int] = {}

    for c in contracts:
        strike = c["strike"]
        oi = c.get("oi", 0) or 0
        if oi <= 0:
            continue
        gamma = bs_gamma(spot, strike, c["T"], c["iv"], q=q)
        if gamma <= 0:
            continue
        gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        gex_by_strike[strike] = gex_by_strike.get(strike, 0.0) + sign * gex_unit
        oi_by_strike[strike] = oi_by_strike.get(strike, 0) + oi
        try:
            exp_date = datetime.strptime(c["expiry"], "%Y-%m-%d").date()
            if (exp_date - today).days <= 0:
                zero_dte_oi[strike] = zero_dte_oi.get(strike, 0) + oi
        except Exception:
            pass

    if not gex_by_strike:
        return {"gamma_flip": None, "call_wall": None, "put_wall": None,
                "max_pain": None, "zero_dte_magnet": None, "total_gex": 0,
                "regime": "unknown", "hedging_flow": {}}

    sorted_strikes = sorted(gex_by_strike.keys())
    total_gex = sum(gex_by_strike.values())
    # Ensure it's a clean Python float
    try:
        total_gex = float(total_gex)
    except (TypeError, ValueError):
        total_gex = 0.0

    # Gamma flip: first zero crossing
    gamma_flip = None
    for i in range(len(sorted_strikes) - 1):
        k1, k2 = sorted_strikes[i], sorted_strikes[i + 1]
        g1, g2 = gex_by_strike[k1], gex_by_strike[k2]
        if g1 * g2 < 0 and g2 != g1:  # avoid division by zero
            gamma_flip = k1 + (k2 - k1) * (-g1 / (g2 - g1))
            break

    call_wall = max(sorted_strikes, key=lambda k: gex_by_strike[k])
    put_wall = min(sorted_strikes, key=lambda k: gex_by_strike[k])

    # Max pain
    if oi_by_strike:
        min_pain = float("inf")
        max_pain = sorted_strikes[len(sorted_strikes) // 2]
        for candidate in sorted_strikes:
            pain = sum(oi * abs(candidate - k) for k, oi in oi_by_strike.items())
            if pain < min_pain:
                min_pain = pain
                max_pain = candidate
    else:
        max_pain = None

    zero_dte_magnet = max(zero_dte_oi, key=zero_dte_oi.get) if zero_dte_oi else None

    # Regime classification
    regime = "unknown"
    try:
        spot_f = float(spot)
        if spot_f != spot_f:  # NaN check
            regime = "unknown"
        elif gamma_flip is not None:
            gf = float(gamma_flip)
            if gf == gf:  # not NaN
                regime = "positive_gamma" if spot_f >= gf else "negative_gamma"
            else:
                regime = "positive_gamma" if spot_f >= 0 else "negative_gamma"
        else:
            tg = float(total_gex)
            if tg == tg:  # not NaN
                regime = "positive_gamma" if tg >= 0 else "negative_gamma"
    except (TypeError, ValueError, AttributeError):
        regime = "unknown"

    # Dealer hedging flow at ±1%
    move_pct = 0.01
    try:
        if spot > 0 and total_gex == total_gex:  # NaN check: NaN != NaN
            up_shares = int(total_gex * move_pct / spot)
            dn_shares = int(total_gex * (-move_pct) / spot)
        else:
            up_shares = 0
            dn_shares = 0
    except (TypeError, ValueError, OverflowError):
        up_shares = 0
        dn_shares = 0

    try:
        total_gex_clean = round(total_gex, 0) if total_gex == total_gex else 0
    except (TypeError, ValueError):
        total_gex_clean = 0

    return {
        "gamma_flip": round(gamma_flip, 2) if gamma_flip else None,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "max_pain": max_pain,
        "zero_dte_magnet": zero_dte_magnet,
        "total_gex": total_gex_clean,
        "regime": regime,
        "hedging_flow": {
            "up_1pct": {"shares": abs(up_shares), "direction": "buy" if up_shares > 0 else "sell", "notional_usd": abs(up_shares) * spot},
            "down_1pct": {"shares": abs(dn_shares), "direction": "buy" if dn_shares > 0 else "sell", "notional_usd": abs(dn_shares) * spot},
        },
        "dist_to_flip": round(spot - gamma_flip, 2) if gamma_flip else None,
        "dist_to_call_wall_pct": round((call_wall - spot) / spot * 100, 2) if spot > 0 else None,
        "dist_to_put_wall_pct": round((spot - put_wall) / spot * 100, 2) if spot > 0 else None,
        "spot": spot,
    }


# ============================================================================
# VEX (Vanna-Exposure)
# ============================================================================

def calc_vex(spot: float, contracts: List[Dict[str, Any]],
             risk_free_rate: float = 0.045) -> Dict[str, Any]:
    """
    Compute Vanna-Exposure (VEX) across all strikes.

    VEX measures the sensitivity of delta to changes in implied volatility,
    weighted by open interest. It captures the "volatility exposure" of the
    options market.

    Formula per strike: vanna_i * OI_i * spot
    Total VEX = sum over all strikes

    Positive VEX = dealers are short vanna (vol increases → delta increases → buy pressure)
    Negative VEX = dealers are long vanna (vol increases → delta decreases → sell pressure)

    Args:
        spot: Current underlying price
        contracts: List of contract dicts with keys: strike, expiry, type, oi, iv, T
        risk_free_rate: Risk-free rate (default 4.5%)

    Returns:
        Dict with total_vex, vex_by_strike, call_vex, put_vex, abs_vex
    """
    if not spot or spot <= 0 or not contracts:
        return {"total_vex": 0, "vex_by_strike": {}, "call_vex": 0, "put_vex": 0, "abs_vex": 0}

    from bs_greeks import bs_vanna

    vex_by_strike: Dict[float, float] = {}
    call_vex = 0.0
    put_vex = 0.0

    for c in contracts:
        strike = c.get("strike", 0)
        oi = c.get("oi", 0) or 0
        T = c.get("T", 0)
        iv = c.get("iv", 0)
        if oi <= 0 or T <= 0 or iv <= 0:
            continue

        vanna = bs_vanna(spot, strike, T, iv, q=0.0, r=risk_free_rate)
        vex = vanna * oi * spot
        vex_by_strike[strike] = vex_by_strike.get(strike, 0.0) + vex

        if c.get("type", "").upper() in ("C", "CALL"):
            call_vex += vex
        else:
            put_vex += vex

    total_vex = sum(vex_by_strike.values())
    abs_vex = sum(abs(v) for v in vex_by_strike.values())

    return {
        "total_vex": round(total_vex, 2),
        "vex_by_strike": {k: round(v, 2) for k, v in sorted(vex_by_strike.items())},
        "call_vex": round(call_vex, 2),
        "put_vex": round(put_vex, 2),
        "abs_vex": round(abs_vex, 2),
        "spot": spot,
    }


# ============================================================================
# DEX (Delta-Exposure)
# ============================================================================

def calc_dex(spot: float, contracts: List[Dict[str, Any]],
             multiplier: float = 100.0,
             risk_free_rate: float = 0.045) -> Dict[str, Any]:
    """
    Compute Delta-Exposure (DEX) across all strikes.

    DEX measures the total delta of the options market, weighted by open
    interest and contract multiplier. It represents the equivalent share
    exposure of all outstanding options.

    Formula per strike: delta_i * OI_i * multiplier * spot
    Total DEX = sum over all strikes

    Positive DEX = net long delta (options market is bullish)
    Negative DEX = net short delta (options market is bearish)

    Args:
        spot: Current underlying price
        contracts: List of contract dicts with keys: strike, expiry, type, oi, iv, T
        multiplier: Contract multiplier (100 for standard options)
        risk_free_rate: Risk-free rate (default 4.5%)

    Returns:
        Dict with total_dex, dex_by_strike, call_dex, put_dex, abs_dex
    """
    if not spot or spot <= 0 or not contracts:
        return {"total_dex": 0, "dex_by_strike": {}, "call_dex": 0, "put_dex": 0, "abs_dex": 0}

    from bs_greeks import bs_delta

    dex_by_strike: Dict[float, float] = {}
    call_dex = 0.0
    put_dex = 0.0

    for c in contracts:
        strike = c.get("strike", 0)
        oi = c.get("oi", 0) or 0
        T = c.get("T", 0)
        iv = c.get("iv", 0)
        ctype = c.get("type", "").upper()
        if oi <= 0 or T <= 0 or iv <= 0:
            continue

        kind = "call" if ctype in ("C", "CALL") else "put"
        delta = bs_delta(spot, strike, T, iv, q=0.0, kind=kind, r=risk_free_rate)
        dex = delta * oi * multiplier * spot
        dex_by_strike[strike] = dex_by_strike.get(strike, 0.0) + dex

        if kind == "call":
            call_dex += dex
        else:
            put_dex += dex

    total_dex = sum(dex_by_strike.values())
    abs_dex = sum(abs(d) for d in dex_by_strike.values())

    return {
        "total_dex": round(total_dex, 2),
        "dex_by_strike": {k: round(v, 2) for k, v in sorted(dex_by_strike.items())},
        "call_dex": round(call_dex, 2),
        "put_dex": round(put_dex, 2),
        "abs_dex": round(abs_dex, 2),
        "spot": spot,
    }


# ============================================================================
# Vega-Total (Total Vega Exposure)
# ============================================================================

def calc_vega_total(spot: float, contracts: List[Dict[str, Any]],
                    risk_free_rate: float = 0.045) -> Dict[str, Any]:
    """
    Compute total vega across all open interest.

    Vega measures sensitivity to a 1 percentage point change in implied
    volatility. Total vega = sum(vega_i * OI_i) for all strikes.

    High total vega = options market is very sensitive to vol changes
    Low total vega = options market is insensitive to vol changes

    Args:
        spot: Current underlying price
        contracts: List of contract dicts with keys: strike, expiry, type, oi, iv, T
        risk_free_rate: Risk-free rate (default 4.5%)

    Returns:
        Dict with total_vega, vega_by_strike, call_vega, put_vega, avg_vega_per_contract
    """
    if not spot or spot <= 0 or not contracts:
        return {"total_vega": 0, "vega_by_strike": {}, "call_vega": 0, "put_vega": 0,
                "avg_vega_per_contract": 0}

    from bs_greeks import bs_vega

    vega_by_strike: Dict[float, float] = {}
    call_vega = 0.0
    put_vega = 0.0
    total_contracts = 0

    for c in contracts:
        strike = c.get("strike", 0)
        oi = c.get("oi", 0) or 0
        T = c.get("T", 0)
        iv = c.get("iv", 0)
        if oi <= 0 or T <= 0 or iv <= 0:
            continue

        vega = bs_vega(spot, strike, T, iv, q=0.0, r=risk_free_rate)
        total = vega * oi
        vega_by_strike[strike] = vega_by_strike.get(strike, 0.0) + total
        total_contracts += oi

        if c.get("type", "").upper() in ("C", "CALL"):
            call_vega += total
        else:
            put_vega += total

    total_vega = sum(vega_by_strike.values())
    avg_vega = total_vega / total_contracts if total_contracts > 0 else 0

    return {
        "total_vega": round(total_vega, 2),
        "vega_by_strike": {k: round(v, 2) for k, v in sorted(vega_by_strike.items())},
        "call_vega": round(call_vega, 2),
        "put_vega": round(put_vega, 2),
        "avg_vega_per_contract": round(avg_vega, 4),
        "total_contracts": total_contracts,
        "spot": spot,
    }
