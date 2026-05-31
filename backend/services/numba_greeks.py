"""
Numba-optimized Black-Scholes Greek calculator for vectorized option chain computation.

This module replaces bs_greeks.py for high-performance batch processing of entire
option chains. All core functions are decorated with @numba.njit for JIT compilation
and accept numpy arrays, computing Greeks element-wise across thousands of options
in a single call without Python-level loops.

Key design decisions:
  - No scipy dependency: norm_pdf and norm_cdf are implemented manually using
    math.erf (supported by numba) since scipy is not numba-compatible.
  - Edge cases (S<=0, K<=0, T<=0, sigma<=0) return 0.0 for affected elements.
  - All functions are pure numpy-vectorized with numba for maximum throughput.
  - A convenience wrapper compute_all_greeks() computes the full Greek surface
    in one call given spot and arrays of strikes, expiries, IVs, and option types.

Usage:
    from services.numba_greeks import compute_all_greeks
    greeks = compute_all_greeks(spot, strikes, expiries, ivs, types)
"""

import logging
import math

import numba
import numpy as np

logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# Manual normal distribution helpers (scipy not numba-compatible)
# ---------------------------------------------------------------------------


@numba.njit
def _norm_pdf(x: float) -> float:
    """Standard normal probability density function.

    Args:
        x: Point at which to evaluate the PDF.

    Returns:
        The PDF value at x.
    """
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@numba.njit
def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function.

    Uses math.erf which is supported by numba's JIT compiler.

    Args:
        x: Point at which to evaluate the CDF.

    Returns:
        The CDF value at x.
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Internal helper: compute d1 and d2 for Black-Scholes
# ---------------------------------------------------------------------------


@numba.njit
def _d1d2(S: float, K: float, T: float, sigma: float, r: float, q: float):
    """Compute the Black-Scholes d1 and d2 parameters.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiry in years.
        sigma: Implied volatility.
        r: Risk-free rate.
        q: Continuous dividend yield.

    Returns:
        Tuple (d1, d2).
    """
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return d1, d2


# ---------------------------------------------------------------------------
# Vectorized Greek functions
# ---------------------------------------------------------------------------


@numba.njit
def bs_gamma_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    r: float = 0.05,
) -> np.ndarray:
    """Vectorized Black-Scholes gamma for an array of options.

    Gamma measures the rate of change of delta with respect to the underlying price.
    It is the same for calls and puts.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        q: Continuous dividend yield (default 0.0).
        r: Risk-free rate (default 0.05).

    Returns:
        Array of gamma values. Elements where S<=0, K<=0, T<=0, or sigma<=0
        are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, _d2 = _d1d2(S, K[i], T[i], sigma[i], r, q)
        out[i] = math.exp(-q * T[i]) * _norm_pdf(d1) / (S * sigma[i] * math.sqrt(T[i]))
    return out


@numba.njit
def bs_delta_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    r: float = 0.05,
    kind: int = 0,
) -> np.ndarray:
    """Vectorized Black-Scholes delta for an array of options.

    Delta measures the rate of change of option price with respect to the
    underlying price. Call delta is positive; put delta is negative.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        q: Continuous dividend yield (default 0.0).
        kind: 0 for call, 1 for put (default 0).

    Returns:
        Array of delta values. Elements where S<=0, K<=0, T<=0, or sigma<=0
        are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, _d2 = _d1d2(S, K[i], T[i], sigma[i], 0.0, q)
        if kind == 0:
            out[i] = math.exp(-q * T[i]) * _norm_cdf(d1)
        else:
            out[i] = math.exp(-q * T[i]) * (_norm_cdf(d1) - 1.0)
    return out


@numba.njit
def bs_vega_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    r: float = 0.05,
) -> np.ndarray:
    """Vectorized Black-Scholes vega for an array of options.

    Vega measures sensitivity to a 1 percentage point change in volatility.
    It is the same for calls and puts. The raw value is divided by 100 to
    represent the change per 1 vol point.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        q: Continuous dividend yield (default 0.0).
        r: Risk-free rate (default 0.05).

    Returns:
        Array of vega values (per 1 vol point). Elements where S<=0, K<=0,
        T<=0, or sigma<=0 are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, _d2 = _d1d2(S, K[i], T[i], sigma[i], r, q)
        out[i] = S * math.exp(-q * T[i]) * _norm_pdf(d1) * math.sqrt(T[i]) / 100.0
    return out


@numba.njit
def bs_vanna_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    r: float = 0.05,
) -> np.ndarray:
    """Vectorized Black-Scholes vanna for an array of options.

    Vanna measures the sensitivity of delta to changes in volatility (or
    equivalently, the sensitivity of vega to changes in the underlying price).
    It is the same for calls and puts.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        q: Continuous dividend yield (default 0.0).
        r: Risk-free rate (default 0.05).

    Returns:
        Array of vanna values. Elements where S<=0, K<=0, T<=0, or sigma<=0
        are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, d2 = _d1d2(S, K[i], T[i], sigma[i], r, q)
        out[i] = -math.exp(-q * T[i]) * _norm_pdf(d1) * d2 / sigma[i]
    return out


@numba.njit
def bs_charm_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    kind: int = 0,
) -> np.ndarray:
    """Vectorized Black-Scholes charm (delta decay) for an array of options.

    Charm measures the rate of change of delta with respect to time. It is
    also known as delta decay.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        q: Continuous dividend yield (default 0.0).
        kind: 0 for call, 1 for put (default 0).

    Returns:
        Array of charm values (per day). Elements where S<=0, K<=0, T<=0,
        or sigma<=0 are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, d2 = _d1d2(S, K[i], T[i], sigma[i], 0.0, q)
        term1 = q * math.exp(-q * T[i]) * _norm_cdf(d1)
        term2_val = -math.exp(-q * T[i]) * _norm_pdf(d1) * (
            2.0 * (0.0 - q) * T[i] - d2 * sigma[i] * math.sqrt(T[i])
        ) / (2.0 * T[i] * sigma[i] * math.sqrt(T[i]))
        if kind == 0:
            out[i] = (term1 - term2_val) / 365.0
        else:
            out[i] = (term1 - math.exp(-q * T[i]) * (1.0 - _norm_cdf(d1)) - term2_val) / 365.0
    return out


@numba.njit
def bs_vomma_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    r: float = 0.05,
) -> np.ndarray:
    """Vectorized Black-Scholes vomma (volga) for an array of options.

    Vomma measures the second-order sensitivity of option price to volatility
    (the derivative of vega with respect to volatility). It is the same for
    calls and puts.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        q: Continuous dividend yield (default 0.0).
        r: Risk-free rate (default 0.05).

    Returns:
        Array of vomma values. Elements where S<=0, K<=0, T<=0, or sigma<=0
        are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, d2 = _d1d2(S, K[i], T[i], sigma[i], r, q)
        vega_i = S * math.exp(-q * T[i]) * _norm_pdf(d1) * math.sqrt(T[i]) / 100.0
        out[i] = vega_i * d1 * d2 / sigma[i]
    return out


@numba.njit
def bs_zomma_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    r: float = 0.05,
) -> np.ndarray:
    """Vectorized Black-Scholes zomma for an array of options.

    Zomma measures the rate of change of gamma with respect to volatility.
    It is the same for calls and puts.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        q: Continuous dividend yield (default 0.0).
        r: Risk-free rate (default 0.05).

    Returns:
        Array of zomma values. Elements where S<=0, K<=0, T<=0, or sigma<=0
        are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, d2 = _d1d2(S, K[i], T[i], sigma[i], r, q)
        gamma_i = (
            math.exp(-q * T[i]) * _norm_pdf(d1) / (S * sigma[i] * math.sqrt(T[i]))
        )
        out[i] = gamma_i * (d1 * d2 - 1.0) / sigma[i]
    return out


@numba.njit
def bs_call_price_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.045,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorized Black-Scholes call option price for an array of options.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        r: Risk-free rate (default 0.045).
        q: Continuous dividend yield (default 0.0).

    Returns:
        Array of call option prices. Elements where S<=0, K<=0, T<=0, or
        sigma<=0 are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, d2 = _d1d2(S, K[i], T[i], sigma[i], r, q)
        out[i] = (
            S * math.exp(-q * T[i]) * _norm_cdf(d1)
            - K[i] * math.exp(-r * T[i]) * _norm_cdf(d2)
        )
    return out


@numba.njit
def bs_put_price_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.045,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorized Black-Scholes put option price for an array of options.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        r: Risk-free rate (default 0.045).
        q: Continuous dividend yield (default 0.0).

    Returns:
        Array of put option prices. Elements where S<=0, K<=0, T<=0, or
        sigma<=0 are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, d2 = _d1d2(S, K[i], T[i], sigma[i], r, q)
        out[i] = (
            K[i] * math.exp(-r * T[i]) * _norm_cdf(-d2)
            - S * math.exp(-q * T[i]) * _norm_cdf(-d1)
        )
    return out


# ---------------------------------------------------------------------------
# Theta helper (internal, not exported as standalone @njit function)
# ---------------------------------------------------------------------------


@numba.njit
def _bs_theta_vec(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float,
    q: float,
    kind: np.ndarray,
) -> np.ndarray:
    """Internal vectorized Black-Scholes theta computation.

    Theta measures the rate of change of option price with respect to time
    (time decay). Returns theta per calendar day.

    Args:
        S: Spot price (scalar).
        K: Array of strike prices.
        T: Array of times to expiry in years.
        sigma: Array of implied volatilities.
        r: Risk-free rate.
        q: Continuous dividend yield.
        kind: Array of option types (0=call, 1=put).

    Returns:
        Array of theta values per day. Elements where S<=0, K<=0, T<=0, or
        sigma<=0 are set to 0.0.
    """
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0:
            out[i] = 0.0
            continue
        d1, d2 = _d1d2(S, K[i], T[i], sigma[i], r, q)
        sqrtT = math.sqrt(T[i])

        # Common term
        common = -(S * math.exp(-q * T[i]) * _norm_pdf(d1) * sigma[i]) / (2.0 * sqrtT)

        if kind[i] == 0:
            # Call theta
            out[i] = (
                common
                - r * K[i] * math.exp(-r * T[i]) * _norm_cdf(d2)
                + q * S * math.exp(-q * T[i]) * _norm_cdf(d1)
            ) / 365.0
        else:
            # Put theta
            out[i] = (
                common
                + r * K[i] * math.exp(-r * T[i]) * _norm_cdf(-d2)
                - q * S * math.exp(-q * T[i]) * _norm_cdf(-d1)
            ) / 365.0
    return out


# ---------------------------------------------------------------------------
# Convenience wrapper: compute the full Greek surface
# ---------------------------------------------------------------------------


def compute_all_greeks(
    spot: float,
    strikes: np.ndarray,
    expiries: np.ndarray,
    ivs: np.ndarray,
    types: np.ndarray,
    r: float = 0.045,
    q: float = 0.0,
) -> dict:
    """Compute the full Black-Scholes Greek surface for an option chain.

    This is a convenience wrapper that calls all individual @numba.njit Greek
    functions and returns them in a dictionary. It handles the theta computation
    separately since it requires per-element option type dispatch.

    Args:
        spot: Current underlying price (scalar float).
        strikes: 1D numpy array of strike prices.
        expiries: 1D numpy array of times to expiry in years.
        ivs: 1D numpy array of implied volatilities.
        types: 1D numpy array of option types (0=call, 1=put).
        r: Risk-free rate (default 0.045).
        q: Continuous dividend yield (default 0.0).

    Returns:
        Dictionary with keys 'delta', 'gamma', 'theta', 'vega', 'vanna',
        'charm', 'vomma', 'zomma', each mapping to a 1D numpy array of
        Greek values corresponding to the input arrays.

    Example:
        >>> import numpy as np
        >>> greeks = compute_all_greeks(
        ...     spot=100.0,
        ...     strikes=np.array([95.0, 100.0, 105.0]),
        ...     expiries=np.array([0.25, 0.25, 0.25]),
        ...     ivs=np.array([0.2, 0.2, 0.2]),
        ...     types=np.array([0, 0, 1]),
        ... )
        >>> logger.info(greeks['delta'])
    """
    # Ensure contiguous float64 arrays for numba
    K = np.ascontiguousarray(strikes, dtype=np.float64)
    T = np.ascontiguousarray(expiries, dtype=np.float64)
    IV = np.ascontiguousarray(ivs, dtype=np.float64)
    kind = np.ascontiguousarray(types, dtype=np.int32)

    # Delta (per-element kind)
    delta = np.empty_like(K)
    call_mask = kind == 0
    put_mask = kind == 1

    if np.any(call_mask):
        delta[call_mask] = bs_delta_vec(
            spot, K[call_mask], T[call_mask], IV[call_mask], q, r, 0
        )
    if np.any(put_mask):
        delta[put_mask] = bs_delta_vec(
            spot, K[put_mask], T[put_mask], IV[put_mask], q, r, 1
        )

    # Gamma (same for calls and puts)
    gamma = bs_gamma_vec(spot, K, T, IV, q, r)

    # Vega (same for calls and puts)
    vega = bs_vega_vec(spot, K, T, IV, q, r)

    # Vanna (same for calls and puts)
    vanna = bs_vanna_vec(spot, K, T, IV, q, r)

    # Charm (per-element kind)
    charm = np.empty_like(K)
    if np.any(call_mask):
        charm[call_mask] = bs_charm_vec(
            spot, K[call_mask], T[call_mask], IV[call_mask], q, 0
        )
    if np.any(put_mask):
        charm[put_mask] = bs_charm_vec(
            spot, K[put_mask], T[put_mask], IV[put_mask], q, 1
        )

    # Vomma (same for calls and puts)
    vomma = bs_vomma_vec(spot, K, T, IV, q, r)

    # Zomma (same for calls and puts)
    zomma = bs_zomma_vec(spot, K, T, IV, q, r)

    # Theta (per-element kind, uses internal helper)
    theta = _bs_theta_vec(spot, K, T, IV, r, q, kind)

    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "vanna": vanna,
        "charm": charm,
        "vomma": vomma,
        "zomma": zomma,
    }
