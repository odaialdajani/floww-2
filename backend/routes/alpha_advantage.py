"""
backend/routes/alpha_advantage.py

Alpha Advantage data proxy routes.
Exposes real-time and historical data from Alpha Vantage API.

Endpoints:
  GET  /api/alpha/quote/{ticker}           — Real-time quote
  GET  /api/alpha/options/{ticker}          — Options chain
  GET  /api/alpha/technical/{ticker}/{indicator} — Technical indicators
  GET  /api/alpha/forex/{from}/{to}         — Forex rates
  GET  /api/alpha/crypto/{symbol}           — Crypto prices
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import aiohttp
from fastapi import APIRouter, HTTPException, Query

from services.alpha_vantage_client import CircuitBreakerOpenError, circuit
from services.rate_limit_tracker import av_rate_tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alpha", tags=["alpha-vantage"])

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

# Alpha Vantage free tier requires apikey as a URL query parameter — header auth
# is not supported for most endpoints. The key is sourced from the ALPHA_VANTAGE_KEY
# environment variable and never accepted from or exposed to clients.
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")


def _safe_params(params: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of params with apikey redacted for safe logging."""
    redacted = dict(params)
    if "apikey" in redacted:
        redacted["apikey"] = "***REDACTED***"
    return redacted


async def _av_request(params: Dict[str, str]) -> Dict[str, Any]:
    """Make an Alpha Vantage API request with rate limiting awareness.

    NOTE: Alpha Vantage's free tier requires ?apikey=... in the query string.
    Header-based auth is not available for most endpoints, so we must send it
    as a query param. The key is loaded from ALPHA_VANTAGE_KEY env var and
    never logged in URL form.
    """
    params["apikey"] = ALPHA_VANTAGE_KEY
    av_rate_tracker.record_call()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ALPHA_VANTAGE_BASE, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.error(
                        "Alpha Vantage returned %s for params %s",
                        resp.status,
                        _safe_params(params),
                    )
                    raise HTTPException(status_code=resp.status, detail=f"Alpha Vantage returned {resp.status}")
                data = await resp.json()
                if "Error Message" in data:
                    raise HTTPException(status_code=400, detail=data["Error Message"])
                if "Note" in data:
                    # Rate limit hit
                    raise HTTPException(status_code=429, detail="Alpha Vantage rate limit reached. Try again in 60s.")
                return data
    except aiohttp.ClientError as e:
        logger.error("Alpha Vantage request failed for params %s: %s", _safe_params(params), e)
        raise HTTPException(status_code=502, detail=str(e))


async def _av_request_circuit(params: Dict[str, Any]) -> Dict[str, Any]:
    """Alpha Vantage request wrapper with circuit breaker protection.

    Wraps _av_request_circuit() with the circuit breaker. If the circuit is OPEN,
    returns a 503 response immediately instead of hitting the API.
    """
    try:
        return await circuit.call(_av_request, params)
    except CircuitBreakerOpenError as e:
        logger.warning("Circuit breaker OPEN for Alpha Vantage: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"Alpha Vantage circuit breaker is open. Service temporarily unavailable. {e}",
        )


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Get real-time quote for a ticker."""
    data = await _av_request_circuit({
        "function": "GLOBAL_QUOTE",
        "symbol": ticker.upper(),
    })
    quote = data.get("Global Quote", {})
    if not quote:
        raise HTTPException(status_code=404, detail=f"No quote found for {ticker}")
    return {
        "ticker": quote.get("01. symbol", ticker),
        "price": float(quote.get("05. price", 0)),
        "change": float(quote.get("09. change", 0)),
        "change_pct": quote.get("10. change percent", "0%"),
        "volume": int(quote.get("06. volume", 0)),
        "latest_trading_day": quote.get("07. latest trading day", ""),
    }


@router.get("/options/{ticker}")
async def get_options_chain(
    ticker: str,
    date: Optional[str] = Query(None, description="Expiration date YYYY-MM-DD"),
):
    """Get options chain for a ticker."""
    params = {
        "function": "OPTION_CHAIN",
        "symbol": ticker.upper(),
    }
    if date:
        params["date"] = date
    data = await _av_request_circuit(params)
    return data


@router.get("/technical/{ticker}/{indicator}")
async def get_technical_indicator(
    ticker: str,
    indicator: str,
    interval: str = Query("daily", pattern="^(daily|weekly|monthly|1min|5min|15min|30min|60min)$"),
    time_period: int = Query(14, ge=1, le=200),
    series_type: str = Query("close", pattern="^(open|high|low|close)$"),
):
    """Get technical indicator for a ticker.

    Supported indicators: SMA, EMA, RSI, MACD, BBANDS, STOCH, ADX, CCI, AROON, OBV, WILLR, MFI, TEMA, TRIMA, KAMA, MAMA, VWAP, HT_TRENDLINE, HT_SINE, HT_TRENDMODE, HT_DCPERIOD, HT_DCPHASE, HT_PHASOR
    """
    data = await _av_request_circuit({
        "function": indicator.upper(),
        "symbol": ticker.upper(),
        "interval": interval,
        "time_period": str(time_period),
        "series_type": series_type,
    })
    return data


@router.get("/forex/{from_currency}/{to_currency}")
async def get_forex_rate(
    from_currency: str,
    to_currency: str,
):
    """Get forex exchange rate."""
    data = await _av_request_circuit({
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
    })
    rate = data.get("Realtime Currency Exchange Rate", {})
    if not rate:
        raise HTTPException(status_code=404, detail="Forex rate not found")
    return {
        "from": rate.get("1. From_Currency Code", from_currency),
        "to": rate.get("2. To_Currency Code", to_currency),
        "rate": float(rate.get("5. Exchange Rate", 0)),
        "bid": float(rate.get("8. Bid Price", 0)),
        "ask": float(rate.get("9. Ask Price", 0)),
    }


@router.get("/crypto/{symbol}")
async def get_crypto_price(
    symbol: str,
    market: str = Query("USD"),
):
    """Get cryptocurrency price."""
    data = await _av_request_circuit({
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": symbol.upper(),
        "to_currency": market.upper(),
    })
    rate = data.get("Realtime Currency Exchange Rate", {})
    if not rate:
        raise HTTPException(status_code=404, detail=f"Crypto price not found for {symbol}")
    return {
        "symbol": rate.get("1. From_Currency Code", symbol),
        "market": rate.get("2. To_Currency Code", market),
        "price": float(rate.get("5. Exchange Rate", 0)),
    }


@router.get("/overview/{ticker}")
async def get_company_overview(ticker: str):
    """Get company overview/fundamentals."""
    data = await _av_request_circuit({
        "function": "OVERVIEW",
        "symbol": ticker.upper(),
    })
    if not data or "Symbol" not in data:
        raise HTTPException(status_code=404, detail=f"No overview found for {ticker}")
    return data


@router.get("/earnings/{ticker}")
async def get_earnings(ticker: str):
    """Get earnings data."""
    data = await _av_request_circuit({
        "function": "EARNINGS",
        "symbol": ticker.upper(),
    })
    return data


@router.get("/news")
async def get_news(
    tickers: Optional[str] = Query(None, description="Comma-separated tickers"),
    topics: Optional[str] = Query(None, description="Comma-separated topics"),
    limit: int = Query(20, ge=1, le=100),
):
    """Get market news and sentiment."""
    params = {
        "function": "NEWS_SENTIMENT",
        "limit": str(limit),
    }
    if tickers:
        params["tickers"] = tickers.upper()
    if topics:
        params["topics"] = topics.lower()
    data = await _av_request_circuit(params)
    return data


@router.get("/market-status")
async def get_market_status():
    """Get current market status (open/closed)."""
    data = await _av_request_circuit({
        "function": "MARKET_STATUS",
    })
    return data


@router.get("/top-gainers-losers")
async def get_top_gainers_losers():
    """Get top gainers, losers, and most active stocks."""
    data = await _av_request_circuit({
        "function": "TOP_GAINERS_LOSERS",
    })
    return data


@router.get("/historical/{ticker}")
async def get_historical(
    ticker: str,
    interval: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    output_size: str = Query("compact", pattern="^(compact|full)$"),
):
    """Get historical OHLCV data."""
    func_map = {
        "daily": "TIME_SERIES_DAILY",
        "weekly": "TIME_SERIES_WEEKLY",
        "monthly": "TIME_SERIES_MONTHLY",
    }
    data = await _av_request_circuit({
        "function": func_map[interval],
        "symbol": ticker.upper(),
        "outputsize": output_size,
    })
    return data


@router.get("/intraday/{ticker}")
async def get_intraday(
    ticker: str,
    interval: str = Query("5min", pattern="^(1min|5min|15min|30min|60min)$"),
    output_size: str = Query("compact", pattern="^(compact|full)$"),
):
    """Get intraday OHLCV data."""
    data = await _av_request_circuit({
        "function": "TIME_SERIES_INTRADAY",
        "symbol": ticker.upper(),
        "interval": interval,
        "outputsize": output_size,
    })
    return data
