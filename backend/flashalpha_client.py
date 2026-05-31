"""
FlashAlpha API Integration for Confluence Decoder

FlashAlpha has 81 endpoints covering:
- Exposure: GEX, DEX, VEX, CHEX, levels, narrative, zero-dte
- Flow: live flow, blocks, sweeps, outliers, leaderboards, pin risk
- Earnings: VRP, expected move, IV crush, dealer positioning, strategies
- Screener: full options screener with 13 endpoints
- Historical: EOD options, OI, quotes
- Pricing: Greeks, IV, Kelly criterion
- Max Pain, Volatility, Stock quotes

Free tier: stock_summary returns previous-day cached snapshot without a key.
Paid tiers unlock real-time data, flow, and advanced endpoints.

API docs: https://lab.flashalpha.com/swagger
Sign up: https://flashalpha.com
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

FLASHALPHA_API_KEY = os.environ.get("FLASHALPHA_API_KEY", "")
FLASHALPHA_BASE_URL = "https://lab.flashalpha.com"


class FlashAlphaClient:
    """Client for the FlashAlpha options analytics API."""

    def __init__(self):
        self.base_url = FLASHALPHA_BASE_URL

    @property
    def enabled(self):
        return bool(os.environ.get("FLASHALPHA_API_KEY", ""))

    @property
    def _headers(self):
        key = os.environ.get("FLASHALPHA_API_KEY", "")
        return {"X-Api-Key": key, "Content-Type": "application/json"} if key else {}

    async def _get(self, path: str, params: dict = None) -> Optional[dict]:
        if not self.enabled:
            return None
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers, params=params or {},
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 401:
                        logger.warning("FlashAlpha: Unauthorized. Check API key.")
                        return None
                    elif resp.status == 403:
                        logger.warning(f"FlashAlpha: Tier-restricted endpoint {path}")
                        return None
                    elif resp.status == 429:
                        logger.warning("FlashAlpha: Rate limited")
                        return None
                    else:
                        text = await resp.text()
                        logger.warning(f"FlashAlpha: HTTP {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            logger.warning(f"FlashAlpha error: {e}")
            return None

    # ── Exposure ─────────────────────────────────────────────────

    async def get_exposure_summary(self, symbol: str) -> Optional[dict]:
        """Get exposure summary (GEX + DEX + VEX + CHEX combined)."""
        return await self._get(f"/v1/exposure/summary/{symbol}")

    async def get_exposure_narrative(self, symbol: str) -> Optional[dict]:
        """Get AI-generated narrative summary of exposure."""
        return await self._get(f"/v1/exposure/narrative/{symbol}")

    async def get_flow_live(self, symbol: str) -> Optional[dict]:
        """Get live options flow."""
        return await self._get(f"/v1/flow/live/{symbol}")

    async def get_flow_summary(self, symbol: str) -> Optional[dict]:
        """Get flow summary."""
        return await self._get(f"/v1/flow/summary/{symbol}")

    async def get_options_flow_recent(self, symbol: str) -> Optional[dict]:
        """Get recent options flow."""
        return await self._get(f"/v1/flow/options/{symbol}/recent")

    async def get_options_flow_summary(self, symbol: str) -> Optional[dict]:
        """Get options flow summary."""
        return await self._get(f"/v1/flow/options/{symbol}/summary")

    async def get_options_flow_blocks(self, symbol: str) -> Optional[dict]:
        """Get options flow blocks (large trades)."""
        return await self._get(f"/v1/flow/options/{symbol}/blocks")

    async def get_options_flow_history(self, symbol: str) -> Optional[dict]:
        """Get historical options flow."""
        return await self._get(f"/v1/flow/options/{symbol}/history")

    async def get_options_flow_outliers(self) -> Optional[dict]:
        """Get options flow outliers across all tickers."""
        return await self._get("/v1/flow/options/outliers")

    async def get_full_dashboard(self, symbol: str) -> Dict[str, Any]:
        """
        Get a full dashboard of data for a ticker.
        Combines multiple endpoints into one response.
        """
        result = {
            "symbol": symbol.upper(),
            "timestamp": datetime.utcnow().isoformat(),
            "exposure": None,
            "flow": None,
            "earnings": None,
            "max_pain": None,
            "volatility": None,
        }

        # Exposure summary (includes GEX, DEX, VEX, CHEX)
        result["exposure"] = await self.get_exposure_summary(symbol)

        # Flow summary
        result["flow"] = await self.get_flow_summary(symbol)

        # Earnings VRP
        result["earnings"] = await self.get_earnings_vrp(symbol)

        # Max pain
        result["max_pain"] = await self.get_max_pain(symbol)

        # Volatility
        result["volatility"] = await self.get_volatility(symbol)

        return result
