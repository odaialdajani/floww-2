"""Provider-backed equity directory shared by search and automatic scanning.

Public's EQUITY category includes stocks and ETFs. A provider catalog is not
an exchange-wide entitlement guarantee. Never substitute a featured list and
call it complete; retain the last good directory with an explicit stale flag.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import re
import time
from datetime import UTC, datetime

log = logging.getLogger(__name__)
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")
_cache: dict | None = None
_loaded_at = 0.0
_retry_at = 0.0
_lock = asyncio.Lock()
TTL_SECONDS = 86400
RETRY_SECONDS = 60


def parse_instruments(instruments: list[dict]) -> list[dict]:
    """Preserve provider spelling (notably share classes) and option eligibility."""
    records = {}
    for item in instruments:
        if not isinstance(item, dict):
            continue
        identity = item.get("instrument") or {}
        if not isinstance(identity, dict):
            continue
        symbol = str(identity.get("symbol") or "").strip().upper()
        if identity.get("type") != "EQUITY" or not _SYMBOL.fullmatch(symbol):
            continue
        if item.get("trading") == "DISABLED":
            continue
        status = item.get("optionTrading")
        if not isinstance(status, str):
            status = None
        records[symbol] = {
            "symbol": symbol,
            "options": status in {"BUY_AND_SELL", "LIQUIDATION_ONLY"},
            "options_status": status or "UNKNOWN",
            "exchange": item.get("exchangeName") or item.get("exchange") or None,
        }
    return [records[s] for s in sorted(records)]


async def _fetch_instruments() -> list[dict]:
    from services.public_api_adapter import _get_broker, _note_public_429
    from services.public_budget import budget

    broker = await _get_broker()
    if broker is None:
        raise RuntimeError("Stock directory unavailable: connect the market data provider")
    await budget.acquire("api.public.com")
    try:
        return await broker.get_all_instruments(type_filter=["EQUITY"])
    except Exception as exc:
        _note_public_429(exc)
        raise
    finally:
        budget.release()


async def get_catalog(refresh: bool = False) -> dict:
    global _cache, _loaded_at, _retry_at
    async with _lock:
        now = time.monotonic()
        if now >= _retry_at and (refresh or _cache is None or now - _loaded_at >= TTL_SECONDS):
            try:
                records = parse_instruments(await _fetch_instruments())
                if not records:
                    raise ValueError("Provider returned an empty stock directory")
                _cache = {"instruments": records, "asof": datetime.now(UTC).isoformat()}
                _loaded_at = now
                _retry_at = 0.0
            except Exception as exc:
                log.warning("Stock directory refresh failed (%s)", type(exc).__name__)
                _retry_at = now + RETRY_SECONDS
        result = copy.deepcopy(_cache or {"instruments": [], "asof": None})
        result.update(
            source="public-instruments", stale=_cache is None or now - _loaded_at >= TTL_SECONDS or _retry_at > now,
            complete_provider_catalog=_cache is not None,
            complete_exchange_catalog=False,
            total=len(result["instruments"]),
            optionable_total=sum(r["options"] for r in result["instruments"]),
        )
        return result


def cached_scan_symbols() -> list[str]:
    """Only symbols the provider explicitly reports as option-enabled."""
    return [r["symbol"] for r in (_cache or {}).get("instruments", []) if r["options"]]
