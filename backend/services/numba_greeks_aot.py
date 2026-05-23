"""
numba_greeks_aot.py  —  AOT-compiled Greek kernels for zero cold-start latency.

This module is compiled into a shared object (``.so``) via ``numba.pycc.CC``
during the Docker build phase (or via ``python scripts/compile_greeks.py``).

Each function is **self-contained** — no calls to other functions — because
``pycc`` does not support cross-function dispatch. All math (norm_pdf,
norm_cdf, d1/d2) is inlined directly in each kernel.

Usage (compile)::

    $ python scripts/compile_greeks.py

Usage (runtime) — in ``numba_greeks.py``::

    try:
        from numba_greeks_compiled import (       # noqa: F401
            compute_delta, compute_gamma, ...
        )
        _AOT_AVAILABLE = True
    except ImportError:
        _AOT_AVAILABLE = False
"""

from __future__ import annotations

import math

import numba
import numpy as np
from numba.pycc import CC

# ---------------------------------------------------------------------------
# CC compiler — registry of AOT-exported functions
# ---------------------------------------------------------------------------
cc = CC("numba_greeks_compiled")

# Type aliases for readability
f8 = numba.float64
f8_1d = numba.types.Array(numba.float64, 1, "C")
i4_1d = numba.types.Array(numba.int32, 1, "C")


# ═══════════════════════════════════════════════════════════════════════════
# 1.  Gamma  (same for calls and puts)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_gamma", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, f8))
def compute_gamma(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.05,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorised gamma — AOT-compiled. All math inlined."""
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2pi = math.sqrt(2.0 * math.pi)
    for i in range(n):
        # NaN / boundary guard (I-8)
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        # d1 = (ln(S/K) + (r - q + 0.5*sigma^2)*T) / (sigma*sqrtT)
        d1 = (math.log(S / K[i]) + (r - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        # norm_pdf(d1) = exp(-0.5*d1^2) / sqrt(2*pi)
        norm_pdf = math.exp(-0.5 * d1 * d1) / sqrt2pi
        out[i] = math.exp(-q * T[i]) * norm_pdf / (S * sigma[i] * sqrtT)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2.  Delta  (0 = call, 1 = put)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_delta", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, i4_1d))
def compute_delta(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    kinds: np.ndarray | None = None,
) -> np.ndarray:
    """Vectorised delta — AOT-compiled. All math inlined.

    ``kinds``: per-element 0=call / 1=put array.
    """
    if kinds is None:
        kinds = np.zeros(K.shape[0], dtype=np.int32)
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2 = math.sqrt(2.0)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        d1 = (math.log(S / K[i]) + (0.0 - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        # norm_cdf(d1) via erf
        cdf_val = 0.5 * (1.0 + math.erf(d1 / sqrt2))
        if kinds[i] == 0:
            out[i] = math.exp(-q * T[i]) * cdf_val
        else:
            out[i] = math.exp(-q * T[i]) * (cdf_val - 1.0)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 3.  Vega  (same for calls and puts)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_vega", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, f8))
def compute_vega(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.05,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorised vega (per 1 vol point) — AOT-compiled. All math inlined."""
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2pi = math.sqrt(2.0 * math.pi)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        d1 = (math.log(S / K[i]) + (r - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        norm_pdf = math.exp(-0.5 * d1 * d1) / sqrt2pi
        out[i] = S * math.exp(-q * T[i]) * norm_pdf * sqrtT / 100.0
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 4.  Vanna  (same for calls and puts)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_vanna", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, f8))
def compute_vanna(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.05,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorised vanna — AOT-compiled. All math inlined."""
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2pi = math.sqrt(2.0 * math.pi)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        d1 = (math.log(S / K[i]) + (r - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        d2 = d1 - sigma[i] * sqrtT
        norm_pdf = math.exp(-0.5 * d1 * d1) / sqrt2pi
        out[i] = -math.exp(-q * T[i]) * norm_pdf * d2 / sigma[i]
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 5.  Charm  (0 = call, 1 = put)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_charm", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, i4_1d))
def compute_charm(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    q: float = 0.0,
    kinds: np.ndarray | None = None,
) -> np.ndarray:
    """Vectorised charm (delta decay per day) — AOT-compiled. All math inlined."""
    if kinds is None:
        kinds = np.zeros(K.shape[0], dtype=np.int32)
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2 = math.sqrt(2.0)
    sqrt2pi = math.sqrt(2.0 * math.pi)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        # d1, d2 inlined
        r_eff = 0.0  # r=0 for charm as in main numba_greeks
        d1 = (math.log(S / K[i]) + (r_eff - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        d2 = d1 - sigma[i] * sqrtT
        norm_pdf = math.exp(-0.5 * d1 * d1) / sqrt2pi
        cdf_val = 0.5 * (1.0 + math.erf(d1 / sqrt2))
        term1 = q * math.exp(-q * T[i]) * cdf_val
        term2_val = -math.exp(-q * T[i]) * norm_pdf * (
            2.0 * (0.0 - q) * T[i] - d2 * sigma[i] * sqrtT
        ) / (2.0 * T[i] * sigma[i] * sqrtT)
        if kinds[i] == 0:
            out[i] = (term1 - term2_val) / 365.0
        else:
            out[i] = (term1 - math.exp(-q * T[i]) * (1.0 - cdf_val) - term2_val) / 365.0
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 6.  Vomma / Volga  (same for calls and puts)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_vomma", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, f8))
def compute_vomma(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.05,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorised vomma — AOT-compiled. All math inlined."""
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2pi = math.sqrt(2.0 * math.pi)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        d1 = (math.log(S / K[i]) + (r - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        d2 = d1 - sigma[i] * sqrtT
        norm_pdf = math.exp(-0.5 * d1 * d1) / sqrt2pi
        vega_i = S * math.exp(-q * T[i]) * norm_pdf * sqrtT / 100.0
        out[i] = vega_i * d1 * d2 / sigma[i]
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 7.  Zomma  (same for calls and puts)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_zomma", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, f8))
def compute_zomma(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.05,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorised zomma — AOT-compiled. All math inlined."""
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2pi = math.sqrt(2.0 * math.pi)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        d1 = (math.log(S / K[i]) + (r - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        d2 = d1 - sigma[i] * sqrtT
        norm_pdf = math.exp(-0.5 * d1 * d1) / sqrt2pi
        gamma_i = norm_pdf * math.exp(-q * T[i]) / (S * sigma[i] * sqrtT)
        out[i] = gamma_i * (d1 * d2 - 1.0) / sigma[i]
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 8.  Theta  (per-element kind array)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_theta", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, f8, i4_1d))
def compute_theta(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float,
    q: float,
    kinds: np.ndarray,
) -> np.ndarray:
    """Vectorised theta (per day) — AOT-compiled. All math inlined."""
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2 = math.sqrt(2.0)
    sqrt2pi = math.sqrt(2.0 * math.pi)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        d1 = (math.log(S / K[i]) + (r - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        d2 = d1 - sigma[i] * sqrtT
        norm_pdf = math.exp(-0.5 * d1 * d1) / sqrt2pi
        common = -(S * math.exp(-q * T[i]) * norm_pdf * sigma[i]) / (2.0 * sqrtT)
        if kinds[i] == 0:
            cdf_d1 = 0.5 * (1.0 + math.erf(d1 / sqrt2))
            cdf_d2 = 0.5 * (1.0 + math.erf(d2 / sqrt2))
            out[i] = (
                common
                - r * K[i] * math.exp(-r * T[i]) * cdf_d2
                + q * S * math.exp(-q * T[i]) * cdf_d1
            ) / 365.0
        else:
            neg_cdf_d1 = 0.5 * (1.0 + math.erf(-d1 / sqrt2))
            neg_cdf_d2 = 0.5 * (1.0 + math.erf(-d2 / sqrt2))
            out[i] = (
                common
                + r * K[i] * math.exp(-r * T[i]) * neg_cdf_d2
                - q * S * math.exp(-q * T[i]) * neg_cdf_d1
            ) / 365.0
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 9.  Call / Put prices  (for completeness)
# ═══════════════════════════════════════════════════════════════════════════

@cc.export("compute_call_price", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, f8))
def compute_call_price(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.045,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorised call price — AOT-compiled. All math inlined."""
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2 = math.sqrt(2.0)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        d1 = (math.log(S / K[i]) + (r - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        d2 = d1 - sigma[i] * sqrtT
        cdf_d1 = 0.5 * (1.0 + math.erf(d1 / sqrt2))
        cdf_d2 = 0.5 * (1.0 + math.erf(d2 / sqrt2))
        out[i] = (
            S * math.exp(-q * T[i]) * cdf_d1
            - K[i] * math.exp(-r * T[i]) * cdf_d2
        )
    return out


@cc.export("compute_put_price", f8_1d(f8, f8_1d, f8_1d, f8_1d, f8, f8))
def compute_put_price(
    S: float,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.045,
    q: float = 0.0,
) -> np.ndarray:
    """Vectorised put price — AOT-compiled. All math inlined."""
    n = K.shape[0]
    out = np.empty(n, dtype=np.float64)
    sqrt2 = math.sqrt(2.0)
    for i in range(n):
        if S <= 0.0 or K[i] <= 0.0 or T[i] <= 0.0 or sigma[i] <= 0.0 \
           or math.isnan(S) or math.isnan(K[i]) or math.isnan(T[i]) or math.isnan(sigma[i]):
            out[i] = 0.0
            continue
        sqrtT = math.sqrt(T[i])
        d1 = (math.log(S / K[i]) + (r - q + 0.5 * sigma[i] * sigma[i]) * T[i]) \
             / (sigma[i] * sqrtT)
        d2 = d1 - sigma[i] * sqrtT
        neg_cdf_d1 = 0.5 * (1.0 + math.erf(-d1 / sqrt2))
        neg_cdf_d2 = 0.5 * (1.0 + math.erf(-d2 / sqrt2))
        out[i] = (
            K[i] * math.exp(-r * T[i]) * neg_cdf_d2
            - S * math.exp(-q * T[i]) * neg_cdf_d1
        )
    return out
