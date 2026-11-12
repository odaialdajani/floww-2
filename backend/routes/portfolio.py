"""
backend/routes/portfolio.py

Portfolio management routes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC

from fastapi import APIRouter, HTTPException, Path, Query

router = APIRouter()


def _book_revision(name: str, positions: list) -> str:
    """Concurrency identity for the stored rows; never an authorization token."""
    if not isinstance(positions, list):
        raise HTTPException(503, "The stored portfolio has no valid positions list")
    try:
        content = json.dumps([name, positions], sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise HTTPException(503, "The stored portfolio cannot be read safely") from error
    return hashlib.sha256(content.encode()).hexdigest()


@router.get("/portfolio/{name}")
async def get_portfolio(name: str, spot: float = Query(0), iv: float = Query(0.15)):
    from server import calc_portfolio_summary, db
    portfolio = await db.portfolios.find_one({"name": name}, {"_id": 0})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    revision = _book_revision(name, portfolio.get("positions"))
    if spot > 0:
        summary = await calc_portfolio_summary(portfolio, spot, iv)
        return {**summary, "book_revision": revision}
    return {**portfolio, "book_revision": revision}


@router.post("/portfolio/{name}/position")
async def add_position(name: str, position: dict):
    from datetime import datetime

    from server import db
    position["added_at"] = datetime.now(UTC).isoformat()
    result = await db.portfolios.update_one(
        {"name": name},
        {"$push": {"positions": position}},
        upsert=True,
    )
    # Return count based on matched + upserted
    count = result.modified_count + (1 if result.upserted_id else 0)
    return {"status": "added", "positions": count}


@router.delete("/portfolio/{name}/position/{index}")
async def remove_position(
    name: str,
    index: int = Path(..., ge=0),
    expected_revision: str | None = Query(None, min_length=64, max_length=64, pattern="^[a-f0-9]{64}$"),
):
    from server import db
    if expected_revision is None:
        raise HTTPException(428, "Refresh the stored book before removing a position")
    portfolio = await db.portfolios.find_one({"name": name})
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{name}' not found")
    positions = portfolio.get("positions")
    if _book_revision(name, positions) != expected_revision:
        raise HTTPException(409, "The stored book changed; refresh and review the position again")
    if index >= len(positions):
        raise HTTPException(400, f"Invalid position index {index}")
    remaining = positions[:index] + positions[index + 1:]
    result = await db.portfolios.update_one(
        {"name": name, "positions": positions}, {"$set": {"positions": remaining}},
    )
    if result.matched_count != 1:
        raise HTTPException(409, "The stored book changed; refresh and review the position again")
    return {"status": "removed", "positions": len(remaining)}


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
