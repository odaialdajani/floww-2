"""
Alpaca Trading API Integration for Confluence Decoder

Free paper trading API — no minimum deposit.
Provides: account info, positions, order placement, market data.

Setup:
1. Sign up at https://alpaca.markets/ (free)
2. Get API key + secret from https://app.alpaca.markets/paper/dashboard/overview
3. Set env vars: ALPACA_API_KEY, ALPACA_SECRET_KEY
"""

import logging
import os
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # Paper trading
ALPACA_DATA_URL = "https://data.alpaca.markets"


class AlpacaClient:
    """Alpaca paper trading client."""

    def __init__(self):
        self._load_keys()

    def _load_keys(self):
        """Load keys from environment at call time (not import time)."""
        self._api_key = os.environ.get("ALPACA_API_KEY", "")
        self._secret_key = os.environ.get("ALPACA_SECRET_KEY", "")

    @property
    def enabled(self):
        self._load_keys()
        return bool(self._api_key and self._secret_key)

    @property
    def headers(self):
        self._load_keys()
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
        }

    async def _get(self, url: str, params: dict = None) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params or {},
                                       timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        text = await resp.text()
                        logger.warning(f"Alpaca API error {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            logger.warning(f"Alpaca API error: {e}")
            return None

    async def _post(self, url: str, data: dict = None) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=data or {},
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    elif resp.status == 207:
                        # Partial success — some orders filled, some failed
                        result = await resp.json()
                        logger.warning(f"Alpaca partial success (207): {result}")
                        return result
                    else:
                        text = await resp.text()
                        logger.warning(f"Alpaca API error {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            logger.warning(f"Alpaca API error: {e}")
            return None

    async def _delete(self, url: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=self.headers,
                                          timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status in (200, 204):
                        return True
                    else:
                        text = await resp.text()
                        logger.warning(f"Alpaca API error {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            logger.warning(f"Alpaca API error: {e}")
            return None

    async def place_stock_order(self, symbol: str, qty: int, side: str = "buy",
                                 order_type: str = "market", limit_price: float = 0) -> Optional[dict]:
        """Place a stock order."""
        order_data = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": "day",
        }
        if order_type == "limit" and limit_price:
            order_data["limit_price"] = str(limit_price)

        data = await self._post(f"{ALPACA_BASE_URL}/v2/orders", order_data)
        if data:
            return {
                "id": data.get("id", ""),
                "status": data.get("status", ""),
                "symbol": data.get("symbol", ""),
                "side": data.get("side", ""),
                "qty": data.get("qty", ""),
                "type": data.get("type", ""),
                "message": f"Order {data.get('status', 'unknown')}",
                "source": "alpaca",
            }
        return None

    async def close_position(self, symbol: str) -> Optional[dict]:
        """Close a position."""
        data = await self._delete(f"{ALPACA_BASE_URL}/v2/positions/{symbol.upper()}")
        if data:
            return {"message": f"Position {symbol} closed", "source": "alpaca"}
        return None

