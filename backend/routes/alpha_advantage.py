"""
backend/routes/alpha_advantage.py

Alpha Vantage proxy — RETIRED 2026-09-03 (public-api-only policy).

Every route now answers from the Public.com API (primary source) or returns
HTTP 410 Gone with a `replacement` pointer to the /api/public/* equivalent:

  /api/alpha/quote/{ticker}      -> GET /api/public/quotes/{ticker}   (live)
  /api/alpha/options/{ticker}    -> GET /api/public/chain/{ticker}    (live)
  /api/alpha/technical/...       -> GET /api/public/technical/...    (live)
  /api/alpha/historical/{ticker} -> GET /api/public/history/{ticker}  (live)
  /api/alpha/intraday/{ticker}   -> GET /api/public/bars/{ticker}     (live)
  everything else                -> 410 + replacement hint

No request ever touches the retired vendor host.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alpha", tags=["alpha-vantage"])

_RETIRED = (
    "Alpha Vantage retired 2026-09-03 — floww is public-API-only. "
    "Use the replacement /api/public/* endpoint."
)


def _gone(replacement: str) -> JSONResponse:
    """HTTP 410 Gone with a machine-readable replacement pointer."""
    return JSONResponse(
        status_code=410,
        content={"error": "alpha_vantage_retired", "message": _RETIRED, "replacement": replacement},
    )


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Retired shim — served live from Public API quotes."""
    from services.public_api_adapter import fetch_spot_from_public_api
    spot = await fetch_spot_from_public_api(ticker)
    if spot is None:
        raise HTTPException(status_code=502, detail=f"Public API unavailable for {ticker}")
    return {
        "ticker": ticker.upper(),
        "price": spot,
        "change": 0,
        "change_pct": "0%",
        "volume": 0,
        "latest_trading_day": "",
        "data_source": "public_api",
        "note": "served by Public API (alpha retired 2026-09-03)",
    }


@router.get("/options/{ticker}")
async def get_options_chain(
    ticker: str,
    date: str | None = Query(None, description="Expiration date YYYY-MM-DD"),
):
    """Retired shim — served live from Public API chain."""
    from services.public_api_adapter import fetch_chain_from_public_api
    result = await fetch_chain_from_public_api(ticker.upper(), max_expiries=4)
    if result is None:
        raise HTTPException(status_code=502, detail=f"Public API unavailable for {ticker}")
    contracts = result.get("contracts", [])
    if date:
        contracts = [c for c in contracts if c.get("expiry") == date]
    return {
        "ticker": ticker.upper(),
        "spot": result.get("spot", 0),
        "expiries": result.get("expiries", []),
        "contracts": contracts,
        "data_source": "public_api",
        "stale": result.get("stale", False),
        "note": "served by Public API (alpha retired 2026-09-03)",
    }


@router.get("/technical/{ticker}/{indicator}")
async def get_technical_indicator(
    ticker: str,
    indicator: str,
    interval: str = Query("daily", pattern="^(daily|weekly|monthly|1min|5min|15min|30min|60min)$"),
    time_period: int = Query(14, ge=1, le=200),
    series_type: str = Query("close", pattern="^(open|high|low|close)$"),
):
    """Retired shim — technicals computed from Public API bars.

    Supported indicators: SMA, EMA, RSI, MACD, BBANDS, STOCH, ADX, CCI, AROON, OBV, WILLR, MFI, TEMA, TRIMA, KAMA, MAMA, VWAP, HT_TRENDLINE, HT_SINE, HT_TRENDMODE, HT_DCPERIOD, HT_DCPHASE, HT_PHASOR
    """
    from services.public_api_adapter import compute_technical_from_bars, fetch_bars_from_public_api
    bars = await fetch_bars_from_public_api(ticker.upper(), interval=interval)
    if not bars:
        raise HTTPException(status_code=502, detail=f"Public API bars unavailable for {ticker}")
    return compute_technical_from_bars(ticker.upper(), indicator.upper(), bars, time_period)


@router.get("/forex/{from_currency}/{to_currency}")
async def get_forex_rate(
    from_currency: str,
    to_currency: str,
):
    """Retired — forex is quoted via Public API instruments; no AV call."""
    return _gone(f"/api/public/quotes/{from_currency.upper()}{to_currency.upper()}")


@router.get("/crypto/{symbol}")
async def get_crypto_price(
    symbol: str,
    market: str = Query("USD"),
):
    """Retired shim — crypto spot via Public API quotes."""
    from services.public_api_adapter import fetch_spot_from_public_api
    pair = f"{symbol.upper()}-{market.upper()}"
    spot = await fetch_spot_from_public_api(pair)
    if spot is None:
        return _gone(f"/api/public/quotes/{symbol.upper()}")
    return {"symbol": symbol.upper(), "market": market.upper(), "price": spot, "data_source": "public_api"}


@router.get("/overview/{ticker}")
async def get_company_overview(ticker: str):
    """Retired — fundamentals are not a Public API surface; see replacement."""
    return _gone(f"/api/public/quotes/{ticker.upper()}")


@router.get("/earnings/{ticker}")
async def get_earnings(ticker: str):
    """Retired — earnings calendar lives on Finnhub; no AV call."""
    return _gone("/api/data/full/{ticker}")


@router.get("/news")
async def get_news(
    tickers: str | None = Query(None, description="Comma-separated tickers"),
    topics: str | None = Query(None, description="Comma-separated topics"),
    limit: int = Query(20, ge=1, le=100),
):
    """Retired — news lives on Finnhub; no AV call."""
    return _gone("/api/data/news/{ticker}")


@router.get("/market-status")
async def get_market_status():
    """Retired — no AV call."""
    return _gone("/api/health")


@router.get("/top-gainers-losers")
async def get_top_gainers_losers():
    """Retired — no AV call."""
    return _gone("/api/public/quotes/SPY")


@router.get("/historical/{ticker}")
async def get_historical(
    ticker: str,
    interval: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    output_size: str = Query("compact", pattern="^(compact|full)$"),
):
    """Retired shim — OHLCV history from Public API bars."""
    from services.public_api_adapter import fetch_history_from_public_api
    bars = await fetch_history_from_public_api(ticker.upper(), interval=interval)
    if bars is None:
        raise HTTPException(status_code=502, detail=f"Public API history unavailable for {ticker}")
    return bars


@router.get("/intraday/{ticker}")
async def get_intraday(
    ticker: str,
    interval: str = Query("5min", pattern="^(1min|5min|15min|30min|60min)$"),
    output_size: str = Query("compact", pattern="^(compact|full)$"),
):
    """Retired shim — intraday bars from Public API."""
    from services.public_api_adapter import fetch_bars_from_public_api
    bars = await fetch_bars_from_public_api(ticker.upper(), interval=interval)
    if bars is None:
        raise HTTPException(status_code=502, detail=f"Public API bars unavailable for {ticker}")
    return {"ticker": ticker.upper(), "interval": interval, "bars": bars, "data_source": "public_api"}
