"""
backend/routes/greeks_api.py

REST API for Greek Exposure data (G|Flows integration).

Endpoints:
  GET  /api/greeks/profile/{ticker}    — Full exposure profile for a ticker
  GET  /api/greeks/yield-curve          — Treasury yield curve
  GET  /api/greeks/opex/{year}/{month}  — OPEX dates for given month
  POST /api/greeks/download             — Trigger CBOE data download
  GET  /api/greeks/tickers              — List available tickers
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

log = logging.getLogger(__name__)

router = APIRouter(tags=["greeks"])

# Deferred import to avoid circular deps & allow graceful fallback
_integrator: Optional[Any] = None


def _get_integrator():
    global _integrator
    if _integrator is None:
        try:
            from services.gflows_integration import gflows_integrator

            _integrator = gflows_integrator
        except ImportError:
            log.warning("gflows_integration not available — Greeks API disabled")
            _integrator = False  # sentinel
    return _integrator if _integrator is not False else None


# ------------------------------------------------------------------
# Profile endpoint (full exposure profile for a ticker)
# ------------------------------------------------------------------


@router.get("/api/greeks/profile/{ticker}")
async def get_greeks_profile(ticker: str, expir: str = "all"):
    """Get full Greek exposure profile for a ticker symbol.

    Args:
        ticker: Ticker symbol (e.g., SPX, NDX, RUT).
        expir: Expiration filter ('all', '0dte', 'opex', 'monthly').

    Returns:
        Dict with spot price, zero delta/gamma flips, and full
        exposure profiles for Delta, Gamma, Vanna, Charm.
    """
    gf = _get_integrator()
    if gf is None:
        return {"error": "G|Flows integration not available"}

    try:
        data = gf.load_cached_data(ticker.lower(), is_json=True, expir=expir)
        if data is None:
            return {
                "ticker": ticker.upper(),
                "expiration": expir,
                "error": "No cached data available. Try POST /api/greeks/download first.",
                "available_tickers": gf.get_available_tickers(),
            }

        profiles = gf.compute_exposure_profiles(data)
        return {"ticker": ticker.upper(), "expiration": expir, **profiles}
    except Exception as e:
        log.error("Greeks profile error for %s: %s", ticker, e)
        return {"error": str(e)}


# ------------------------------------------------------------------
# Yield curve endpoint
# ------------------------------------------------------------------


@router.get("/api/greeks/yield-curve")
async def get_yield_curve():
    """Get the current treasury yield curve.

    Uses multi-tier fallback: FRED → yfinance → default curve.
    Returns dict mapping tenor names to yield rates as decimals.
    """
    gf = _get_integrator()
    if gf is None:
        return {"error": "G|Flows integration not available"}

    try:
        curve = gf.get_yield_curve()
        return {"yield_curve": curve}
    except Exception as e:
        log.error("Yield curve error: %s", e)
        return {"error": str(e)}


# ------------------------------------------------------------------
# OPEX calendar endpoint
# ------------------------------------------------------------------


@router.get("/api/greeks/opex/{year}/{month}")
async def get_opex_dates(year: int, month: int):
    """Get OPEX (options expiration) dates for a given month.

    Returns third Friday, next monthly OPEX, and calendar range
    for option expiration analysis.
    """
    gf = _get_integrator()
    if gf is None:
        return {"error": "G|Flows integration not available"}

    try:
        opex = gf.get_opex_dates(year, month)
        return {"year": year, "month": month, **opex}
    except Exception as e:
        log.error("OPEX error: %s", e)
        return {"error": str(e)}


# ------------------------------------------------------------------
# Data download trigger
# ------------------------------------------------------------------


@router.post("/api/greeks/download")
async def download_data(tickers: Optional[List[str]] = None):
    """Trigger CBOE options data download.

    Args:
        tickers: List of tickers to download (default: SPX, NDX, RUT).

    Returns:
        Success status message.
    """
    gf = _get_integrator()
    if gf is None:
        return {"error": "G|Flows integration not available"}

    try:
        success = await gf.download_options_data(tickers=tickers)
        if success:
            return {
                "status": "ok",
                "message": f"Data download initiated for {tickers or ['SPX', 'NDX', 'RUT']}",
            }
        else:
            return {"status": "error", "message": "Download failed"}
    except Exception as e:
        log.error("Download error: %s", e)
        return {"error": str(e)}


# ------------------------------------------------------------------
# Available tickers
# ------------------------------------------------------------------


@router.get("/api/greeks/tickers")
async def get_tickers():
    """List available tickers with cached CBOE data."""
    gf = _get_integrator()
    if gf is None:
        return {"available_tickers": ["SPX", "NDX", "RUT"]}

    try:
        tickers = gf.get_available_tickers()
        return {"available_tickers": tickers}
    except Exception as e:
        log.error("Tickers error: %s", e)
        return {"error": str(e), "available_tickers": ["SPX", "NDX", "RUT"]}
