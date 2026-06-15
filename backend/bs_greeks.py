"""
Black-Scholes Greeks calculations.
Shared between server.py and portfolio.py to avoid circular imports.
"""

import logging
import math
import sys

from scipy.stats import norm

log = logging.getLogger(__name__)

RISK_FREE_RATE = 0.05


def _mask_zero(exc: Exception) -> float:
    """Return 0.0 for an unexpected numerical error, but log it so the silent
    failure is observable instead of vanishing (B4 audit 2026-06-13).

    Guard-clause zeros (invalid/expired inputs) bypass this helper and stay
    silent -- only errors caught by ``except`` are surfaced. The 0.0 return is
    preserved so every caller (including the frozen ML-feature path) sees
    identical values; this adds observability, not a behavior change.
    """
    fn = sys._getframe(1).f_code.co_name
    log.warning("%s masked error -> 0.0: %s", fn, exc)
    return 0.0


def bs_gamma(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception as exc: return _mask_zero(exc)


def bs_delta(S, K, T, sigma, q=0.0, kind="call", r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        if kind == "call": return math.exp(-q * T) * norm.cdf(d1)
        else: return math.exp(-q * T) * (norm.cdf(d1) - 1)
    except Exception as exc: return _mask_zero(exc)


def bs_vanna(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        result = -math.exp(-q * T) * norm.pdf(d1) * d2 / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception as exc: return _mask_zero(exc)


def bs_charm(S, K, T, sigma, q=0.0, kind="call", r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = norm.pdf(d1)
        cdf_d1 = norm.cdf(d1)
        charm = -math.exp(-q * T) * (q * cdf_d1 - pdf_d1 * (2 * (r - q) * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if kind == "put":
            charm = -math.exp(-q * T) * (-q * (1 - cdf_d1) - pdf_d1 * (2 * (r - q) * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if math.isnan(charm) or math.isinf(charm): return 0.0
        return charm
    except Exception as exc: return _mask_zero(exc)


def bs_vomma(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        vega = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        result = vega * d1 * d2 / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception as exc: return _mask_zero(exc)


def bs_zomma(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        gamma = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        result = gamma * (d1 * d2 - 1) / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception as exc: return _mask_zero(exc)


def bs_vega(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception as exc: return _mask_zero(exc)


def bs_call_price(S, K, T, sigma, r=0.045, q=0.0):
    """Black-Scholes call option price."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        if math.isnan(price) or math.isinf(price): return 0.0
        return price
    except Exception as exc: return _mask_zero(exc)


def bs_put_price(S, K, T, sigma, r=0.045, q=0.0):
    """Black-Scholes put option price."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
        if math.isnan(price) or math.isinf(price): return 0.0
        return price
    except Exception as exc: return _mask_zero(exc)
