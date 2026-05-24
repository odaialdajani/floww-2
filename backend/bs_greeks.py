"""
Black-Scholes Greeks calculations.
Shared between server.py and portfolio.py to avoid circular imports.

Risk-free rate: Uses dynamic treasury yield curve from gflows_modules/treasury.
Falls back to 5.0% (0.05) when treasury data is unavailable.
"""

import math
from typing import Optional
from scipy.stats import norm

# Hardcoded fallback — replaced by dynamic treasury rates when available
RISK_FREE_RATE = 0.05


def _get_dynamic_rfr(ttm_years: float = 0.08) -> float:
    """Return a tenor-matched risk-free rate from the treasury yield curve.
    Delegates to get_tenor_matched_rate which has its own 4-hour FRED cache.
    Falls back to RISK_FREE_RATE (0.05) if treasury module is unavailable."""
    days = max(ttm_years * 365.0, 1.0)
    from gflows_modules.treasury import get_tenor_matched_rate
    return get_tenor_matched_rate(days)


def _rfr(r: Optional[float], T: float) -> float:
    """Resolve risk-free rate: use explicit value if provided, otherwise dynamic."""
    if r is not None:
        return r
    if T <= 0:
        return RISK_FREE_RATE
    return _get_dynamic_rfr(T)


def bs_gamma(S, K, T, sigma, q=0.0, r=None):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_delta(S, K, T, sigma, q=0.0, kind="call", r=None):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        if kind == "call": return math.exp(-q * T) * norm.cdf(d1)
        else: return math.exp(-q * T) * (norm.cdf(d1) - 1)
    except Exception: return 0.0


def bs_vanna(S, K, T, sigma, q=0.0, r=None):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        result = -math.exp(-q * T) * norm.pdf(d1) * d2 / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_charm(S, K, T, sigma, q=0.0, kind="call", r=None):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = norm.pdf(d1)
        cdf_d1 = norm.cdf(d1)
        charm = -math.exp(-q * T) * (q * cdf_d1 - pdf_d1 * (2 * (_r - q) * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if kind == "put":
            charm = -math.exp(-q * T) * (-q * (1 - cdf_d1) - pdf_d1 * (2 * (_r - q) * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if math.isnan(charm) or math.isinf(charm): return 0.0
        return charm
    except Exception: return 0.0


def bs_vomma(S, K, T, sigma, q=0.0, r=None):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        vega = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        result = vega * d1 * d2 / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_zomma(S, K, T, sigma, q=0.0, r=None):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        gamma = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        result = gamma * (d1 * d2 - 1) / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_vega(S, K, T, sigma, q=0.0, r=None):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_call_price(S, K, T, sigma, r=None, q=0.0):
    """Black-Scholes call option price."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-_r * T) * norm.cdf(d2)
        if math.isnan(price) or math.isinf(price): return 0.0
        return price
    except Exception: return 0.0


def bs_put_price(S, K, T, sigma, r=None, q=0.0):
    """Black-Scholes put option price."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    _r = _rfr(r, T)
    try:
        d1 = (math.log(S / K) + (_r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = K * math.exp(-_r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
        if math.isnan(price) or math.isinf(price): return 0.0
        return price
    except Exception: return 0.0
