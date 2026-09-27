"""Broad stock directory and provider release status (read-only)."""
import asyncio
import contextlib

from fastapi import APIRouter, Query

from services.market_catalog import get_catalog

router = APIRouter(prefix="/api/market", tags=["market-directory"])


@router.get("/catalog")
async def catalog_page(page: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=5000),
                       q: str = Query("", max_length=40), options_only: bool = False):
    catalog = await get_catalog()
    query = q.strip().upper().lstrip("$")
    records = [row for row in catalog["instruments"]
               if (not query or query in row["symbol"]) and (not options_only or row["options"])]
    start = (page - 1) * limit
    return {**{k: v for k, v in catalog.items() if k != "instruments"},
            "instruments": records[start:start + limit], "matches": len(records),
            "page": page, "limit": limit, "has_more": start + limit < len(records)}


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
