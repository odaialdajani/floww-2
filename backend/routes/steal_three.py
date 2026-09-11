"""
Steal-Three Router (steal-list ranks #1, #3, #5)
====================================================

Single consolidated FastAPI ``APIRouter`` for the three top-ranked items
on the steal-list integration roadmap. Mounted by:

  * ``backend/server.py``     — canonical :8000 (behind the existing
                                CORSMiddleware, alongside ``analytics_router``)
  * ``backend/services/steal_three_server.py`` — dev sidecar on :8001
                                (corner-case convenience for offline work)

Endpoints:

  GET ``/api/dual_gex/{ticker}``             — rank #1 Dual-GEX + activity ratio
  GET ``/api/iv_mid/{ticker}?width=N``        — rank #5 IV-from-mid cross-check
  GET ``/api/screener/income?symbol=...``     — rank #3 Wheel income screener

Sidecar-only ``/health`` lives in ``steal_three_server.py`` (server.py already
has its own root-level probes; we don't double them up).

Routes are intentionally synchronous (``def`` not ``async def``) so FastAPI
runs the yfinance-bound handlers in its threadpool — ``yfinance.Ticker``
synchronously scrapes HTTP and would otherwise block the event loop.

Audit: ``docs/reports/2026-07-11-steal-list-integration-roadmap.md`` #1, #3, #5
       ``backend/tests/routes/test_steal_three_routes.py`` (smoke)
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from bs_greeks import bs_call_price, bs_put_price, implied_vol_from_price

try:
    import decoder_core as _dc_mod
    _dc_iv = _dc_mod.implied_vol_from_price
except ImportError:  # pragma: no cover
    _dc_iv = None
from services.consensus_pricing import (
    compute_consensus_per_expiry,
    compute_overall_consensus,
)

# NOTE: aggregate_sentiment will be re-imported when the deferred social_flow_pipeline wiring
# lands (per the .md PARTIAL block).
from services.gex_dual import DualGexCalculator
from services.max_pain import compute_max_pain_per_expiry, compute_overall_max_pain
from services.screeners.wheel_income import rank_calls_to_sell, rank_puts_to_sell
from services.sentiment import TEXTBLOB_AVAILABLE, VADER_AVAILABLE, clean_text, clean_text_sentiment, score_text

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Canonical constants — DO NOT drift.
# _RISK_FREE matches backend/server.py:495 (used in calc_probability_distribution).
# ----------------------------------------------------------------------
_RISK_FREE: float = 0.05       # canonical r used by backend/server.py:495
_DIV_YIELD: float = 0.0        # yfinance doesn't give a clean dividendYield per strike

router = APIRouter()


# ----------------------------------------------------------------------
# Helpers (kept identical to the prior sidecar implementation).
# ----------------------------------------------------------------------

def _load_chain(
    ticker: str,
    expiry_index: int = 0,
    min_dte: int = 0,
) -> tuple[float, list[dict], list[dict], str | None]:
    """Fetch spot + nearest-listed-expiry chain via yfinance.

    Returns (spot, calls_list, puts_list, expiry_str). Offers a single
    call to ``yt.history`` (5d) and ``yt.option_chain(expiry_attr[0])``.
    Raises ``HTTPException(404)`` for symbols that have no chain (forex / futures).
    """
    yt = yf.Ticker(ticker.upper())
    hist = yt.history(period="5d")
    if hist is None or len(hist) == 0:
        raise HTTPException(status_code=404, detail=f"No price history for {ticker}")
    spot = float(hist["Close"].iloc[-1])
    expiry_attr = getattr(yt, "options", None) or []
    if not expiry_attr:
        raise HTTPException(status_code=404, detail=f"No options chain available for {ticker}")
    if min_dte > 0:
        # Skip expiries closer than min_dte (e.g. the 0DTE front expiry,
        # where T=0 makes a Black-Scholes IV solve impossible). Falls back
        # to expiry_index if nothing qualifies (deep-illiquid names).
        picks = _select_expiries_in_window(expiry_attr, min_dte, 36500, cap=1)
        chosen_expiry = picks[0] if picks else str(expiry_attr[expiry_index])
    else:
        chosen_expiry = str(expiry_attr[expiry_index])
    chain = yt.option_chain(chosen_expiry)
    calls = chain.calls.fillna(0).to_dict(orient="records") if chain.calls is not None else []
    puts = chain.puts.fillna(0).to_dict(orient="records") if chain.puts is not None else []
    for c in calls:
        c.setdefault("expiry", chosen_expiry)
    for p in puts:
        p.setdefault("expiry", chosen_expiry)
    return spot, calls, puts, chosen_expiry


def _t_years_from_dte(dte_days: int) -> float:
    return max(int(dte_days), 0) / 365.0


# ----------------------------------------------------------------------
# Rank #1 — Dual-GEX + activity-ratio badge.
#
# Defensive degrade (steal-list triage 2026-07-15): wrap the entire
# route body in try/except so any upstream exception (yfinance network
# error, GexAggregator._resolve KeyError on a truly malformed broker
# row, numba kernel weirdness, etc.) falls through to a well-formed
# EMPTY-SHAPE response that mirrors ``DualGexCalculator.empty`` plus the
# route's documented decorations. ``DualGEXBadge.jsx`` reads the empty
# shape's keys (``activity_ratio``, ``activity_badge``, ``net_gex_volume``
# etc.) and renders the offline tile state cleanly rather than the
# dashboard hard-crashing on a 500. The fidelity: a regression test
# pins this contract (``test_dual_gex_route_defensive_degrade_when_dual_gex_raises``).
# ----------------------------------------------------------------------
@router.get("/api/dual_gex/{ticker}")
def dual_gex(ticker: str) -> dict[str, Any]:
    # Empty shape mirrors DualGexCalculator.compute()'s documented
    # "empty contracts / spot <= 0" return so the frontend sees the
    # same keys regardless of whether the failure is upstream (yfinance)
    # or downstream (DualGexCalculator, GexAggregator._resolve).
    empty_shape: dict[str, Any] = {
        "strikes": [],
        "gex_oi_1d": [],
        "gex_volume_1d": [],
        "total_gex": 0.0,
        "net_gex_oi": 0.0,
        "net_gex_volume": 0.0,
        "gex_oi_total": 0.0,
        "gex_volume_total": 0.0,
        "activity_ratio": 0.0,
        "activity_badge": "quiet",
        "positive_gex_oi": 0.0,
        "positive_gex_volume": 0.0,
        "ticker": ticker.upper(),
        "spot": 0.0,
        "source": "steal-three-router",
        "note": "dual_gex endpoint degraded gracefully — see error key for cause.",
        "error": None,
    }
    try:
        spot, calls, puts, _expiry = _load_chain(ticker)
        # Production gamma via the numba Black-Scholes pipeline (2026-09-03):
        # bare yfinance rows carry strike + impliedVolatility + stamped
        # expiry but no greeks. Compute per-row gamma from (S, K, T, IV)
        # so the activity ratio is a true Σ±γ·Vol / Σ±γ·OI instead of
        # degenerating to |signed Vol| / |signed OI| (gamma=1.0 fallback).
        # Bare rows also carry no type column — stamp side here or
        # GexAggregator._resolve raises KeyError (live 500, 2026-07-15).
        today = datetime.now(UTC).date()
        sided: list[tuple[str, dict]] = (
            [("call", c) for c in calls] + [("put", p) for p in puts]
        )
        gammas: list[float] | None = None
        try:
            import numpy as np

            from services.numba_greeks import bs_gamma_vec

            _K: list[float] = []
            _IV: list[float] = []
            _T: list[float] = []
            for _, c in sided:
                _K.append(float(c.get("strike") or 0))
                _IV.append(float(c.get("impliedVolatility") or c.get("iv") or 0.2))
                try:
                    _exp_d = datetime.strptime(
                        str(c.get("expiry", "")), "%Y-%m-%d"
                    ).date()
                    _dte = max((_exp_d - today).days, 1)
                except (ValueError, TypeError):
                    _dte = 30
                _T.append(_dte / 365.0)
            gammas = [
                float(g) for g in bs_gamma_vec(
                    float(spot), np.array(_K), np.array(_T), np.array(_IV),
                    q=_DIV_YIELD, r=_RISK_FREE,
                )
            ]
        except Exception as exc:  # noqa: BLE001 — numba fallback, not a route failure
            logger.warning("dual_gex: numba gamma failed for %s (%s); using 1.0", ticker, exc)
            gammas = None
        augmented: list[dict] = []
        for (side, c), g in zip(
            sided, gammas if gammas is not None else [1.0] * len(sided),
            strict=False,
        ):
            aug = dict(c)
            aug.setdefault("type", side)
            aug["gamma"] = g
            augmented.append(aug)

        result = DualGexCalculator.compute(spot, augmented)
        result["ticker"] = ticker.upper()
        result["spot"] = round(spot, 4)
        result["source"] = "steal-three-router"
        result["gamma_model"] = "numba_bs" if gammas is not None else "flat_1.0_fallback"
        result["note"] = (
            "Per-row gamma from the numba Black-Scholes pipeline "
            "(S, K, T, IV); flat 1.0 only if the kernel fails."
        )

        # ── Paper-accurate GEX metrics (Barbon-Buraschi + Ni-Pearson) ──
        try:
            from services.gex_paper_accurate import compute_gamma_imbalance
            net_gex = result.get("net_gex_oi", 0.0)
            gi = compute_gamma_imbalance(net_gex, spot, 75_000_000)
            result["gamma_imbalance"] = gi
        except Exception:
            pass  # silent by design: gamma_imbalance key simply absent from result; response stays 200

        return result
    except Exception as exc:    # pragma: no cover (defensive degrade)
        empty_shape["error"] = f"{type(exc).__name__}: {exc}"
        return empty_shape


# ----------------------------------------------------------------------
# Rank #5 — IV-from-mid cross-check (Newton solver + bisection fallback).
# ----------------------------------------------------------------------
@router.get("/api/iv_mid/{ticker}")
def iv_mid(
    ticker: str,
    width: int = Query(6, ge=1, le=20, description="Strikes on either side of ATM"),
) -> dict[str, Any]:
    # min_dte=1: never solve on the 0DTE front expiry — T=0 makes the
    # Black-Scholes inversion impossible (every row came back INVALID).
    spot, calls, puts, expiry = _load_chain(ticker, min_dte=1)
    # Estimate step size from sorted strike series (yfinance returns strikes ascending).
    if calls:
        center = min(calls, key=lambda c: abs(c["strike"] - spot))["strike"]
        step = (calls[1]["strike"] - calls[0]["strike"]) if len(calls) > 1 else 1.0
        atmos_calls = sorted(
            [c for c in calls if abs(c["strike"] - center) <= width * step],
            key=lambda c: c["strike"],
        )
    else:
        atmos_calls = []
    if puts:
        center_p = min(puts, key=lambda p: abs(p["strike"] - spot))["strike"]
        step_p = (puts[1]["strike"] - puts[0]["strike"]) if len(puts) > 1 else 1.0
        atm_puts = sorted(
            [p for p in puts if abs(p["strike"] - center_p) <= width * step_p],
            key=lambda p: p["strike"],
        )
    else:
        atm_puts = []

    dte_days = 0
    if expiry:
        try:
            dte_days = max(
                (datetime.strptime(expiry, "%Y-%m-%d").date() - datetime.now(UTC).date()).days,
                0,
            )
        except ValueError:
            dte_days = 0
    T = _t_years_from_dte(dte_days)

    out_rows: list[dict] = []
    for row in atmos_calls:
        out_rows.append(_iv_row(row, spot, T, "call", dte_days))
    for row in atm_puts:
        out_rows.append(_iv_row(row, spot, T, "put", dte_days))

    return {
        "ticker": ticker.upper(),
        "spot": round(spot, 4),
        "expiry": str(expiry) if expiry else None,
        "T_years": round(T, 4),
        "rows": out_rows,
        "source": "steal-three-router",
    }


def _iv_row(row: dict, spot: float, T: float, kind: str, dte_days: int = 0) -> dict[str, Any]:
    """Solve IV from the bid/ask mid (Newton + bisection fallback in bs_greeks).

    Returns a dict with yfinance_iv vs solved_iv vs round-trip residual.
    Includes a sentinel ``solved_iv_is_invalid`` flag so the frontend can
    distinguish 'intrinsic-floor guard tripped' from 'genuine zero IV', plus
    a machine-readable ``invalid_reason`` (None when valid):
      zero_mid | below_intrinsic | degenerate_expiry | solve_failed
    """
    K = float(row["strike"])
    bid = float(row.get("bid") or 0.0)
    ask = float(row.get("ask") or 0.0)
    if bid > 0 and ask > 0:
        mid = 0.5 * (bid + ask)
    else:
        mid = float(row.get("lastPrice") or 0.0)
    last_price = float(row.get("lastPrice") or 0.0)
    raw_iv = float(row.get("impliedVolatility") or 0.0)
    if raw_iv <= 0 or raw_iv > 3.0:
        raw_iv = 0.0

    invalid_reason: str | None = None
    # Vega collapses as T -> 0 (1-DTE rows: Newton explodes, bisection
    # starves on penny time-value). Floor the *solve* T at 2 days; the
    # displayed T_years is untouched.
    solve_T = max(T, 2 / 365.0)
    if T <= 0:
        invalid_reason = "degenerate_expiry"
    elif mid <= 0:
        invalid_reason = "zero_mid"
    else:
        intrinsic = max(spot - K, 0.0) if kind == "call" else max(K - spot, 0.0)
        if mid < intrinsic - 1e-8:
            # Stale wide quote below parity — no IV exists. Flag honestly
            # instead of letting the solver spin and return boundary dust.
            invalid_reason = "below_intrinsic"

    # float() casts: the Newton solve returns np.float64 when it actually
    # runs (T>0); numpy scalars leak numpy.bool into the == comparison below
    # and Pydantic cannot serialize them (live 500, 2026-07-15).
    # 2026-08-22: decoder_core Rust solver first — parity verified, ~723x
    # faster per solve; python fallback retained.
    if invalid_reason is None and mid > 0 and _dc_iv is not None:
        try:
            solved_iv = float(_dc_iv(mid, spot, K, solve_T, kind, q=_DIV_YIELD, r=_RISK_FREE))
        except Exception:
            solved_iv = float(implied_vol_from_price(
                mid, spot, K, solve_T, kind=kind, q=_DIV_YIELD, r=_RISK_FREE
            ))
    elif invalid_reason is None and mid > 0:
        solved_iv = float(implied_vol_from_price(
            mid, spot, K, solve_T, kind=kind, q=_DIV_YIELD, r=_RISK_FREE
        ))
    else:
        solved_iv = 0.0
    if invalid_reason is None and solved_iv == 0.0:
        invalid_reason = "solve_failed"

    # Round-trip sanity: plug solved sigma back into bs_*_price.
    if solved_iv > 0:
        if kind == "call":
            rt_price = bs_call_price(spot, K, solve_T, solved_iv, r=_RISK_FREE, q=_DIV_YIELD)
        else:
            rt_price = bs_put_price(spot, K, solve_T, solved_iv, r=_RISK_FREE, q=_DIV_YIELD)
        rt_diff = float(abs(rt_price - mid))
    else:
        rt_diff = 0.0

    return {
        "strike": K,
        "kind": kind,
        "mid": round(mid, 4),
        "lastPrice": round(last_price, 4),
        "yfinance_iv": round(raw_iv, 4),
        "solved_iv": round(solved_iv, 4),
        "solved_iv_is_invalid": solved_iv == 0.0,
        "invalid_reason": invalid_reason,
        "iv_delta": round(solved_iv - raw_iv, 4) if raw_iv > 0 else None,
        "round_trip_diff": round(rt_diff, 6),
        "dte_days": dte_days,
    }


# ----------------------------------------------------------------------
# Rank #3 — Wheel income screener (CSP + covered call ranked by ARR).
# ----------------------------------------------------------------------
def _select_expiries_in_window(
    expiry_strs,
    min_dte: int,
    max_dte: int,
    cap: int = 8,
    today=None,
) -> list[str]:
    """Pick listed expiries whose DTE falls inside [min_dte, max_dte].

    Pure logic (injectable ``today`` for tests). Malformed expiry strings
    are skipped. Capped so liquid names (30+ listed expiries) don't blow
    the network budget the way max_pain's loader also guards against.
    """
    if today is None:
        today = datetime.now(UTC).date()
    picked: list[str] = []
    for exp in expiry_strs:
        try:
            dte = (datetime.strptime(str(exp), "%Y-%m-%d").date() - today).days
        except ValueError:
            continue
        if min_dte <= dte <= max_dte:
            picked.append(str(exp))
        if len(picked) >= cap:
            break
    return picked


def _load_chain_window(
    symbol: str,
    min_dte: int,
    max_dte: int,
    cap: int = 8,
) -> tuple[float, list[dict], list[dict]]:
    """Side-preserving multi-expiry loader for the income screener.

    Unlike ``_load_chain`` (front expiry only — today's 0DTE, which the
    screener's min_dte filter then rejects wholesale) this fetches every
    listed expiry inside the [min_dte, max_dte] window, capped. Returns
    (spot, calls, puts) with ``expiry`` stamped on each row.
    """
    yt = yf.Ticker(symbol.upper())
    hist = yt.history(period="5d")
    if hist is None or len(hist) == 0:
        raise HTTPException(status_code=404, detail=f"No price history for {symbol}")
    spot = float(hist["Close"].iloc[-1])
    expiry_attr = getattr(yt, "options", None) or []
    if not expiry_attr:
        raise HTTPException(status_code=404, detail=f"No options chain available for {symbol}")

    calls: list[dict] = []
    puts: list[dict] = []
    for exp_str in _select_expiries_in_window(expiry_attr, min_dte, max_dte, cap):
        try:
            chain = yt.option_chain(exp_str)
        except Exception as exc:  # noqa: BLE001 — best-effort per-expiry fetch
            logger.warning(
                "income-screener: skipping expiry=%s for symbol=%s (%s)",
                exp_str, symbol.upper(), exc.__class__.__name__,
            )
            continue
        cs = chain.calls.fillna(0).to_dict(orient="records") if chain.calls is not None else []
        ps = chain.puts.fillna(0).to_dict(orient="records") if chain.puts is not None else []
        for c in cs:
            c.setdefault("expiry", exp_str)
        for p in ps:
            p.setdefault("expiry", exp_str)
        calls.extend(cs)
        puts.extend(ps)
    return spot, calls, puts


# ----------------------------------------------------------------------
# Shared income-screener runner (steal-list triage 2026-07-15)
#
# Extracted from the prior monolithic screener_income body so that
# BOTH ``/api/screener/income`` and ``/api/wheel_income/{ticker}`` route
# to ONE pure-logic helper. Mirrors the documented pattern at other
# steal-list routes (max_pain + max_pain_drift, consensus_pricing +
# consensus_drift) where the route is a thin wrapper.
# ----------------------------------------------------------------------
def _run_income_screener(
    symbol: str,
    side: str,
    min_iv: float,
    min_volume: int,
    min_dte: int,
    max_dte: int,
    top: int,
) -> dict[str, Any]:
    """Pure-logic runner shared by ``/api/screener/income`` and the
    backwards-compat ``/api/wheel_income/{ticker}`` alias. Validates
    DTE bounds + dispatches to the canonical rank_*_to_sell helpers.

    30s TTL cache (2026-09-03): the loader scrapes 1 + up-to-8 Yahoo
    pages per call and the dashboard mounts this panel on every view —
    without coalescing, panel polling Yahoo-429s itself. Cache key covers
    every filter so distinct screens never share rows.
    """
    if max_dte < min_dte:
        raise HTTPException(
            status_code=400, detail="max_dte must be >= min_dte",
        )
    import time as _time

    _key = (symbol.upper(), side, min_iv, min_volume, min_dte, max_dte, top)
    _now = _time.time()
    _hit = _income_cache.get(_key)
    if _hit is not None and _now - _hit[0] < _INCOME_CACHE_TTL:
        _cached = dict(_hit[1])
        _cached["cached"] = True
        return _cached
    spot, calls, puts = _load_chain_window(symbol, min_dte, max_dte)

    def _keep(c: dict) -> bool:
        exp = c.get("expiry")
        if not exp:
            return True
        try:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - datetime.now(UTC).date()).days
        except ValueError:
            return True
        return min_dte <= dte <= max_dte

    filtered_calls = [c for c in calls if _keep(c)]
    filtered_puts = [c for c in puts if _keep(c)]

    res: dict[str, list[dict]] = {"puts": [], "calls": []}
    if side in ("both", "put"):
        res["puts"] = rank_puts_to_sell(
            filtered_puts, spot,
            min_iv=min_iv, min_volume=min_volume,
            min_dte=min_dte, max_dte=max_dte, top=top,
        )
    if side in ("both", "call"):
        res["calls"] = rank_calls_to_sell(
            filtered_calls, spot,
            min_iv=min_iv, min_volume=min_volume,
            min_dte=min_dte, max_dte=max_dte, top=top,
        )

    result = {
        "symbol": symbol.upper(),
        "spot": round(spot, 4),
        "filters": {
            "min_iv": min_iv,
            "min_volume": min_volume,
            "min_dte": min_dte,
            "max_dte": max_dte,
            "top": top,
        },
        "puts": res["puts"],
        "calls": res["calls"],
        "source": "steal-three-router",
        "cached": False,
    }
    if len(_income_cache) > 256:
        _income_cache.clear()
    _income_cache[_key] = (_now, result)
    return result


# TTL cache for _run_income_screener (key -> (timestamp, result)).
_income_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_INCOME_CACHE_TTL: float = 30.0


@router.get("/api/screener/income")
def screener_income(
    symbol: str = Query(..., min_length=1, max_length=10),
    side: str = Query("both", pattern="^(both|put|call)$"),
    min_iv: float = Query(0.0, ge=0.0, le=3.0),
    min_volume: int = Query(0, ge=0),
    min_dte: int = Query(7, ge=1, le=365),
    max_dte: int = Query(45, ge=1, le=730),
    top: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    """Wheel-Income Screener (steal-list rank #3) — canonical route.

    Backward-compat note: a sibling ``/api/wheel_income/{ticker}``
    route is mounted AFTER this one to support legacy callers/manual
    curl habits — both routes share the ``_run_income_screener``
    helper below, so behavior is identical apart from the ticker
    argument name (``symbol`` vs ``ticker``).
    """
    return _run_income_screener(
        symbol=symbol, side=side,
        min_iv=min_iv, min_volume=min_volume,
        min_dte=min_dte, max_dte=max_dte, top=top,
    )


# ----------------------------------------------------------------------
# Rank #3 — Wheel-Income Screener ALIAS route (backwards-compat).
# Matches the canonical route's body verbatim via the shared helper.
# Declared AFTER ``/api/screener/income`` so FastAPI's path matcher
# prioritises the static (no-path-param) canonical route first if
# any future refinement keys off of that. Here it's purely a
# ``{ticker}``-shaped alias — same semantics, ticker is the symbol.
# ----------------------------------------------------------------------
@router.get("/api/wheel_income/{ticker}")
def wheel_income_alias(
    ticker: str,
    side: str = Query("both", pattern="^(both|put|call)$"),
    min_iv: float = Query(0.0, ge=0.0, le=3.0),
    min_volume: int = Query(0, ge=0),
    min_dte: int = Query(7, ge=1, le=365),
    max_dte: int = Query(45, ge=1, le=730),
    top: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    return _run_income_screener(
        symbol=ticker, side=side,
        min_iv=min_iv, min_volume=min_volume,
        min_dte=min_dte, max_dte=max_dte, top=top,
    )


# ----------------------------------------------------------------------
# Rank #9 — Max Pain per expiry (steal-list [quick-win, partial]).
# ----------------------------------------------------------------------
def _load_multi_expiry_chain(
    ticker: str,
    expiries: int = 8,
) -> tuple[float | None, list[dict], int]:
    """Fetch spot + concatenated calls+puts across the next ``expiries``
    listed-expirations.

    Caps the network blast radius — liquid names list 30+ expiries but for
    a max-pain ranking per expiry the first handful (0DTE → ~3mo) is the
    actionable subset. Returns (spot, contracts_list, expiries_scanned).
    Raises ``HTTPException(404)`` when no chain exists.
    """
    yt = yf.Ticker(ticker.upper())
    expiry_attr = getattr(yt, "options", None) or []
    if not expiry_attr:
        raise HTTPException(status_code=404, detail=f"No options chain available for {ticker}")
    hist = yt.history(period="5d")
    spot = float(hist["Close"].iloc[-1]) if hist is not None and len(hist) > 0 else None

    scanned = 0
    contracts: list[dict] = []
    for exp_str in list(expiry_attr)[:expiries]:
        try:
            chain = yt.option_chain(exp_str)
        except Exception as exc:  # noqa: BLE001 — best-effort per-expiry fetch
            # Log so real upstream breakage isn't silently lost on /api/max_pain.
            # Per standing rule: avoid silent except-clauses; only swallow the
            # identifiably-transient yfinance ones (rate limit, delistings).
            logger.warning(
                "max-pain: skipping expiry=%s for ticker=%s (%s)",
                exp_str, ticker.upper(), exc.__class__.__name__,
            )
            continue
        calls = chain.calls.fillna(0).to_dict(orient="records") if chain.calls is not None else []
        puts = chain.puts.fillna(0).to_dict(orient="records") if chain.puts is not None else []
        for c in calls:
            c.setdefault("expiry", exp_str)
        for p in puts:
            p.setdefault("expiry", exp_str)
        contracts.extend(calls)
        contracts.extend(puts)
        scanned += 1
    return spot, contracts, scanned


@router.get("/api/max_pain/{ticker}")
def max_pain_route(
    ticker: str,
    expiries: int = Query(8, ge=1, le=20, description="Number of listed expiries to scan"),
) -> dict[str, Any]:
    """Per-expiry max-pain strike plus an overall pin number.

    Max pain = the strike where total intrinsic-loss-to-option-holders at
    expiry is MINIMIZED (= the strike where option writers are most
    exposed = the pin magnet). Distinct from the GEX King node (which is
    *gamma*-based). Daily-drift snapshot into DuckDB is intentionally
    deferred (see ``docs/reports/2026-07-11-steal-list-integration-roadmap.md``
    #9 PARTIAL block).
    """
    spot, contracts, scanned = _load_multi_expiry_chain(ticker.upper(), expiries)
    return {
        "ticker": ticker.upper(),
        "spot": round(spot, 4) if spot is not None else None,
        "expiries_scanned": scanned,
        "rows": compute_max_pain_per_expiry(contracts),
        "overall": compute_overall_max_pain(contracts),
        "source": "steal-three-router",
    }


# ----------------------------------------------------------------------
# Steal-Three Router — endpoint inventory
# ----------------------------------------------------------------------
#   GET /api/dual_gex/{ticker}             — rank #1 Dual-GEX + activity ratio
#   GET /api/iv_mid/{ticker}?width=N        — rank #5 IV-from-mid cross-check
#   GET /api/screener/income?symbol=...     — rank #3 Wheel income screener
#   GET /api/max_pain/{ticker}?expiries=N   — rank #9 Max Pain per expiry
#   GET /api/chain_consensus/{ticker}?expiries=N — rank #6 OI-weighted consensus


# ----------------------------------------------------------------------
# Rank #6 — OI-weighted chain consensus per expiry (chain-implied
# pin magnet — distinct from gamma King node + max-pain).
# ----------------------------------------------------------------------
@router.get("/api/chain_consensus/{ticker}")
def chain_consensus_route(
    ticker: str,
    expiries: int = Query(8, ge=1, le=20, description="Number of listed expiries to scan"),
) -> dict[str, Any]:
    """Per-expiry OI-weighted (strike +/- premium) consensus price + overall.

    consensus_price = SUM((strike+premium)*call_OI + (strike-premium)*put_OI) / SUM(all_OI)
    See backend/services/consensus_pricing.py for the algorithm spec + 16-case pytest.
    Drift tracking deferred (.md #6 PARTIAL block).
    """
    spot, contracts, scanned = _load_multi_expiry_chain(ticker.upper(), expiries)
    return {
        "ticker": ticker.upper(),
        "spot": round(spot, 4) if spot is not None else None,
        "expiries_scanned": scanned,
        "rows": compute_consensus_per_expiry(contracts),
        "overall": compute_overall_consensus(contracts),
        "source": "steal-three-router",
    }


# ---------------------------------------------------------------------------
# Sentiment rank — Multi-model VADER + TextBlob agreement gate.
# See backend/services/sentiment.py for the algorithm spec + 16-case pytest.
# ---------------------------------------------------------------------------
@router.get("/api/sentiment")
def sentiment_route(
    text: str = Query("", description="Single text to score (URL-encode). Empty ⇒ neutral no-op."),
) -> dict[str, Any]:
    """Single-text sentiment scorer via VADER+TextBlob agreement gate.

    Returns ``{polarity, subjectivity, label, available}``. For per-ticker
    bulk-aggregate over many headlines/tweets, callers (e.g.
    social_flow_pipeline.py) should call
    ``services.sentiment.aggregate_sentiment(...)`` directly. The single-text
    GET endpoint exists for ad-hoc UI flows and integration tests.
    """
    polarity, subjectivity, label = score_text(text)
    return {
        "text": text,
        "cleaned": clean_text_sentiment(clean_text(text)),
        "polarity": polarity,
        "subjectivity": subjectivity,
        "label": label,
        "available": VADER_AVAILABLE and TEXTBLOB_AVAILABLE,
        "source": "steal-three-router",
    }


def sentiment_mod_attr() -> bool:
    """Tiny shim to avoid circular import — module-level VADER_AVAILABLE AND
    TEXTBLOB_AVAILABLE flag inspection happens inside services.sentiment."""
    from services.sentiment import TEXTBLOB_AVAILABLE, VADER_AVAILABLE
    return VADER_AVAILABLE and TEXTBLOB_AVAILABLE


# ---------------------------------------------------------------------------
# Steal-list #8 — Opportunity Engine
# GET /api/opportunity/{ticker}
# Maps (HMM trend × realised-vol band × IV rank × dealer gamma-sign) into:
#   {
#     "regime": str, "opportunity_score": float,
#     "opportunity_tier": str, "direction": str,
#     "trade_type": str, "trade_bias": str,
#     "invalidation": str, "components": {...}, "warnings": [...]
#   }
# Inputs are query-params for testability; in production these are pulled
# from existing floww services:
#   - hmm_state + hmm_confidence  <- hmm_regime.GaussianHMMRegime().classify()
#   - rv_band                     <- realised_volatility.classify()
#   - iv_rank                     <- vol_analytics.calc_iv_rank_percentile()
#   - gamma_sign                  <- advanced_analytics.calc_gamma_flip_levels()
#   - roc_5d                      <- composite_flow_score helper
# Cleanup matches the canonical steal-three pattern: pure-logic service
# owns the math; this layer owns external I/O + dict assembly + JSON shape.
# Errors degrade to a no_trade response (never a 500).
# ---------------------------------------------------------------------------
@router.get("/api/opportunity/{ticker}")
def opportunity_endpoint(
    ticker: str,
    hmm_state: str | None = None,
    hmm_confidence: float = 0.5,
    rv_band: str | None = None,
    rv_value: float | None = None,
    iv_rank: float | None = None,
    gamma_sign: str | None = None,
    roc_5d: float | None = None,
):
    """Opportunity Engine — pure-sync to keep FastAPI's threadpool happy."""
    try:
        from services.regime_opportunity import compute as opp_compute
        out = opp_compute({
            "hmm_state": hmm_state,
            "hmm_confidence": hmm_confidence,
            "rv_band": rv_band,
            "rv_value": rv_value,
            "iv_rank": iv_rank,
            "gamma_sign": gamma_sign,
            "roc_5d": roc_5d,
        })
        return {"ticker": ticker.upper(), **out}
    except Exception as exc:    # pragma: no cover (defensive degrade)
        return {
            "ticker": ticker.upper(),
            "regime": None,
            "opportunity_score": 0.0,
            "opportunity_tier": "LOW",
            "direction": "NEUTRAL",
            "trade_type": "no_trade",
            "trade_bias": "defensive",
            "invalidation": f"Engine failed: {exc}",
            "components": {
                "trend_component": 0.0,
                "momentum_component": 0.0,
                "alignment_component": 0.0,
                "vol_penalty": 0.5,
                "mean_rev_component": 0.0,
            },
            "warnings": [f"engine exception: {exc}"],
        }



# ---------------------------------------------------------------------------
# Steal-list #10 — Strike-Cone service
# GET /api/strike_cone/{ticker}
# Translates the existing calc_probability_distribution (per-strike
# {prob_above, prob_below, delta}) into concrete strikes at target
# probability and delta levels (16/30/70/84% expected-move bands; 16/30-delta
# iron-condor wings). Pure-logic service owns the math; this layer owns
# external I/O + query-string parsing + defensive degrade.
# ---------------------------------------------------------------------------
@router.get("/api/strike_cone/{ticker}")
def strike_cone_endpoint(
    ticker: str,
    target_probs: str = "0.16,0.30,0.70,0.84",
    target_deltas: str = "0.16,0.30",
    expiries: int = 1,
):
    """Strike cone — strikes at target prob / target delta levels.

    ``target_probs`` and ``target_deltas`` accept comma-separated lists
    (e.g. "0.16,0.30,0.70,0.84" / "0.16,0.30"). Out-of-range tokens
    are silently dropped by the service.
    """
    try:
        from services.strike_cone import compute_cone
        # Parse comma-separated targets with defensive float coercion.
        def _parse_probs(s: str) -> list[float]:
            out: list[float] = []
            for tok in s.split(","):
                tok = tok.strip()
                if not tok:
                    continue
                try:
                    f = float(tok)
                    if 0.0 <= f <= 1.0:
                        out.append(f)
                except (TypeError, ValueError):
                    continue
            return out

        probs = _parse_probs(target_probs)
        deltas = _parse_probs(target_deltas)

        # Defer to the server's own calc for spot + prob_distribution so
        # the route has zero external I/O duplication.  Reuses the same
        # helper as the heatmap builder.
        from server import calc_probability_distribution, fetch_spot_and_chains
        raw = fetch_spot_and_chains(ticker.upper(), max_expiries=max(1, expiries))
        spot = raw.get("spot") or 0.0
        prob_dist = calc_probability_distribution(spot, raw.get("contracts", []))
        out = compute_cone(
            prob_distribution=prob_dist,
            spot=spot,
            target_probs=tuple(probs),
            target_deltas=tuple(deltas),
        )
        return {"ticker": ticker.upper(), **out}
    except Exception as exc:    # pragma: no cover (defensive degrade)
        return {
            "ticker": ticker.upper(),
            "spot": None,
            "n_strikes": 0,
            "method": "linear_interp_bisect",
            "prob_cones": [],
            "delta_cones": [],
            "warnings": [f"engine exception: {exc}"],
        }



# ---------------------------------------------------------------------------
# Steal-list #4 — Risk-Neutral Density (Breeden-Litzenberger implied PDF)
# GET /api/rnd/{ticker}?expiry_index=N
# Translates the chain (call surface for a single expiry) into the
# risk-neutral probability density f_Q(K) = exp(rT) * d²C/dK² via the
# Breeden-Litzenberger formula (1978). Returns the PDF, CDF, expected
# price (= E[S_T] under Q), median, mode, and tail probabilities at the
# canonical spot-relative thresholds (95 / 98 / 102 / 105 %).
#
# Pure-logic service owns the math; this layer owns external I/O + chain
# fetching + defensive degrade. Default expiry_index=1 skips 0DTE because
# T=0 makes the 2nd derivative degenerate (same guard as strike_cone
# which uses min_dte=1). Cleanup matches the canonical steal-three
# pattern: try/except never 500s.
# ---------------------------------------------------------------------------
@router.get("/api/rnd/{ticker}")
def risk_neutral_density_endpoint(
    ticker: str,
    expiry_index: int = Query(
        1, ge=0, le=20,
        description="Listed-expiry index forwarded verbatim to _load_chain. "
                    "Default 1 maps to the first non-0DTE expiry (yfinance "
                    "lists today's 0DTE first for liquid names). "
                    "0 = today's 0DTE (T=0 makes BL degenerate; the engine "
                    "returns an explicit warning rather than crashing). "
                    "2+ = progressively longer-dated expiries (recommended "
                    "for the most stable PDFs — 1DTE chain prices still "
                    "show BL-degenerate artifacts from near-zero time-value).",
    ),
):
    """Breeden–Litzenberger risk-neutral density at one option expiry.

    Reads the chain via ``_load_chain`` (which returns spot + calls + puts
    + chosen_expiry in a single structured tuple, the same helper strike_cone
    uses for its IV inputs). Filters to calls-only (the BL formula is
    call-side) and forwards to ``services.risk_neutral_density.compute_rnd_pdf``
    for the math.

    The route returns the full documented schema:
    {ticker, expiry, spot, T_years, r, n_strikes_used, n_grid_points,
     x_grid, pdf, cdf, expected_price, expected_move_pct, median, mode,
     tail_probs={p_below_95|98pct_spot, p_above_102|105pct_spot},
     warnings, method=cubic_spline_2nd_derivative|central_diff}.

    Defensive degrade: any upstream failure returns a well-formed empty
    dict so the dashboard never breaks on a cold cache.

    Routing hygiene: ``expiry_index`` flows through to ``_load_chain``
    verbatim. The upstream prior bug was a forced ``min_dte=1`` override
    that silently set ``cap=1`` and discarded the user's index — that
    is now removed, and the documented Query contract (0 = 0DTE, 1 =
    first non-0DTE, 2+ longer-dated) is honored as-is.
    """
    try:
        from services.risk_neutral_density import compute_rnd_pdf
        # Pass expiry_index verbatim. Query ge=0 already validates the
        # range, so a single cast suffices. Default of 1 exercises the
        # most useful path (first non-0DTE member of ``yt.options``).
        effective_index = int(expiry_index)
        spot, calls, _puts, chosen_expiry = _load_chain(
            ticker.upper(), expiry_index=effective_index, min_dte=0,
        )
        # Compute T (years to expiry). Default to 1/52 (1 week) if we
        # can't parse the ISO date — that's a sensible minimum-spread
        # assumption for the "to expiry" metric on a chosen chain.
        T = 1.0 / 52.0
        if chosen_expiry:
            try:
                dte = (
                    datetime.strptime(str(chosen_expiry), "%Y-%m-%d").date()
                    - datetime.now(UTC).date()
                ).days
                T = max(int(dte), 0) / 365.0
            except ValueError:
                pass
        out = compute_rnd_pdf(
            chain_calls=calls,
            spot=float(spot) if spot is not None else 0.0,
            T=T,
            r=_RISK_FREE,
            expiry=str(chosen_expiry) if chosen_expiry else None,
        )
        return {"ticker": ticker.upper(), **out}
    except Exception as exc:    # pragma: no cover (defensive degrade)
        return {
            "ticker": ticker.upper(),
            "expiry": None,
            "spot": None,
            "T_years": None,
            "r": None,
            "n_strikes_used": 0,
            "n_grid_points": 0,
            "x_grid": [], "pdf": [], "cdf": [],
            "expected_price": None, "expected_move_pct": None,
            "median": None, "mode": None,
            "tail_probs": {},
            "warnings": [f"engine exception: {exc}"],
            "method": "cubic_spline_2nd_derivative",
        }



# ---------------------------------------------------------------------------
# Steal-list #9 deferred completion — Max-Pain Drift tracking
# GET /api/max_pain_drift/{ticker}?days=30
# Initialises the max_pain_daily DuckDB table on first hit (idempotent
# CREATE TABLE IF NOT EXISTS). Reads the last `days` snapshots and
# runs the pure-logic compute_max_pain_drift analytics over them.
# Returns drift-strike-1d, drift-strike-Nd, drift-toward-now,
# pin-probability-score, direction-label, n-covered, warnings.
# Try/except defensive degrade — never 500s on DB hiccup.
# ---------------------------------------------------------------------------

# NEW (2026-07-16): path-style alias per the steal-list #4 user spec.
# /api/rnd/{ticker}/{expiry} is a thin wrapper that maps an ISO expiry
# string (path param) to the existing /api/rnd/{ticker} query-style
# endpoint's expiry_index contract. Additive only — never replaces
# the query-style route, so any test/curl surface currently relying
# on /api/rnd/SPY?expiry_index=N keeps working unchanged.
@router.get("/api/rnd/{ticker}/{expiry}")
def risk_neutral_density_path_endpoint(ticker: str, expiry: str):
    """Steal-list #4 path-style alias — /api/rnd/{ticker}/{expiry}.

    ISO expiry date in the path (e.g. /api/rnd/SPY/2026-07-19) maps
    to the existing /api/rnd/{ticker}?expiry_index=N contract here.
    If the requested ISO isn't in ``yt.options`` (off-market-week gap,
    post-expiry fetch) fall back to expiry_index=1 (first non-0DTE)
    so the dashboard never 500s on cold cache — mirrors the parent
    route's defensive pattern.
    """
    import yfinance as yf
    try:
        opts = list(
            getattr(yf.Ticker(ticker.upper()), "options", []) or []
        )
        if expiry in opts:
            idx = opts.index(expiry)
        else:
            idx = 1  # fallback: first non-0DTE per the parent route's default
    except (ImportError, AttributeError, IndexError):
        idx = 1
    return risk_neutral_density_endpoint(
        ticker=ticker, expiry_index=idx,
    )



@router.post("/api/strategy/evaluate")
def strategy_evaluate_endpoint(payload: dict):
    """Evaluate a multi-leg option strategy.

    Body shape::

        {
            "ticker": "SPY",          # informational; for logging
            "spot": 100.0,             # underlying price at evaluation
            "legs": [                  # list of leg dicts
                {"side": "buy"/"sell", "qty": int,
                 "option_type": "call"/"put", "strike": float,
                 "expiry": "YYYY-MM-DD", "premium": float,
                 "iv": float | None}
            ],
            "n_grid_points": 150,      # optional spot-grid resolution
            "today": "YYYY-MM-DD",     # optional anchor today (ISO)
            "expiry": "YYYY-MM-DD",    # optional anchor expiry (ISO)
        }

    Returns the ``evaluate_strategy`` dict — structure label, payoff
    grid, breakevens, PoP, expected P&L, VaR/ES, aggregate greeks.

    Invalid leg shapes degrade gracefully — the service filters
    invalid legs (zero qty / negative strike / bad expiry) out of
    the calculation, populates the ``warnings`` list with the
    skipped message, and continues with the surviving legs (or
    returns empty grids if none survive). No HTTP 400 mapping is
    needed; the route mirrors the service's defensive pattern.
    """
    from services.strategy_builder import evaluate_strategy
    legs = payload.get("legs") or []
    spot = float(payload.get("spot") or 0.0)
    n_grid_points = int(payload.get("n_grid_points") or 150)
    kwargs = {}
    if "today" in payload:
        kwargs["today"] = payload["today"]
    if "expiry" in payload:
        kwargs["expiry"] = payload["expiry"]
    return evaluate_strategy(
        legs=legs, spot=spot,
        n_grid_points=n_grid_points,
        **kwargs,
    )


@router.get("/api/max_pain_drift/{ticker}")
def max_pain_drift_endpoint(
    ticker: str,
    days: int = 30,
    accumulate: bool = False,
):
    """Max-Pain Drift — accumulated daily snapshots + drift analytics.

    ``accumulate=true`` writes TODAY's per-expiry max-pain snapshots into
    DuckDB before running the analytics; ``accumulate=false`` (default)
    is a pure read so cron jobs can poll without Write-Amp. Standard
    cron workflow:
      1. /api/max_pain_drift/SPY?accumulate=true&days=30     # after EOD
      2. Frontend polls /api/max_pain_drift/SPY?accumulate=false&days=30
         every minute for the live drift readout.
    """
    try:
        from server import (
            compute_max_pain_per_expiry,
            compute_overall_max_pain,
            fetch_spot_and_chains,
        )
        from services.duckdb_engine import db as duckdb_engine
        from services.max_pain_drift import (
            accumulate_today,
            accumulate_today_per_expiry,
            compute_max_pain_drift,
            init_max_pain_daily_table,
            read_recent_drift,
        )

        # Idempotent table init — every request repays this cost microscopically
        # but guarantees first-hit + crash-during-cron robustness.
        try:
            init_max_pain_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            # Table already exists (IF NOT EXISTS) → idempotent skip;
            # surface non-DuplicationError exceptions into the warning pile.
            import logging
            logging.warning(
                f"max_pain_drift: init_table preflight failed: {table_exc}"
            )

        # Optional accumulate-today (writes one row).
        if accumulate:
            try:
                raw = fetch_spot_and_chains(ticker.upper(), max_expiries=4)
                contracts = raw.get("contracts") or []
                spot_val = raw.get("spot") or 0.0

                # Always write ONE overall row (overall pin magnet).
                overall = compute_overall_max_pain(contracts)
                accumulate_today(
                    duckdb_engine, ticker, spot_val, overall, expiry="",
                )

                # Also write ONE row per listed expiry (per-expiry drift).
                # The "_unknown" sentinel is filtered by
                # accumulate_today_per_expiry itself — callers don't
                # need to remember.
                per_expiry = compute_max_pain_per_expiry(contracts)
                accumulate_today_per_expiry(
                    duckdb_engine, ticker, spot_val, per_expiry,
                )
            except Exception as acc_exc:    # pragma: no cover
                import logging
                logging.warning(
                    f"max_pain_drift: accumulate_today failed: {acc_exc}"
                )

        # Pure-logic analytics over the historical window.
        n = max(1, min(int(days or 30), 365))
        snaps = read_recent_drift(duckdb_engine, ticker, n_days=n)
        result = compute_max_pain_drift(snaps)
        return {"ticker": ticker.upper(), **result}
    except Exception as exc:    # pragma: no cover
        return {
            "ticker": ticker.upper(),
            "today_strike": None, "today_spot": None,
            "yesterday_strike": None,
            "drift_strike_1d": None, "drift_strike_Nd": None,
            "drift_toward_now": None, "drift_velocity_per_day": None,
            "pin_probability_score": 0.0,
            "direction_label": "error",
            "n_days_covered": 0,
            "warnings": [f"engine exception: {exc}"],
        }



# ---------------------------------------------------------------------------
# Steal-list #9 — Per-expiry MAX-PAIN DRIFT history (multi-line chart data).
# GET /api/max_pain_drift/{ticker}/per_expiry_history?days=30
#
# Reads per-expiry rows from max_pain_daily (PK = (snapshot_date, symbol,
# expiry)) and returns a JSON shape ready for the frontend line chart:
# {ticker, days, expiries: [{expiry, n_points, first_strike, last_strike,
#   drift_strike_Nd, history: [{date, strike, spot}, ...]}, ...], warnings,
#   source}.
#
# The OVERALL drift scalars on `/api/max_pain_drift/{ticker}` collapse
# the per-expiry dimension; this sibling endpoint surfaces that
# dimension explicitly for the rich visualization (Heatseeker Row 3 +
# Skylit steal-list band).
#
# Routing hygiene: declared BEFORE the `/api/max_pain_drift/{ticker}`
# catch-all below the comment header; FastAPI's path-resolution
# matches the longer-suffix route first regardless of declaration
# order, but conventional ordering keeps related routes grouped.
# ---------------------------------------------------------------------------
@router.get("/api/max_pain_drift/{ticker}/per_expiry_history")
def max_pain_drift_per_expiry_history_endpoint(
    ticker: str,
    days: int = Query(
        30, ge=1, le=365,
        description="Window of history to return per listed expiry. "
                    "Default 30 matches the chart's primary visual range.",
    ),
):
    """Per-expiry max-pain-strike trajectory over the last ``days`` days.

    Returns a list of one entry per listed expiry, sorted ASC by ISO
    expiry date, each containing a chronological ``history`` array of
    {date, strike, spot} points for the rendering polyline.

    Defensive degrade: any upstream failure (DB exception, missing
    rows) returns an empty ``expiries`` array + a warning rather than
    crashing the route \u2014 mirrors the established steal-three
    defensive-degrade signature.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.max_pain_drift import (
            init_max_pain_daily_table,
            read_recent_drift_per_expiry,
        )

        # Idempotent table init (matches the parent pattern). Cost is
        # microscopic once the table exists.
        try:
            init_max_pain_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            import logging
            logging.warning(
                f"max_pain_drift_per_expiry_history: "
                f"init_table preflight failed: {table_exc}"
            )

        n = max(1, min(int(days or 30), 365))
        expiries = read_recent_drift_per_expiry(
            duckdb_engine, ticker, n_days=n,
        )
        warnings: list[str] = []
        if not expiries:
            warnings.append(
                "no per-expiry max_pain history yet \u2014 run "
                "POST /api/max_pain_drift/{ticker}/accumulate?accumulate=true first"
            )
        return {
            "ticker": ticker.upper(),
            "days": n,
            "expiries": expiries,
            "warnings": warnings,
            "source": "steal-three-router",
        }
    except Exception as exc:    # pragma: no cover
        return {
            "ticker": ticker.upper(),
            "days": days,
            "expiries": [],
            "warnings": [f"engine exception: {exc}"],
            "source": "steal-three-router",
        }



# ---------------------------------------------------------------------------
# Steal-list #6 deferred completion — Consensus Drift tracking
# GET /api/consensus_drift/{ticker}?days=14&expiry=ISO&accumulate=true|false
# Mirrors max_pain_drift endpoint shape. Reads per-expiry + overall rows
# from consensus_daily DuckDB. Returns per-expiry drift analytics
# (call_side_pulling_up / put_side_pulling_down / balanced / stable).
# accumulate=true writes today's snapshot before running analytics.
# Try/except defensive degrade — never 500s on DB hiccup.
# ---------------------------------------------------------------------------
@router.get("/api/consensus_drift/{ticker}")
def consensus_drift_endpoint(
    ticker: str,
    days: int = 14,
    expiry: str | None = None,
    accumulate: bool = False,
):
    """Consensus Drift — accumulated daily snapshots + drift analytics.

    ``accumulate=true`` writes TODAY's snapshot into DuckDB before running
    the pure-logic analytics; ``accumulate=false`` (default) is a pure
    read so cron jobs can poll without Write-Amp.

    Standard cron workflow:
      1. /api/consensus_drift/SPY?accumulate=true&days=14&expiry=2026-08-15
      2. Frontend polls /api/consensus_drift/SPY?accumulate=false&days=14
         every minute for the live drift readout.
    """
    try:
        from server import fetch_spot_and_chains
        from services.consensus_pricing_daily import (
            accumulate_today,
            compute_consensus_drift,
            init_consensus_daily_table,
            read_recent_drift,
        )
        from services.duckdb_engine import db as duckdb_engine

        # Idempotent table init — every request repays this cost microscopically
        # but guarantees first-hit + crash-during-cron robustness.
        try:
            init_consensus_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            import logging
            logging.warning(
                f"consensus_drift: init_table preflight failed: {table_exc}"
            )

        # Optional accumulate-today. We need the chain to feed
        # compute_consensus_per_expiry + compute_overall_consensus.
        if accumulate:
            try:
                raw = fetch_spot_and_chains(ticker.upper(), max_expiries=4)
                accumulate_today(
                    duckdb_engine, ticker,
                    raw.get("contracts") or [],
                )
            except Exception as acc_exc:    # pragma: no cover
                import logging
                logging.warning(
                    f"consensus_drift: accumulate_today failed: {acc_exc}"
                )

        # Pure-logic analytics over the historical window.
        n = max(1, min(int(days or 14), 365))
        snaps = read_recent_drift(
            duckdb_engine, ticker, n_days=n, expiry=expiry,
        )
        result = compute_consensus_drift(snaps)
        return {"ticker": ticker.upper(), **result}
    except Exception as exc:    # pragma: no cover
        return {
            "ticker": ticker.upper(),
            "today_consensus": None, "today_call_premium": None,
            "today_put_premium": None, "today_spot": None,
            "yesterday_consensus": None,
            "drift_consensus_1d": None, "drift_consensus_Nd": None,
            "drift_skew_today": None, "drift_skew_change_1d": None,
            "convergence_score": 0.0,
            "direction_label": "error",
            "n_days_covered": 0,
            "warnings": [f"engine exception: {exc}"],
        }



# -------------------------------------------------------------------------
# Steal-list #8 — Regime-Persistence classifier (the one I tried to land
# in the earlier str_replace cascade per the user). Service exists at
# backend/services/regime_persistence.py::classify_window with a 13-case
# hand-verified pytest suite green; the route was simply never mounted.
# Lands now per the .md spec:
#   "Endpoint GET /api/regime_persistence/{ticker}?days=30 mounted in
#    canonical steal-three router at :8000 (mirrors consensus_drift +
#    max_pain_drift pattern; uses from server import db as mongo_db
#    per the precedent at routes/analytics.py:336, defensive try/except
#    returns regime=None + empty metrics on MongoDB failure)."
#
# The MongoDB-backed data path: services/gex_history.py ::
# get_gex_history_sync(ticker, days=, mongo_db=) returns the per-day
# gex_total time-series from databento_eod_chains + underlying_bars
# collections. The endpoint layer is a thin wrapper that:
#   - fetches the rows,
#   - calls classify_window(rows, window_label=f"{days}d"),
#   - returns the documented metrics schema with the ticker echoed.
# The defensive-degrade contract mirrors consensus_drift + max_pain_drift
# exactly: any upstream failure (Mongo unreachable, no chain data, etc.)
# returns regime=None + zeroed metrics + a warning, never a 500.
# ----------------------------------------------------------------------
@router.get("/api/regime_persistence/{ticker}")
def regime_persistence_endpoint(
    ticker: str,
    days: int = Query(
        30, ge=1, le=365,
        description="Window of gex_total history to classify (default 30d).",
    ),
) -> dict[str, Any]:
    """Regime-Persistence classifier (steal-list #8).

    Returns the canonical classifier schema::

        {
            ticker, regime (None | persistent_positive | persistent_negative
                            | transitional | low_conviction),
            sign_persistence_pct, flip_count, magnitude_conviction,
            coefficient_of_variation, n_days_covered, window_label, warnings,
        }

    The ``warnings`` field surfaces DB hiccups and missing-data
    conditions. ``regime=None`` indicates either: no gex_total history
    found for the ticker in the window, OR that the window sits below
    the absolute noise floor (NOISE_FLOOR_ABS=1.0 in
    services.regime_persistence).
    """
    try:
        from server import db as mongo_db
        from services.gex_history import get_gex_history_sync
        from services.regime_persistence import classify_window

        rows = get_gex_history_sync(
            ticker.upper(), days=days, mongo_db=mongo_db,
        )
        out = classify_window(rows, window_label=f"{days}d")
        # Echo ticker for parity with the canonical steal-three schema.
        return {"ticker": ticker.upper(), **out}
    except Exception as exc:    # pragma: no cover (defensive degrade)
        return {
            "ticker": ticker.upper(),
            "regime": None,
            "sign_persistence_pct": 0.0,
            "flip_count": 0,
            "magnitude_conviction": 0.0,
            "coefficient_of_variation": 0.0,"n_days_covered": 0,
            "window_label": f"{days}d",
            # Peer-consistent warning format: include exception class name so
            # triage reads "engine exception: RuntimeError: <msg>" (matches
            # dual_gex's `empty_shape["error"] = f"{type(exc).__name__}: {exc}"`
            # pattern and the test_chain_consensus / test_regime_persistence
            # regression guards).
            "warnings": [f"engine exception: {type(exc).__name__}: {exc}"],
        }


# -------------------------------------------------------------------------
# (decorative separator - orphan -- removed on 2026-07-15 to restore PEP-valid Python syntax)



# ---------------------------------------------------------------------------
# Steal-list #4 — Free financial-news headline ingestion (Yahoo Finance)
# GET /api/news/article?url=...&max_paragraphs=N    (declared FIRST — static)
# GET /api/news/{ticker}?limit=N                   (declared SECOND — catch-all)
# Pure-Python scraper mirroring services/insider_scraper.py's defensive
# degrade pattern. No DuckDB persistence this turn (scheduler wiring is a
# focused follow-up). See backend/services/news_feed.py for the algorithm.
# ---------------------------------------------------------------------------
# Route #1: /api/news/article   (declared first — static)
@router.get("/api/news/article")
def news_article_endpoint(
    url: str = Query(..., description="Article URL to scrape (URL-encoded)"),
    max_paragraphs: int = Query(10, ge=1, le=50),
):
    """Follow a news URL and extract its body paragraphs.

    Returns ``{url, paragraphs, warnings}``. Empty paragraphs + warning
    indicates a paywall / malformed page / network failure.
    """
    try:
        from services.news_feed import fetch_article_text
        return fetch_article_text(url, max_paragraphs=max_paragraphs)
    except Exception as exc:    # pragma: no cover (defensive degrade)
        return {
            "url": url,
            "paragraphs": [],
            "warnings": [f"engine exception: {exc}"],
        }


# Route #2: /api/news/{ticker}/history   (more-specific path, declared BEFORE catch-all)
@router.get("/api/news/{ticker}/history")
def news_history_endpoint(
    ticker: str,
    days: int = Query(14, ge=1, le=365),
    accumulate: bool = False,
):
    """Multi-day news history + summary from DuckDB.

    ``accumulate=true`` writes today's snapshot into DuckDB before
    responding (standard cron pattern); default is pure read.
    Mirrors /api/max_pain_drift + /api/insider shape.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.news_feed import (
            accumulate_today,
            compute_news_summary,
            fetch_ticker_news,
            init_news_daily_table,
            read_recent_news,
        )

        try:
            init_news_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            import logging
            logging.warning(
                f"news-history: init_table preflight: {table_exc}"
            )

        if accumulate:
            try:
                rows = fetch_ticker_news(
                    ticker, cache_engine=duckdb_engine,
                )
                if rows:
                    accumulate_today(duckdb_engine, rows)
            except Exception as acc_exc:    # pragma: no cover
                import logging
                logging.warning(
                    f"news-history: accumulate_today: {acc_exc}"
                )

        history = read_recent_news(
            duckdb_engine, ticker, n_days=days,
        )
        summary = compute_news_summary(ticker.upper(), history)
        return {
            "ticker": ticker.upper(),
            "history": history,
            "summary": summary,
            "days": days,
            "source": "steal-three-router",
            "warnings": summary.get("warnings", []),
        }
    except Exception as exc:    # pragma: no cover (defensive degrade)
        return {
            "ticker": ticker.upper(),
            "history": [],
            "summary": {
                "ticker": ticker.upper(), "n_headlines": 0,
                "n_unique_domains": 0, "top_publishers": [],
                "has_catalyst_news": False, "warnings": [],
            },
            "days": days,
            "source": "steal-three-router",
            "warnings": [f"engine exception: {exc}"],
        }


# Route #3: /api/news/{ticker}   (catch-all, declared LAST)
@router.get("/api/news/{ticker}")
def news_ticker_endpoint(
    ticker: str,
    limit: int = Query(15, ge=1, le=100),
    accumulate: bool = False,
):
    """Zero-cost Yahoo Finance headline scraper per ticker.

    Returns ``{ticker, headlines, source, warnings}``. Headlines are
    ``[{ticker, title, url, publisher, scraped_at}]``. ``accumulate=true``
    also writes today's snapshot into DuckDB before responding
    (standard cron pattern, mirrors /api/occ_volume shape).
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.news_feed import (
            accumulate_today,
            fetch_ticker_news,
            init_news_daily_table,
        )

        if accumulate:
            try:
                init_news_daily_table(duckdb_engine)
            except Exception as table_exc:    # pragma: no cover
                import logging
                logging.warning(
                    f"news: init_table preflight: {table_exc}"
                )

        headlines = fetch_ticker_news(
            ticker, limit=limit, cache_engine=duckdb_engine,
        )

        if accumulate and headlines:
            try:
                accumulate_today(duckdb_engine, headlines)
            except Exception as acc_exc:    # pragma: no cover
                import logging
                logging.warning(
                    f"news: accumulate_today: {acc_exc}"
                )

        return {
            "ticker": ticker.upper(),
            "headlines": headlines,
            "source": "steal-three-router",
            "warnings": [] if headlines else [
                "No headlines found or Yahoo rate-limited",
            ],
        }
    except Exception as exc:    # pragma: no cover (defensive degrade)
        return {
            "ticker": ticker.upper(),
            "headlines": [],
            "source": "steal-three-router",
            "warnings": [f"engine exception: {exc}"],
        }


# ---------------------------------------------------------------------------
# Steal-list #20 — Finviz insider-trading scraper (latest / top / per-ticker)
# ROUTE-ORDER NOTICE: the static routes below MUST be declared BEFORE
# the per-ticker catch-all, otherwise FastAPI matches ``{ticker}="top"``
# first. The installer enforces this order; do NOT re-order casually.
# ---------------------------------------------------------------------------
# Route #1: /api/insider/top   (GET-only — pure-read static)
# Refactor (RFC-7231 polish): the legacy ``accumulate=true`` query param
# is now accepted for backward compat but *ignored* (with a deprecation
# warning). The write-side lives at ``POST /api/insider/top/accumulate``
# (declared immediately after this GET) which is the right verb per
# RFC-7231 §4.2.2. GET MUST NOT have user-data side effects per §4.2.1.
@router.get("/api/insider/top")
def insider_top_endpoint(
    min_value: int = 100_000,
    tc: int = 7,
    limit: int = 20,
    accumulate: bool = Query(
        False,
        description="DEPRECATED, ignored. Use POST /api/insider/top/accumulate "
                    "for the write side. Kept for backward compat only.",
    ),
):
    """Finviz top insider trades ranked by transaction value (PURE-READ).

    GET must be safe per RFC-7231 §4.2.1 — no side effects beyond
    retrieval. The legacy ``accumulate=true`` query param is accepted
    for backward compat but *ignored* with a deprecation warning
    returned in the ``warnings`` key — use
    ``POST /api/insider/top/accumulate`` to write today's snapshot.
    Defaults mirror the upstream Buzzfund filter
    (?or=-10&tv=100000&tc=7&o=-transactionValue).
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.insider_scraper import (
            compute_insider_summary,
            fetch_top_insider,
        )

        rows = fetch_top_insider(
            min_value=int(min_value), days=int(tc),
            cache_engine=duckdb_engine,
            limit=int(limit),
        )
        warnings: list[str] = []
        if accumulate:
            warnings.append(
                "accumulate=true deprecated; ignored on GET. "
                "Use POST /api/insider/top/accumulate for the write side."
            )
        if not rows:
            warnings.append("Finviz empty or unreachable")
        return {
            "rows": rows[: max(0, int(limit))],
            "summary": compute_insider_summary(None, rows),
            "source": "steal-three-router",
            "warnings": warnings,
        }
    except Exception as exc:    # pragma: no cover
        return {
            "rows": [],
            "summary": {
                "ticker": None, "n_buys_30d": 0,
                "n_sells_30d": 0, "total_buy_value": 0.0,
                "total_sell_value": 0.0, "net_buy_pressure": 0.0,
                "largest_buy_value": None, "ceo_bought_recent": False,
                "n_rows_considered": 0, "warnings": [],
            },
            "source": "steal-three-router",
            "warnings": [f"engine exception: {exc}"],
        }


# Route #1b: /api/insider/top/accumulate   (POST-only — write side)
@router.post("/api/insider/top/accumulate")
def insider_top_accumulate_endpoint(
    min_value: int = Query(100_000, ge=0, le=10_000_000),
    tc: int = Query(7, ge=1, le=365),
    limit: int = Query(20, ge=1, le=200),
):
    """Write today's Finviz top insider snapshot into DuckDB.

    POST is the right verb for write side effects per RFC-7231 §4.2.2.
    Schedule this once per trading day from the cron — the GET endpoint
    stays safe to poll repeatedly.

    Returns ``{rows, summary, source, written_n_rows, warnings}``.
    ``written_n_rows`` reports the count of rows that passed the
    pre-write filter (ticker/insider_name/transaction_date present),
    matching the contract that ``accumulate_today`` returns in
    ``backend/services/insider_scraper.py``.

    Idempotent: UPSERT by (snapshot_date, ticker, transaction_date,
    insider_name); safe to re-fire within the same trading day.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.insider_scraper import (
            accumulate_today,
            compute_insider_summary,
            fetch_top_insider,
            init_insider_daily_table,
        )

        try:
            init_insider_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            import logging
            logging.warning(
                f"insider-top/accumulate: init_table preflight: {table_exc}"
            )

        rows = fetch_top_insider(
            min_value=int(min_value), days=int(tc),
            cache_engine=duckdb_engine,
            limit=int(limit),
        )
        written_n_rows = 0
        if rows:
            try:
                written_n_rows = accumulate_today(duckdb_engine, rows)
            except Exception as acc_exc:    # pragma: no cover
                import logging
                logging.warning(
                    f"insider-top/accumulate: accumulate_today: {acc_exc}"
                )
                return {
                    "rows": rows[: max(0, int(limit))],
                    "summary": compute_insider_summary(None, rows),
                    "source": "steal-three-router",
                    "written_n_rows": 0,
                    "warnings": [
                        f"accumulate failed: {acc_exc}",
                        "Finviz rows fetched but DuckDB write did not persist.",
                    ],
                }
        warnings = [] if rows else ["Finviz empty or unreachable"]
        return {
            "rows": rows[: max(0, int(limit))],
            "summary": compute_insider_summary(None, rows),
            "source": "steal-three-router",
            "written_n_rows": written_n_rows,
            "warnings": warnings,
        }
    except Exception as exc:    # pragma: no cover
        return {
            "rows": [],
            "summary": {
                "ticker": None, "n_buys_30d": 0,
                "n_sells_30d": 0, "total_buy_value": 0.0,
                "total_sell_value": 0.0, "net_buy_pressure": 0.0,
                "largest_buy_value": None, "ceo_bought_recent": False,
                "n_rows_considered": 0, "warnings": [],
            },
            "source": "steal-three-router",
            "written_n_rows": 0,
            "warnings": [f"engine exception: {exc}"],
        }


# Route #2: /api/insider/latest   (GET-only — pure-read static)
# Refactor (RFC-7231 polish): the legacy ``accumulate=true`` query param
# is deprecated and ignored on GET — see Route #1 /api/insider/top for
# the full RFC-7231 §4.2.1/§4.2.2 rationale.
@router.get("/api/insider/latest")
def insider_latest_endpoint(
    limit: int = 50,
    accumulate: bool = Query(
        False,
        description="DEPRECATED, ignored. Use POST /api/insider/latest/accumulate "
                    "for the write side. Kept for backward compat only.",
    ),
):
    """Finviz market-wide latest insider trades (PURE-READ).

    GET must be safe per RFC-7231 §4.2.1. ``accumulate=true`` is
    deprecated and ignored; use ``POST /api/insider/latest/accumulate``
    for the cron-write workflow.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.insider_scraper import (
            compute_insider_summary,
            fetch_latest_insider,
        )

        rows = fetch_latest_insider(
            cache_engine=duckdb_engine,
            limit=int(limit),
        )
        warnings: list[str] = []
        if accumulate:
            warnings.append(
                "accumulate=true deprecated; ignored on GET. "
                "Use POST /api/insider/latest/accumulate for the write side."
            )
        if not rows:
            warnings.append("Finviz empty or unreachable")
        return {
            "rows": rows[: max(0, int(limit))],
            "summary": compute_insider_summary(None, rows),
            "source": "steal-three-router",
            "warnings": warnings,
        }
    except Exception as exc:    # pragma: no cover
        return {
            "rows": [],
            "summary": {
                "ticker": None, "n_buys_30d": 0,
                "n_sells_30d": 0, "total_buy_value": 0.0,
                "total_sell_value": 0.0, "net_buy_pressure": 0.0,
                "largest_buy_value": None, "ceo_bought_recent": False,
                "n_rows_considered": 0, "warnings": [],
            },
            "source": "steal-three-router",
            "warnings": [f"engine exception: {exc}"],
        }


# Route #2b: /api/insider/latest/accumulate   (POST-only — write side)
@router.post("/api/insider/latest/accumulate")
def insider_latest_accumulate_endpoint(
    limit: int = Query(50, ge=1, le=200),
):
    """Write today's Finviz latest-insider snapshot into DuckDB.

    POST is the right verb for write side effects per RFC-7231 §4.2.2.
    Returns ``{rows, summary, source, written_n_rows, warnings}``.
    Idempotent: UPSERT by (snapshot_date, ticker, transaction_date,
    insider_name); safe to re-fire within the same trading day.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.insider_scraper import (
            accumulate_today,
            compute_insider_summary,
            fetch_latest_insider,
            init_insider_daily_table,
        )

        try:
            init_insider_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            import logging
            logging.warning(
                f"insider-latest/accumulate: init_table preflight: {table_exc}"
            )

        rows = fetch_latest_insider(
            cache_engine=duckdb_engine,
            limit=int(limit),
        )
        written_n_rows = 0
        if rows:
            try:
                written_n_rows = accumulate_today(duckdb_engine, rows)
            except Exception as acc_exc:    # pragma: no cover
                import logging
                logging.warning(
                    f"insider-latest/accumulate: accumulate_today: {acc_exc}"
                )
                return {
                    "rows": rows[: max(0, int(limit))],
                    "summary": compute_insider_summary(None, rows),
                    "source": "steal-three-router",
                    "written_n_rows": 0,
                    "warnings": [
                        f"accumulate failed: {acc_exc}",
                        "Finviz rows fetched but DuckDB write did not persist.",
                    ],
                }
        warnings = [] if rows else ["Finviz empty or unreachable"]
        return {
            "rows": rows[: max(0, int(limit))],
            "summary": compute_insider_summary(None, rows),
            "source": "steal-three-router",
            "written_n_rows": written_n_rows,
            "warnings": warnings,
        }
    except Exception as exc:    # pragma: no cover
        return {
            "rows": [],
            "summary": {
                "ticker": None, "n_buys_30d": 0,
                "n_sells_30d": 0, "total_buy_value": 0.0,
                "total_sell_value": 0.0, "net_buy_pressure": 0.0,
                "largest_buy_value": None, "ceo_bought_recent": False,
                "n_rows_considered": 0, "warnings": [],
            },
            "source": "steal-three-router",
            "written_n_rows": 0,
            "warnings": [f"engine exception: {exc}"],
        }


# Route #3: /api/insider/{ticker}   (GET-only — pure-read catch-all)
# Refactor (RFC-7231 polish): the legacy ``accumulate=true`` query param
# is deprecated and ignored on GET — see Route #1 /api/insider/top for
# the full RFC-7231 §4.2.1/§4.2.2 rationale. Declared LAST so the static
# ``/top`` and ``/latest`` GET paths match first.
@router.get("/api/insider/{ticker}")
def insider_ticker_endpoint(
    ticker: str,
    limit: int = 50,
    accumulate: bool = Query(
        False,
        description="DEPRECATED, ignored. Use POST /api/insider/{ticker}/accumulate "
                    "for the write side. Kept for backward compat only.",
    ),
):
    """Per-ticker Finviz insider trades + Flowseeker-badge summary (PURE-READ).

    GET must be safe per RFC-7231 §4.2.1. ``accumulate=true`` is
    deprecated and ignored; use ``POST /api/insider/{ticker}/accumulate``
    for the cron-write workflow.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.insider_scraper import (
            compute_insider_summary,
            fetch_ticker_insider,
        )

        ticker_upper = ticker.upper()
        finviz_ticker = ticker_upper.replace(".", "-")
        rows = fetch_ticker_insider(finviz_ticker, cache_engine=duckdb_engine)
        for _r in rows:
            _r["ticker"] = ticker_upper
        warnings: list[str] = []
        if accumulate:
            warnings.append(
                "accumulate=true deprecated; ignored on GET. Use POST "
                "/api/insider/{ticker}/accumulate for the write side."
            )
        if not rows:
            warnings.append("Finviz empty or unreachable")
        return {
            "ticker": ticker_upper,
            "rows": rows[: max(0, int(limit))],
            "summary": compute_insider_summary(ticker_upper, rows),
            "source": "steal-three-router",
            "warnings": warnings,
        }
    except Exception as exc:    # pragma: no cover
        return {
            "ticker": ticker.upper(),
            "rows": [],
            "summary": {
                "ticker": ticker.upper(), "n_buys_30d": 0,
                "n_sells_30d": 0, "total_buy_value": 0.0,
                "total_sell_value": 0.0, "net_buy_pressure": 0.0,
                "largest_buy_value": None, "ceo_bought_recent": False,
                "n_rows_considered": 0, "warnings": [],
            },
            "source": "steal-three-router",
            "warnings": [f"engine exception: {exc}"],
        }


# Route #3b: /api/insider/{ticker}/accumulate   (POST-only — write side)
# Declared LAST so the static ``/top/accumulate`` and ``/latest/accumulate``
# POST paths match first; FastAPI's path-resolution ordering handles it.
@router.post("/api/insider/{ticker}/accumulate")
def insider_ticker_accumulate_endpoint(
    ticker: str,
    limit: int = Query(50, ge=1, le=200),
):
    """Write today's per-ticker Finviz insider snapshot into DuckDB.

    POST is the right verb for write side effects per RFC-7231 §4.2.2.
    Returns ``{ticker, rows, summary, source, written_n_rows, warnings}``.
    Idempotent: UPSERT by (snapshot_date, ticker, transaction_date,
    insider_name); safe to re-fire within the same trading day.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        from services.insider_scraper import (
            accumulate_today,
            compute_insider_summary,
            fetch_ticker_insider,
            init_insider_daily_table,
        )

        ticker_upper = ticker.upper()
        finviz_ticker = ticker_upper.replace(".", "-")
        try:
            init_insider_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            import logging
            logging.warning(
                f"insider/{ticker}/accumulate: init_table preflight: {table_exc}"
            )

        rows = fetch_ticker_insider(finviz_ticker, cache_engine=duckdb_engine)
        for _r in rows:
            _r["ticker"] = ticker_upper
        written_n_rows = 0
        if rows:
            try:
                written_n_rows = accumulate_today(duckdb_engine, rows)
            except Exception as acc_exc:    # pragma: no cover
                import logging
                logging.warning(
                    f"insider/{ticker}/accumulate: accumulate_today: {acc_exc}"
                )
                return {
                    "ticker": ticker_upper,
                    "rows": rows[: max(0, int(limit))],
                    "summary": compute_insider_summary(ticker_upper, rows),
                    "source": "steal-three-router",
                    "written_n_rows": 0,
                    "warnings": [
                        f"accumulate failed: {acc_exc}",
                        "Finviz rows fetched but DuckDB write did not persist.",
                    ],
                }
        warnings = [] if rows else ["Finviz empty or unreachable"]
        return {
            "ticker": ticker_upper,
            "rows": rows[: max(0, int(limit))],
            "summary": compute_insider_summary(ticker_upper, rows),
            "source": "steal-three-router",
            "written_n_rows": written_n_rows,
            "warnings": warnings,
        }
    except Exception as exc:    # pragma: no cover
        return {
            "ticker": ticker.upper(),
            "rows": [],
            "summary": {
                "ticker": ticker.upper(), "n_buys_30d": 0,
                "n_sells_30d": 0, "total_buy_value": 0.0,
                "total_sell_value": 0.0, "net_buy_pressure": 0.0,
                "largest_buy_value": None, "ceo_bought_recent": False,
                "n_rows_considered": 0, "warnings": [],
            },
            "source": "steal-three-router",
            "written_n_rows": 0,
            "warnings": [f"engine exception: {exc}"],
        }


# ---------------------------------------------------------------------------
# Steal-list #14 — OCC cleared volume by account type (latest / per-ticker)
# GET /api/occ_volume/{ticker}?days=14&accumulate=true|false
#
# T+1 daily OCC market-wide CSV → cached 24 h in DuckDB → parsed into
# wide 10-column rows per (trade_date, ticker). accumulate=true writes
# today's snapshot into occ_volume_daily before responding; default is a
# pure read so cron jobs can poll without write amplification.
# ---------------------------------------------------------------------------
@router.get("/api/occ_volume/{ticker}")
def occ_volume_endpoint(
    ticker: str,
    days: int = 14,
    accumulate: bool = False,
):
    # OCC cleared volume by account type (Customer / Firm / Market-Maker).
    # ``accumulate=true`` writes today's snapshot into DuckDB before
    # responding; ``accumulate=false`` (default) is a pure read so
    # pollers don't write-amplify.
    # Standard cron workflow:
    #   1. /api/occ_volume/SPY?accumulate=true&days=14     # after T+1 settles
    #   2. Frontend polls /api/occ_volume/SPY?accumulate=false&days=14
    #      on a 24 h cadence for the live "Who traded" readout.
    try:
        from datetime import date as _date
        from datetime import timedelta as _td

        from services.duckdb_engine import db as duckdb_engine
        from services.occ_scraper import (
            accumulate_today,
            compute_occ_summary,
            fetch_ticker_occ,
            init_occ_daily_table,
            read_recent_occ,
        )

        # Idempotent table init.
        try:
            init_occ_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            import logging
            logging.warning(f"occ_volume: init_table preflight: {table_exc}")

        # Always fetch today's T+1 snapshot for the ticker.
        target = _date.today() - _td(days=1)
        rows = fetch_ticker_occ(
            ticker.upper(),
            target,
            cache_engine=duckdb_engine,
        )

        # Optional accumulate-today (writes one wide row).
        if accumulate and rows:
            try:
                accumulate_today(duckdb_engine, rows, snapshot_date=target)
            except Exception as acc_exc:    # pragma: no cover
                import logging
                logging.warning(f"occ_volume: accumulate_today: {acc_exc}")

        # Pure-logic analytics over the historical window.
        n = max(1, min(int(days or 14), 365))
        history = read_recent_occ(duckdb_engine, ticker.upper(), n_days=n)

        if not history and not rows:
            return {
                "ticker": ticker.upper(),
                "rows": [],
                "summary": compute_occ_summary(ticker.upper(), []),
                "source": "steal-three-router",
                "warnings": ["OCC empty for date"],
            }

        # Prefer the DuckDB history (multi-day) over today's fresh fetch.
        merged = history if history else rows
        return {
            "ticker":   ticker.upper(),
            "rows":     merged,
            "summary":  compute_occ_summary(ticker.upper(), merged),
            "source":   "steal-three-router",
            "warnings": [],
        }
    except Exception as exc:    # pragma: no cover
        return {
            "ticker":   ticker.upper(),
            "rows":     [],
            "summary":  compute_occ_summary(None, []),
            "source":   "steal-three-router",
            "warnings": [f"engine exception: {exc}"],
        }


@router.get("/api/vol/realized/{ticker}")
def realized_volatility_endpoint(
    ticker: str,
    days: int = 30,
    accumulate: bool = False,
) -> dict[str, Any]:
    """Steal-list #7 — Realised-vol suite + cones + typical-range bands + VRP.

    Pure-logic orchestration:
      1. Pull 60+ daily OHLC bars from yfinance (same path #7 consumes).
      2. Compute all 5 estimators (yang_zhang, garman_klass, parkinson,
         rogers_satchell, close_to_close).
      3. Compute the 20d/30d/60d vol-cone percentiles.
      4. Compute the daily/weekly/monthly typical-range bands.
      5. Compute VRP (front-month ATM IV / YZ RV) via _load_chain for
         the IV numerator.
      6. If ``accumulate=true`` and at least one estimator produced a
         finite value, UPSERT today’s snapshot into the rv_daily DuckDB
         table (mirrors max_pain_drift / news_feed / occ_volume cron
         pattern).
      7. Return the last ``days`` rows from rv_daily as ``history``.

    Defensive degrade: yfinance crash, chain load failure, or DB error
    never propagates as a 500 — the route returns 200 with the empty
    shape + warnings so the frontend can render without crashing.
    """
    _ESTIMATOR_NAMES = (
        "yang_zhang", "garman_klass", "parkinson",
        "rogers_satchell", "close_to_close",
    )
    empty_estimates = {name: None for name in _ESTIMATOR_NAMES}
    warnings: list[str] = []
    try:
        import logging

        import yfinance as yf

        from services.duckdb_engine import db as duckdb_engine
        from services.realized_volatility import (
            accumulate_today,
            compute_realized_volatility,
            compute_typical_range_bands,
            compute_vol_cone,
            compute_vrp,
            init_rv_daily_table,
            read_recent_rv,
        )

        # 1. Idempotent table init.
        try:
            init_rv_daily_table(duckdb_engine)
        except Exception as table_exc:    # pragma: no cover
            logging.warning(f"vol_realized: init_table preflight: {table_exc}")

        # 2. OHLC bars from yfinance (6mo is enough to feed 60d cone + bands).
        # NOTE: NO inner try/except — a yfinance crash MUST propagate to
        # the outer handler so the response carries the canonical
        # ``engine exception`` warning per the test contract.
        yt = yf.Ticker(ticker.upper())
        hist = yt.history(period="6mo")
        bars: list[dict[str, Any]] = []
        if hist is not None and not hist.empty:
            for i, r in hist.iterrows():
                bars.append({
                    "date": i.strftime("%Y-%m-%d")
                    if hasattr(i, "strftime") else str(i),
                    "open":  float(o) if (o := getattr(r, "Open", None)) is not None else None,
                    "high":  float(h) if (h := getattr(r, "High", None)) is not None else None,
                    "low":   float(lo) if (lo := getattr(r, "Low", None)) is not None else None,
                    "close": float(c) if (c := getattr(r, "Close", None)) is not None else None,
                    "prev_close": float(c) if c is not None else None,
                })

        # 3. ATM IV from the canonical chain loader.
        spot: float | None = None
        front_atm_iv: float | None = None
        try:
            spot, calls, _, _ = _load_chain(ticker.upper(), min_dte=1)
            if calls:
                atm = min(
                    calls,
                    key=lambda c: abs(float(c.get("strike", 0.0)) - float(spot or 0.0)),
                )
                front_atm_iv = float(atm.get("impliedVolatility", 0.0) or 0.0)
        except Exception as exc:
            warnings.append(f"_load_chain failed: {exc}")

        # 4. Compute all 5 estimators.
        estimators: dict[str, Any] = {}
        estimator_warnings: list[str] = []
        for est in _ESTIMATOR_NAMES:
            try:
                r = compute_realized_volatility(bars, estimator=est)
                estimators[est] = r.get("volatility")
                estimator_warnings.extend(r.get("warnings", []))
            except Exception as exc:
                estimators[est] = None
                estimator_warnings.append(f"{est}: {exc}")

        # 5. Cone + bands.
        try:
            cones = compute_vol_cone(bars)
        except Exception as exc:
            cones = {}
            warnings.append(f"cone compute failed: {exc}")
        try:
            bands = compute_typical_range_bands(bars)
        except Exception as exc:
            bands = {}
            warnings.append(f"bands compute failed: {exc}")

        # 6. VRP — yang_zhang denominator.
        # User contract: vrp dict carries {atm_iv, yz_rv, ratio, spread,
        # label} (we map compute_vrp's {ratio, spread, label} keys to the
        # contract's {ratio, spread, label} via the leading-vrp_ prefix
        # also kept for backward compatibility).
        yz_value = estimators.get("yang_zhang")
        try:
            vrp = {
                "atm_iv":    front_atm_iv,
                "yz_rv":     yz_value,
                **compute_vrp(front_atm_iv, yz_value),
            }
        except Exception as exc:
            vrp = {
                "atm_iv":    front_atm_iv,
                "yz_rv":     yz_value,
                "vrp_ratio":  None,
                "vrp_spread": None,
                "vrp_label":  "undefined",
            }
            warnings.append(f"vrp compute failed: {exc}")

        # 7. Optional accumulate-today cron write.
        if accumulate:
            rv_payload = {
                k: v for k, v in estimators.items()
                if v is not None and math.isfinite(v)
            }
            if rv_payload:
                try:
                    accumulate_today(duckdb_engine, ticker, rv_payload)
                except Exception as acc_exc:
                    warnings.append(f"accumulate_today failed: {acc_exc}")

        # 8. Recent history.
        n_days = max(1, min(int(days or 30), 365))
        try:
            history = read_recent_rv(duckdb_engine, ticker, n_days=n_days)
        except Exception as hist_exc:
            history = []
            warnings.append(f"read_recent_rv failed: {hist_exc}")

        return {
            "ticker": ticker.upper(),
            "spot": spot,
            "front_atm_iv": front_atm_iv,
            "estimators": estimators,
            "vrp": vrp,
            "cones": cones,
            "typical_range_bands": bands,
            "history": history,
            "source": "steal-three-router",
            "warnings": warnings + estimator_warnings,
        }
    except Exception as exc:    # pragma: no cover
        return {
            "ticker": ticker.upper(),
            "spot": None,
            "front_atm_iv": None,
            "estimators": empty_estimates,
            "vrp": {"vrp_ratio": None, "vrp_spread": None, "vrp_label": "undefined"},
            "cones": {},
            "typical_range_bands": {},
            "history": [],
            "source": "steal-three-router",
            "warnings": [f"engine exception: {exc}"],
        }
