"""Broad stock directory and provider release status (read-only)."""
import asyncio
import contextlib
import math
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Query

from services.market_catalog import get_catalog

router = APIRouter(prefix="/api/market", tags=["market-directory"])


@router.get("/catalog")
async def catalog_page(page: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=5000),
                       q: str = Query("", max_length=40), options_only: bool = False,
                       sector: str = Query("", max_length=100)):
    catalog = await get_catalog()
    query = q.strip().upper().lstrip("$")
    records = [row for row in catalog["instruments"]
               if (not query or query in row["symbol"]) and (not options_only or row["options"])
               and (not sector.strip() or row.get("sector") == sector.strip())]
    start = (page - 1) * limit
    return {**{k: v for k, v in catalog.items() if k != "instruments"},
            "instruments": records[start:start + limit], "matches": len(records),
            "page": page, "limit": limit, "has_more": start + limit < len(records)}


def _count(value):
    return value if type(value) is int and value >= 0 else None


@router.get("/status")
async def market_status():
    """Existing list, completed option reads and observed health; no new scan."""
    from services.market_catalog import peek_catalog
    from services.meta_observability import provider_monitor
    from services.public_scanner import peek_scan_view

    now = time.time()
    directory = peek_catalog()
    coverage = (peek_scan_view(now=now) or {}).get("coverage") or {}
    progress = coverage.get("progress") or {}
    health = provider_monitor.get_health().get("providers", {}).get("public_api") or {}
    seconds = health.get("seconds_since_last_success")
    seconds = seconds if type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0 else None
    checked = coverage.get("checked_at")
    checked = checked if type(checked) in (int, float) and math.isfinite(checked) and 0 <= checked <= now + 30 else None
    window = coverage.get("fresh_window_seconds")
    window = window if type(window) in (int, float) and math.isfinite(window) and window > 0 else None
    receipts = [value for value in (coverage.get("received_at_by_ticker") or {}).values()
                if window is not None and type(value) in (int, float) and math.isfinite(value)
                and -30 <= now - value <= window]
    valid_receipts = (window is not None and all(type(value) in (int, float) and math.isfinite(value)
                      and -30 <= now - value <= window for value in receipts)
                      and len(receipts) == _count(coverage.get("fresh")))
    return {
        "status": "available" if checked is not None else "not_checked",
        "checked_at": datetime.now(UTC).isoformat(),
        "directory": directory,
        "options": {"received_recently": len(receipts) if checked is not None and valid_receipts else None,
                    "receipt_times": receipts if checked is not None and valid_receipts else None,
                    "window_seconds": window, "last_scan_at": checked,
                    "oldest_receipt_age_seconds": coverage.get("max_age_s"),
                    "scan_scope": coverage.get("scope_kind"), "scope_size": _count(coverage.get("universe")),
                    "attempted": _count(coverage.get("attempted")), "failed": _count(coverage.get("latest_failed")),
                    "attempted_in_pass": _count(progress.get("attempted_in_pass")),
                    "succeeded_in_pass": _count(progress.get("succeeded_in_pass")),
                    "failed_in_pass": _count(progress.get("failed_in_pass")),
                    "complete_realtime_market": False},
        "provider": {"last_success_at": now - seconds if seconds is not None else None,
                     "window_calls": _count(health.get("window_calls")),
                     "consecutive_failures": _count(health.get("consecutive_failures"))},
    }


@router.get("/provider-updates")
async def provider_updates():
    from services.public_release_watch import get_release_status
    return await get_release_status()


_release_task = None


async def _watch_releases():
    from services.public_release_watch import get_release_status
    while True:
        await get_release_status()
        await asyncio.sleep(300)  # service caches successful checks for a day


@router.on_event("startup")
async def start_release_watch():
    global _release_task
    _release_task = asyncio.create_task(_watch_releases())


@router.on_event("shutdown")
async def stop_release_watch():
    if _release_task:
        _release_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _release_task
