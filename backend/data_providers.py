"""
Free Data Source Integrations for Confluence Decoder

PUBLIC-API-ONLY POLICY (2026-09-03, per architect directive):
- PRIMARY: Public.com API via services/public_api_adapter.py
  (chains, spot quotes, bars/history, portfolio, orders)
- Emergency fallback only: Finnhub/Polygon quotes, yfinance chains
  (kept for offline resilience; see ADR-0002 data source policy)
- REMOVED from production path: Schwab (no account), Alpha Vantage
  (retired). AlphaVantageProvider below is a disabled stub kept only so
  legacy imports don't break — it never makes network calls and always
  reports enabled=False.

Falls back gracefully when rate limits hit.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider call tracking — success/failure recording
# ---------------------------------------------------------------------------
def _record_provider_call(provider: str, success: bool):
    """Record a provider call result for monitoring. Safe to call from any context."""
    try:
        from services.meta_observability import provider_monitor
        provider_monitor.record(provider, success)
    except Exception:
        pass  # monitoring must never break data fetching

    try:
        from services.observability import provider_calls_total
        status = "success" if success else "failure"
        provider_calls_total.labels(provider=provider, status=status).inc()
    except Exception:
        pass


# API Keys from environment
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")


class RateLimiter:
    """Simple rate limiter for API calls with async lock."""
    def __init__(self, calls_per_minute: int):
        self.interval = 60.0 / calls_per_minute
        self.last_call = 0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            self.last_call = time.time()


class FreeDataProvider:
    """Base class for free data providers."""

    def __init__(self, name: str, rate_limit: int = 60):
        self.name = name
        self.rate_limiter = RateLimiter(rate_limit)
        self.enabled = False

    async def _get(self, url: str, params: dict = None, headers: dict = None) -> dict | None:
        await self.rate_limiter.wait()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params or {}, headers=headers or {},
                                       timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        _record_provider_call(self.name, True)
                        return await resp.json()
                    elif resp.status == 429:
                        logger.warning(f"{self.name}: Rate limited")
                        _record_provider_call(self.name, False)
                        try:
                            from services.observability import provider_calls_total
                            provider_calls_total.labels(provider=self.name, status="rate_limited").inc()
                        except Exception:
                            pass
                        return None
                    else:
                        logger.warning(f"{self.name}: HTTP {resp.status}")
                        _record_provider_call(self.name, False)
                        return None
        except Exception as e:
            logger.warning(f"{self.name}: {e}")
            _record_provider_call(self.name, False)
            return None


class FinnhubProvider(FreeDataProvider):
    """Finnhub free tier: 60 calls/min."""

    def __init__(self):
        super().__init__("Finnhub", rate_limit=60)
        self.enabled = bool(FINNHUB_API_KEY)
        self.base = "https://finnhub.io/api/v1"
        self._headers = {"X-Finnhub-Token": FINNHUB_API_KEY} if FINNHUB_API_KEY else {}

    async def _finnhub_get(self, path: str, params: dict = None) -> dict | None:
        """Make a Finnhub API call with token in header."""
        return await self._get(f"{self.base}{path}", params=params, headers=self._headers)

    async def get_quote(self, ticker: str) -> dict | None:
        """Get real-time quote."""
        if not self.enabled:
            return None
        data = await self._finnhub_get("/quote", {"symbol": ticker})
        if data and data.get("c", 0) > 0:
            prev_close = data.get("pc", 0) or 0
            change = data["c"] - prev_close
            change_pct = round(change / prev_close * 100, 2) if prev_close != 0 else 0
            return {
                "price": data["c"],
                "open": data.get("o", 0),
                "high": data.get("h", 0),
                "low": data.get("l", 0),
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct,
                "source": "finnhub",
            }
        return None

    async def get_news(self, ticker: str | None = None, count: int = 10) -> list[dict]:
        """Get market news or company news."""
        if not self.enabled:
            return []

        if ticker:
            data = await self._finnhub_get("/company-news", {
                "symbol": ticker,
                "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "to": datetime.now().strftime("%Y-%m-%d"),
            })
        else:
            data = await self._finnhub_get("/news", {"category": "general"})

        if data and isinstance(data, list):
            return [{
                "headline": item.get("headline", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "timestamp": datetime.fromtimestamp(item.get("datetime", 0)).isoformat() if item.get("datetime") else "",
                "summary": item.get("summary", "")[:200],
                "ticker": ticker or "",
            } for item in data[:count]]
        return []

    async def get_earnings(self, ticker: str) -> list[dict]:
        """Get earnings calendar."""
        if not self.enabled:
            return []
        data = await self._finnhub_get("/calendar/earnings", {"symbol": ticker})
        if data and isinstance(data, list):
            return [{
                "date": item.get("date", ""),
                "eps_estimate": item.get("epsEstimate"),
                "revenue_estimate": item.get("revenueEstimate"),
                "hour": item.get("hour", ""),
            } for item in data[:4]]
        return []

    async def get_recommendation(self, ticker: str) -> dict | None:
        """Get analyst recommendations."""
        if not self.enabled:
            return None
        data = await self._finnhub_get("/stock/recommendation", {"symbol": ticker})
        if data and isinstance(data, list) and len(data) > 0:
            latest = data[0]
            return {
                "strong_buy": latest.get("strongBuy", 0),
                "buy": latest.get("buy", 0),
                "hold": latest.get("hold", 0),
                "sell": latest.get("sell", 0),
                "strong_sell": latest.get("strongSell", 0),
                "period": latest.get("period", ""),
                "source": "finnhub",
            }
        return None

    async def get_options_flow(self, ticker: str) -> dict | None:
        """Get options flow data (if available on free tier)."""
        if not self.enabled:
            return None
        data = await self._finnhub_get("/stock/option-chain", {"symbol": ticker})
        if data and data.get("data"):
            return {
                "expirations": [d.get("expirationDate") for d in data["data"][:4]],
                "source": "finnhub",
            }
        return None


class PolygonProvider(FreeDataProvider):
    """Polygon.io free tier: 5 calls/min."""

    def __init__(self):
        super().__init__("Polygon", rate_limit=5)
        self.enabled = bool(POLYGON_API_KEY)
        self.base = "https://api.polygon.io"
        self._headers = {"Authorization": f"Bearer {POLYGON_API_KEY}"} if POLYGON_API_KEY else {}

    async def get_ticker_details(self, ticker: str) -> dict | None:
        """Get ticker details."""
        if not self.enabled:
            return None
        data = await self._get(f"{self.base}/v3/reference/tickers/{ticker}", headers=self._headers)
        if data and data.get("results"):
            r = data["results"]
            return {
                "name": r.get("name", ""),
                "market": r.get("market", ""),
                "locale": r.get("locale", ""),
                "active": r.get("active", True),
                "source": "polygon",
            }
        return None

    async def get_options_contracts(self, ticker: str, limit: int = 20) -> list[dict]:
        """Get options contracts for a ticker."""
        if not self.enabled:
            return []
        data = await self._get(f"{self.base}/v3/reference/options/contracts", params={"underlying_ticker": ticker, "limit": limit}, headers=self._headers)
        if data and data.get("results"):
            return [{
                "ticker": c.get("ticker", ""),
                "strike": c.get("strike_price", 0),
                "expiry": c.get("expiration_date", ""),
                "type": c.get("contract_type", ""),
                "exercise": c.get("exercise_style", ""),
            } for c in data["results"]]
        return []

    async def get_last_trade(self, ticker: str) -> dict | None:
        """Get last trade."""
        if not self.enabled:
            return None
        data = await self._get(f"{self.base}/v2/last/trade/{ticker}", headers=self._headers)
        if data and data.get("results"):
            r = data["results"]
            return {
                "price": r.get("p", 0),
                "size": r.get("s", 0),
                "timestamp": r.get("t", 0),
                "source": "polygon",
            }
        return None


class DataAggregator:
    """
    Aggregates data from all free providers with fallback.
    Priority: Public API -> Finnhub -> Polygon -> yfinance
    (Alpha Vantage retired 2026-09-03 — stub kept for import compat only.)
    """

    def __init__(self):
        self.finnhub = FinnhubProvider()
        self.polygon = PolygonProvider()
        self.alphavantage = AlphaVantageProvider()

    async def get_spot_price(self, ticker: str) -> dict | None:
        """Get spot price from best available source."""
        # Try Public API first (primary source per public-api-only policy)
        try:
            from services.public_api_adapter import fetch_spot_from_public_api
            spot = await fetch_spot_from_public_api(ticker)
            if spot and spot > 0:
                _record_provider_call("public_api", True)
                return {"price": spot, "source": "public_api"}
            _record_provider_call("public_api", False)
        except Exception:
            _record_provider_call("public_api", False)

        # Try Finnhub first (fastest, highest rate limit)
        quote = await self.finnhub.get_quote(ticker)
        if quote:
            return quote

        # Try Polygon
        trade = await self.polygon.get_last_trade(ticker)
        if trade:
            return {
                "price": trade["price"],
                "source": "polygon",
            }

        # Alpha Vantage retired (2026-09-03) — skipped, provider disabled.

        # Fallback to yfinance
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = info.last_price
            if price:
                _record_provider_call("yfinance", True)
                try:
                    from services.observability import yfinance_calls_total
                    yfinance_calls_total.labels(endpoint="get_spot_price", status="success").inc()
                except Exception:
                    pass
                return {
                    "price": price,
                    "prev_close": info.previous_close,
                    "source": "yfinance",
                }
            else:
                _record_provider_call("yfinance", False)
                try:
                    from services.observability import yfinance_calls_total
                    yfinance_calls_total.labels(endpoint="get_spot_price", status="failure").inc()
                except Exception:
                    pass
                return None
        except Exception:
            _record_provider_call("yfinance", False)
            try:
                from services.observability import yfinance_calls_total
                yfinance_calls_total.labels(endpoint="get_spot_price", status="failure").inc()
            except Exception:
                pass
            return None

    async def get_full_quote(self, ticker: str) -> dict:
        """Get comprehensive quote data from all sources."""
        result = {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "spot": None,
            "news": [],
            "earnings": [],
            "recommendation": None,
            "technicals": {},
            "options_contracts": [],
        }

        # Spot price
        result["spot"] = await self.get_spot_price(ticker)

        # News (Finnhub)
        result["news"] = await self.finnhub.get_news(ticker, count=5)

        # Earnings
        result["earnings"] = await self.finnhub.get_earnings(ticker)

        # Analyst recommendation
        result["recommendation"] = await self.finnhub.get_recommendation(ticker)

        # Technical indicators (Alpha Vantage retired 2026-09-03 —
        # use /api/public/technical/{ticker}/{indicator}, computed locally
        # from Public API bars). Kept empty so callers don't hit a dead API.
        result["technicals"] = {}

        # Options contracts (Polygon)
        result["options_contracts"] = await self.polygon.get_options_contracts(ticker, limit=10)

        return result

    def get_status(self) -> dict:
        """Get status of all data providers."""
        return {
            "public_api": {"enabled": True, "rate_limit": "primary source"},
            "finnhub": {"enabled": self.finnhub.enabled, "rate_limit": "60/min"},
            "polygon": {"enabled": self.polygon.enabled, "rate_limit": "5/min"},
            "alphavantage": {"enabled": False, "rate_limit": "retired 2026-09-03 — use /api/public/*"},
            "yfinance": {"enabled": True, "rate_limit": "unlimited (unofficial)"},
        }


class AlphaVantageProvider(FreeDataProvider):
    """Alpha Vantage — RETIRED 2026-09-03 (public-api-only policy).

    Disabled stub kept so legacy imports (routes, scripts, tests) don't
    break. All methods return None without making network calls. Use
    /api/public/* endpoints (Public.com API) instead:
      quote      -> GET /api/public/quotes/{ticker}
      chain      -> GET /api/public/chain/{ticker}
      technicals -> GET /api/public/technical/{ticker}/{indicator}
      bars       -> GET /api/public/bars/{ticker} | /history/{ticker}
    """

    def __init__(self):
        super().__init__("AlphaVantage", rate_limit=5)
        # Forced disabled — never read ALPHA_VANTAGE_KEY.
        self.enabled = False
        self.base = "https://www.alphavantage.co/query"

    async def get_quote(self, ticker: str) -> dict | None:
        """Retired — always None. Use fetch_spot_from_public_api()."""
        logger.info("AlphaVantage retired — get_quote(%s) skipped, use Public API", ticker)
        return None

    async def get_technical_indicator(self, ticker: str, indicator: str = "RSI", period: int = 14) -> dict | None:
        """Retired — always None. Use /api/public/technical/{ticker}/{indicator}."""
        logger.info("AlphaVantage retired — get_technical_indicator(%s, %s) skipped", ticker, indicator)
        return None

    async def get_forex_rate(self, from_cur: str = "USD", to_cur: str = "EUR") -> float | None:
        """Retired — always None. Use Public API quotes."""
        logger.info("AlphaVantage retired — get_forex_rate(%s, %s) skipped", from_cur, to_cur)
        return None

