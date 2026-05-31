"""
backend/routes/analytics.py

Analytics routes with cache-first routing, validated query params,
request coalescing, and graceful degradation.

All /api/analytics/* endpoints now:
  1. Accept bounded query params with defaults (no more 422s).
  2. Read from DuckDB cache first.
  3. Return stale cache rather than blocking on external API.
  4. Return structured degradation payloads on failure (never raw 429/500).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services.fetch_coordinator import CacheRouter, FetchCoordinator, degraded_response

logger = logging.getLogger(__name__)
router = APIRouter()

_cache = CacheRouter()
_coordinator = FetchCoordinator()


async def _fetch_chain(ticker: str, expiries: int):
    """Fetch option chain — cache-first with fallback."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await _cache.get_chain(t, expiries, 300, _coordinator)


def _check_chain(raw: dict, ticker: str):
    """Validate chain data exists."""
    spot = raw.get("spot")
    if not spot or not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")


@router.get("/implied-pdf/{ticker}")
async def implied_pdf(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12, description="Number of expiries to fetch"),
    max_age_seconds: int = Query(default=300, ge=0, le=3600, description="Max cache age in seconds"),
):
    try:
        from advanced_analytics import calc_implied_pdf
        from server import _sanitize
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        return _sanitize(calc_implied_pdf(raw["spot"], raw["contracts"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("implied-pdf error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/regime/{ticker}")
async def regime(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from advanced_analytics import calc_market_regime
        from server import _sanitize
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        return _sanitize(calc_market_regime(raw["spot"], raw["contracts"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("regime error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/hedge-impulse/{ticker}")
async def hedge_impulse(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from advanced_analytics import calc_hedge_impulse_curve
        from server import _sanitize
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        return _sanitize(calc_hedge_impulse_curve(raw["spot"], raw["contracts"], ticker.strip().upper()))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("hedge-impulse error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/pressure-cloud/{ticker}")
async def pressure_cloud(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from advanced_analytics import calc_pressure_cloud
        from server import _sanitize
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        return _sanitize(calc_pressure_cloud(raw["spot"], raw["contracts"], ticker.strip().upper()))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("pressure-cloud error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/charm-integral/{ticker}")
async def charm_integral_endpoint(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from advanced_analytics import calc_charm_integral
        from server import _sanitize
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        return _sanitize(calc_charm_integral(raw["spot"], raw["contracts"], ticker.strip().upper()))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("charm-integral error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/vanna/{ticker}")
async def vanna_endpoint(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
):
    """Alias for vanna-exposure."""
    return await vanna_exposure_endpoint(ticker, expiries)


@router.get("/vanna-exposure/{ticker}")
async def vanna_exposure_endpoint(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        import numpy as np

        from server import _sanitize
        from services.numba_greeks import bs_vanna_vec

        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        spot = raw["spot"]
        contracts = raw["contracts"]
        t = ticker.strip().upper()

        strike_vanna: dict = {}
        for c in contracts:
            strike = c.get("strike")
            if not strike:
                continue
            iv = c.get("iv", 0)
            if iv <= 0:
                continue
            oi = c.get("oi", c.get("open_interest", 0))
            T = c.get("dte", 30) / 365.0
            if T <= 0:
                continue

            vanna = float(bs_vanna_vec(
                np.array([float(spot)]),
                np.array([float(strike)]),
                np.array([T]),
                np.array([float(iv)]),
                0.0,
                0.05,
            )[0])

            sign = 1.0 if c.get("type") == "call" else -1.0
            weighted = vanna * oi * sign * 100
            strike_vanna[strike] = strike_vanna.get(strike, 0.0) + weighted

        sorted_strikes = sorted(strike_vanna.keys())
        return _sanitize({
            "ticker": t,
            "spot": spot,
            "strikes": sorted_strikes,
            "vanna": [strike_vanna[k] for k in sorted_strikes],
            "asof": datetime.now(timezone.utc).isoformat(),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("vanna-exposure error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/advanced/{ticker}")
async def advanced_analytics(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from advanced_analytics import (
            calc_charm_integral,
            calc_hedge_impulse_curve,
            calc_implied_pdf,
            calc_market_regime,
            calc_pressure_cloud,
        )
        from server import _sanitize
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        spot = raw["spot"]
        contracts = raw["contracts"]
        t = ticker.strip().upper()

        return _sanitize({
            "ticker": t,
            "spot": spot,
            "implied_pdf": calc_implied_pdf(spot, contracts),
            "regime": calc_market_regime(spot, contracts),
            "hedge_impulse": calc_hedge_impulse_curve(spot, contracts, t),
            "pressure_cloud": calc_pressure_cloud(spot, contracts, t),
            "charm_integral": calc_charm_integral(spot, contracts, t),
            "asof": datetime.now(timezone.utc).isoformat(),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("advanced error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/gamma-flip/{ticker}")
async def gamma_flip(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from advanced_analytics import calc_gamma_flip_levels
        from server import _sanitize
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        spot = raw.get("spot")
        if not spot or spot != spot or not raw.get("contracts"):
            raise HTTPException(404, f"No options data for {ticker}")
        return _sanitize(calc_gamma_flip_levels(spot, raw["contracts"], ticker.strip().upper()))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("gamma-flip error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/daily-checklist/{ticker}")
async def daily_checklist(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from advanced_analytics import calc_gamma_flip_levels, calc_market_regime
        from server import _sanitize
        from vol_analytics import calc_iv_surface_data, calc_skew_metrics
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        spot = raw.get("spot")
        if not spot or spot != spot or not raw.get("contracts"):
            raise HTTPException(404, f"No options data for {ticker}")

        gf = calc_gamma_flip_levels(spot, raw["contracts"], ticker.strip().upper())
        regime_data = calc_market_regime(spot, raw["contracts"])
        iv_surface = calc_iv_surface_data(spot, raw["contracts"])
        skew = calc_skew_metrics(spot, raw["contracts"])

        return _sanitize({
            "ticker": ticker.strip().upper(),
            "spot": spot,
            "asof": datetime.now(timezone.utc).isoformat(),
            "regime": {
                "gex_regime": gf["regime"],
                "market_regime": regime_data.get("regime", "unknown"),
                "iv_rank": iv_surface.get("atm_iv", 0),
                "skew": skew.get("risk_reversal_25d", 0),
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("daily-checklist error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/movers")
async def movers(
    limit: int = Query(default=20, ge=1, le=100, description="Max number of movers to return"),
):
    try:
        from server import _fetch_movers_sync
        data = _fetch_movers_sync()
        return {"results": data[:limit], "asof": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.warning(f"movers error: {e}")
        return {"results": [], "status": "degraded", "reason": str(e), "asof": datetime.now(timezone.utc).isoformat()}


@router.get("/history/{ticker}")
async def history(
    ticker: str,
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
):
    try:
        from datetime import timedelta

        from server import db as mongo_db
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cursor = mongo_db.snapshots.find(
            {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("ts", -1)
        snapshots = await cursor.to_list(length=1000)
        return {"ticker": ticker.upper(), "snapshots": snapshots, "count": len(snapshots)}
    except Exception as e:
        logger.warning(f"history error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "snapshots": [], "count": 0, "status": "degraded", "reason": str(e)}


@router.get("/patterns/glossary")
async def patterns_glossary():
    from server import PATTERN_GLOSSARY
    return PATTERN_GLOSSARY


@router.get("/contract/{ticker}")
async def contract(
    ticker: str,
    expiry: Optional[str] = None,
    expiries: int = Query(default=12, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from server import _sanitize
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        contracts = raw["contracts"]
        if expiry:
            contracts = [c for c in contracts if c.get("expiry") == expiry]
        spot = raw["spot"]
        rows = []
        for c in contracts:
            gamma = c.get("gamma", 0)
            oi = c.get("oi", c.get("open_interest", 0))
            gex = gamma * oi * 100 * spot * (1 if c["type"] == "call" else -1)
            rows.append({
                "type": c["type"],
                "strike": c["strike"],
                "expiry": c["expiry"],
                "iv": c.get("iv", 0),
                "delta": c.get("delta", 0),
                "gamma": c.get("gamma", 0),
                "vega": c.get("vega", 0),
                "theta": c.get("theta", 0),
                "oi": c.get("oi", c.get("open_interest", 0)),
                "volume": c.get("volume", 0),
                "bid": c.get("bid", 0),
                "ask": c.get("ask", 0),
                "gex": gex,
            })
        return _sanitize({"ticker": ticker.strip().upper(), "spot": spot, "rows": rows, "count": len(rows)})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("contract error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/flow/{ticker}")
async def flow(
    ticker: str,
    days: int = Query(default=7, ge=1, le=30),
):
    try:
        from datetime import timedelta

        from server import db as mongo_db
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cursor = mongo_db.flow.find(
            {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("ts", -1).limit(500)
        return await cursor.to_list(length=500)
    except Exception as e:
        logger.warning(f"flow error for {ticker}: {e}")
        return []


@router.get("/surface/{ticker}")
async def surface(
    ticker: str,
    expiries: int = Query(default=4, ge=1, le=12),
    max_age_seconds: int = Query(default=300, ge=0, le=3600),
):
    try:
        from server import _sanitize, calc_iv_surface_data
        raw = await _cache.get_chain(ticker, expiries, max_age_seconds, _coordinator)
        _check_chain(raw, ticker)
        return _sanitize(calc_iv_surface_data(raw["spot"], raw["contracts"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("surface error for %s: %s", ticker, e)
        return degraded_response("computation_error", str(e))


@router.get("/regime-stats/{ticker}")
async def regime_stats(
    ticker: str,
    days: int = Query(default=30, ge=1, le=365),
):
    try:
        from datetime import timedelta

        from server import db as mongo_db
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cursor = mongo_db.snapshots.find(
            {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
            {"regime": 1, "ts": 1, "_id": 0},
        ).sort("ts", -1)
        docs = await cursor.to_list(length=1000)
        return {"ticker": ticker.upper(), "n_samples": len(docs), "data": docs}
    except Exception as e:
        logger.warning(f"regime-stats error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "n_samples": 0, "data": [], "status": "degraded", "reason": str(e)}


@router.get("/compare")
async def compare(
    tickers: str = Query(..., description="Comma-separated ticker symbols"),
):
    from server import _sanitize, calc_market_regime
    syms = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    out = {}
    for sym in syms:
        try:
            raw = await _cache.get_chain(sym, 4, 300, _coordinator)
            _check_chain(raw, sym)
            out[sym] = _sanitize(calc_market_regime(raw["spot"], raw["contracts"]))
        except HTTPException as e:
            out[sym] = {"error": e.detail, "status": "degraded"}
        except Exception as e:
            out[sym] = {"error": str(e), "status": "degraded"}
    return out


@router.get("/correlation")
async def correlation(
    tickers: str = Query(..., description="Comma-separated ticker symbols"),
    days: int = Query(default=30, ge=1, le=365),
):
    try:
        from datetime import timedelta

        import pandas as pd

        from server import db as mongo_db
        syms = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        data = {}
        for sym in syms:
            cursor = mongo_db.snapshots.find(
                {"ticker": sym, "ts": {"$gte": cutoff}},
                {"spot": 1, "ts": 1, "_id": 0},
            ).sort("ts", 1)
            docs = await cursor.to_list(length=1000)
            if docs:
                data[sym] = pd.DataFrame(docs)

        if not data:
            return {"error": "No data found", "correlation": {}}

        closes = pd.DataFrame({sym: df.set_index("ts")["spot"] for sym, df in data.items() if "spot" in df.columns})
        corr = closes.corr().to_dict()
        return {"correlation": corr, "n_samples": len(closes)}
    except Exception as e:
        logger.warning(f"correlation error: {e}")
        return {"correlation": {}, "n_samples": 0, "status": "degraded", "reason": str(e)}
