"""
backend/services/gex_history.py

Pure, side-effect-free helpers for building a per-day ``gex_total`` time
series from Databento end-of-day chains stored in MongoDB.

The output shape — ``List[{"ts": iso8601, "gex_total": float, "spot": float}]``
— matches the ``gex_history`` column consumed by
``backend.services.ml.features.add_gex_features`` (see its docstring for the
leakage contract).

Math: per-strike GEX is computed as

    gex_i = sign_i * gamma_i * OI_i * 100 * spot * 0.01

where ``sign_i = +1`` for calls and ``-1`` for puts. ``gamma_i`` is the
Black-Scholes gamma at ``(spot, strike_i, T_i, iv=0.20, r=0.045, q=0)``.
This mirrors the canonical formula used in ``scripts/compute_gex_features.py``
and is the same convention the rest of the platform expects for ``gex_total``.

SCALE CONVENTION (S^1 -- ML FEATURE, MODEL-LOCKED). This single-spot-factor
scale, with fixed ``iv=0.20`` (``_IV_FALLBACK``) and ``r=0.045`` (``_RISK_FREE``),
is a frozen model-input contract: ``gex_total`` here -> the ``gex_history``
collection -> ``ml.features.add_gex_features`` -> the trained GBM models.
Changing the scale or those constants silently shifts every training feature and
breaks inference at the trained scale. It is DISTINCT from the S^2 dollar-GEX
(display) scale in ``services/gex_aggregator.py``; the two differ by a factor of
``spot`` and are NOT interchangeable. Both scales and their ratio are pinned by
``tests/services/test_gex_aggregator_oracle.py``. Audit:
``docs/superpowers/specs/2026-06-13-gex-gamma-correctness-audit-design.md``.

No synthetic data: the functions here only aggregate real fields from
``databento_eod_chains`` documents. Days without a chain or without an
underlying bar are skipped (not interpolated). The Mongo handle is passed
in so unit tests can inject a fake DB.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List

import numpy as np
from scipy.stats import norm

log = logging.getLogger("services.gex_history")

# Constants mirror scripts/compute_gex_features.py — single source of truth
# for the platform-wide GEX convention. If these change, change them there
# too (and audit downstream features).
_IV_FALLBACK = 0.20
_RISK_FREE = 0.045
_OPTION_MULTIPLIER = 100.0
_PCT_MOVE = 0.01
_MIN_T_YEARS = 0.01  # 3-4 trading days — guards against div-by-zero
_DEFAULT_T_YEARS = 0.25  # 3-month fallback when expiry is unparseable


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return f


def _is_call(contract_type: Any) -> bool:
    """Accept 'call'/'CALL'/'C'/'c' as call, anything else as put."""
    if contract_type is None:
        return False
    s = str(contract_type).strip().lower()
    return s in ("call", "c")


def compute_gex_total_for_chain(chain: Dict[str, Any], spot: float) -> float:
    """One day's ``gex_total`` (signed, summed across strikes) for a Databento chain.

    ``chain`` is a document from ``databento_eod_chains`` with shape::

        {
            "ticker": "SPY",
            "day": "2024-01-02",          # ISO date
            "contracts": {
                "SPY   240105C00475000": {
                    "underlying": "SPY",
                    "expiry": "2024-01-05",
                    "type": "call",       # or "put"
                    "strike": 475.0,
                    "oi": 18992,
                },
                ...
            },
        }

    Contracts with missing/non-positive ``strike`` or ``oi`` are silently
    skipped (logged at DEBUG). Contracts with unparseable ``expiry`` fall
    back to a 3-month tenor. Returns ``0.0`` for an empty or all-invalid
    chain — never raises on malformed input.
    """
    if spot is None or spot <= 0:
        return 0.0
    contracts = chain.get("contracts") or {}
    if not contracts:
        return 0.0

    day_str = chain.get("day")
    try:
        today = date.fromisoformat(day_str) if day_str else date.today()
    except (TypeError, ValueError):
        today = date.today()

    strikes: List[float] = []
    ois: List[float] = []
    signs: List[float] = []
    Ts: List[float] = []

    for sym, c in contracts.items():
        if not isinstance(c, dict):
            log.debug("skip non-dict contract %r", sym)
            continue
        k = _safe_float(c.get("strike"), 0.0)
        oi = _safe_float(c.get("oi"), 0.0)
        if k <= 0 or oi <= 0:
            # Missing/zero strike or OI — can't contribute. Test 3's contract.
            continue
        expiry_raw = c.get("expiry")
        try:
            exp = date.fromisoformat(expiry_raw)
            T = max((exp - today).days / 365.0, _MIN_T_YEARS)
        except (TypeError, ValueError):
            T = _DEFAULT_T_YEARS

        strikes.append(k)
        ois.append(oi)
        signs.append(1.0 if _is_call(c.get("type")) else -1.0)
        Ts.append(T)

    if not strikes:
        return 0.0

    K = np.asarray(strikes, dtype=float)
    OI = np.asarray(ois, dtype=float)
    sgn = np.asarray(signs, dtype=float)
    T_arr = np.asarray(Ts, dtype=float)
    iv = _IV_FALLBACK

    # Black-Scholes gamma (q=0): gamma = phi(d1) / (S * sigma * sqrt(T))
    d1 = (np.log(spot / K) + (_RISK_FREE + 0.5 * iv ** 2) * T_arr) / (
        iv * np.sqrt(T_arr)
    )
    gamma = norm.pdf(d1) / (spot * iv * np.sqrt(T_arr))
    # Per-strike GEX: sign * gamma * OI * multiplier * spot * 1% move
    gex = sgn * gamma * OI * _OPTION_MULTIPLIER * spot * _PCT_MOVE
    total = float(np.sum(gex))
    if total != total:  # NaN — defensive; shouldn't happen with the math above
        return 0.0
    return total


def _iso_utc(d: str) -> str:
    """Render a yyyy-mm-dd day string as an ISO-8601 UTC timestamp at midnight."""
    return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()


async def build_gex_history(
    ticker: str,
    *,
    start_date: date,
    end_date: date,
    mongo_db: Any,
) -> List[Dict[str, Any]]:
    """Return per-day ``gex_total`` rows for ``ticker`` in ``[start_date, end_date]``.

    For each trading day that has BOTH a ``databento_eod_chains`` row AND an
    ``underlying_bars`` row, emit::

        {"ts": "<iso8601 UTC>", "gex_total": <float>, "spot": <float>}

    Days missing either side are skipped — never interpolated, never
    synthesized. Output is sorted chronologically ascending regardless of
    Mongo iteration order.

    ``mongo_db`` is a pymongo Database (or any object with the same
    ``[collection].find(query[, projection])`` interface), passed in so
    tests can inject a fake.
    """
    if end_date < start_date:
        return []
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    bars_cur = mongo_db["underlying_bars"].find(
        {"ticker": ticker, "date": {"$gte": start_str, "$lte": end_str}},
        {"date": 1, "close": 1, "_id": 0},
    )
    spots: Dict[str, float] = {}
    async for b in bars_cur:
        d = b.get("date")
        c = _safe_float(b.get("close"), 0.0)
        if d and c > 0:
            spots[d] = c

    chains_cur = mongo_db["databento_eod_chains"].find(
        {"ticker": ticker, "day": {"$gte": start_str, "$lte": end_str}},
        {"day": 1, "contracts": 1, "_id": 0},
    )

    rows: List[Dict[str, Any]] = []
    async for chain in chains_cur:
        day = chain.get("day")
        if not day:
            continue
        spot = spots.get(day)
        if spot is None or spot <= 0:
            # No matching bar — skip per the no-synthesis rule.
            continue
        gex_total = compute_gex_total_for_chain(chain, spot)
        rows.append(
            {
                "ts": _iso_utc(day),
                "gex_total": gex_total,
                "spot": spot,
            }
        )

    rows.sort(key=lambda r: r["ts"])
    return rows


def calc_gex_timeframes(
    spot: float,
    contracts: List[Dict[str, Any]],
    ticker: str,
) -> Dict[str, Any]:
    """Aggregate GEX by timeframe buckets: 0DTE, 1DTE, weekly, monthly, all.

    Returns:
        {"timeframes": {"0DTE": {...}, "1DTE": {...}, "weekly": {...}, "monthly": {...}, "all": {...}}}
        Each bucket contains: {"gex_total": float, "call_gex": float, "put_gex": float, "net_gex": float, "n_contracts": int}
    """
    from datetime import date

    today = date.today()
    buckets = {"0DTE": [], "1DTE": [], "weekly": [], "monthly": [], "all": []}

    for c in contracts:
        expiry_str = c.get("expiry", "")
        try:
            exp_date = date.fromisoformat(expiry_str)
        except (ValueError, TypeError):
            buckets["all"].append(c)
            continue
        dte = (exp_date - today).days
        if dte <= 0:
            buckets["0DTE"].append(c)
        elif dte == 1:
            buckets["1DTE"].append(c)
        elif dte <= 7:
            buckets["weekly"].append(c)
        else:
            buckets["monthly"].append(c)
        buckets["all"].append(c)

    def _bs_gamma(spot: float, strike: float, T: float, iv: float) -> float:
        """Black-Scholes gamma. Returns 0.0 on invalid inputs."""
        if spot <= 0 or strike <= 0 or T <= 0 or iv <= 0:
            return 0.0
        try:
            from math import log, sqrt
            from scipy.stats import norm as _norm
            d1 = (log(spot / strike) + (_RISK_FREE + 0.5 * iv * iv) * T) / (iv * sqrt(T))
            return float(_norm.pdf(d1)) / (spot * iv * sqrt(T))
        except Exception:
            return 0.0

    def _agg(contract_list):
        call_gex = 0.0
        put_gex = 0.0
        # Track per-strike GEX for top floors/ceilings
        strike_gex: Dict[float, float] = {}
        n_valid = 0
        for c in contract_list:
            gamma = _safe_float(c.get("gamma"), 0.0)
            if gamma <= 0:
                # Contract has no pre-computed gamma — compute from B-S
                gamma = _bs_gamma(
                    spot,
                    _safe_float(c.get("strike"), 0.0),
                    _safe_float(c.get("T"), 0.0),
                    _safe_float(c.get("iv"), 0.0),
                )
            if gamma <= 0:
                continue
            oi = _safe_float(c.get("oi", c.get("open_interest", 0)))
            if oi <= 0:
                continue
            n_valid += 1
            gex = gamma * oi * 100.0 * spot * 0.01
            strike = _safe_float(c.get("strike"), 0.0)
            if _is_call(c.get("type")):
                call_gex += gex
                strike_gex[strike] = strike_gex.get(strike, 0.0) + gex
            else:
                put_gex -= gex  # negative for puts (dealer convention)
                strike_gex[strike] = strike_gex.get(strike, 0.0) - gex
        net_gex = call_gex + put_gex
        # Top floors = highest positive GEX strikes (above spot, stabilizing)
        top_floors = sorted(
            [{"strike": k, "gex": round(v, 2)} for k, v in strike_gex.items() if k > spot and v > 0],
            key=lambda x: x["gex"], reverse=True
        )[:3]
        # Top ceilings = highest negative GEX strikes below spot (destabilizing)
        top_ceilings = sorted(
            [{"strike": k, "gex": round(v, 2)} for k, v in strike_gex.items() if k <= spot and v < 0],
            key=lambda x: x["gex"]
        )[:3]
        return {
            "gex_total": round(abs(call_gex) + abs(put_gex), 2),
            "call_gex": round(call_gex, 2),
            "put_gex": round(put_gex, 2),
            "net_gex": round(net_gex, 2),
            "n_contracts": len(contract_list),
            "contract_count": n_valid,
            "top_floors": top_floors,
            "top_ceilings": top_ceilings,
        }

    return {"timeframes": {k: _agg(v) for k, v in buckets.items()}}


__all__ = [
    "compute_gex_total_for_chain",
    "build_gex_history",
    "calc_gex_timeframes",
]
