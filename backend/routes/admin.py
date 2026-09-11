"""
backend/routes/admin.py

Admin/utility routes: errors, performance, databento usage.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import get_api_key
from services.rate_limit_tracker import av_rate_tracker


async def _require_admin_auth(request: Request) -> bool:
    """Auth dependency for admin routes — checks X-API-Key for ALL methods."""
    api_key = request.headers.get("X-API-Key", "")
    expected_key = get_api_key()
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Authentication not configured. Set API_SECRET_KEY.",
        )
    if api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True


router = APIRouter()


@router.get("/errors/summary")
async def errors_summary(_: bool = Depends(_require_admin_auth)):
    from server import db
    cutoff = __import__("datetime").datetime.now(__import__("datetime").timezone.utc) - __import__("datetime").timedelta(hours=24)
    errors = db.errors.find({"ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", -1).limit(100)
    return {"errors": await errors.to_list(length=100)}


@router.get("/performance/stats")
async def performance_stats(_: bool = Depends(_require_admin_auth)):
    from server import _rate_limits
    return {
        "rate_limit_tracked_ips": len(_rate_limits),
        "uptime_seconds": __import__("time").time() - __import__("server")._start_time if hasattr(__import__("server"), "_start_time") else 0,
    }


@router.post("/errors/clear")
async def errors_clear():
    from datetime import datetime, timedelta

    from server import db
    cutoff = datetime.now(UTC) - timedelta(days=7)
    # Motor's delete_many is async — must await before reading result.deleted_count.
    # Without await this returned a coroutine and .deleted_count raised AttributeError.
    result = await db.errors.delete_many({"ts": {"$lt": cutoff}})
    return {"deleted": result.deleted_count}


@router.get("/databento/usage")
async def databento_usage(_: bool = Depends(_require_admin_auth)):
    from datetime import datetime, timedelta

    from server import LIVE_WINDOW, PAID_TICKERS, _live_tape_session, db
    cutoff = datetime.now(UTC) - timedelta(days=30)
    usage = db.databento_usage.find({"ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", -1).limit(100)
    usage_list = await usage.to_list(length=100)

    # Budget calculation
    BUDGET_USD = 125.0
    est_cost = sum(u.get("cost_usd", 0) for u in usage_list)
    budget_remaining = BUDGET_USD - est_cost
    budget_pct = (est_cost / BUDGET_USD * 100) if BUDGET_USD > 0 else 0

    # Window check
    now_et = datetime.now(UTC) - timedelta(hours=5)  # rough ET
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
    cached_days = len({d for _, d in day_counts})

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


@router.get("/databento/breaker/status")
async def databento_breaker_status(_: bool = Depends(_require_admin_auth)):
    """Per-parent databento circuit breaker snapshot.

    Operators use this to check whether databento is reachable for each OPRA
    parent (SPY/QQQ/IWM/DIA/TLT/SPXW) after a vendor incident. The
    `databento_provider.py:_on_failure` / `_on_success` state machine drives
    the underlying state; this route simply exposes `snapshot_circuits()` over
    HTTP.

    Response shape: `{ts, providers: [{parent, state, consecutive_failures,
    close_attempts, opened_at, ttl_remaining_s}], open_count, half_open_count,
    closed_count}`. Sort order: OPENs first by ttl_remaining ascending (closest
    to half-open probe), then half-open, then closed.

    Test pinning: `backend/tests/services/test_databento_snapshot.py` covers the
    snapshot shape; `backend/tests/routes/test_databento_breaker_status.py`
    covers route auth + graceful degradation when cache is unavailable.
    """
    cache = None
    try:
        from databento_provider import get_cache as _databento_cache
        cache = _databento_cache()
    except Exception as e:  # noqa: BLE001
        logger.error(f"databento_breaker_status: get_cache import/init failed: {e}")
        return {
            "ts": time.time(),
            "providers": [],
            "open_count": 0,
            "half_open_count": 0,
            "closed_count": 0,
            "no_cache": True,
            "error": f"databento cache unavailable: {e}",
        }
    if cache is None:
        return {
            "ts": time.time(),
            "providers": [],
            "open_count": 0,
            "half_open_count": 0,
            "closed_count": 0,
            "no_cache": True,
        }
    try:
        snap = cache.snapshot_circuits()
    except Exception as e:  # noqa: BLE001
        logger.error(f"databento_breaker_status: snapshot_circuits raised: {e}")
        return {
            "ts": time.time(),
            "providers": [],
            "open_count": 0,
            "half_open_count": 0,
            "closed_count": 0,
            "snapshot_error": str(e),
        }
    open_n = sum(1 for x in snap if x["state"] == "open")
    half_open_n = sum(1 for x in snap if x["state"] == "half_open")
    closed_n = sum(1 for x in snap if x["state"] == "closed")
    return {
        "ts": time.time(),
        "providers": snap,
        "open_count": open_n,
        "half_open_count": half_open_n,
        "closed_count": closed_n,
    }


# ---------------------------------------------------------------------------
# Rate Limit Tracking
# ---------------------------------------------------------------------------

@router.get("/admin/rate-limits")
async def get_rate_limits(_: bool = Depends(_require_admin_auth)):
    """Return Alpha Vantage API rate limit status."""
    return av_rate_tracker.get_status()


# ---------------------------------------------------------------------------
# Trading State + Circuit Breaker
# ---------------------------------------------------------------------------

@router.get("/admin/trading/status")
async def trading_status(_: bool = Depends(_require_admin_auth)):
    """Return current trading state, circuit breaker status, and SLO summary."""
    from services.circuit_breaker import main_breaker
    from services.live_trading_switch import switch
    from services.slo_tracker import tracker

    return {
        "trading": switch.get_status(),
        "circuit_breaker": main_breaker.get_status(),
        "slos": tracker.get_summary(),
    }


@router.post("/admin/trading/transition")
async def trading_transition(request: dict, _: bool = Depends(_require_admin_auth)):
    """
    Request a trading state transition.
    Requires 2FA: totp_code + email_code in request body.
    """
    from services.live_trading_switch import TradingState, switch

    target_str = request.get("target_state", "")
    totp_code = request.get("totp_code", "")
    email_code = request.get("email_code", "")

    try:
        target = TradingState[target_str.upper()]
    except KeyError:
        return {"success": False, "error": f"Invalid state: {target_str}"}

    ok, msg = switch.request_transition(target, totp_code, email_code)
    return {"success": ok, "message": msg, "state": switch.get_status()}


@router.post("/admin/trading/circuit-breaker/reset")
async def circuit_breaker_reset(request: dict | None = None, _: bool = Depends(_require_admin_auth)):
    """Manually reset the circuit breaker (requires admin auth)."""
    from services.circuit_breaker import main_breaker

    actor = (request or {}).get("actor", "nav")
    main_breaker.manual_reset(actor=actor)
    return {"success": True, "state": main_breaker.get_status()}


@router.post("/admin/trading/circuit-breaker/trip")
async def circuit_breaker_trip(request: dict | None = None, _: bool = Depends(_require_admin_auth)):
    """Manually trip the circuit breaker (emergency stop)."""
    from services.circuit_breaker import main_breaker

    reason = (request or {}).get("reason", "manual")
    actor = (request or {}).get("actor", "nav")
    main_breaker.manual_trip(reason=reason, actor=actor)
    return {"success": True, "state": main_breaker.get_status()}


@router.get("/admin/trading/circuit-breaker/log")
async def circuit_breaker_log(_: bool = Depends(_require_admin_auth)):
    """Return circuit breaker trip log."""
    from services.circuit_breaker import main_breaker

    return {
        "trips": main_breaker.get_trip_log(),
        "status": main_breaker.get_status(),
    }
