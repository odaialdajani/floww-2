"""
backend/services/finnhub_api.py

Thin REST-shim layer over finnhub_client.

Each function takes plain query-param dicts (as FastAPI would receive from
?key=value query strings) and returns a plain dict — the caller (FastAPI
server.py, or a test) wraps it in the appropriate response type.

Mount pattern (when server.py exists):
    from fastapi import APIRouter
    from services.finnhub_api import router as finnhub_router
    app.include_router(finnhub_router, prefix="/api/finnhub")

This module also works standalone for testing without a running server.
"""

from __future__ import annotations

import logging
from typing import Any

from services.finnhub_client import FinnhubClient

log = logging.getLogger(__name__)

# Module-level client singleton — keyed off FINNHUB_API_KEY env var.
_client: FinnhubClient | None = None


def _get_client() -> FinnhubClient:
    global _client
    if _client is None:
        _client = FinnhubClient()
    return _client


# ------------------------------------------------------------------
# Quote
# ------------------------------------------------------------------

def quote(ticker: str) -> dict[str, Any]:
    """GET /api/finnhub/quote?ticker=SPY"""
    c = _get_client()
    q = c.quote(ticker)
    if q is None:
        return {"error": "no_data", "ticker": ticker}
    return {"ticker": ticker, "quote": q}


def quote_bulk(tickers: str) -> dict[str, Any]:
    """GET /api/finnhub/quote-bulk?tickers=SPY,QQQ,IWM

    tickers: comma-separated string.
    """
    c = _get_client()
    sym_list = [s.strip() for s in tickers.split(",") if s.strip()]
    if not sym_list:
        return {"error": "empty_tickers"}
    results = c.quote_bulk(sym_list)
    failed = [s for s, q in results.items() if q is None]
    ok = {s: q for s, q in results.items() if q is not None}
    return {
        "tickers_requested": sym_list,
        "quotes": ok,
        "failed": failed,
    }


# ------------------------------------------------------------------
# Options
# ------------------------------------------------------------------

def options_chain(ticker: str) -> dict[str, Any]:
    """GET /api/finnhub/options-chain?ticker=SPY"""
    c = _get_client()
    chain = c.options_chain(ticker)
    if chain is None:
        return {"error": "no_data", "ticker": ticker}
    return {"ticker": ticker, "options_chain": chain}


def options_chain_for_expiry(
    ticker: str, expiry: str
) -> dict[str, Any]:
    """GET /api/finnhub/options-chain/expiry?ticker=SPY&expiry=2026-09-18"""
    c = _get_client()
    chain = c.options_chain_for_expiry(ticker, expiry)
    if chain is None:
        return {"error": "no_data", "ticker": ticker, "expiry": expiry}
    return {"ticker": ticker, "expiry": expiry, "options": chain}


# ------------------------------------------------------------------
# Company / Fundamentals
# ------------------------------------------------------------------

def company_profile(ticker: str) -> dict[str, Any]:
    """GET /api/finnhub/company-profile?ticker=SPY"""
    c = _get_client()
    profile = c.company_profile(ticker)
    if profile is None:
        return {"error": "no_data", "ticker": ticker}
    return {"ticker": ticker, "profile": profile}


def fundamentals(ticker: str) -> dict[str, Any]:
    """GET /api/finnhub/fundamentals?ticker=SPY"""
    c = _get_client()
    fund = c.fundamentals(ticker)
    if fund is None:
        return {"error": "no_data", "ticker": ticker}
    return {"ticker": ticker, "fundamentals": fund}


# ------------------------------------------------------------------
# News
# ------------------------------------------------------------------

def news_for_symbol(
    ticker: str,
    _from: str | None = None,
    to: str | None = None,
) -> dict[str, Any]:
    """GET /api/finnhub/news?ticker=SPY[&from=2026-07-01][&to=2026-08-01]"""
    c = _get_client()
    news = c.news_for_symbol(ticker, _from=_from, to=to)
    if news is None:
        return {"error": "no_data", "ticker": ticker}
    return {"ticker": ticker, "news": news}


def top_news(category: str = "general") -> dict[str, Any]:
    """GET /api/finnhub/top-news?category=general"""
    c = _get_client()
    news = c.top_news(category)
    if news is None:
        return {"error": "no_data", "category": category}
    return {"category": category, "news": news}


# ------------------------------------------------------------------
# Technical indicators
# ------------------------------------------------------------------

def technicals(
    ticker: str,
    timeframe: str = "D",
    tech: str = "rsi",
    _from: int | None = None,
    to: int | None = None,
) -> dict[str, Any]:
    """GET /api/finnhub/technicals?ticker=SPY[&timeframe=D][&tech=rsi]"""
    c = _get_client()
    vals = c.technicals(ticker, timeframe, tech, _from=_from, to=to)
    if vals is None:
        return {"error": "no_data", "ticker": ticker, "tech": tech}
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "tech": tech,
        "values": vals,
    }


# ------------------------------------------------------------------
# List
# ------------------------------------------------------------------

def all_symbols() -> dict[str, Any]:
    """GET /api/finnhub/symbols"""
    c = _get_client()
    syms = c.all_symbols()
    if syms is None:
        return {"error": "no_data"}
    return {"symbols": syms}
