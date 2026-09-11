"""
backend/routes/paper_trading.py

Paper trading routes with Almgren-Chriss execution.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query

if TYPE_CHECKING:
    from services.paper_trading import PaperTradingEngine

logger = logging.getLogger(__name__)

router = APIRouter()

# Global paper trading engine (set by server.py)
_paper_engine = None


def set_paper_engine(engine: PaperTradingEngine | None) -> None:
    """Called by server.py to inject the paper trading engine."""
    global _paper_engine
    _paper_engine = engine


@router.post("/api/paper-trading/submit")
async def submit_paper_order(request: dict):
    """Submit a paper trade order.

    Request body:
    {
        "symbol": "SPY",
        "side": "buy",
        "quantity": 10,
        "order_type": "almgren_chriss",
        "urgency": 0.5,
        "limit_price": 0.0
    }
    """
    global _paper_engine
    if not _paper_engine:
        raise HTTPException(503, "Paper trading engine not initialized")

    result = _paper_engine.submit_order(
        symbol=request.get("symbol", ""),
        side=request.get("side", "buy"),
        quantity=request.get("quantity", 0),
        order_type=request.get("order_type", "almgren_chriss"),
        urgency=request.get("urgency", 0.5),
        limit_price=request.get("limit_price", 0.0),
    )

    if result["status"] == "rejected":
        raise HTTPException(400, result["reason"])

    return result


@router.post("/api/paper-trading/execute")
async def execute_paper_order(request: dict):
    """Execute a paper trade immediately with simulated market impact."""
    global _paper_engine
    if not _paper_engine:
        raise HTTPException(503, "Paper trading engine not initialized")

    from services.execution_engine import MarketState

    order_id = request.get("order_id", "")
    market_data = request.get("market", {})
    market = MarketState(
        symbol=market_data.get("symbol", "SPY"),
        bid=market_data.get("bid", 0),
        ask=market_data.get("ask", 0),
        last=market_data.get("last", 0),
        bid_size=market_data.get("bid_size", 0),
        ask_size=market_data.get("ask_size", 0),
        volume=market_data.get("volume", 0),
        volatility=market_data.get("volatility", 0.15),
    )

    result = _paper_engine.execute_order(order_id, market)
    return {
        "order_id": result.order_id,
        "symbol": result.symbol,
        "side": result.side,
        "filled_qty": result.filled_qty,
        "avg_price": result.avg_price,
        "total_cost": result.total_cost,
        "implementation_shortfall": result.implementation_shortfall,
        "market_impact": result.market_impact,
        "slippage_bps": result.slippage_bps,
        "duration_ms": result.duration_ms,
    }


@router.get("/api/paper-trading/portfolio")
async def portfolio_summary():
    """Get current portfolio summary."""
    global _paper_engine
    if not _paper_engine:
        raise HTTPException(503, "Paper trading engine not initialized")
    return _paper_engine.get_portfolio_summary()


@router.get("/api/paper-trading/attribution")
async def pnl_attribution(tickers: str | None = Query(default=None)):
    """P&L attribution by ticker (Phase 6.5, 2026-09-05).

    Query params:
      tickers: optional comma-separated symbols to fetch live marks for
        unrealized P&L (via the merged chain fetcher). Omitted tickers
        report unrealized_pnl=null (unknown, never mark-to-model).
    """
    global _paper_engine
    if not _paper_engine:
        raise HTTPException(503, "Paper trading engine not initialized")
    prices: dict[str, float] = {}
    if tickers:
        from server import fetch_spot_and_chains_merged
        for sym in [t.strip().upper() for t in tickers.split(",") if t.strip()][:20]:
            try:
                raw = await fetch_spot_and_chains_merged(sym, 1)
                if raw and (raw.get("spot") or 0) > 0:
                    prices[sym] = float(raw["spot"])
            except Exception as e:
                logger.warning("attribution mark fetch failed for %s: %s", sym, e)
    return {"status": "ok", **_paper_engine.get_pnl_attribution(prices or None)}


@router.get("/api/paper-trading/history")
async def trade_history(limit: int = Query(50, ge=1, le=500)):
    """Get trade history."""
    global _paper_engine
    if not _paper_engine:
        raise HTTPException(503, "Paper trading engine not initialized")
    return _paper_engine.get_trade_history(limit=limit)


@router.get("/api/paper-trading/status")
async def paper_trading_status():
    """Get paper trading engine status."""
    global _paper_engine
    if not _paper_engine:
        return {"status": "not_initialized"}
    return _paper_engine.get_state()


@router.post("/api/paper-trading/estimate-cost")
async def estimate_execution_cost(request: dict):
    """Estimate execution cost before trading."""
    global _paper_engine
    if not _paper_engine:
        raise HTTPException(503, "Paper trading engine not initialized")

    from services.execution_engine import MarketState, Order

    market_data = request.get("market", {})
    market = MarketState(
        symbol=request.get("symbol", "SPY"),
        bid=market_data.get("bid", 0),
        ask=market_data.get("ask", 0),
        last=market_data.get("last", 0),
        bid_size=market_data.get("bid_size", 0),
        ask_size=market_data.get("ask_size", 0),
        volume=market_data.get("volume", 0),
        volatility=market_data.get("volatility", 0.15),
        spread=market_data.get("spread", 0),
    )

    order = Order(
        symbol=request.get("symbol", "SPY"),
        side=request.get("side", "buy"),
        quantity=request.get("quantity", 0),
    )

    estimate = _paper_engine.execution_engine.estimate_execution_cost(
        order, market,
        time_horizon_seconds=request.get("time_horizon_seconds", 300),
    )
    return estimate
