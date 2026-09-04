"""
backend/routes/public_api.py

Public API (public.com) data endpoints.

Routes:
    GET /api/public/chain/{ticker}?expiration=YYYY-MM-DD&expirations=N
        Options chain from Public API (primary source)

    GET /api/public/quotes/{ticker}
        Live quote from Public API (spot price + bid/ask + sizes)

    GET /api/public/bars/{ticker}?timeframe=1Day&limit=100
        OHLCV price bars from Public API (stocks data feed)

    GET /api/public/portfolio
        Account portfolio from Public API (paper trading only)

Mounted in server.py: app.include_router(public_api_router, prefix="/api/public")

DATA ONLY — this router exposes quotes, bars and chains. It never reaches
PublicBroker's order-placement methods, which target the LIVE trading gateway.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from services.public_api_adapter import (
    PUBLIC_BARS_TIMEFRAMES,
    _get_broker,
    _normalize_symbol,
    fetch_bars_from_public_api,
    fetch_chain_from_public_api,
    fetch_quotes_from_public_api,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public_api"])

_TIMEFRAME_HELP = "Bar timeframe. One of: " + ", ".join(PUBLIC_BARS_TIMEFRAMES)
_TIMEFRAMES_LOWER = frozenset(tf.lower() for tf in PUBLIC_BARS_TIMEFRAMES)


def _jsonable(value: Any) -> Any:
    """Convert PublicBroker dataclasses recursively for explicit API output."""
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


@router.get("/chain/{ticker}")
async def get_public_chain(
    ticker: str,
    expiration: str | None = Query(default=None, description="Specific expiration YYYY-MM-DD. If omitted, returns first N expirations."),
    expirations: int = Query(default=4, ge=1, le=12, description="Number of expirations to fetch (when expiration not specified)."),
):
    """
    Return options chain data from Public API for a given ticker.

    Uses PUBLIC_API_KEY to authenticate against the Public.com Trading API.
    Returns the same shape as /api/chain but with data_source="public_api".
    """
    result = await fetch_chain_from_public_api(ticker.upper(), max_expiries=expirations)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail=f"Public API unavailable for {ticker} — key may be missing or API call failed",
        )

    # If specific expiration requested, filter to that expiry
    if expiration:
        result["contracts"] = [c for c in result["contracts"] if c["expiry"] == expiration]
        result["expiries"] = [expiration] if result["contracts"] else []

    return {
        "ok": True,
        "ticker": ticker.upper(),
        "spot": result.get("spot", 0),
        "expiries": result.get("expiries", []),
        "n_contracts": len(result.get("contracts", [])),
        "data_source": result.get("data_source", "public_api"),
        "contracts": result.get("contracts", []),
    }


@router.get("/quotes/{ticker}")
async def get_public_quotes(ticker: str):
    """
    Return live quote data from Public API for a given ticker.

    ``ok`` / ``ticker`` / ``spot`` / ``data_source`` keep their original names and
    meanings (frontend/src/lib/publicApi.js reads them); the top-of-book fields
    are additive.
    """
    quotes = await fetch_quotes_from_public_api(ticker)
    quote = (quotes or {}).get(_normalize_symbol(ticker))
    if quote is None and quotes and len(quotes) == 1:
        quote = next(iter(quotes.values()))
    if quote is None:
        raise HTTPException(
            status_code=502,
            detail=f"Public API unavailable for {ticker}",
        )
    return {
        "ok": True,
        "ticker": ticker.upper(),
        "spot": quote.get("spot"),
        "last": quote.get("last"),
        "bid": quote.get("bid"),
        "ask": quote.get("ask"),
        "bid_size": quote.get("bid_size"),
        "ask_size": quote.get("ask_size"),
        "volume": quote.get("volume"),
        "previous_close": quote.get("previous_close"),
        "change": quote.get("change"),
        "percent_change": quote.get("percent_change"),
        "timestamp": quote.get("timestamp"),
        "data_source": "public_api",
    }


@router.get("/bars/{ticker}")
async def get_public_bars(
    ticker: str,
    timeframe: str = Query(default="1Day", description=_TIMEFRAME_HELP),
    limit: int = Query(default=100, ge=1, le=5000, description="Maximum number of most-recent bars to return."),
    sessions: str = Query(
        default="regular",
        pattern="^(regular|all)$",
        description=(
            "'regular' (default) returns regular-session bars ONLY. 'all' also "
            "returns pre-market and after-hours bars. Every row carries a "
            "'session' field ('regular'|'pre'|'after')."
        ),
    ),
):
    """
    Return OHLCV price bars from Public API for a given ticker.

    Rows use floww's canonical bar shape (date/open/high/low/close/volume) plus a
    'session' label — the same shape routes/backtest.py and the underlying_bars
    store already read.

    Extended-hours bars are EXCLUDED by default. Mixing them into the same series
    would let an intraday request near the close return extended-hours prints that
    look identical to regular-session bars.
    """
    if timeframe.strip().lower() not in _TIMEFRAMES_LOWER:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported timeframe {timeframe!r} — {_TIMEFRAME_HELP}",
        )

    bars = await fetch_bars_from_public_api(
        ticker.upper(), timeframe=timeframe, limit=limit, sessions=sessions
    )
    if bars is None:
        raise HTTPException(
            status_code=502,
            detail=f"Public API unavailable for {ticker} — key may be missing or API call failed",
        )

    return {
        "ok": True,
        "ticker": ticker.upper(),
        "timeframe": timeframe,
        "sessions": sessions,
        "count": len(bars),
        "data_source": "public_api",
        "bars": bars,
    }


@router.get("/portfolio")
async def get_public_portfolio():
    """Return the authenticated Public.com paper-trading portfolio."""
    broker = await _get_broker()
    if broker is None:
        raise HTTPException(
            status_code=502,
            detail="Public API unavailable — key may be missing or API call failed",
        )

    account = broker.get_trading_account()
    if account is None:
        raise HTTPException(status_code=502, detail="No trading account available")

    try:
        portfolio = await broker.get_portfolio(account.account_id)
    except Exception as exc:
        log.warning("Public API portfolio failed: %s", exc)
        raise HTTPException(status_code=502, detail="Public API portfolio unavailable") from exc

    return {
        "ok": True,
        "account_id": account.account_id,
        "portfolio": _jsonable(portfolio),
        "data_source": "public_api",
    }
