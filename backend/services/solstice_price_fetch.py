"""
backend/services/solstice_price_fetch.py — real default-off price observation seam.

Reuses the existing Public adapter (no new SDK, no new gateway). Returns one
observation per symbol for the scheduled price-path producer, or None when no
supported observation exists (key missing, account unavailable, symbol
mismatch, stale book). Never raises, never fabricates: gaps stay gaps.

Observation shape (contract `price-path-producer.v1`):
  {ticker, price, event_time (vendor), fetched_at (fetch), source}
Vendor time and fetch time are carried separately end-to-end.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)


async def fetch_one_public_quote(symbol: str) -> dict[str, Any] | None:
    """One supported price observation for `symbol` via the Public adapter.

    Uses `fetch_quotes_from_public_api` (single-symbol batch). The adapter
    already enforces symbol-match (no substitution), book sanity (crossed/wide/
    stale rejection with completed-session fallback), and transport-vs-data
    telemetry. Returns None when no supported observation exists.
    """
    ticker = str(symbol or "").upper().replace("^", "")
    if not ticker:
        return None
    try:
        from services.public_api_adapter import fetch_quotes_from_public_api

        quotes = await fetch_quotes_from_public_api(ticker)
    except Exception as exc:
        log.debug("price fetch failed for %s: %s", ticker, exc)
        return None
    if not isinstance(quotes, dict):
        return None
    row = quotes.get(ticker)
    if not isinstance(row, dict):
        return None
    try:
        price = row.get("spot")
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        return None
    import math as _math

    if price_f is None or not _math.isfinite(price_f) or price_f <= 0:
        return None
    event_time = row.get("spot_event_time")
    fetched_at = row.get("spot_fetched_at")
    if not isinstance(fetched_at, str) or not fetched_at:
        fetched_at = datetime.now(UTC).isoformat()
    # Missing vendor clocks stay unknown — they are NEVER backfilled with fetch
    # time. The producer refuses observations without a vendor event time.
    if not isinstance(event_time, str) or not event_time:
        event_time = None
    return {
        "ticker": ticker,
        "price": price_f,
        "event_time": event_time,
        "fetched_at": fetched_at,
        "source": str(row.get("spot_source") or "public-quote"),
    }


def symbols_from_env(limit: int = 32) -> list[str]:
    """Operator symbol allowlist: `FLOWW_PRICE_PATH_SYMBOLS`, default SPY,QQQ."""
    import os as _os

    raw = _os.environ.get("FLOWW_PRICE_PATH_SYMBOLS", "SPY,QQQ")
    syms = [s.strip().upper() for s in raw.split(",") if s.strip()]
    seen: list[str] = []
    for s in syms:
        if s not in seen:
            seen.append(s)
    return seen[: max(1, int(limit))]
