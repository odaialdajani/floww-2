"""
backend/services/finnhub_client.py

Public API trading layer — Finnhub SDK wrapper.

Provides:
  - Real-time quote (latest price, bid/ask, volume, change)
  - Options chain (strikes, expiration, IV, OI, volume, Greeks)
  - Company profile / fundamentals
  - News for a ticker / top market news
  - Technical indicators (SMA, EMA, RSI, etc.)

Env wiring:
  FINNHUB_API_KEY  — Finnhub API key (from .env or environment)

Usage:
    from services.finnhub_client import FinnhubClient
    c = FinnhubClient()
    q = c.quote("SPY")
    chain = c.options_chain("SPY")
    profile = c.company_profile("SPY")
"""

from __future__ import annotations

import logging
import os
from typing import Any

import finnhub

log = logging.getLogger(__name__)

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")


class FinnhubClient:
    """Thin wrapper around the Finnhub REST API.

    All methods return dicts (parsed JSON) or None on failure.
    """

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or FINNHUB_API_KEY
        if not key:
            log.warning("Finnhub API key not set — methods will return None")
        self._client = finnhub.Client(api_key=key) if key else None

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    def quote(self, symbol: str) -> dict[str, Any] | None:
        """Latest quote for a symbol.

        Returns dict with keys: c (current), o (open), h (high), l (low),
        pc (previous close), d (change), dp (change %), va (volume),
        hv (high over 52w), lv (low over 52w), delay, initials, etc.
        """
        if not self._client:
            return None
        try:
            return self._client.quote(symbol)
        except Exception as e:
            log.error("Finnhub quote failed for %s: %s", symbol, e)
            return None

    # ------------------------------------------------------------------
    # Options chain
    # ------------------------------------------------------------------

    def options_chain(self, symbol: str) -> dict[str, Any] | None:
        """Options chain for a symbol.

        Returns dict with 'expirations' list; each expiry has 'strikes'
        list with strike-level data (iv, oi, volume, type, etc.).
        """
        if not self._client:
            return None
        try:
            return self._client.options_chain(symbol)
        except Exception as e:
            log.error("Finnhub options_chain failed for %s: %s", symbol, e)
            return None

    def options_chain_for_expiry(
        self, symbol: str, expiry: str
    ) -> dict[str, Any] | None:
        """Options chain filtered to a specific expiry date (YYYY-MM-DD).

        Wraps options_chain and filters to the matching expiry.
        """
        chain = self.options_chain(symbol)
        if not chain:
            return None
        for exp in chain.get("expirations", []):
            if exp.get("expiration") == expiry:
                return exp
        return None

    # ------------------------------------------------------------------
    # Company profile
    # ------------------------------------------------------------------

    def company_profile(self, symbol: str) -> dict[str, Any] | None:
        """Company profile: name, ticker, exchange, industry, sector,
        description, logo, website, employees, etc."""
        if not self._client:
            return None
        try:
            return self._client.company_profile2(symbol=symbol)
        except Exception as e:
            log.error("Finnhub company_profile failed for %s: %s", symbol, e)
            return None

    # ------------------------------------------------------------------
    # Fundamentals
    # ------------------------------------------------------------------

    def fundamentals(self, symbol: str) -> dict[str, Any] | None:
        """Fundamental ratios for a symbol.

        Returns dict of ratio categories (e.g. 'rating', 'financials',
        ' valuation', etc.) with time-series entries.
        """
        if not self._client:
            return None
        try:
            return self._client.fundamentals(symbol)
        except Exception as e:
            log.error("Finnhub fundamentals failed for %s: %s", symbol, e)
            return None

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    def news_for_symbol(
        self, symbol: str, _from: str | None = None, to: str | None = None
    ) -> list[dict[str, Any]] | None:
        """News articles mentioning a symbol.

        _from / to: ISO date strings (YYYY-MM-DD). If omitted, defaults
        to the last 30 days.
        """
        if not self._client:
            return None
        try:
            return self._client.company_news(
                symbol, _from=_from, to=to
            )
        except Exception as e:
            log.error("Finnhub news failed for %s: %s", symbol, e)
            return None

    def top_news(self, category: str = "general") -> list[dict[str, Any]] | None:
        """Top market news for a category.

        Categories: 'general', 'crypto', 'forex', 'merger', 'economy'.
        """
        if not self._client:
            return None
        try:
            return self._client.top_news(category)
        except Exception as e:
            log.error("Finnhub top_news failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Technical indicators
    # ------------------------------------------------------------------

    def technicals(
        self,
        symbol: str,
        timeframe: str = "D",
        tech: str = "rsi",
        _from: int | None = None,
        to: int | None = None,
    ) -> list[dict[str, Any]] | None:
        """Technical indicator values for a symbol.

        timeframe: 'D' (daily), 'W' (weekly), 'M' (monthly), 'm' (min),
                   'H' (hour).
        tech: one of 'sma', 'ema', 'wma', 'bbi', 'rsi', ' MACD', etc.
        _from / to: UNIX timestamps. If omitted, defaults to recent range.
        """
        if not self._client:
            return None
        try:
            return self._client.technical_indicator(
                symbol, timeframe, tech, _from=_from, to=to
            )
        except Exception as e:
            log.error(
                "Finnhub technicals failed for %s (%s): %s",
                symbol, tech, e,
            )
            return None

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    def quote_bulk(self, symbols: list[str]) -> dict[str, dict[str, Any] | None]:
        """Fetch quotes for multiple symbols.

        Returns dict mapping symbol -> quote dict or None.
        """
        results: dict[str, dict[str, Any] | None] = {}
        for sym in symbols:
            results[sym] = self.quote(sym)
        return results

    def all_symbols(self) -> list[dict[str, Any]] | None:
        """List of all symbols available via Finnhub."""
        if not self._client:
            return None
        try:
            return self._client.symbol_list()
        except Exception as e:
            log.error("Finnhub symbol_list failed: %s", e)
            return None
