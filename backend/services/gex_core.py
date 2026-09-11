"""
backend/services/gex_core.py

Pure GEX computation functions extracted from server.py.

All functions are stateless — no DB access, no server context, no async.
This module is importable at module-load time without side effects.

Functions moved from server.py (2026-08-06 refactor):
  - safe_float
  - compute_gex_by_strike
  - compute_gex_grid
  - classify_nodes
  - detect_opportunities
  - detect_patterns
  - calc_aggregate_gex_curve
  - calc_implied_move
  - calc_probability_distribution
  - compute_gex_by_strike_volume
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from scipy.stats import norm

from bs_greeks import (
    bs_charm,
    bs_gamma,
    bs_vanna,
    bs_vega,
    bs_vomma,
    bs_zomma,
    dollar_charm_per_contract,
    dollar_gex_per_contract,
    dollar_vex_per_contract,
)

# Dividend yields for Black-Scholes (moved from server.py)
DIV_YIELD = {"SPY": 0.013, "QQQ": 0.006, "^SPX": 0.013, "IWM": 0.012}

# ── Rust fast path (decoder-core, phase 2 of the Rust migration) ──────────
# compute_gex_by_strike is delegated to the decoder_core PyO3 extension when
# available (verified bit-exact parity vs this module, 2026-08-22). Any import
# or runtime failure falls back to the pure-Python implementation below.
try:
    import decoder_core as _dc

    _RUST_GEX = True
except ImportError:  # pragma: no cover - fallback path
    _dc = None
    _RUST_GEX = False


def safe_float(v, default=0.0):
    """Safely convert a value to float, handling None and NaN."""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def classify_nodes_rust(rows: list[dict[str, Any]], spot: float) -> dict[str, Any] | None:
    """Rust classify_nodes via decoder_core; None when unavailable/failed."""
    if not _RUST_GEX:
        return None
    try:
        return _dc.classify_nodes(rows, spot)
    except Exception as exc:  # pragma: no cover - defensive fallback
        import logging

        logging.getLogger(__name__).warning(
            "decoder_core classify_nodes failed (%s) — falling back to python", exc
        )
        return None


def compute_gex_by_strike(spot: float, contracts: list[dict[str, Any]], ticker: str = "") -> list[dict[str, Any]]:
    """Per-strike net GEX, VEX, and Vega. Convention: dealer-positive convention.

    Delegates to the decoder_core Rust extension when installed (bit-exact
    parity verified 2026-08-22); falls back to the pure-Python loop below.
    """
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    if _RUST_GEX:
        try:
            return _dc.compute_gex_by_strike(spot, contracts, q)
        except Exception as exc:  # pragma: no cover - defensive fallback
            import logging

            logging.getLogger(__name__).warning(
                "decoder_core gex failed (%s) — falling back to python", exc
            )
    agg: dict[float, dict[str, float]] = {}
    for c in contracts:
        oi = safe_float(c.get("oi"))
        if oi <= 0:
            continue
        iv = safe_float(c.get("iv"))
        if iv <= 0:
            continue
        T = safe_float(c.get("T"))
        if T <= 0:
            continue
        strike = safe_float(c.get("strike"))
        if strike <= 0:
            continue
        try:
            gamma = float(bs_gamma(spot, strike, T, iv, q=q) or 0)
            vanna = float(bs_vanna(spot, strike, T, iv, q=q) or 0)
            vega_val = float(bs_vega(spot, strike, T, iv, q=q) or 0)
            charm = float(bs_charm(spot, strike, T, iv, q=q, kind=c["type"]) or 0)
            vomma = float(bs_vomma(spot, strike, T, iv, q=q) or 0)
            zomma = float(bs_zomma(spot, strike, T, iv, q=q) or 0)
        except (TypeError, ValueError):
            continue
        if gamma <= 0 and abs(vanna) <= 0:
            continue
        gex_unit = dollar_gex_per_contract(gamma, oi, spot)
        vex_unit = dollar_vex_per_contract(vanna, oi, spot)
        vega_unit = vega_val * oi * 100.0
        charm_unit = dollar_charm_per_contract(charm, oi, spot)
        vomma_unit = vomma * oi * 100.0
        zomma_unit = zomma * oi * 100.0 * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        bucket = agg.setdefault(c["strike"], {
            "strike": c["strike"], "gex": 0.0, "call_gex": 0.0, "put_gex": 0.0,
            "call_oi": 0.0, "put_oi": 0.0, "total_oi": 0.0,
            "vex": 0.0, "call_vex": 0.0, "put_vex": 0.0,
            "vega": 0.0, "call_vega": 0.0, "put_vega": 0.0,
            "charm": 0.0, "call_charm": 0.0, "put_charm": 0.0,
            "vomma": 0.0, "call_vomma": 0.0, "put_vomma": 0.0,
            "zomma": 0.0, "call_zomma": 0.0, "put_zomma": 0.0,
        })
        bucket["gex"] += sign * gex_unit
        bucket["vex"] += sign * vex_unit
        bucket["vega"] += sign * vega_unit
        bucket["charm"] += sign * charm_unit
        bucket["vomma"] += sign * vomma_unit
        bucket["zomma"] += sign * zomma_unit
        if c["type"] == "call":
            bucket["call_gex"] += gex_unit
            bucket["call_vex"] += vex_unit
            bucket["call_vega"] += vega_unit
            bucket["call_charm"] += charm_unit
            bucket["call_vomma"] += vomma_unit
            bucket["call_zomma"] += zomma_unit
            bucket["call_oi"] += oi
        else:
            bucket["put_gex"] += gex_unit
            bucket["put_vex"] += vex_unit
            bucket["put_vega"] += vega_unit
            bucket["put_charm"] += charm_unit
            bucket["put_vomma"] += vomma_unit
            bucket["put_zomma"] += zomma_unit
            bucket["put_oi"] += oi
        bucket["total_oi"] += oi

    out = sorted(agg.values(), key=lambda r: r["strike"])
    return out


def compute_gex_grid(spot: float, contracts: list[dict[str, Any]], ticker: str = "") -> dict[str, Any]:
    """2D grid: GEX per (strike, expiry). Skylit-style heatmap layout."""
    if spot <= 0 or not contracts:
        return {"expiries": [], "strikes": [], "grid": {}, "charm_grid": {}, "vex_grid": {}}
    q = DIV_YIELD.get(ticker, 0.0)
    if _RUST_GEX:
        try:
            strikes_c: list[float] = []
            ts_c: list[float] = []
            ois_c: list[float] = []
            ivs_c: list[float] = []
            kinds_c: list[bool] = []
            expiries_c: list[str] = []
            contracts_c: list[dict[str, Any]] = []
            for c in contracts:
                oi = safe_float(c.get("oi"))
                iv = safe_float(c.get("iv"))
                t = safe_float(c.get("T"))
                strike = safe_float(c.get("strike"))
                expiry = c.get("expiry") or ""
                if oi <= 0 or iv <= 0 or t <= 0 or strike <= 0 or not expiry:
                    continue
                strikes_c.append(strike)
                ts_c.append(t)
                ois_c.append(oi)
                ivs_c.append(iv)
                kinds_c.append((c.get("type") or "call") == "call")
                expiries_c.append(expiry)
                contracts_c.append(c)
            out = _dc.compute_gex_grid(spot, strikes_c, ts_c, ois_c, ivs_c,
                                       kinds_c, expiries_c, q)
            if out is not None and out.get("grid"):
                # The Rust core predates vomma: merge a Python-computed
                # vomma section with identical fallback semantics (same
                # filters incl. gamma>0, same sign convention, same units).
                vomma_sec: dict[str, dict[str, float]] = {}
                for _c, _strike, _tt, _oi, _iv, _exp in zip(
                        contracts_c, strikes_c, ts_c, ois_c, ivs_c, expiries_c,
                        strict=True):
                    _g = bs_gamma(spot, _strike, _tt, _iv, q=q)
                    if _g <= 0:
                        continue
                    _ct = _c.get("type") or "call"
                    _sgn = 1.0 if _ct == "call" else -1.0
                    _cell = _sgn * bs_vomma(spot, _strike, _tt, _iv, q=q) * _oi * 100.0
                    _row = vomma_sec.setdefault(_exp, {})
                    # Same strike-key encoding as the fallback return below
                    # (_k is defined after this block; replicate verbatim).
                    _kk = str(int(_strike)) if float(_strike).is_integer() else str(_strike)
                    _row[_kk] = _row.get(_kk, 0.0) + _cell
                return {
                    "expiries": out["expiries"],
                    "strikes": out["strikes"],
                    "grid": out["grid"],
                    "charm_grid": out["charm_grid"],
                    "vex_grid": out["vex_grid"],
                    "vomma_grid": vomma_sec,
                    "strike_totals": out["strike_totals"],
                }
        except Exception as exc:  # pragma: no cover - fallback path
            import logging
            logging.getLogger(__name__).warning("decoder_core compute_gex_grid failed (%s) — python fallback", exc)
    grid: dict[str, dict[float, float]] = {}
    charm_grid: dict[str, dict[float, float]] = {}
    vex_grid: dict[str, dict[float, float]] = {}
    vomma_grid: dict[str, dict[float, float]] = {}
    strike_totals: dict[float, float] = {}
    for c in contracts:
        oi = safe_float(c.get("oi"))
        if oi <= 0:
            continue
        iv = safe_float(c.get("iv"))
        if iv <= 0:
            continue
        T = safe_float(c.get("T"))
        if T <= 0:
            continue
        strike = safe_float(c.get("strike"))
        if strike <= 0:
            continue
        expiry = c.get("expiry") or ""
        if not expiry:
            continue
        contract_type = c.get("type") or "call"
        gamma = bs_gamma(spot, strike, T, iv, q=q)
        charm = bs_charm(spot, strike, T, iv, q=q, kind=contract_type)
        vanna = bs_vanna(spot, strike, T, iv, q=q)
        vomma = bs_vomma(spot, strike, T, iv, q=q)
        if gamma <= 0:
            continue
        gex_unit = dollar_gex_per_contract(gamma, oi, spot)
        charm_unit = dollar_charm_per_contract(charm, oi, spot)
        vex_unit = dollar_vex_per_contract(vanna, oi, spot)
        vomma_unit = vomma * oi * 100.0  # contract-dollars of volga (cf. per-strike path)
        sign = 1.0 if contract_type == "call" else -1.0
        cell = sign * gex_unit
        charm_cell = sign * charm_unit
        vex_cell = sign * vex_unit
        vomma_cell = sign * vomma_unit
        d = grid.setdefault(expiry, {})
        d[strike] = d.get(strike, 0.0) + cell
        dc = charm_grid.setdefault(expiry, {})
        dc[strike] = dc.get(strike, 0.0) + charm_cell
        dv = vex_grid.setdefault(expiry, {})
        dv[strike] = dv.get(strike, 0.0) + vex_cell
        dvm = vomma_grid.setdefault(expiry, {})
        dvm[strike] = dvm.get(strike, 0.0) + vomma_cell
        strike_totals[strike] = strike_totals.get(strike, 0.0) + cell

    expiries = sorted(grid.keys())
    strikes = sorted(strike_totals.keys())

    def _k(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else str(x)

    return {
        "expiries": expiries,
        "strikes": strikes,
        "grid": {e: {_k(k): v for k, v in grid[e].items()} for e in expiries},
        "charm_grid": {e: {_k(k): v for k, v in charm_grid[e].items()} for e in expiries},
        "vex_grid": {e: {_k(k): v for k, v in vex_grid[e].items()} for e in expiries},
        "vomma_grid": {e: {_k(k): v for k, v in vomma_grid[e].items()} for e in expiries},
        "strike_totals": [{"strike": k, "gex": v} for k, v in sorted(strike_totals.items())],
    }


def compute_gex_grid_volume(spot: float, contracts: list[dict[str, Any]],
                            ticker: str = "") -> dict[str, Any]:
    """2D GEX grid weighted by VOLUME instead of OI.

    OI-suppression fallback: when the upstream feed blanks open interest
    (Yahoo overnight/throttle windows), compute_gex_grid skips every contract
    and the heatmap renders blank. Volume is still reported, so weight by it —
    same per-cell structure as compute_gex_grid so the frontend needs no changes.
    """
    if spot <= 0 or not contracts:
        return {"expiries": [], "strikes": [], "grid": {}, "charm_grid": {}, "vex_grid": {}}
    q = DIV_YIELD.get(ticker, 0.0)
    if _RUST_GEX:
        try:
            strikes_c: list[float] = []
            ts_c: list[float] = []
            vols_c: list[float] = []
            ivs_c: list[float] = []
            kinds_c: list[bool] = []
            expiries_c: list[str] = []
            for c in contracts:
                vol = safe_float(c.get("volume"))
                iv = safe_float(c.get("iv"))
                t = safe_float(c.get("T"))
                strike = safe_float(c.get("strike"))
                expiry = c.get("expiry") or ""
                if vol <= 0 or iv <= 0 or t <= 0 or strike <= 0 or not expiry:
                    continue
                strikes_c.append(strike)
                ts_c.append(t)
                vols_c.append(vol)
                ivs_c.append(iv)
                kinds_c.append((c.get("type") or "call") == "call")
                expiries_c.append(expiry)
            out = _dc.compute_gex_grid(spot, strikes_c, ts_c, vols_c, ivs_c,
                                       kinds_c, expiries_c, q, True)
            if out is not None and out.get("grid"):
                return {
                    "expiries": out["expiries"],
                    "strikes": out["strikes"],
                    "grid": out["grid"],
                    "charm_grid": out["charm_grid"],
                    "vex_grid": out["vex_grid"],
                    "strike_totals": out["strike_totals"],
                }
        except Exception as exc:  # pragma: no cover - fallback path
            import logging
            logging.getLogger(__name__).warning(
                "decoder_core compute_gex_grid(volume) failed (%s) — python fallback", exc)
    grid: dict[str, dict[float, float]] = {}
    charm_grid: dict[str, dict[float, float]] = {}
    vex_grid: dict[str, dict[float, float]] = {}
    strike_totals: dict[float, float] = {}
    for c in contracts:
        vol = safe_float(c.get("volume"))
        if vol <= 0:
            continue
        iv = safe_float(c.get("iv"))
        if iv <= 0:
            continue
        T = safe_float(c.get("T"))
        if T <= 0:
            continue
        strike = safe_float(c.get("strike"))
        if strike <= 0:
            continue
        expiry = c.get("expiry") or ""
        if not expiry:
            continue
        contract_type = c.get("type") or "call"
        gamma = bs_gamma(spot, strike, T, iv, q=q)
        charm = bs_charm(spot, strike, T, iv, q=q, kind=contract_type)
        vanna = bs_vanna(spot, strike, T, iv, q=q)
        # Weight by volume directly (contracts traded) rather than OI.
        gex_unit = gamma * vol * spot * 100.0
        charm_unit = abs(charm) * vol * spot * 100.0
        vex_unit = abs(vanna) * vol * spot * 100.0
        sign = 1.0 if contract_type == "call" else -1.0
        cell = sign * gex_unit
        d = grid.setdefault(expiry, {})
        d[strike] = d.get(strike, 0.0) + cell
        dc = charm_grid.setdefault(expiry, {})
        dc[strike] = dc.get(strike, 0.0) + sign * charm_unit
        dv = vex_grid.setdefault(expiry, {})
        dv[strike] = dv.get(strike, 0.0) + sign * vex_unit
        strike_totals[strike] = strike_totals.get(strike, 0.0) + cell

    expiries = sorted(grid.keys())
    strikes = sorted(strike_totals.keys())

    def _k(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else str(x)

    return {
        "expiries": expiries,
        "strikes": strikes,
        "grid": {e: {_k(k): v for k, v in grid[e].items()} for e in expiries},
        "charm_grid": {e: {_k(k): v for k, v in charm_grid[e].items()} for e in expiries},
        "vex_grid": {e: {_k(k): v for k, v in vex_grid[e].items()} for e in expiries},
        "strike_totals": [{"strike": k, "gex": v} for k, v in sorted(strike_totals.items())],
    }


def calc_probability_distribution(spot: float, contracts: list[dict[str, Any]],
                                   risk_free_rate: float = 0.05) -> list[dict[str, Any]]:
    """Risk-neutral probability distribution from option prices.

    Delegates to decoder_core Rust when available (40.6x, parity 2026-08-22);
    pure-Python body retained as fallback."""
    if spot <= 0 or not contracts:
        return []
    if _RUST_GEX:
        try:
            return _dc.probability_distribution(
                spot,
                [safe_float(c.get("strike")) for c in contracts],
                [str(c.get("type", "call")).lower().startswith("c") for c in contracts],
                [safe_float(c.get("iv")) for c in contracts],
                [safe_float(c.get("T")) for c in contracts],
                risk_free_rate,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            import logging

            logging.getLogger(__name__).warning(
                "decoder_core probability_distribution failed (%s) — python fallback", exc
            )
    strikes = sorted(set(c["strike"] for c in contracts))
    result = []
    for k in strikes:
        calls = [c for c in contracts if c["strike"] == k and c["type"] == "call"]
        puts = [c for c in contracts if c["strike"] == k and c["type"] == "put"]
        iv = None
        T = None
        if calls:
            iv = calls[0].get("iv") or 0.2
            T = calls[0].get("T") or 1/365
        elif puts:
            iv = puts[0].get("iv") or 0.2
            T = puts[0].get("T") or 1/365
        if not iv or iv <= 0 or not T or T <= 0:
            continue
        try:
            d1 = (math.log(spot / k) + (risk_free_rate + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
            d2 = d1 - iv * math.sqrt(T)
            prob_above = float(norm.cdf(d2))
            prob_below = 1.0 - prob_above
            delta_call = float(norm.cdf(d1))
            result.append({
                "strike": k,
                "prob_above": round(prob_above, 4),
                "prob_below": round(prob_below, 4),
                "delta": round(delta_call, 4),
                "iv": round(iv, 4),
            })
        except Exception:
            continue
    return result


def calc_implied_move(spot: float, contracts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Calculate implied move from ATM straddle price."""
    if spot <= 0 or not contracts:
        return None
    strikes = sorted(set(c["strike"] for c in contracts))
    if not strikes:
        return None
    atm = min(strikes, key=lambda s: abs(s - spot))
    atm_calls = [c for c in contracts if c["strike"] == atm and c["type"] == "call"]
    atm_puts = [c for c in contracts if c["strike"] == atm and c["type"] == "put"]
    if not atm_calls or not atm_puts:
        return None
    call_iv = atm_calls[0].get("iv") or 0.2
    put_iv = atm_puts[0].get("iv") or 0.2
    T = atm_calls[0].get("T") or 1/365
    if T <= 0:
        T = 1/365
    avg_iv = (call_iv + put_iv) / 2
    straddle = 0.8 * spot * avg_iv * math.sqrt(T)
    return {
        "atm_strike": atm,
        "straddle_price": round(straddle, 2),
        "implied_move_pct": round((straddle / spot) * 100, 2),
        "implied_move_dollars": round(straddle, 2),
        "upper_range": round(spot + straddle, 2),
        "lower_range": round(spot - straddle, 2),
        "avg_iv": round(avg_iv, 4),
        "tte_years": round(T, 6),
    }


def calc_aggregate_gex_curve(spot: float, contracts: list[dict[str, Any]],
                              ticker: str = "") -> list[dict[str, float]]:
    """Aggregate GEX curve: total GEX if spot moved to each price point.

    Delegates to decoder_core Rust implementation when available
    (3180x faster, parity within 4dp rounding); falls back to pure Python.
    """
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    if _RUST_GEX:
        try:
            return _dc.aggregate_gex_curve(
                spot,
                [safe_float(c.get("strike")) for c in contracts],
                [safe_float(c.get("oi")) for c in contracts],
                [safe_float(c.get("iv")) for c in contracts],
                [safe_float(c.get("T")) for c in contracts],
                [str(c.get("type", "call")) for c in contracts],
                q,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            import logging

            logging.getLogger(__name__).warning(
                "decoder_core aggregate_gex_curve failed (%s) — python fallback", exc
            )
    q = DIV_YIELD.get(ticker, 0.0)
    strikes = sorted(set(c["strike"] for c in contracts))
    if not strikes:
        return []
    min_s = min(strikes)
    max_s = max(strikes)
    lo = max(min_s, spot * 0.85)
    hi = min(max_s, spot * 1.15)
    step = (hi - lo) / 100
    if step <= 0:
        return []
    relevant = []
    for c in contracts:
        oi = safe_float(c.get("oi"))
        if oi <= 0:
            continue
        strike = safe_float(c.get("strike"))
        if strike < lo * 0.5 or strike > hi * 1.5:
            continue
        relevant.append(c)
    curve = []
    price = lo
    while price <= hi:
        total_gex = 0.0
        for c in relevant:
            T = safe_float(c.get("T"))
            iv = safe_float(c.get("iv"))
            if T <= 0 or iv <= 0:
                continue
            gamma = bs_gamma(price, safe_float(c.get("strike")), T, iv, q=q)
            if gamma <= 0:
                continue
            gex = dollar_gex_per_contract(gamma, safe_float(c.get("oi")), price)
            sign = 1.0 if c.get("type") == "call" else -1.0
            total_gex += sign * gex
        curve.append({"price": round(price, 2), "gex": round(total_gex / 1e9, 4) if not (math.isnan(total_gex) or math.isinf(total_gex)) else 0.0})
        price += step
    return curve


def classify_nodes(strikes: list[dict[str, Any]], spot: float) -> dict[str, Any]:
    """Classify GEX node hierarchy: king, floors, ceilings, gatekeepers, air pockets, risk metrics.

    Delegates to decoder_core Rust implementation when available (bit-exact
    parity verified 2026-08-22); falls back to the pure-Python body below."""
    if _RUST_GEX:
        rust_result = classify_nodes_rust(strikes, spot)
        if rust_result is not None:
            return rust_result
    if not strikes or spot <= 0:
        return {"king": None, "floors": [], "ceilings": [], "gatekeepers": [], "air_pockets": [],
                "polarity_level": None, "regime": "unknown", "total_gex": 0, "near_gex": 0,
                "vex_flip": None, "stacked_nodes": [], "tug_of_war": [], "total_vega": 0}

    king = max(strikes, key=lambda r: abs(r["gex"]))
    max_abs = abs(king["gex"]) or 1.0

    floors = sorted(
        [s for s in strikes if s["strike"] < spot and s["gex"] > 0],
        key=lambda r: r["gex"], reverse=True,
    )
    ceilings = sorted(
        [s for s in strikes if s["strike"] > spot and s["gex"] > 0],
        key=lambda r: r["gex"], reverse=True,
    )

    gk_threshold = 0.15 * max_abs
    if king and king["strike"] != spot:
        lo, hi = sorted([spot, king["strike"]])
        gks = [s for s in strikes
               if lo < s["strike"] < hi and s["strike"] != king["strike"]
               and abs(s["gex"]) >= gk_threshold]
        gatekeepers = sorted(gks, key=lambda r: abs(r["gex"]), reverse=True)
    else:
        gatekeepers = []

    ap_threshold = 0.08 * max_abs
    air_pockets = []
    run_start = None
    run_strikes: list[float] = []
    for s in strikes:
        weak = abs(s["gex"]) < ap_threshold
        if weak:
            if run_start is None:
                run_start = s["strike"]
            run_strikes.append(s["strike"])
        else:
            if run_start is not None and len(run_strikes) >= 3:
                air_pockets.append({"low": min(run_strikes), "high": max(run_strikes),
                                    "width": len(run_strikes), "mid": (min(run_strikes) + max(run_strikes)) / 2})
            run_start = None
            run_strikes = []
    if run_start is not None and len(run_strikes) >= 3:
        air_pockets.append({"low": min(run_strikes), "high": max(run_strikes),
                            "width": len(run_strikes), "mid": (min(run_strikes) + max(run_strikes)) / 2})

    total_gex = sum(s["gex"] for s in strikes)
    spot_window = [s for s in strikes if abs(s["strike"] - spot) / spot < 0.02]
    near_gex = sum(s["gex"] for s in spot_window)
    if total_gex > 0:
        regime = "positive"
    elif total_gex < 0:
        regime = "negative"
    else:
        regime = "neutral"

    total_abs_gex = sum(abs(s["gex"]) for s in strikes)
    polarity = sum(s["strike"] * abs(s["gex"]) for s in strikes) / total_abs_gex if total_abs_gex > 0 else spot

    total_abs_vex = sum(abs(s.get("vex", 0.0) or 0) for s in strikes)
    if total_abs_vex > 0:
        vex_flip = sum(s["strike"] * abs(s.get("vex", 0.0) or 0) for s in strikes) / total_abs_vex
    else:
        vex_flip = spot

    stacked = []
    for s in strikes:
        if abs(s["strike"] - spot) / spot > 0.03:
            continue
        total = abs(s.get("call_gex", 0)) + abs(s.get("put_gex", 0))
        if total > 0:
            call_pct = abs(s.get("call_gex", 0)) / total
            put_pct = abs(s.get("put_gex", 0)) / total
            if call_pct > 0.2 and put_pct > 0.2:
                stacked.append({"strike": s["strike"], "call_pct": round(call_pct, 2), "put_pct": round(put_pct, 2)})

    tug_of_war = []
    near_strikes = sorted([s for s in strikes if abs(s["strike"] - spot) / spot < 0.03], key=lambda r: r["strike"])
    for i in range(1, len(near_strikes)):
        a, b = near_strikes[i-1], near_strikes[i]
        if (a["gex"] > 0 and b["gex"] < 0) or (a["gex"] < 0 and b["gex"] > 0):
            tug_of_war.append({"low": a["strike"], "high": b["strike"],
                                "positive": a["gex"] if a["gex"] > 0 else b["gex"],
                                "negative": a["gex"] if a["gex"] < 0 else b["gex"]})

    total_vega = sum((s.get("vega") or 0.0) for s in strikes)
    if math.isnan(total_vega) or math.isinf(total_vega):
        total_vega = 0.0
    total_charm = sum((s.get("charm") or 0.0) for s in strikes)
    if math.isnan(total_charm) or math.isinf(total_charm):
        total_charm = 0.0
    total_vomma = sum((s.get("vomma") or 0.0) for s in strikes)
    if math.isnan(total_vomma) or math.isinf(total_vomma):
        total_vomma = 0.0
    total_zomma = sum((s.get("zomma") or 0.0) for s in strikes)
    if math.isnan(total_zomma) or math.isinf(total_zomma):
        total_zomma = 0.0

    total_abs_charm = sum(abs(s.get("charm") or 0.0) for s in strikes)
    if total_abs_charm > 0:
        charm_flip = sum(s["strike"] * abs(s.get("charm") or 0.0) for s in strikes) / total_abs_charm
    else:
        charm_flip = spot

    max_pain = None
    if strikes:
        strike_range = sorted(set(s["strike"] for s in strikes))
        min_pain = float("inf")
        for test_strike in strike_range:
            pain = 0.0
            for s in strikes:
                oi = s.get("total_oi", 0) or 0
                pain += oi * abs(s["strike"] - test_strike)
            if pain < min_pain:
                min_pain = pain
                max_pain = test_strike

    total_call_oi = sum(s.get("call_oi", 0) or 0 for s in strikes)
    total_put_oi = sum(s.get("put_oi", 0) or 0 for s in strikes)
    put_call_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else None

    total_abs = sum(abs(s["gex"]) for s in strikes) or 1.0
    gamma_shares = [abs(s["gex"]) / total_abs for s in strikes]
    gci = sum(s * s for s in gamma_shares)

    gdw_decay = 20.0
    near_spot = 20.0
    gamma_near = sum(abs(s["gex"]) for s in strikes if abs(s["strike"] - spot) <= near_spot)
    pgr = gamma_near / total_abs if total_abs > 0 else 0.0

    gdw = sum(abs(s["gex"]) * math.exp(-abs(s["strike"] - spot) / gdw_decay) for s in strikes)

    avg_tte = 1.0 / 252.0
    time_amp = min(30.0, 1.0 / math.sqrt(max(avg_tte, 0.001)))
    gamma_sign = -1.0 if total_gex < 0 else 1.0
    car_net = gamma_sign * (0.6 * total_zomma + 0.4 * total_vomma) * time_amp / 1e6
    car_gross = (0.6 * abs(total_zomma) + 0.4 * abs(total_vomma)) * time_amp / 1e6

    charm_risk = total_charm / 1e6

    return {
        "king": king,
        "floors": floors[:5],
        "ceilings": ceilings[:5],
        "gatekeepers": gatekeepers[:6],
        "air_pockets": air_pockets[:10],
        "polarity_level": round(polarity, 4),
        "regime": regime,
        "total_gex": round(total_gex, 4),
        "near_gex": round(near_gex, 4),
        "vex_flip": round(vex_flip, 4),
        "stacked_nodes": stacked,
        "tug_of_war": tug_of_war,
        "total_vega": round(total_vega, 4),
        "total_charm": round(total_charm, 4),
        "total_vomma": round(total_vomma, 4),
        "total_zomma": round(total_zomma, 4),
        "charm_flip": round(charm_flip, 4),
        "max_pain": max_pain,
        "put_call_ratio": round(put_call_ratio, 4) if put_call_ratio is not None else None,
        "_spot": round(spot, 2),
        "risk_metrics": {
            "gci": round(gci, 4),
            "pgr": round(pgr, 4),
            "gdw": round(gdw, 4),
            "car_net": round(car_net, 4),
            "car_gross": round(car_gross, 4),
            "charm_risk": round(charm_risk, 4),
        },
    }


def detect_opportunities(strikes: list[dict[str, Any]], nodes: dict[str, Any],
                          spot: float, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect trading opportunities from GEX analysis."""
    opportunities = []
    if not strikes or spot <= 0:
        return opportunities

    king = nodes.get("king")
    if not king:
        return opportunities
    total_gex = nodes.get("total_gex", 0)
    polarity = nodes.get("polarity_level", spot)
    regime = nodes.get("regime", "neutral")

    call_wall = nodes.get("ceilings", [{}])
    call_wall_strike = call_wall[0]["strike"] if call_wall else None
    if call_wall_strike and spot < call_wall_strike:
        dist_pct = (call_wall_strike - spot) / spot * 100
        if dist_pct < 3.0:
            calls_above = [s for s in strikes if s["strike"] > spot and s.get("call_gex", 0) > 0]
            total_call_gex = sum(s.get("call_gex", 0) for s in calls_above)
            max_call_gex = max((s.get("call_gex", 0) for s in calls_above), default=0)
            concentration = max_call_gex / total_call_gex if total_call_gex > 0 else 0
            proximity = 1 - (dist_pct / 3.0)
            confidence = min((concentration + proximity) / 2, 1.0)
            if confidence >= 0.3:
                opportunities.append({
                    "type": "gamma_squeeze", "name": "Gamma Squeeze Setup",
                    "direction": "bullish", "risk": "high",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% below call wall at {call_wall_strike:.1f}. Breakout could trigger dealer hedging acceleration.",
                    "trigger": {"call_wall": call_wall_strike, "distance_pct": round(dist_pct, 2), "concentration": round(concentration, 2)},
                    "entry": (round(spot * 0.995, 2), round(call_wall_strike * 0.99, 2)),
                    "target": round(call_wall_strike * 1.02, 2),
                    "stop": round(spot * 0.97, 2),
                })

    put_wall = nodes.get("floors", [{}])
    put_wall_strike = put_wall[0]["strike"] if put_wall else None
    if put_wall_strike and spot > put_wall_strike:
        dist_pct = (spot - put_wall_strike) / spot * 100
        if dist_pct < 3.0:
            proximity = 1 - (dist_pct / 3.0)
            regime_bonus = 0.2 if regime == "positive" else 0
            confidence = min(proximity + regime_bonus, 1.0)
            if confidence >= 0.4:
                opportunities.append({
                    "type": "put_wall_support", "name": "Put Wall Support",
                    "direction": "bullish", "risk": "low",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% above put wall at {put_wall_strike:.1f}. Dealers likely to buy dips here.",
                    "trigger": {"put_wall": put_wall_strike, "distance_pct": round(dist_pct, 2), "regime": regime},
                    "entry": (round(put_wall_strike * 1.005, 2), round(spot * 1.01, 2)),
                    "target": round(polarity, 2),
                    "stop": round(put_wall_strike * 0.98, 2),
                })

    if call_wall_strike and spot < call_wall_strike:
        dist_pct = (call_wall_strike - spot) / spot * 100
        if dist_pct < 3.0:
            proximity = 1 - (dist_pct / 3.0)
            regime_bonus = 0.2 if regime == "positive" else 0
            confidence = min(proximity + regime_bonus, 1.0)
            if confidence >= 0.4:
                opportunities.append({
                    "type": "call_wall_resistance", "name": "Call Wall Resistance",
                    "direction": "bearish", "risk": "low",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% below call wall at {call_wall_strike:.1f}. Dealers likely to sell rallies here.",
                    "trigger": {"call_wall": call_wall_strike, "distance_pct": round(dist_pct, 2), "regime": regime},
                    "entry": (round(call_wall_strike * 0.99, 2), round(call_wall_strike * 1.005, 2)),
                    "target": round(polarity, 2),
                    "stop": round(call_wall_strike * 1.02, 2),
                })

    if regime in ("negative", "neutral") and total_gex < 0:
        dist_to_flip = ((spot - polarity) / spot) * 100 if polarity else 0
        confidence = min(abs(dist_to_flip) / 5, 1.0)
        if confidence >= 0.3:
            opportunities.append({
                "type": "volatility_expansion", "name": "Volatility Expansion",
                "direction": "neutral", "risk": "medium",
                "confidence": round(confidence, 2),
                "description": "Negative gamma regime. Dealers amplifying moves. Expect increased volatility.",
                "trigger": {"regime": regime, "total_gex": total_gex, "dist_to_flip_pct": round(dist_to_flip, 2)},
            })

    if regime == "positive" and total_gex > 0:
        dist_to_flip = ((spot - polarity) / spot) * 100 if polarity else 0
        confidence = min(dist_to_flip / 5, 1.0)
        if confidence >= 0.3:
            opportunities.append({
                "type": "volatility_compression", "name": "Volatility Compression",
                "direction": "neutral", "risk": "low",
                "confidence": round(confidence, 2),
                "description": "Positive gamma regime. Dealers dampening moves. Good for selling premium.",
                "trigger": {"regime": regime, "total_gex": total_gex, "dist_to_flip_pct": round(dist_to_flip, 2)},
            })

    if contracts:
        expiries = sorted(set(c["expiry"] for c in contracts))
        if expiries:
            nearest_exp = expiries[0]
            try:
                exp_date = datetime.strptime(nearest_exp, "%Y-%m-%d").date()
                dte = (exp_date - datetime.now(UTC).date()).days
            except Exception:
                dte = 999
            if dte <= 5:
                atm_strike_val = min(strikes, key=lambda s: abs(s["strike"] - spot))["strike"]
                atm_strikes_data = [s for s in strikes if abs(s["strike"] - atm_strike_val) < spot * 0.01]
                if atm_strikes_data:
                    max_oi = max(s.get("total_oi", 0) for s in atm_strikes_data)
                    if max_oi > 1000:
                        confidence = min(0.3 + (max_oi / 10000) * 0.3 + (1 - dte / 5) * 0.3, 1.0)
                        if confidence >= 0.4:
                            opportunities.append({
                                "type": "pin_risk", "name": "Expiration Pin Risk",
                                "direction": "neutral", "risk": "medium",
                                "confidence": round(confidence, 2),
                                "description": f"High OI ({max_oi:,.0f}) at {atm_strike_val:.0f} with {dte} DTE. Price may gravitate here.",
                                "trigger": {"pin_strike": atm_strike_val, "oi": max_oi, "dte": dte},
                                "target": atm_strike_val,
                            })

    calls_above = sorted([s for s in strikes if s["strike"] > spot and s.get("call_gex", 0) > 0],
                         key=lambda s: s["strike"])
    if len(calls_above) >= 3:
        call_gex_vals = [s.get("call_gex", 0) for s in calls_above[:5]]
        ascending = sum(1 for i in range(len(call_gex_vals) - 1) if call_gex_vals[i + 1] > call_gex_vals[i] * 0.8)
        if ascending >= 2:
            pattern_strength = ascending / (len(call_gex_vals) - 1)
            total_call_gex_above = sum(call_gex_vals)
            total_call_gex_all = sum(s.get("call_gex", 0) for s in strikes if s.get("call_gex", 0) > 0)
            concentration = total_call_gex_above / total_call_gex_all if total_call_gex_all > 0 else 0
            confidence = min((pattern_strength + concentration) / 2, 1.0)
            if confidence >= 0.35:
                rungs = [s["strike"] for s in calls_above[:3]]
                opportunities.append({
                    "type": "gamma_ladder", "name": "Gamma Call Ladder",
                    "direction": "bullish", "risk": "medium",
                    "confidence": round(confidence, 2),
                    "description": f"Call ladder with {ascending} rungs. Targets: {', '.join(f'{r:.0f}' for r in rungs)}.",
                    "trigger": {"rungs": rungs, "ascending": ascending, "concentration": round(concentration, 2)},
                    "entry": (round(spot * 0.99, 2), round(rungs[0] * 0.995, 2)),
                    "target": rungs[-1],
                    "stop": round(spot * 0.97, 2),
                })

    opportunities.sort(key=lambda o: o.get("confidence", 0), reverse=True)
    return opportunities[:8]


def detect_patterns(strikes: list[dict[str, Any]], nodes: dict[str, Any], spot: float) -> list[dict[str, Any]]:
    """Detect GEX patterns: beach ball, reverse rug, rainbow road, velocity mode."""
    patterns = []
    king = nodes.get("king")
    if not king or spot <= 0:
        return patterns

    king_strike = king.get("strike") or spot
    if king_strike and king_strike > 0:
        distance_pct = abs(spot - king_strike) / king_strike
        if distance_pct > 0.005:
            confidence = min(1.0, distance_pct / 0.02)
            patterns.append({
                "pattern": "beach_ball",
                "active": True,
                "king_node": round(float(king_strike), 4),
                "spot_distance_pct": round(distance_pct, 6),
                "direction": "above" if spot > king_strike else "below",
                "confidence": round(confidence, 4),
            })

    floors = nodes.get("floors", [])
    ceilings = nodes.get("ceilings", [])
    if floors and ceilings:
        floor_strike = floors[0].get("strike")
        floor_gex = floors[0].get("gex", 0)
        ceiling_strike = ceilings[0].get("strike")
        ceiling_gex = ceilings[0].get("gex", 0)
        if floor_strike and ceiling_strike and floor_strike < spot < ceiling_strike:
            patterns.append({
                "pattern": "reverse_rug",
                "active": True,
                "floor_strike": round(floor_strike, 4),
                "floor_gex": round(floor_gex, 4),
                "ceiling_strike": round(ceiling_strike, 4),
                "ceiling_gex": round(ceiling_gex, 4),
            })

    near_window = [s for s in strikes if abs(s["strike"] - spot) / spot < 0.05]
    if near_window:
        near_abs = {s["strike"]: abs(s["gex"]) for s in near_window}
        total_near = sum(near_abs.values())
        if total_near > 0:
            top_share = max(near_abs.values()) / total_near
            mean_abs = total_near / len(near_window)
            n_significant = sum(1 for v in near_abs.values() if v > 0.5 * mean_abs)
            if top_share < 0.15:
                patterns.append({
                    "pattern": "rainbow_road",
                    "active": True,
                    "top_strike_share": round(top_share, 6),
                    "n_strikes_significant": n_significant,
                })

    return patterns


def compute_gex_by_strike_volume(spot: float, contracts: list[dict[str, Any]], ticker: str) -> list[dict[str, Any]]:
    """Per-strike GEX weighted by volume instead of OI (intraday signal)."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    agg: dict[float, dict[str, float]] = {}
    for c in contracts:
        vol = safe_float(c.get("volume")) or safe_float(c.get("vol"))
        if vol <= 0:
            continue
        iv = safe_float(c.get("iv"))
        if iv <= 0:
            continue
        T = safe_float(c.get("T"))
        if T <= 0:
            continue
        strike = safe_float(c.get("strike"))
        if strike <= 0:
            continue
        try:
            gamma = float(bs_gamma(spot, strike, T, iv, q=q) or 0)
        except (TypeError, ValueError):
            continue
        if gamma <= 0:
            continue
        gex_unit = dollar_gex_per_contract(gamma, vol, spot)
        sign = 1.0 if c.get("type") == "call" else -1.0
        bucket = agg.setdefault(strike, {"strike": strike, "gex": 0.0, "call_gex": 0.0, "put_gex": 0.0, "total_vol": 0.0})
        bucket["gex"] += sign * gex_unit
        bucket["total_vol"] += vol
        if c.get("type") == "call":
            bucket["call_gex"] += gex_unit
        else:
            bucket["put_gex"] += gex_unit
    return sorted(agg.values(), key=lambda r: r["strike"])


def find_zero_crossings(spot: float, contracts: list[dict]) -> list[float]:
    """
    Find zero-gamma flip points by linear interpolation.

    Uses aggregate GEX curve to identify price levels where net dealer
    gamma transitions from positive to negative.
    """
    # Aggregate GEX by strike
    by_strike = {}
    for c in contracts:
        strike = c.get("strike") or 0
        gex_val = c.get("gex", 0)
        if isinstance(gex_val, dict):
            gex_val = gex_val.get("net_gex", 0)
        if strike and gex_val:
            by_strike[strike] = by_strike.get(strike, 0) + gex_val

    if not by_strike:
        return []

    # Sort by strike
    sorted_strikes = sorted(by_strike.keys())
    gex_values = [by_strike[s] for s in sorted_strikes]

    # Find sign changes
    flip_levels = []
    for i in range(1, len(sorted_strikes)):
        prev_gex = gex_values[i - 1]
        curr_gex = gex_values[i]

        if prev_gex * curr_gex < 0:
            prev_s = sorted_strikes[i - 1]
            curr_s = sorted_strikes[i]

            if curr_gex != prev_gex:
                flip = prev_s - prev_gex * (curr_s - prev_s) / (curr_gex - prev_gex)
                flip_levels.append(flip)

    return sorted(set(flip_levels))
