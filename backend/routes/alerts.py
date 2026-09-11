"""API routes for the alert system."""

import logging
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _parse_strike_map(raw: Any, value_kind: str = "float") -> dict[float, Any]:
    """Coerce a JSON strike-keyed map to float keys.

    JSON object keys always arrive as strings; the detectors do strike
    arithmetic on keys, so raw string keys crash detection with a 503.
    Malformed entries are skipped, never raised: a partial map still
    carries signal, and an empty map disables only its own detector.
    """
    import math

    if not isinstance(raw, dict):
        return {}
    out: dict[float, Any] = {}
    for key, value in raw.items():
        try:
            strike = float(key)
            amount = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(strike) or not math.isfinite(amount):
            continue
        out[strike] = int(amount) if value_kind == "int" else amount
    return out


def _parse_momentum_score(raw: Any) -> int:
    """Coerce a momentum input to the 0-100 detector scale."""
    try:
        score = int(float(raw))
    except (TypeError, ValueError, OverflowError):
        return 50
    return max(0, min(100, score))


def _compute_paper_metrics(snapshot: dict) -> dict:
    """Compute Barbon-Buraschi paper metrics from alert snapshot."""
    try:
        from services.gex_paper_accurate import DEFAULT_ADV_SHARES, compute_gamma_imbalance
        net_gex = snapshot.get("net_gex", 0)
        spot = snapshot.get("spot_price", 0)
        if spot > 0:
            return {"gamma_imbalance": compute_gamma_imbalance(net_gex, spot, adv_shares=DEFAULT_ADV_SHARES)}
    except Exception:
        pass  # silent by design: endpoint returns {} degraded instead of 500; outer contract documented
    return {}

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
_signal_clients: list[WebSocket] = []


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
    from datetime import datetime, timedelta

    try:
        engine = get_alert_engine()
        tickers = list(engine._snapshots.keys())

        total = 0
        critical = 0
        warning = 0
        info = 0
        last_24h = 0
        now = datetime.now(UTC)
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
        return JSONResponse(
            status_code=503,
            content={
                "total": 0,
                "critical": 0,
                "warning": 0,
                "info": 0,
                "last_24h": 0,
                "error": str(e),
            },
        )


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
        return JSONResponse(status_code=503, content={"error": str(e)})


@router.get("/whales")
async def get_whale_tracks(state: str | None = Query(None),
                           days: int = Query(30, ge=1, le=365)):
    """P1-7 whale-tracker badge read (Agent C): bookmarked whale alerts with
    live STILL_IN/PARTIAL/EXITED/EXPIRED state + underlying-leg P&L proxy.
    Declared before /{ticker} so 'whales' never matches the catch-all."""
    try:
        from services.journal_store import get_engine, init_whale_tables, read_whales
        jeng = get_engine()
        init_whale_tables(jeng)
        tracks = read_whales(jeng, state=state, days=days)
        return {"ok": True, "tracks": tracks, "n": len(tracks)}
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(e)})


@router.get("/{ticker}")
async def get_alerts(ticker: str, momentum_score: int = Query(50, ge=0, le=100)):
    """Get current alerts for a ticker."""
    try:
        engine = get_alert_engine()
        summary = engine.get_alert_summary(
            ticker.upper(), momentum_score=momentum_score
        )
        return summary
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e)}


@router.post("/snapshot")
async def add_snapshot(snapshot: dict[str, Any]):
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
            gex_by_strike=_parse_strike_map(snapshot.get("gex_by_strike", {})),
            volume_by_strike=_parse_strike_map(
                snapshot.get("volume_by_strike", {}), value_kind="int"
            ),
        )

        engine.add_snapshot(snap)

        # Detect alerts
        momentum = _parse_momentum_score(snapshot.get("momentum_score", 50))
        alerts = engine.detect_alerts(snap.ticker, momentum_score=momentum)

        return {
            "status": "ok",
            "snapshot_stored": True,
            "alerts_detected": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
            "paper_metrics": _compute_paper_metrics(snapshot) if snapshot else {},
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
