"""
Institutional Volatility Analytics Module
Extracted from server.py to avoid circular imports and improve modularity.

Functions:
- calc_iv_surface_data: IV surface (smile + term structure) with interpolation
- calc_skew_metrics: 25d risk reversal, butterfly, skew slope
- calc_realized_volatility: Close/Parkinson/Garman-Klass estimators
- calc_iv_rank_percentile: IV rank and percentile for options valuation
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import yfinance as yf
from scipy.interpolate import griddata as scipy_griddata


def calc_iv_surface_data(spot: float, contracts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate IV surface data: IV across moneyness and time.
    Returns grid data suitable for 3D surface or heatmap visualization.
    Institutional standard: moneyness (K/S) x TTE -> IV."""
    if spot <= 0 or not contracts:
        return {"strikes": [], "expiries": [], "iv_grid": [], "smile": []}

    # Build raw data points
    points = []  # (moneyness, tte)
    values = []  # IV
    raw_by_expiry = defaultdict(list)

    for c in contracts:
        iv = c.get("iv", 0)
        T = c.get("T", 0)
        if iv <= 0 or iv > 3.0 or T <= 0:
            continue
        moneyness = c["strike"] / spot
        points.append([moneyness, T])
        values.append(iv)
        raw_by_expiry[c["expiry"]].append({
            "strike": c["strike"],
            "moneyness": round(moneyness, 4),
            "iv": round(iv, 4),
            "type": c["type"],
        })

    if len(points) < 4:
        return {"strikes": [], "expiries": [], "iv_grid": [], "smile": [], "raw": raw_by_expiry}

    points_arr = np.array(points)
    values_arr = np.array(values)

    # Create interpolation grid
    moneyness_range = np.linspace(0.85, 1.15, 50)
    tte_range = np.linspace(
        max(min(p[1] for p in points), 0.001),
        max(p[1] for p in points),
        30
    )
    grid_m, grid_t = np.meshgrid(moneyness_range, tte_range)

    # Interpolate with linear + nearest fill
    try:
        grid_iv = scipy_griddata(points_arr, values_arr, (grid_m, grid_t), method='linear')
        mask = np.isnan(grid_iv)
        if mask.any():
            grid_iv[mask] = scipy_griddata(points_arr, values_arr, (grid_m[mask], grid_t[mask]), method='nearest')
    except Exception:
        grid_iv = np.zeros_like(grid_m)

    # Extract ATM smile (across strikes for nearest expiry)
    nearest_expiry = min(raw_by_expiry.keys())
    smile_data = sorted(raw_by_expiry[nearest_expiry], key=lambda x: x["strike"])

    # Term structure (ATM IV across expiries)
    term_structure = []
    for exp in sorted(raw_by_expiry.keys()):
        exp_data = raw_by_expiry[exp]
        # Find ATM IV for this expiry
        atm_data = min(exp_data, key=lambda x: abs(x["moneyness"] - 1.0))
        try:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - datetime.now(timezone.utc).date()).days
        except Exception:
            dte = 0
        term_structure.append({
            "expiry": exp,
            "dte": dte,
            "atm_iv": atm_data["iv"],
            "atm_strike": atm_data["strike"],
        })

    return {
        "smile": smile_data[:30],  # limit for performance
        "term_structure": term_structure,
        "raw_by_expiry": {k: v[:20] for k, v in raw_by_expiry.items()},
    }


def calc_skew_metrics(spot: float, contracts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate volatility skew metrics.
    - 25d risk reversal: IV(25d call) - IV(25d put). Positive = call skew (bullish).
    - 25d butterfly: (IV(25d call) + IV(25d put))/2 - IV(ATM). Measures smile convexity.
    - Skew slope: IV change per unit moneyness.
    Institutional standard from CBOE/Deutsche Bank."""
    if spot <= 0 or not contracts:
        return {}

    # Group by strike, get average IV for calls and puts
    call_ivs = defaultdict(list)
    put_ivs = defaultdict(list)
    for c in contracts:
        iv = c.get("iv", 0)
        if iv <= 0 or iv > 3.0:
            continue
        if c["type"] == "call":
            call_ivs[c["strike"]].append(iv)
        else:
            put_ivs[c["strike"]].append(iv)

    # Average IV per strike
    call_iv_avg = {k: sum(v)/len(v) for k, v in call_ivs.items()}
    put_iv_avg = {k: sum(v)/len(v) for k, v in put_ivs.items()}
    all_strikes = sorted(set(list(call_iv_avg.keys()) + list(put_iv_avg.keys())))
    if not all_strikes:
        return {}

    # Find ATM
    atm_strike = min(all_strikes, key=lambda s: abs(s - spot))
    atm_iv_call = call_iv_avg.get(atm_strike, 0)
    atm_iv_put = put_iv_avg.get(atm_strike, 0)
    atm_iv = (atm_iv_call + atm_iv_put) / 2 if atm_iv_call and atm_iv_put else (atm_iv_call or atm_iv_put)

    # Find 25 delta strikes (approximate via moneyness)
    call_25d_strike = None
    put_25d_strike = None
    for s in all_strikes:
        moneyness = s / spot
        if moneyness > 1.0 and call_25d_strike is None:
            call_25d_strike = s  # first OTM call
        if moneyness < 1.0:
            put_25d_strike = s  # last OTM put

    iv_25d_call = call_iv_avg.get(call_25d_strike, atm_iv) if call_25d_strike else atm_iv
    iv_25d_put = put_iv_avg.get(put_25d_strike, atm_iv) if put_25d_strike else atm_iv

    # Risk reversal: 25d call IV - 25d put IV
    risk_reversal_25d = iv_25d_call - iv_25d_put

    # Butterfly: average of wings minus body
    butterfly_25d = (iv_25d_call + iv_25d_put) / 2 - atm_iv if atm_iv > 0 else 0

    # Skew slope: IV change from 90% to 110% moneyness
    iv_90 = None
    iv_110 = None
    for s in all_strikes:
        m = s / spot
        iv_s = call_iv_avg.get(s) or put_iv_avg.get(s)
        if iv_s:
            if abs(m - 0.90) < 0.02:
                iv_90 = iv_s
            if abs(m - 1.10) < 0.02:
                iv_110 = iv_s

    skew_slope = (iv_110 - iv_90) / 0.20 if iv_90 and iv_110 else 0

    return {
        "atm_iv": round(atm_iv, 4),
        "atm_strike": atm_strike,
        "risk_reversal_25d": round(risk_reversal_25d, 4),
        "butterfly_25d": round(butterfly_25d, 4),
        "skew_slope": round(skew_slope, 4),
        "iv_25d_call": round(iv_25d_call, 4),
        "iv_25d_put": round(iv_25d_put, 4),
        "call_25d_strike": call_25d_strike,
        "put_25d_strike": put_25d_strike,
        "interpretation": {
            "risk_reversal": "bullish" if risk_reversal_25d > 0.02 else "bearish" if risk_reversal_25d < -0.02 else "neutral",
            "butterfly": "fat_tails" if butterfly_25d > 0.02 else "thin_tails" if butterfly_25d < -0.01 else "normal",
            "skew_slope": "steep" if abs(skew_slope) > 0.5 else "flat" if abs(skew_slope) < 0.1 else "moderate",
        }
    }


def calc_realized_volatility(ticker: str, days: int = 20) -> Optional[Dict[str, Any]]:
    """Calculate realized volatility from historical prices.
    Uses Parkinson (high-low) and Garman-Klass estimators for efficiency.
    Institutional standard: annualized, with comparison to implied.
    NOTE: This is a synchronous function, call via asyncio.to_thread()."""
    try:
        yt = yf.Ticker(ticker)
        hist = yt.history(period=f"{days+10}d")
    except Exception:
        return None
    if hist is None or len(hist) < 5:
        return None
    hist = hist.tail(days)
    close = hist["Close"].values.astype(float)
    high = hist["High"].values.astype(float)
    low = hist["Low"].values.astype(float)
    open_p = hist["Open"].values.astype(float)
    if len(close) < 5:
        return None
    # Standard close-to-close RV
    log_returns = np.log(close[1:] / close[:-1])
    rv_close = float(np.std(log_returns, ddof=1) * np.sqrt(252))
    # Parkinson (high-low) RV
    hl_ratio = np.log(high[1:] / low[1:])
    rv_parkinson = float(np.sqrt(np.mean(hl_ratio**2) / (4 * np.log(2)) * 252))
    # Garman-Klass
    log_hl = np.log(high[1:] / low[1:])
    log_co = np.log(close[1:] / open_p[1:])
    rv_gk = float(np.sqrt(np.mean(0.5 * log_hl**2 - (2*np.log(2)-1) * log_co**2) * 252))
    return {
        "rv_close": round(rv_close, 4),
        "rv_parkinson": round(rv_parkinson, 4),
        "rv_garman_klass": round(rv_gk, 4),
        "days": days,
        "current_price": round(float(close[-1]), 2),
    }


def calc_iv_rank_percentile(ticker: str, current_iv: float, lookback_days: int = 252) -> Dict[str, Any]:
    """Calculate IV rank and IV percentile.
    IV Rank = (current IV - 52w low IV) / (52w high IV - 52w low IV)
    IV Percentile = % of days in past year with IV below current.
    Institutional standard for determining if options are cheap/expensive."""
    try:
        yt = yf.Ticker(ticker)
        hist = yt.history(period=f"{lookback_days}d")
        if hist is None or len(hist) < 30:
            return {"iv_rank": None, "iv_percentile": None, "note": "Insufficient history"}

        # Estimate historical IV from realized vol of different windows
        close = hist["Close"].values
        iv_estimates = []
        for window in [5, 10, 20, 30, 60]:
            if len(close) > window:
                rets = np.log(close[-window:] / close[-window-1:-1])
                iv_est = float(np.std(rets) * np.sqrt(252))
                iv_estimates.append(iv_est)

        if not iv_estimates:
            return {"iv_rank": None, "iv_percentile": None}

        iv_min = min(iv_estimates)
        iv_max = max(iv_estimates)
        iv_range = iv_max - iv_min if iv_max > iv_min else 0.01

        iv_rank = (current_iv - iv_min) / iv_range
        iv_percentile = sum(1 for iv in iv_estimates if iv <= current_iv) / len(iv_estimates)

        return {
            "iv_rank": round(iv_rank, 4),
            "iv_percentile": round(iv_percentile, 4),
            "iv_52w_low": round(iv_min, 4),
            "iv_52w_high": round(iv_max, 4),
            "current_iv": round(current_iv, 4),
            "interpretation": "expensive" if iv_rank > 0.7 else "cheap" if iv_rank < 0.3 else "fair",
        }
    except Exception:
        return {"iv_rank": None, "iv_percentile": None, "note": "Calculation failed"}
