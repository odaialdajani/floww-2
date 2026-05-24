"""
backend/routes/admin.py

Admin/utility routes: errors, performance, databento usage.
"""
from __future__ import annotations

from fastapi import APIRouter
from typing import Optional

from services.data_source_router import get_active_source_info, set_data_source, VALID_SOURCES

router = APIRouter()


@router.get("/api/admin/data-source")
async def data_source_info():
    """Return active data source metadata.

    Used by the frontend ``useDataSource`` hook to show the current
    data source and delay in the UI badge.

    Returns:
        {
            "active": "alpha_vantage",
            "delay_seconds": 900,
            "configured": "auto",
            "key_present": True,
            "asof": "2024-01-15T...",
        }
    """
    return get_active_source_info()


@router.post("/api/admin/data-source")
async def data_source_set(request: dict):
    """Set the active data source at runtime.

    Request body:
        {"source": "alpha_vantage" | "databento" | "schwab" | "auto"}

    Returns the updated source info on success, or an error if the
    source name is invalid.

    Note: This overrides the ``FLOWW_DATA_SOURCE`` env var for the
    lifetime of the process. A server restart reverts to the env value.
    """
    source = (request.get("source") or "").strip().lower()

    if not source:
        return {"success": False, "error": "Missing 'source' field"}

    ok = set_data_source(source)
    if not ok:
        return {
            "success": False,
            "error": f"Invalid source '{source}'. Valid options: {', '.join(sorted(VALID_SOURCES))}",
        }

    return {
        "success": True,
        "message": f"Data source switched to {source}",
        "info": get_active_source_info(),
    }


@router.get("/api/errors/summary")
async def errors_summary():
    from server import db
    cutoff = __import__("datetime").datetime.now(__import__("datetime").timezone.utc) - __import__("datetime").timedelta(hours=24)
    errors = db.errors.find({"ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", -1).limit(100)
    return {"errors": await errors.to_list(length=100)}


@router.get("/api/performance/stats")
async def performance_stats():
    from server import db
    from server import _rate_limits
    return {
        "rate_limit_tracked_ips": len(_rate_limits),
        "uptime_seconds": __import__("time").time() - __import__("server")._start_time if hasattr(__import__("server"), "_start_time") else 0,
    }


@router.post("/api/errors/clear")
async def errors_clear():
    from server import db
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = db.errors.delete_many({"ts": {"$lt": cutoff}})
    return {"deleted": result.deleted_count}


@router.get("/databento/usage")
async def databento_usage():
    from server import db, PAID_TICKERS, LIVE_WINDOW, _live_tape_session
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    usage = db.databento_usage.find({"ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", -1).limit(100)
    usage_list = await usage.to_list(length=100)

    # Budget calculation
    BUDGET_USD = 125.0
    est_cost = sum(u.get("cost_usd", 0) for u in usage_list)
    budget_remaining = BUDGET_USD - est_cost
    budget_pct = (est_cost / BUDGET_USD * 100) if BUDGET_USD > 0 else 0

    # Window check
    now_et = datetime.now(timezone.utc) - timedelta(hours=5)  # rough ET
    current_hhmm = now_et.strftime("%H:%M")
    ws = LIVE_WINDOW.get("start_hhmm", "09:00")
    we = LIVE_WINDOW.get("stop_hhmm", "16:00")
    in_window = ws <= current_hhmm <= we

    # Aggregate per-day usage for the `recent` view
    day_counts: dict[tuple[str, str], int] = {}
    for u in usage_list:
        ts = u.get("ts")
        if not ts:
            continue
        day = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        parent = u.get("parent") or u.get("symbol") or "unknown"
        key = (parent, day)
        day_counts[key] = day_counts.get(key, 0) + 1
    recent = [
        {"parent": p, "day": d, "count": c}
        for (p, d), c in sorted(day_counts.items(), key=lambda kv: kv[0][1], reverse=True)
    ]
    cached_days = len({d for _, d in day_counts.keys()})

    return {
        "usage": usage_list,
        "recent": recent,
        "cached_days": cached_days,
        "paid_tickers": sorted(PAID_TICKERS),
        "live_window_et": {"start_hhmm": ws, "stop_hhmm": we},
        "est_total_cost_usd": round(est_cost, 2),
        "budget_remaining_usd": round(budget_remaining, 2),
        "budget_pct_used": round(budget_pct, 2),
        "in_window_now": in_window,
        "live_tape_state": "active" if _live_tape_session.get("active") else "stopped",
        "budget_usd": BUDGET_USD,
    }


# ---------------------------------------------------------------------------
# Schwab Health
# ---------------------------------------------------------------------------

@router.get("/api/admin/schwab/health")
async def schwab_health():
    """Return Schwab streamer health status.

    All values cached in process memory; does not hit Schwab API.
    Response time target: <50ms even under heavy ingestion load.
    """
    health = {
        "connected": False,
        "token_ttl_seconds": 0,
        "last_message_at": None,
        "messages_per_minute_5min": 0.0,
        "reconnect_count_24h": 0,
        "lob_depth_rows_24h": 0,
    }

    # Try to get health from the streamer instance
    try:
        from server import _schwab_streamer
        if _schwab_streamer:
            streamer_health = _schwab_streamer.get_health()
            health.update(streamer_health)
    except Exception:
        pass

    # Compute token TTL
    try:
        from schwab import SchwabTokenManager
        tm = SchwabTokenManager()
        token = tm.load()
        if token:
            expires_at = token.get("expires_at", 0)
            now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp()
            health["token_ttl_seconds"] = max(0, int(expires_at - now))
        else:
            health["token_ttl_seconds"] = 0
    except Exception:
        health["token_ttl_seconds"] = 0

    return health


# ---------------------------------------------------------------------------
# Trading State + Circuit Breaker
# ---------------------------------------------------------------------------

@router.get("/api/admin/trading/status")
async def trading_status():
    """Return current trading state, circuit breaker status, and SLO summary."""
    from services.live_trading_switch import switch
    from services.circuit_breaker import main_breaker
    from services.slo_tracker import tracker

    return {
        "trading": switch.get_status(),
        "circuit_breaker": main_breaker.get_status(),
        "slos": tracker.get_summary(),
    }


@router.post("/api/admin/trading/transition")
async def trading_transition(request: dict):
    """
    Request a trading state transition.
    Requires 2FA: totp_code + email_code in request body.
    """
    from services.live_trading_switch import switch, TradingState

    target_str = request.get("target_state", "")
    totp_code = request.get("totp_code", "")
    email_code = request.get("email_code", "")

    try:
        target = TradingState[target_str.upper()]
    except KeyError:
        return {"success": False, "error": f"Invalid state: {target_str}"}

    ok, msg = switch.request_transition(target, totp_code, email_code)
    return {"success": ok, "message": msg, "state": switch.get_status()}


@router.post("/api/admin/trading/circuit-breaker/reset")
async def circuit_breaker_reset(request: Optional[dict] = None):
    """Manually reset the circuit breaker (requires admin auth)."""
    from services.circuit_breaker import main_breaker

    actor = (request or {}).get("actor", "nav")
    main_breaker.manual_reset(actor=actor)
    return {"success": True, "state": main_breaker.get_status()}


@router.post("/api/admin/trading/circuit-breaker/trip")
async def circuit_breaker_trip(request: Optional[dict] = None):
    """Manually trip the circuit breaker (emergency stop)."""
    from services.circuit_breaker import main_breaker

    reason = (request or {}).get("reason", "manual")
    actor = (request or {}).get("actor", "nav")
    main_breaker.manual_trip(reason=reason, actor=actor)
    return {"success": True, "state": main_breaker.get_status()}


@router.get("/api/admin/trading/circuit-breaker/log")
async def circuit_breaker_log():
    """Return circuit breaker trip log."""
    from services.circuit_breaker import main_breaker

    return {
        "trips": main_breaker.get_trip_log(),
        "status": main_breaker.get_status(),
    }
