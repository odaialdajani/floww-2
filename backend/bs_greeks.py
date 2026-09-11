"""
Black-Scholes Greeks calculations.
Shared between server.py and portfolio.py to avoid circular imports.

Dollar-GEX Convention (PLATFORM-WIDE)
=====================================
The ``GEX_per_contract`` helper below produces the industry-standard
"Dollar Gamma Exposure" value (US dollars of stock dealers must trade to
remain delta-neutral for a 1% upward spot move):

    GEX_per_contract = gamma * OI * CONTRACT_MULTIPLIER * spot^2 * DOLLAR_MOVE_CONVENTION

with the *SqueezeMetrics / SpotGamma / Perfiliev* constants:

    CONTRACT_MULTIPLIER  = 100.0      # shares per equity option contract
    DOLLAR_MOVE_CONVENTION = 0.01     # 1% spot move

References (open-access):
  - Perfiliev, S. (2022). "How to Calculate Gamma Exposure (GEX) and Zero
    Gamma Level." https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/
  - SqueezeMetrics / SpotGamma community implementations (the standard
    formula used by every retail GEX dashboard we cross-check against).
  - TradingView community-authored GEX scripts.

Second-order dollar exposures follow the same 1%-move convention but use
a linear (rather than quadratic) spot factor because the underlying greek's
unit [1/spot] for vanna/charm/vomma cancels one of the spot factors:

    VEX   = vanna  * OI * MULTIPLIER * spot    * 0.01   (per 1% move)
    charm = charm  * OI * MULTIPLIER * spot    * 0.01   (per 1% move)
    vomma = vomma  * OI * MULTIPLIER                 (per unit-σ; no 0.01)
    vega  = vega   * OI * MULTIPLIER                 (per unit-σ; no 0.01)

NOTE: ``services/gex_vex_calculator.compute_vex_surface`` deliberately uses
GEX-like scaling (vomma * OI * 100 * spot^2 * 0.01) for its display surface.
The two scales differ by exactly spot^2 * 0.01 (~3364x at SPY 580), pinned by
``backend/tests/services/test_vex_scale_parity.py``. Neither is observed
dealer inventory; both assume dealer positioning and sign.

CRITICAL: This display/UI scale is **distinct from** the *frozen ML-feature*
scale used in ``services/gex_history.py`` (which uses a *single* spot factor
and fixed ``iv=0.20`` for model-input stability). The two scales differ by
exactly a factor of ``spot`` and are pinned by
``tests/services/test_gex_aggregator_oracle.py``.

If you change any of these constants, ALSO re-read the platform-wide audit
``docs/superpowers/specs/2026-06-13-gex-gamma-correctness-audit-design.md``
and run ``backend/tests/test_dollar_gex_convention.py`` to confirm parity
with the published SqueezeMetrics/SpotGamma band (SPY at $580 typically
$3B–$15B net in positive-gamma regimes; -$5B to -$15B in negative).
"""

import logging
import math
import sys

from scipy.stats import norm

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Platform-wide GEX/VE constants.  See module docstring for citations.
# ------------------------------------------------------------------
CONTRACT_MULTIPLIER: float = 100.0
DOLLAR_MOVE_CONVENTION: float = 0.01


def dollar_gex_per_contract(gamma: float, oi: float, spot: float) -> float:
    """Dollar Gamma Exposure per contract (industry-standard 1%-move convention).

    Returns ``gamma * OI * 100 * spot^2 * 0.01`` — the dollar amount of
    underlying stock a dealer must trade to remain delta-hedged if spot
    moves 1%. Matches SqueezeMetrics / SpotGamma / Perfiliev (2022).

    Sign convention: caller multiplies by ``+1`` for calls and ``-1`` for
    puts (dealer-shorts-what-customers-long ⇒ calls positive, puts negative).
    """
    return gamma * oi * CONTRACT_MULTIPLIER * spot * spot * DOLLAR_MOVE_CONVENTION


def dollar_vex_per_contract(vanna: float, oi: float, spot: float) -> float:
    """Dollar Vanna Exposure per contract (1%-move convention).

    Vanna has units ``[1/spot]`` so the formula is linear in spot (with
    the 0.01 convention still representing the 1% move). Matches the
    canonical VEX calculation used across ``backend``.
    """
    return vanna * oi * CONTRACT_MULTIPLIER * spot * DOLLAR_MOVE_CONVENTION


def dollar_charm_per_contract(charm: float, oi: float, spot: float) -> float:
    """Dollar Charm Exposure per contract (1%-move convention)."""
    return charm * oi * CONTRACT_MULTIPLIER * spot * DOLLAR_MOVE_CONVENTION


def dollar_vomma_per_contract(vomma: float, oi: float) -> float:
    """Dollar Vomma Exposure per contract (per unit-σ; no 0.01 factor)."""
    return vomma * oi * CONTRACT_MULTIPLIER


def dollar_vega_per_contract(vega: float, oi: float) -> float:
    """Dollar Vega Exposure per contract (per unit-σ; no 0.01 factor)."""
    return vega * oi * CONTRACT_MULTIPLIER


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
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_delta(S, K, T, sigma, q=0.0, kind="call", r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        if kind == "call":
            return math.exp(-q * T) * norm.cdf(d1)
        else:
            return math.exp(-q * T) * (norm.cdf(d1) - 1)
    except Exception as exc:
        return _mask_zero(exc)


def bs_vanna(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        result = -math.exp(-q * T) * norm.pdf(d1) * d2 / sigma
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_charm(S, K, T, sigma, q=0.0, kind="call", r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = norm.pdf(d1)
        cdf_d1 = norm.cdf(d1)
        charm = math.exp(-q * T) * (q * cdf_d1 - pdf_d1 * (2 * (r - q) * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if kind == "put":
            charm = math.exp(-q * T) * (-q * (1 - cdf_d1) - pdf_d1 * (2 * (r - q) * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if math.isnan(charm) or math.isinf(charm):
            return 0.0
        return charm
    except Exception as exc:
        return _mask_zero(exc)


def bs_vomma(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        vega = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        result = vega * d1 * d2 / sigma
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_zomma(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        gamma = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        result = gamma * (d1 * d2 - 1) / sigma
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_vega(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_call_price(S, K, T, sigma, r=0.045, q=0.0):
    """Black-Scholes call option price."""
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        if math.isnan(price) or math.isinf(price):
            return 0.0
        return price
    except Exception as exc:
        return _mask_zero(exc)


def bs_put_price(S, K, T, sigma, r=0.045, q=0.0):
    """Black-Scholes put option price."""
    if S <= 0 or K <= 0 or T <= 0 or not sigma or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
        if math.isnan(price) or math.isinf(price):
            return 0.0
        return price
    except Exception as exc:
        return _mask_zero(exc)


# ----------------------------------------------------------------------
# Steal-list rank #5 — IV-from-mid solver (Newton-Raphson + bisection).
# Pure addition. Steal: MattL922/implied-volatility getImpliedVolatility.
# Lands in: services/steal_three_server.py /api/iv_mid/{ticker} in :8001.
#           Called optionally from vol_analytics.calc_iv_surface_data via a
#           route-level interceptor (no edit to vol_analytics itself).
# Audit:    docs/reports/2026-07-11-steal-list-integration-roadmap.md #5.
# ----------------------------------------------------------------------
def implied_vol_from_price(
    market_price: float,
    S: float,
    K: float,
    T: float,
    kind: str = "call",
    q: float = 0.0,
    r: float = 0.045,
    tol: float = 1e-6,
    max_iter: int = 50,
) -> float:
    """Solve bs_{call,put}_price(S, K, T, sigma) == market_price for sigma.

    Method: Newton-Raphson using ``bs_vega`` as the derivative. Falls back to
    bisection over [1e-4, 5.0] when Newton fails to bracket, oscillates,
    or returns a non-positive vega. The bisection tail is far slower but
    guaranteed monotone, so the caller always returns a finite sigma.

    Returns ``0.0`` for guard-clause bad inputs (consistent with the
    silent-mask convention ``bs_put_price`` / ``bs_call_price`` use). Any
    numerical error caught by ``except`` is logged via ``_mask_zero``.
    """
    if S <= 0 or K <= 0 or T <= 0 or market_price <= 0:
        return 0.0
    px_fn = bs_call_price if kind == "call" else bs_put_price

    # Intrinsic-floor guard. No Black-Scholes sigma can produce a market
    # price strictly below the option's intrinsic value; if we see one
    # the input is bad (stale quote, broken chain, mis-typed sign). Mask
    # to 0.0 via the existing _mask_zero channel so callers can observe
    # the failure rather than silently accept a tiny boundary sigma.
    intrinsic = max(0.0, S - K) if kind == "call" else max(0.0, K - S)
    if market_price < intrinsic - 1e-8:
        return _mask_zero(
            ValueError(
                f"implied_vol_from_price: market_price={market_price} "
                f"< intrinsic={intrinsic:.4f} ({kind})"
            )
        )

    # Brenner-style initial guess: σ₀ ≈ √(2π/T) · time_value / S
    if kind == "call":
        intrinsic = max(0.0, S - K)
    else:
        intrinsic = max(0.0, K - S)
    time_value = max(market_price - intrinsic, 0.01)
    sigma = max(0.05, min(2.0, time_value / max(S * math.sqrt(T), 1e-6) * math.sqrt(2 * math.pi)))

    try:
        # Newton phase
        for _ in range(max_iter):
            price = px_fn(S, K, T, sigma, r=r, q=q)
            diff = price - market_price
            if abs(diff) < tol:
                return round(sigma, 6)
            vega = bs_vega(S, K, T, sigma, q=q, r=r)
            if not vega or vega <= 1e-10:
                break  # fall through to bisection
            step = diff / vega
            next_sigma = sigma - step
            # Keep the update inside a reasonable interval to avoid runaway.
            if next_sigma < 1e-4 or next_sigma > 5.0:
                break
            sigma = next_sigma
        # Bisection fallback (guaranteed monotone in [lo, hi]).
        lo, hi = 1e-4, 5.0
        best = sigma
        for _ in range(120):
            mid_sigma = 0.5 * (lo + hi)
            p = px_fn(S, K, T, mid_sigma, r=r, q=q)
            if abs(p - market_price) < tol:
                return round(mid_sigma, 6)
            if p > market_price:
                hi = mid_sigma
            else:
                lo = mid_sigma
            best = mid_sigma
        return round(best, 6)
    except Exception as exc:
        return _mask_zero(exc)
