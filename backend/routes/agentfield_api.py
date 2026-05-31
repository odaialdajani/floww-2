"""
routes/agentfield_api.py

REST API routes for the AgentField integration.

These routes call the AgentField hub's registered reasoners directly,
bypassing the Agent.call() RPC layer. This is simpler and avoids
the need to reason about target naming conventions.

Mounted at /api/agentfield/v1/* via server.py
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_reasoner(name: str):
    """Look up a registered reasoner function from the hub."""
    from services.agentfield_hub import get_hub  # type: ignore
    hub = get_hub()
    if not hub._initialized:
        raise HTTPException(503, "AgentField hub not initialized")
    # The hub stores reasoner entries; find by function name
    for entry in hub.router.reasoners:
        if entry["func"].__name__ == name:
            return entry["func"]
    raise HTTPException(404, f"Reasoner '{name}' not found in hub")


@router.get("/agentfield/v1/status")
async def agentfield_status() -> Dict[str, Any]:
    from services.agentfield_hub import get_hub  # type: ignore
    hub = get_hub()
    return {
        "status": "ok" if hub._initialized else "not_initialized",
        "node_id": "floww-trading",
        "version": "1.0.0",
        "cost_total_usd": hub.cost_tracker.total_cost_usd,
        "cost_total_tokens": hub.cost_tracker.total_tokens,
        "reasoner_count": len(hub.router.reasoners),
    }


@router.get("/agentfield/v1/signals/gex")
async def signal_gex(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    fn = _get_reasoner("gex_regime")
    return await fn(ticker=ticker)


@router.get("/agentfield/v1/signals/alerts")
async def signal_alerts(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    fn = _get_reasoner("scan_alerts")
    return await fn(ticker=ticker)


@router.get("/agentfield/v1/signals/vpin")
async def signal_vpin(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    fn = _get_reasoner("vpin_signal")
    return await fn(ticker=ticker)


@router.get("/agentfield/v1/signals/hawkes")
async def signal_hawkes(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    fn = _get_reasoner("hawkes_intensity")
    return await fn(ticker=ticker)


@router.get("/agentfield/v1/risk/greeks")
async def risk_greeks(
    name: str = Query(default="main"),
    spot: float = Query(default=0.0, ge=0),
    iv: float = Query(default=0.15, ge=0, le=5),
) -> Dict[str, Any]:
    fn = _get_reasoner("portfolio_greeks")
    return await fn(name=name, spot=spot, iv=iv)


@router.get("/agentfield/v1/risk/scenario")
async def risk_scenario(
    name: str = Query(default="main"),
    spot_shock: float = Query(default=0.0),
    vol_shock: float = Query(default=0.0),
    time_decay_days: int = Query(default=1, ge=0, le=30),
) -> Dict[str, Any]:
    fn = _get_reasoner("scenario_analysis")
    return await fn(name=name, spot_shock=spot_shock, vol_shock=vol_shock, time_decay_days=time_decay_days)


@router.get("/agentfield/v1/risk/size")
async def risk_size(
    account_size: float = Query(default=5000.0, gt=0),
    risk_per_trade_pct: float = Query(default=0.02, gt=0, le=0.5),
    spot: float = Query(default=0.0, ge=0),
    gex_level: float = Query(default=0.0),
) -> Dict[str, Any]:
    fn = _get_reasoner("position_size")
    return await fn(account_size=account_size, risk_per_trade_pct=risk_per_trade_pct, spot=spot, gex_level=gex_level)


@router.get("/agentfield/v1/briefing/build")
async def briefing_build(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    fn = _get_reasoner("build_briefing")
    return await fn(ticker=ticker)


@router.get("/agentfield/v1/briefing/classify")
async def briefing_classify(
    net_gex: float = Query(default=0.0),
    call_oi: float = Query(default=0),
    put_oi: float = Query(default=0),
    iv_skew: float = Query(default=0.0),
    flip_level: float = Query(default=0.0),
    spot: float = Query(default=0.0),
) -> Dict[str, Any]:
    fn = _get_reasoner("classify_regime")
    return await fn(net_gex=net_gex, call_oi=call_oi, put_oi=put_oi, iv_skew=iv_skew, flip_level=flip_level, spot=spot)


@router.get("/agentfield/v1/data/chain")
async def data_chain(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    fn = _get_reasoner("option_chain")
    return await fn(ticker=ticker)


@router.get("/agentfield/v1/data/vol-surface")
async def data_vol_surface(ticker: str = Query(default="SPY", min_length=1, max_length=10)) -> Dict[str, Any]:
    fn = _get_reasoner("vol_surface")
    return await fn(ticker=ticker)


@router.post("/agentfield/v1/execute/order")
async def execute_order(order: Dict[str, Any]) -> Dict[str, Any]:
    fn = _get_reasoner("submit_order")
    return await fn(order=order)


@router.get("/agentfield/v1/execute/health")
async def execute_health() -> Dict[str, Any]:
    fn = _get_reasoner("execution_health")
    return await fn()
