"""API routes for Alpaca paper trading."""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alpaca", tags=["alpaca"])


@router.get("/account")
async def get_account():
    """Get Alpaca account info."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        account = await client.get_account()
        if account:
            return account
        return {"error": "Alpaca not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY env vars."}
    except Exception as e:
        return {"error": str(e)}


@router.get("/positions")
async def get_positions():
    """Get all open positions."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        positions = await client.get_positions()
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        return {"error": str(e), "positions": []}


@router.get("/orders")
async def get_orders(status: str = "open", limit: int = 50):
    """Get orders."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        orders = await client.get_orders(status=status, limit=limit)
        return {"orders": orders, "count": len(orders)}
    except Exception as e:
        return {"error": str(e), "orders": []}


@router.get("/clock")
async def get_clock():
    """Get market clock."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        clock = await client.get_clock()
        if clock:
            return clock
        return {"error": "Alpaca not configured"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/bars/{ticker}")
async def get_bars(ticker: str, timeframe: str = "1Day", limit: int = 100):
    """Get price bars for a ticker."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        bars = await client.get_bars(ticker, timeframe=timeframe, limit=limit)
        return {"ticker": ticker.upper(), "bars": bars, "count": len(bars)}
    except Exception as e:
        return {"error": str(e), "bars": []}


@router.post("/order")
async def place_order(
    symbol: str,
    qty: int,
    side: str = "buy",
    order_type: str = "market",
    limit_price: float = 0,
):
    """Place a stock order."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        result = await client.place_stock_order(symbol, qty, side, order_type, limit_price)
        if result:
            return result
        return {"error": "Order failed. Check Alpaca credentials and parameters."}
    except Exception as e:
        return {"error": str(e)}


@router.delete("/position/{symbol}")
async def close_position(symbol: str):
    """Close a position."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        result = await client.close_position(symbol)
        if result:
            return result
        return {"error": "Failed to close position"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/status")
async def get_status():
    """Get Alpaca connection status."""
    try:
        from alpaca_client import ALPACA_API_KEY, ALPACA_SECRET_KEY
        return {
            "configured": bool(ALPACA_API_KEY and ALPACA_SECRET_KEY),
            "api_key_set": bool(ALPACA_API_KEY),
            "secret_key_set": bool(ALPACA_SECRET_KEY),
            "base_url": "https://paper-api.alpaca.markets",
            "mode": "paper trading",
        }
    except Exception as e:
        return {"error": str(e)}
