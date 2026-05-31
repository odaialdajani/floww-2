"""API routes for the alert system."""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# Global alert engine instance
_alert_engine = None

def get_alert_engine():
    """Get the global alert engine instance."""
    global _alert_engine
    if _alert_engine is None:
        from alert_engine import AlertEngine
        _alert_engine = AlertEngine()
    return _alert_engine


# Connected WebSocket clients for signal streaming
_signal_clients: List[WebSocket] = []


@router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket endpoint for real-time trading signal streaming.

    Clients connect here to receive BUY/SELL signals pushed from
    trading_signals.py or the alert engine.
    """
    await websocket.accept()
    _signal_clients.append(websocket)
    logger.info(f"Signal client connected. Total: {len(_signal_clients)}")
    try:
        while True:
            # Keep connection alive, handle pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _signal_clients.remove(websocket)
        logger.info(f"Signal client disconnected. Total: {len(_signal_clients)}")
    except Exception as e:
        logger.error(f"Signal WebSocket error: {e}")
        if websocket in _signal_clients:
            _signal_clients.remove(websocket)

@router.get("/summary")
async def get_alerts_summary():
    """Get aggregated alert summary across all monitored tickers.

    Returns:
        JSON with total, critical, warning, info counts and last_24h breakdown.
    """
    import math
    from datetime import datetime, timedelta, timezone

    try:
        engine = get_alert_engine()
        tickers = list(engine._snapshots.keys())

        total = 0
        critical = 0
        warning = 0
        info = 0
        last_24h = 0
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        for ticker in tickers:
            alerts = engine.detect_alerts(ticker)
            for alert in alerts:
                total += 1
                priority = getattr(alert, "priority", "").upper()
                if priority == "HIGH":
                    critical += 1
                elif priority == "MEDIUM":
                    warning += 1
                else:
                    info += 1

                # Check if alert is within last 24h
                ts_str = getattr(alert, "timestamp", "")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts >= cutoff:
                            last_24h += 1
                    except (ValueError, AttributeError):
                        pass

        # NaN guards — ensure clean integers
        def _safe_int(val):
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                return 0
            return int(val) if val else 0

        return {
            "total": _safe_int(total),
            "critical": _safe_int(critical),
            "warning": _safe_int(warning),
            "info": _safe_int(info),
            "last_24h": _safe_int(last_24h),
        }
    except Exception as e:
        logger.error(f"Error in alerts summary: {e}")
        return {
            "total": 0,
            "critical": 0,
            "warning": 0,
            "info": 0,
            "last_24h": 0,
            "error": str(e),
        }


@router.get("/status")
async def get_alert_status():
    """Get alert system status."""
    try:
        engine = get_alert_engine()
        tickers = list(engine._snapshots.keys())
        return {
            "status": "active",
            "monitored_tickers": tickers,
            "snapshot_counts": {t: len(s) for t, s in engine._snapshots.items()},
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/{ticker}")
async def get_alerts(ticker: str, momentum_score: int = Query(50, ge=0, le=100)):
    """Get current alerts for a ticker."""
    try:
        engine = get_alert_engine()
        summary = engine.get_alert_summary(ticker.upper())
        return summary
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e)}


@router.post("/snapshot")
async def add_snapshot(snapshot: Dict[str, Any]):
    """Add a GEX snapshot for alert detection."""
    try:
        from alert_engine import GEXSnapshot
        engine = get_alert_engine()

        snap = GEXSnapshot(
            ticker=snapshot.get("ticker", "UNKNOWN").upper(),
            spot_price=snapshot.get("spot_price", 0),
            gamma_flip=snapshot.get("gamma_flip", 0),
            call_wall=snapshot.get("call_wall", 0),
            put_wall=snapshot.get("put_wall", 0),
            max_pain=snapshot.get("max_pain", 0),
            max_gamma_strike=snapshot.get("max_gamma_strike", 0),
            total_gex=snapshot.get("total_gex", 0),
            net_gex=snapshot.get("net_gex", 0),
            regime=snapshot.get("regime", "UNKNOWN"),
            gex_by_strike=snapshot.get("gex_by_strike", {}),
        )

        engine.add_snapshot(snap)

        # Detect alerts
        alerts = engine.detect_alerts(snap.ticker)

        return {
            "status": "ok",
            "snapshot_stored": True,
            "alerts_detected": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
        }
    except Exception as e:
        return {"error": str(e)}
