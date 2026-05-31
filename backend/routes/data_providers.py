"""API routes for free data providers."""

import logging
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/status")
async def get_data_status():
    """Get status of all data providers."""
    try:
        from data_providers import ALPHA_VANTAGE_KEY, FINNHUB_API_KEY, POLYGON_API_KEY, DataAggregator
        agg = DataAggregator()
        status = agg.get_status()
        return {
            "providers": status,
            "env_vars_set": {
                "FINNHUB_API_KEY": bool(FINNHUB_API_KEY),
                "ALPHA_VANTAGE_KEY": bool(ALPHA_VANTAGE_KEY),
                "POLYGON_API_KEY": bool(POLYGON_API_KEY),
            }
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/health")
async def get_data_health():
    """Get detailed health metrics for all data providers including success rates and alerts."""
    try:
        from services.meta_observability import provider_monitor

        health = provider_monitor.get_health()

        # Update Prometheus gauges
        provider_monitor.update_prometheus()

        return health
    except Exception as e:
        return {"error": str(e)}


@router.get("/{ticker}")
async def get_ticker_data(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    taps: bool = True,
    mode: str = Query("day", pattern="^(day|swing|scalp)$"),
    dte: Optional[int] = Query(None, ge=0, le=30),
    scalp: bool = Query(False),
):
    """Get full heatmap data for a ticker (compatible with frontend data fetch)."""
    from server import build_heatmap
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await build_heatmap(t, expiries, taps, mode, dte, scalp)


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Get aggregated spot price from all available sources."""
    try:
        from data_providers import DataAggregator
        agg = DataAggregator()
        spot = await agg.get_spot_price(ticker.upper())
        if spot:
            return {"ticker": ticker.upper(), **spot}
        return {"ticker": ticker.upper(), "error": "No data available", "price": None}
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e), "price": None}


@router.get("/full/{ticker}")
async def get_full_data(
    ticker: str,
    include_news: bool = True,
    include_technicals: bool = False,
):
    """Get full aggregated data for a ticker (spot + news + earnings + technicals)."""
    try:
        from data_providers import DataAggregator
        agg = DataAggregator()
        result = await agg.get_full_quote(ticker.upper())

        if not include_news:
            result["news"] = []
        if not include_technicals:
            result["technicals"] = {}

        return result
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e)}


@router.get("/news/{ticker}")
async def get_news(ticker: str, count: int = Query(10, ge=1, le=50)):
    """Get news for a ticker from Finnhub."""
    try:
        from data_providers import FinnhubProvider
        provider = FinnhubProvider()
        news = await provider.get_news(ticker.upper(), count=count)
        return {"ticker": ticker.upper(), "news": news, "count": len(news)}
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e), "news": []}
