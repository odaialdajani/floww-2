"""One selected equity versus bounded cached daily series; warming is explicit."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from weakref import WeakValueDictionary

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.related_correlations import WINDOWS, aware_clock, compare_series, completed_window
from services.related_price_series import (
    MAX_NAMES,
    RelatedSeriesStore,
    canonical_symbol,
    provider_read_cost,
    warm_daily_series,
)

router = APIRouter(prefix="/api/related", tags=["related-stock-comparisons"])
_REGISTRY = Path(__file__).resolve().parents[1] / "services" / "related_product_registry.json"
_STORE = None
_SCOPE_LOCKS = WeakValueDictionary()
_PRIORITY = ("SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "MSFT", "AMZN", "META", "AMD")


def _store():
    global _STORE
    if _STORE is None:
        default = Path(__file__).resolve().parents[1] / "data" / "related_price_series.sqlite3"
        _STORE = RelatedSeriesStore(os.environ.get("FLOWW_RELATED_PRICE_SERIES_PATH") or default)
    return _STORE


def _catalog_snapshot():
    from services import market_catalog

    cache = market_catalog._cache
    metadata = market_catalog.peek_catalog()
    metadata.update(available=cache is not None, asof=(cache or {}).get("asof"))
    records = (cache or {}).get("instruments", [])
    symbols = list(dict.fromkeys(canonical_symbol(row.get("symbol")) for row in records if isinstance(row, dict)))
    return {**metadata, "symbols": [symbol for symbol in symbols if symbol]}


def registry_related(symbol, catalog, *, registry_path=None):
    try:
        file = Path(registry_path or _REGISTRY)
        if file.stat().st_size > 512 * 1024:
            raise ValueError("Oversized registry")
        registry = json.loads(file.read_text(encoding="utf-8"))
        if (
            not isinstance(registry, dict)
            or registry.get("version") != 1
            or not isinstance(registry.get("products"), list)
        ):
            raise ValueError("Invalid registry")
    except (OSError, ValueError, TypeError):
        return [], {"available": False, "complete": False, "reason": "registry_unavailable", "products": 0}
    items = {}
    for entry in registry["products"][:1000]:
        if not isinstance(entry, dict):
            continue
        ticker = canonical_symbol(entry.get("symbol"))
        under = canonical_symbol(entry.get("underlying")) if entry.get("underlying") is not None else None
        benchmark = entry.get("benchmark")
        urls = entry.get("source_urls")
        try:
            verified = date.fromisoformat(entry.get("verified_at", "")).isoformat()
        except (ValueError, TypeError):
            continue
        if (
            ticker is None
            or entry.get("underlying") is not None
            and under is None
            or benchmark is not None
            and (not isinstance(benchmark, str) or not 1 <= len(benchmark) <= 100)
        ):
            continue
        if (
            not isinstance(urls, list)
            or not urls
            or not all(
                isinstance(url, str) and len(url) <= 2000 and urlparse(url).scheme == "https" and urlparse(url).netloc
                for url in urls
            )
        ):
            continue
        items[ticker] = {**entry, "symbol": ticker, "underlying": under, "verified_at": verified}
    selected = items.get(symbol)
    underlying = selected.get("underlying") if selected else symbol
    benchmark = selected.get("benchmark") if selected else None
    related = {
        ticker: item
        for ticker, item in items.items()
        if ticker != symbol
        and (underlying and item.get("underlying") == underlying or benchmark and item.get("benchmark") == benchmark)
    }
    if selected and selected.get("underlying") and selected["underlying"] != symbol:
        stock = selected["underlying"]
        related.setdefault(
            stock,
            {
                "symbol": stock,
                "underlying": None,
                "benchmark": None,
                "issuer": None,
                "product_type": "underlying_stock",
                "daily_target": None,
                "reset": None,
                "source_urls": selected["source_urls"],
                "verified_at": selected["verified_at"],
            },
        )
    names = set(catalog.get("symbols", []))
    available = catalog.get("available") is True
    products = [
        {
            **item,
            "provider_listed": item["symbol"] in names if available else None,
            "provider_list_asof": catalog.get("asof"),
            "provider_list_stale": bool(catalog.get("stale")),
        }
        for _, item in sorted(related.items())
    ]
    coverage = {
        "available": True,
        "complete": False,
        "reason": "verified_subset",
        "products": len(items),
        **(registry.get("coverage") if isinstance(registry.get("coverage"), dict) else {}),
    }
    coverage["complete"] = False
    return products, coverage


def _context(ticker, window, scope, catalog, registry_path, now):
    symbol = canonical_symbol(ticker)
    products, registry_coverage = registry_related(symbol, catalog, registry_path=registry_path)
    base = {
        "ticker": symbol or ticker,
        "window": window,
        "scope": scope,
        "products": products,
        "registry_coverage": registry_coverage,
        "reason": None,
    }
    if symbol is None:
        base["reason"] = "unsupported_symbol"
        return base, []
    if window not in WINDOWS or type(window) is not int or scope not in ("related", "all"):
        base["reason"] = "unsupported_window_or_scope"
        return base, []
    if catalog.get("available") is not True:
        base["reason"] = "provider_directory_unavailable"
        return base, []
    names = list(dict.fromkeys(canonical_symbol(name) for name in catalog.get("symbols", [])))
    names = [name for name in names if name and name != symbol]
    if len(names) > MAX_NAMES:
        base["reason"] = "provider_directory_over_capacity"
        return base, []
    if symbol not in catalog.get("symbols", []):
        base["reason"] = "selected_not_in_cached_provider_directory"
        return base, []
    related = [item["symbol"] for item in products if item["provider_listed"]]
    if scope == "related":
        names = related
    priority = [name for name in dict.fromkeys(related + list(_PRIORITY)) if name in names]
    seen = set(priority)
    ordered = priority + [name for name in sorted(names) if name not in seen]
    if scope == "related" and not ordered:
        base["reason"] = "no_verified_available_related_products"
    return base, ordered


def build_snapshot(
    ticker, *, window=30, scope="related", limit=200, offset=0, now=None, store=None, catalog=None, registry_path=None
):
    current = aware_clock(now or datetime.now(UTC))
    catalog = catalog if catalog is not None else _catalog_snapshot()
    store = store or _store()
    result, names = _context(ticker, window, scope, catalog, registry_path, current)
    coverage = {
        "eligible": len(names),
        "checked": 0,
        "usable": 0,
        "pending": len(names),
        "failed": 0,
        "stale": 0,
        "partial": 0,
        "complete": False,
        "checked_complete": False,
        "directory_stale": bool(catalog.get("stale")),
        "directory_asof": catalog.get("asof"),
        "price_basis": "provider_reported",
        "adjustment_policy": "unknown",
    }
    result.update(
        status="unavailable",
        coverage=coverage,
        positive=[],
        negative=[],
        comparisons=[],
        comparisons_total=len(names),
        comparisons_offset=offset,
        comparisons_limit=limit,
        has_more=False,
        next_offset=None,
        expected_last_close=None,
    )
    if type(window) is int and window in WINDOWS and current is not None:
        days, expected = completed_window(window, current)
        result["expected_last_close"] = expected
    if result["reason"]:
        return result
    days, expected = completed_window(window, current)
    result["expected_last_close"] = expected
    cached = store.many([result["ticker"]] + names, now=current)
    selected = cached.get(result["ticker"])
    if store.read_error:
        result.update(status="unavailable", reason="cache_storage_unavailable")
        return result
    rows = []
    threshold = aware_clock(expected).timestamp()
    for name in names:
        data = cached.get(name)
        attempt = (data or {}).get("latest_fetch") or {}
        attempted = aware_clock(attempt.get("attempted_at"))
        current_read = data and data.get("event_time") == expected
        checked = bool(
            current_read
            or attempted
            and attempted.timestamp() >= threshold
            and attempt.get("status") in ("available", "failed")
        )
        coverage["checked"] += checked
        coverage["failed"] += bool(
            attempted and attempted.timestamp() >= threshold and attempt.get("status") == "failed"
        )
        pair = compare_series(selected, data or {"ticker": name}, window=window, now=current, _window=(days, expected))
        pair["symbol"] = name
        rows.append(pair)
        usable = pair["coefficient"] is not None
        coverage["usable"] += usable
        coverage["stale"] += bool(pair["stale"])
        coverage["partial"] += bool(usable and pair["partial"])
    coverage["pending"] = coverage["eligible"] - coverage["checked"]
    coverage["checked_complete"] = bool(names and not coverage["pending"])
    positives = sorted(
        (row for row in rows if row["coefficient"] is not None and row["coefficient"] > 0),
        key=lambda row: (-row["coefficient"], row["symbol"]),
    )
    negatives = sorted(
        (row for row in rows if row["coefficient"] is not None and row["coefficient"] < 0),
        key=lambda row: (row["coefficient"], row["symbol"]),
    )
    ordered = sorted(rows, key=lambda row: (row["coefficient"] is None, -abs(row["coefficient"] or 0), row["symbol"]))
    result.update(
        status="partial" if coverage["usable"] else "pending" if coverage["pending"] else "unavailable",
        reason=None
        if coverage["usable"]
        else "selected_series_unavailable"
        if not selected or not selected.get("bars")
        else "no_usable_comparisons",
        positive=positives[:10],
        negative=negatives[:10],
        comparisons=ordered[offset : offset + limit],
        has_more=offset + limit < len(rows),
        next_offset=offset + limit if offset + limit < len(rows) else None,
        selected_clock={
            "event_time": (selected or {}).get("event_time"),
            "received_at": (selected or {}).get("received_at"),
            "latest_fetch": (selected or {}).get("latest_fetch"),
        },
    )
    return result


class WarmRequest(BaseModel):
    window: Literal[30, 90, 252] = 30
    scope: Literal["related", "all"] = "related"
    batch_size: int = Field(8, ge=1, le=8)
    limit: int = Field(200, ge=1, le=1000)
    offset: int = Field(0, ge=0)


async def warm_snapshot(
    ticker,
    *,
    window=30,
    scope="related",
    batch_size=8,
    limit=200,
    offset=0,
    now=None,
    store=None,
    catalog=None,
    registry_path=None,
    disconnected=None,
):
    current = aware_clock(now or datetime.now(UTC))
    catalog = catalog if catalog is not None else _catalog_snapshot()
    store = store or _store()
    context, names = _context(ticker, window, scope, catalog, registry_path, current)
    if context["reason"]:
        result = build_snapshot(
            ticker,
            window=window,
            scope=scope,
            limit=limit,
            offset=offset,
            now=current,
            store=store,
            catalog=catalog,
            registry_path=registry_path,
        )
        result["batch"] = {
            "attempted": 0,
            "fetched": 0,
            "cached": 0,
            "failed": 0,
            "deferred": 0,
            "reserved_calls": 0,
            "cursor": 0,
            "total": 0,
            "done": True,
            "retry_after": None,
            "reason": context["reason"],
        }
        return result
    days, expected = completed_window(window, current)
    targets = [context["ticker"]] + names
    fingerprint = hashlib.sha256(json.dumps(targets, separators=(",", ":")).encode()).hexdigest()
    key = context["ticker"] + ":" + str(window) + ":" + scope + ":" + fingerprint + ":" + expected
    lock = _SCOPE_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _SCOPE_LOCKS[key] = lock
    batch = {
        "attempted": 0,
        "fetched": 0,
        "cached": 0,
        "failed": 0,
        "deferred": 0,
        "reserved_calls": 0,
        "cursor": 0,
        "total": len(targets),
        "done": False,
        "retry_after": None,
    }
    async with lock:
        cursor = store.scope(key, total=len(targets))["cursor"]
        try:
            store.advance(key, cursor, total=len(targets), now=current)
        except (OSError, sqlite3.Error, ValueError):
            result = build_snapshot(
                ticker,
                window=window,
                scope=scope,
                limit=limit,
                offset=offset,
                now=current,
                store=store,
                catalog=catalog,
                registry_path=registry_path,
            )
            batch.update(cursor=cursor, reason="cache_storage_unavailable")
            result.update(status="unavailable", reason="cache_storage_unavailable", batch=batch)
            return result
        first_pass = cursor < len(targets)
        if first_pass:
            work = targets[cursor : cursor + min(8, max(1, int(batch_size)))]
        else:
            existing = store.many(targets, now=current)
            work = sorted(
                (
                    symbol
                    for symbol in targets
                    if ((existing.get(symbol) or {}).get("latest_fetch") or {}).get("status") in ("failed", "deferred")
                    and ((existing.get(symbol) or {}).get("latest_fetch") or {}).get("retry_at", 0)
                    <= current.timestamp()
                ),
                key=lambda symbol: ((existing[symbol]["latest_fetch"]).get("attempted_at", ""), symbol),
            )[: min(8, max(1, int(batch_size)))]
        for symbol in work:
            if disconnected is not None and await disconnected():
                break
            cache = store.get(symbol, now=current)
            hit = cache and cache.get("event_time") == expected and not cache.get("cache_stale")
            cost = 0 if hit else provider_read_cost()
            if batch["reserved_calls"] + cost > 8:
                break
            outcome = await warm_daily_series(
                symbol, store, now=current if now is not None else None, max_reserved_calls=8 - batch["reserved_calls"]
            )
            batch["reserved_calls"] += outcome.get("reserved_calls", 0)
            status = outcome["status"]
            batch["attempted"] += 1
            if status in ("cached", "fetched", "failed"):
                batch[status] += 1
            else:
                batch["deferred"] += 1
                batch["retry_after"] = outcome.get("retry_after", 30)
                if outcome.get("reason") != "retry_cooldown":
                    break
            if first_pass:
                cursor += 1
                store.advance(key, cursor, total=len(targets), now=current)
        batch.update(cursor=cursor, done=cursor >= len(targets))
    result = build_snapshot(
        ticker,
        window=window,
        scope=scope,
        limit=limit,
        offset=offset,
        now=current if now is not None else None,
        store=store,
        catalog=catalog,
        registry_path=registry_path,
    )
    result["batch"] = batch
    return result


@router.get("/{ticker}")
async def related_ticker_snapshot(
    ticker: str,
    window: int = Query(30),
    scope: Literal["related", "all"] = "related",
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    if window not in WINDOWS:
        raise HTTPException(422, "Window must be 30, 90 or 252 returns")
    return await asyncio.to_thread(build_snapshot, ticker, window=window, scope=scope, limit=limit, offset=offset)


@router.post("/{ticker}/warm")
async def related_ticker_warm(ticker: str, body: WarmRequest, request: Request):
    from services.agent.local_access import require_local

    require_local(request)
    return await warm_snapshot(ticker, **body.model_dump(), disconnected=request.is_disconnected)
