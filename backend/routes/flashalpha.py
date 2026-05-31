"""API routes for FlashAlpha integration."""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flashalpha", tags=["flashalpha"])


def get_client():
    from flashalpha_client import FlashAlphaClient
    return FlashAlphaClient()


@router.get("/exposure/{symbol}")
async def get_exposure(symbol: str):
    """Get full exposure data (GEX, DEX, VEX, CHEX)."""
    client = get_client()
    data = await client.get_exposure_summary(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/gex/{symbol}")
async def get_gex(symbol: str):
    """Get Gamma Exposure data."""
    client = get_client()
    data = await client.get_gex(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/flow/{symbol}")
async def get_flow(symbol: str):
    """Get options flow data."""
    client = get_client()
    data = await client.get_flow_summary(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/flow-live/{symbol}")
async def get_flow_live(symbol: str):
    """Get live options flow."""
    client = get_client()
    data = await client.get_flow_live(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/flow-blocks/{symbol}")
async def get_flow_blocks(symbol: str):
    """Get flow blocks (large trades)."""
    client = get_client()
    data = await client.get_options_flow_blocks(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/earnings-vrp/{symbol}")
async def get_earnings_vrp(symbol: str):
    """Get Variance Risk Premium for earnings."""
    client = get_client()
    data = await client.get_earnings_vrp(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/max-pain/{symbol}")
async def get_max_pain(symbol: str):
    """Get max pain data."""
    client = get_client()
    data = await client.get_max_pain(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/volatility/{symbol}")
async def get_volatility(symbol: str):
    """Get volatility data."""
    client = get_client()
    data = await client.get_volatility(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/zero-dte/{symbol}")
async def get_zero_dte(symbol: str):
    """Get 0DTE exposure data."""
    client = get_client()
    data = await client.get_zero_dte(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/narrative/{symbol}")
async def get_narrative(symbol: str):
    """Get AI-generated exposure narrative."""
    client = get_client()
    data = await client.get_exposure_narrative(symbol.upper())
    return {"symbol": symbol.upper(), "data": data}


@router.get("/dashboard/{symbol}")
async def get_dashboard(symbol: str):
    """Get full dashboard (exposure + flow + earnings + max pain + volatility)."""
    client = get_client()
    data = await client.get_full_dashboard(symbol.upper())
    return data


@router.get("/status")
async def get_status():
    """Get FlashAlpha connection status."""
    from flashalpha_client import FLASHALPHA_API_KEY
    return {
        "configured": bool(FLASHALPHA_API_KEY),
        "key_set": bool(FLASHALPHA_API_KEY),
        "base_url": "https://lab.flashalpha.com",
        "endpoints": 81,
        "categories": [
            "exposure (GEX, DEX, VEX, CHEX, levels, narrative, zero-dte)",
            "flow (live, blocks, sweeps, outliers, leaderboards, pin risk)",
            "earnings (VRP, expected move, IV crush, dealer positioning, strategies)",
            "screener (13 endpoints)",
            "historical (EOD options, OI, quotes)",
            "pricing (Greeks, IV, Kelly)",
        ],
    }
