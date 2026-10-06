"""API routes for the alert system."""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
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
    """Coerce a momentum input to the 0-100 detector scale.

    Returns 50 for anything that is not a usable reading. That is a no-alert
    sentinel, not a measurement: it sits inside the dead band between
    MOMENTUM_EXTREME_LOW (20) and MOMENTUM_EXTREME_HIGH (80), so unavailable
    momentum cannot fire an alert.

    bool is rejected explicitly. It subclasses int, so `float(True)` is 1.0
    and the old coercion turned a boolean into a real score of 1 -- below
    MOMENTUM_EXTREME_LOW, which BROADCASTS a "Strong BEARISH momentum" alert
    to every /ws/signals client from a value that was never a measurement.
    """
    if isinstance(raw, bool):
        return 50
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


def broadcast_signal(payload: dict[str, Any]) -> None:
    """Push one signal payload to every connected client.

    The missing producer: detection already ran (POST /snapshot) and its
    result used to be returned to the caller and dropped — nothing read
    `_signal_clients`, so the socket accepted connections and then waited
    forever for a push no code path could make.

    FRAME SHAPE IS PART OF THE CONTRACT. The one real consumer,
    frontend/src/components/AlertOverlay.js, discards any frame that fails
    `data.type === 'signal' || data.signal`. A raw `alert.to_dict()` carries
    `type: "GAMMA_FLIP"` and no `signal` key, so sending it verbatim moved
    real bytes that the overlay silently threw away — the channel looked
    wired and displayed nothing. So every frame is normalized to carry BOTH
    `type: "signal"` (what the overlay matches on) and `signal` (the original
    alert kind, which `addAlert` renders as the badge). The original alert
    type is preserved under `alert_type` for anything that needs it.

    Dead-client policy: a send failure evicts that socket and continues.
    `_signal_clients` is a plain list mutated from both the reader loop and
    the detector, so one vanished client must never 500 the detector's
    request. Mutating a copy keeps the reader loop's own removal safe.
    """
    for client in list(_signal_clients):
        frame = _signal_frame(payload)
        try:
            asyncio.get_running_loop().create_task(
                _send_and_evict(client, frame)
            )
        except RuntimeError:
            # No running loop (sync context) — fall back to direct send.
            _send_and_evict(client, frame)


def _signal_frame(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize any alert dict into a frame AlertOverlay will actually keep.

    `payload` may be a raw `alert.to_dict()` (type='GAMMA_FLIP'), an already
    normalized frame, or anything else a caller passes. The result always
    satisfies the overlay's filter.
    """
    frame = dict(payload or {})
    original = frame.get("type")
    # `type` is the overlay's match key and must be the literal "signal".
    frame["type"] = "signal"
    # `signal` is the human-readable kind the overlay renders as a badge.
    # Only default it when absent, so a caller-supplied value is respected.
    frame.setdefault("signal", original if original and original != "signal" else "ALERT")
    if original and original != "signal":
        frame["alert_type"] = original
    frame.setdefault("ts", datetime.now(UTC).isoformat())
    return frame


async def _send_and_evict(client: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await client.send_json(payload)
    except Exception as e:
        logger.debug("signal client evicted after send failure: %s", e)
        if client in _signal_clients:
            _signal_clients.remove(client)


@router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket endpoint for real-time trading signal streaming.

    Clients connect here to receive BUY/SELL signals pushed from
    trading_signals.py or the alert engine.

    Token-gated exactly like /ws/gex/{ticker}: a live signal stream is a
    higher-value surface than a read-only GEX stream, so leaving it open
    while the other closed was a hole, not a feature.
    """
    from auth import verify_ws_token

    if not await verify_ws_token(websocket):
        await websocket.close(code=4001, reason="Unauthorized")
        return

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
        if websocket in _signal_clients:
            _signal_clients.remove(websocket)
        logger.info(f"Signal client disconnected. Total: {len(_signal_clients)}")
    except Exception as e:
        logger.error(f"Signal WebSocket error: {e}")
        if websocket in _signal_clients:
            _signal_clients.remove(websocket)


async def broadcast_signal_and_wait(payload: dict[str, Any]) -> int:
    """Push one signal frame to every connected client. Returns the fanout count.

    This endpoint had clients but no producer: `_signal_clients` was appended
    to on connect and never read, so AlertOverlay connected successfully,
    sat silent forever, and showed no alerts. The channel was "live" in the
    sense that nothing crashed, which is worse than an obvious failure --
    it looked wired and delivered nothing.

    Callers must pass a payload carrying `type` (and optionally `signal`),
    which is exactly what the frontend's onmessage filter looks for.
    Dead or wedged clients are dropped rather than allowed to block the
    fanout, so one bad socket cannot silence the channel for everyone.
    """
    frame = _signal_frame(payload)
    delivered = 0
    for client in list(_signal_clients):
        try:
            await client.send_json(frame)
            delivered += 1
        except Exception as exc:  # noqa: BLE001 - one bad socket must not stop the rest
            logger.warning("Dropping dead signal client: %s", exc)
            with contextlib.suppress(ValueError):
                _signal_clients.remove(client)
    return delivered


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

        # Push to connected /ws/signals clients. Before this, the result was
        # returned to the caller and dropped: `_signal_clients` was appended
        # to but never read, so the socket had no producer at all. Silence
        # when there are no alerts is deliberate — an overlay that toasts on
        # every snapshot poll is worse than one that stays quiet.
        for alert in alerts or []:
            broadcast_signal(alert.to_dict())

        return {
            "status": "ok",
            "snapshot_stored": True,
            "alerts_detected": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
            "paper_metrics": _compute_paper_metrics(snapshot) if snapshot else {},
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
