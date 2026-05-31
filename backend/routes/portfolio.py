"""
backend/routes/portfolio.py

Portfolio management routes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query

router = APIRouter()


@router.get("/portfolio/{name}")
async def get_portfolio(name: str, spot: float = Query(0), iv: float = Query(0.15)):
    from server import calc_portfolio_summary, db
    portfolio = await db.portfolios.find_one({"name": name}, {"_id": 0})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    if spot > 0:
        summary = await calc_portfolio_summary(portfolio, spot, iv)
        return summary
    return portfolio


@router.post("/portfolio/{name}/position")
async def add_position(name: str, position: dict):
    from datetime import datetime, timezone

    from server import db
    position["added_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.portfolios.update_one(
        {"name": name},
        {"$push": {"positions": position}},
        upsert=True,
    )
    # Return count based on matched + upserted
    count = result.modified_count + (1 if result.upserted_id else 0)
    return {"status": "added", "positions": count}


@router.delete("/portfolio/{name}/position/{index}")
async def remove_position(name: str, index: int = Path(..., ge=0)):
    from server import db
    portfolio = await db.portfolios.find_one({"name": name})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    positions = portfolio.get("positions", [])
    if index >= len(positions):
        raise HTTPException(400, f"Invalid position index {index}")
    positions.pop(index)
    await db.portfolios.update_one({"name": name}, {"$set": {"positions": positions}})
    return {"status": "removed", "positions": len(positions)}


@router.get("/portfolio/{name}/scenario")
async def scenario(name: str, spot: float = Query(0), iv: float = Query(0.15)):
    from server import calc_portfolio_scenario, db
    portfolio = await db.portfolios.find_one({"name": name})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    result = await calc_portfolio_scenario(portfolio, spot, iv)
    return result


@router.post("/portfolio/{name}/hedge")
async def hedge(name: str, hedge_request: dict):
    from server import calc_hedge_recommendation, db
    portfolio = await db.portfolios.find_one({"name": name})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    result = await calc_hedge_recommendation(portfolio, hedge_request)
    return result


@router.post("/position-size")
async def position_size(
    account_size: float = Query(100000),
    risk_per_trade_pct: float = Query(0.02),
    spot: float = Query(0),
    gex_level: float = Query(0),
):
    from server import calc_position_size
    result = calc_position_size(
        account_size=account_size,
        risk_per_trade_pct=risk_per_trade_pct,
        spot=spot,
        gex_level=gex_level,
    )
    return result
