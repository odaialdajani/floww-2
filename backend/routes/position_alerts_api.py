"""
backend/routes/position_alerts_api.py

REST + WebSocket API for real-time position alerts.

Endpoints:
  GET    /api/position-alerts/config            — Get global + per-position thresholds
  PUT    /api/position-alerts/config            — Update global thresholds
  GET    /api/position-alerts/config/{symbol}   — Get per-position thresholds
  PUT    /api/position-alerts/config/{symbol}   — Set per-position thresholds
  GET    /api/position-alerts/history           — Get alert history (filterable)
  POST   /api/position-alerts/acknowledge       — Acknowledge an alert
  GET    /api/position-alerts/status            — Service status
  PUT    /api/position-alerts/enabled           — Enable/disable alerting
  WS     /api/position-alerts/ws                — Real-time position alert stream
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/position-alerts", tags=["position-alerts"])

# Import lazily to avoid circular imports at module level
_POSITION_ALERTS_SERVICE = None


def _get_service():
    global _POSITION_ALERTS_SERVICE
    if _POSITION_ALERTS_SERVICE is None:
        from services.position_alerts import position_alert_service
        _POSITION_ALERTS_SERVICE = position_alert_service
    return _POSITION_ALERTS_SERVICE


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class ConfigUpdate(BaseModel):
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_hold_minutes: Optional[int] = None
    poll_seconds: Optional[int] = None
    enabled: Optional[bool] = None


class PerPositionConfigUpdate(BaseModel):
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_hold_minutes: Optional[int] = None


class AcknowledgeRequest(BaseModel):
    alert_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/config")
async def get_global_config() -> Dict[str, Any]:
    """Get global position alert thresholds."""
    svc = _get_service()
    return svc.config.to_dict()


@router.put("/config")
async def update_global_config(update: ConfigUpdate) -> Dict[str, Any]:
    """Update global position alert thresholds."""
    svc = _get_service()
    cfg = svc.config
    if update.stop_loss_pct is not None:
        cfg.stop_loss_pct = update.stop_loss_pct
    if update.take_profit_pct is not None:
        cfg.take_profit_pct = update.take_profit_pct
    if update.max_drawdown_pct is not None:
        cfg.max_drawdown_pct = update.max_drawdown_pct
    if update.max_hold_minutes is not None:
        cfg.max_hold_minutes = update.max_hold_minutes
    if update.poll_seconds is not None and update.poll_seconds >= 5:
        cfg.poll_seconds = update.poll_seconds
    if update.enabled is not None:
        cfg.enabled = update.enabled
    logger.info("Global position alert config updated: %s", cfg.to_dict())
    return cfg.to_dict()


@router.get("/config/{symbol}")
async def get_per_position_config(symbol: str) -> Dict[str, Any]:
    """Get per-position threshold overrides for a symbol."""
    svc = _get_service()
    return {
        "symbol": symbol.upper(),
        "effective": svc.get_position_thresholds(symbol.upper()),
    }


@router.put("/config/{symbol}")
async def set_per_position_config(
    symbol: str, update: PerPositionConfigUpdate
) -> Dict[str, Any]:
    """Set per-position threshold overrides for a symbol."""
    svc = _get_service()
    sym = symbol.upper()
    svc.set_position_thresholds(
        sym,
        stop_loss_pct=update.stop_loss_pct,
        take_profit_pct=update.take_profit_pct,
        max_hold_minutes=update.max_hold_minutes,
    )
    return {
        "symbol": sym,
        "effective": svc.get_position_thresholds(sym),
    }


@router.get("/history")
async def get_alert_history(
    limit: int = Query(50, ge=1, le=500),
    alert_type: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    unacknowledged_only: bool = Query(False),
) -> List[Dict[str, Any]]:
    """Get alert history with optional filters."""
    svc = _get_service()
    return svc.get_alert_history(
        limit=limit,
        alert_type=alert_type,
        symbol=symbol,
        severity=severity,
        unacknowledged_only=unacknowledged_only,
    )


@router.post("/acknowledge")
async def acknowledge_alert(req: AcknowledgeRequest) -> Dict[str, Any]:
    """Acknowledge a position alert."""
    svc = _get_service()
    ok = svc.acknowledge_alert(req.alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Alert not found or already acknowledged: {req.alert_id}")
    return {"status": "acknowledged", "alert_id": req.alert_id}


@router.get("/status")
async def get_service_status() -> Dict[str, Any]:
    """Get position alert service status."""
    svc = _get_service()
    return svc.get_status()


@router.put("/enabled")
async def set_enabled(body: ConfigUpdate) -> Dict[str, bool]:
    """Enable or disable position alerting."""
    svc = _get_service()
    if body.enabled is not None:
        svc.config.enabled = body.enabled
    logger.info("Position alerting %s", "enabled" if svc.config.enabled else "disabled")
    return {"enabled": svc.config.enabled}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def websocket_position_alerts(websocket: WebSocket):
    """WebSocket endpoint for real-time position alert streaming.

    Clients receive JSON messages:
    ```json
    {
      "type": "position_alert",
      "data": {
        "alert_id": "STOP_LOSS_SPY_1712345678",
        "alert_type": "STOP_LOSS",
        "severity": "CRITICAL",
        "symbol": "SPY",
        "side": "LONG",
        ...
      }
    }
    ```
    """
    svc = _get_service()
    await websocket.accept()
    svc.register_ws_client(websocket)
    logger.info("Position alert WebSocket client connected")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Position alert WebSocket error: %s", e)
    finally:
        svc.unregister_ws_client(websocket)
        logger.info("Position alert WebSocket client disconnected")
