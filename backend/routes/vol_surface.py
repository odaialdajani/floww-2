"""
backend/routes/vol_surface.py

Stochastic Volatility Surface API routes.
Exposes SABR and SVI models for IV surface interpolation.

Endpoints:
  GET  /api/vol-surface/{ticker}          — Full IV surface data
  POST /api/vol-surface/{ticker}/sabr     — Fit SABR to market data
  POST /api/vol-surface/{ticker}/svi      — Fit SVI to market data
"""
from __future__ import annotations

import logging
from typing import List

import numpy as np
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vol-surface", tags=["vol_surface"])


async def _fetch_chain(ticker: str, expiries: int = 4):
    from server import fetch_spot_and_chains_merged
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await fetch_spot_and_chains_merged(t, expiries)


@router.get("/{ticker}")
async def get_vol_surface(ticker: str, expiries: int = Query(6, ge=1, le=12)):
    """Return the full implied volatility surface for a ticker."""
    t = ticker.upper()
    raw = await _fetch_chain(t, expiries)
    spot = raw.get("spot", 0)
    contracts = raw.get("contracts", [])
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {t}")

    # Build surface data
    expiries_list = sorted(set(c["expiry"] for c in contracts))
    strikes_list = sorted(set(c["strike"] for c in contracts))

    surface = {}
    for exp in expiries_list:
        surface[exp] = {}
        for c in contracts:
            if c["expiry"] == exp:
                surface[exp][c["strike"]] = c.get("iv", 0)

    return {
        "ticker": t,
        "spot": spot,
        "expiries": expiries_list,
        "strikes": strikes_list,
        "surface": surface,
    }


@router.post("/{ticker}/sabr")
async def fit_sabr(
    ticker: str,
    strikes: List[float],
    market_vols: List[float],
    F: float,
    T: float,
):
    """Fit SABR model to market volatility smile."""
    from services.stochastic_vol import SABRModel

    if len(strikes) != len(market_vols) or len(strikes) < 4:
        raise HTTPException(400, "strikes and market_vols must have same length >= 4")

    model = SABRModel()
    result = model.fit(
        strikes=np.array(strikes),
        market_vols=np.array(market_vols),
        F=F,
        T=T,
    )
    return {"ticker": ticker.upper(), **result}


@router.post("/{ticker}/svi")
async def fit_svi(
    ticker: str,
    log_moneyness: List[float],
    market_vols: List[float],
    T: float,
):
    """Fit SVI model to market data."""
    from services.stochastic_vol import SVIProfile

    if len(log_moneyness) != len(market_vols) or len(log_moneyness) < 5:
        raise HTTPException(400, "log_moneyness and market_vols must have same length >= 5")

    model = SVIProfile()
    result = model.fit(
        log_moneyness=np.array(log_moneyness),
        market_vols=np.array(market_vols),
        T=T,
    )
    return {"ticker": ticker.upper(), **result}
