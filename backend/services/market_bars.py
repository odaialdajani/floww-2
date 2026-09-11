"""C13 bars/ADV provider over paid Public data (Agent B1, institutional loop).

Contract (CONTRACTS.md C13):
  get_1min_bars(ticker, days=5)  -> [{t,o,h,l,c,v}] | None
  get_daily_bars(ticker, days=60) -> [{t,o,h,l,c,v}] | None
  get_adv_21d(ticker) -> float | None  (mean daily share volume, >=10 sessions)

Budget-gated (1 token per upstream fetch), cached day-granular with
RTH-aware TTLs, OHLC-validated with quarantine counters, stale-serve on
failure, None when cold+unavailable. last_error() exposes the reason.
Pure helpers (_period_for, _validate, _slice_sessions, _adv_from_daily)
take injected data — no network. Never raises to callers.
"""

from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

_DAILY_TTL = 6 * 3600.0
_INTRADAY_TTL = 120.0
_CACHE_MAX = 256

_CACHE: dict[tuple, tuple[float, Any]] = {}
_QUARANTINE: dict[str, int] = {"total": 0}
_LAST_ERROR: dict[str, Any] = {"reason": None, "at": None}

try:
    from services.public_budget import BudgetExhausted
    from services.public_budget import budget as _budget
except Exception:  # pragma: no cover - import-time safety
    BudgetExhausted = Exception  # type: ignore[assignment,misc]

    class _NullBudget:  # type: ignore[no-redef]
        async def acquire(self, host: str = "public") -> None:
            return None

        def release(self) -> None:
            return None

    _budget = _NullBudget()  # type: ignore[assignment]


def _reset_state() -> None:
    """Tests only — clear cache, quarantine counts, last error."""
    _CACHE.clear()
    _QUARANTINE["total"] = 0
    _LAST_ERROR.update(reason=None, at=None)


def last_error() -> dict[str, Any]:
    return dict(_LAST_ERROR)


def quarantine_counts() -> dict[str, int]:
    return dict(_QUARANTINE)


def _note_error(reason: str) -> None:
    _LAST_ERROR.update(reason=reason, at=time.time())


def _period_for(kind: str, days: int) -> tuple[str, str]:
    if kind == "1min":
        if days <= 1:
            return ("DAY", "ONE_MINUTE")
        if days <= 5:
            return ("WEEK", "ONE_MINUTE")
        return ("MONTH", "ONE_MINUTE")
    return ("YEAR", "ONE_DAY")


def _validate(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """OHLC invariants; violations quarantined + counted, never raised."""
    out: list[dict[str, Any]] = []
    for r in rows or []:
        try:
            if not isinstance(r, dict):
                raise ValueError("non-dict row")
            o = float(r["o"])
            h = float(r["h"])
            lo = float(r["l"])
            c = float(r["c"])
            v = float(r.get("v", 0) or 0)
            if not (o > 0 and h > 0 and lo > 0 and c > 0):
                raise ValueError("non-positive price")
            if not (h >= max(o, c, lo) and lo <= min(o, c, h)):
                raise ValueError("range violation")
            if v < 0:
                raise ValueError("negative volume")
            row = {"t": r.get("t"), "o": o, "h": h, "l": lo, "c": c, "v": v}
            if r.get("session") is not None:
                row["session"] = r["session"]
            out.append(row)
        except (KeyError, TypeError, ValueError) as e:
            _QUARANTINE["total"] += 1
            log.debug("bars quarantine: %s (%s)", e, str(r)[:80])
    return out


def _day_key(ts: Any) -> str | None:
    """Best-effort session date (ET) from a bar timestamp."""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(float(ts), tz=_ET)
            return dt.strftime("%Y-%m-%d")
        s = str(ts)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_ET)
        return dt.astimezone(_ET).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _slice_sessions(bars: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    """Keep the last `days` distinct sessions; unparseable stamps pass through."""
    if days <= 0:
        return []
    dated = [(b, _day_key(b.get("t"))) for b in bars or []]
    if any(d is None for _, d in dated):
        return list(bars or [])  # honest fallback: no date info, no cut
    days_seen: list[str] = []
    for _, d in dated:
        if d not in days_seen:
            days_seen.append(d)
    keep = set(days_seen[-days:])
    return [b for b, d in dated if d in keep]


def _adv_from_daily(bars: list[dict[str, Any]]) -> float | None:
    """Mean daily share volume over up to 21 sessions; None under 10."""
    vols = [float(b["v"]) for b in (bars or [])[-21:] if float(b.get("v", 0) or 0) > 0]
    if len(vols) < 10:
        return None
    return sum(vols) / len(vols)


def _cache_get(key: tuple, ttl: float) -> Any | None:
    hit = _CACHE.get(key)
    if hit is None:
        return None
    ts, payload = hit
    if time.time() - ts < ttl:
        return payload
    return None


def _cache_put(key: tuple, payload: Any) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
        _CACHE.pop(oldest, None)
    _CACHE[key] = (time.time(), payload)


def _cache_stale(key: tuple) -> Any | None:
    hit = _CACHE.get(key)
    return hit[1] if hit is not None else None


async def _upstream(ticker: str, period: str, aggregation: str,
                  sessions: str = "regular") -> list[dict[str, Any]] | None:
    """Raw vendor fetch (no budget — the caller owns acquire/release).

    Returns bars or None. Raises on transport failure. Separated for tests.
    """
    from services.public_api_adapter import fetch_bars_from_public_api

    return await fetch_bars_from_public_api(
        ticker, interval="daily", period=period, aggregation=aggregation,
        sessions=sessions,
    )


async def _get(kind: str, ticker: str, days: int, sessions: str = "regular") -> list[dict[str, Any]] | None:
    sym = (ticker or "").strip().upper()
    if not sym or days <= 0:
        return None
    ttl = _DAILY_TTL if kind == "daily" else _INTRADAY_TTL
    key = (sym, kind, days, sessions)
    hit = _cache_get(key, ttl)
    if hit is not None:
        return hit
    try:
        await _budget.acquire("api.public.com")
    except Exception as e:
        _note_error("budget-exhausted")
        log.debug("bars budget exhausted for %s: %s", sym, e)
        return _cache_stale(key)
    try:
        period, aggregation = _period_for(kind, days)
        raw = await _upstream(sym, period, aggregation, sessions)
    except Exception as e:
        _note_error("upstream-failure")
        log.warning("bars upstream fail %s: %s", sym, e)
        return _cache_stale(key)
    finally:
        with contextlib.suppress(Exception):
            _budget.release()
    if raw is None:
        _note_error("upstream-unavailable")
        return _cache_stale(key)
    bars = _validate(raw)
    if not bars:
        _note_error("all-quarantined")
        return _cache_stale(key)
    if kind == "1min":
        bars = _slice_sessions(bars, days)
    else:
        bars = bars[-days:]
    _cache_put(key, bars)
    _note_error(None)  # type: ignore[arg-type]
    return bars


async def get_1min_bars(ticker: str, days: int = 5,
                       sessions: str = "regular") -> list[dict[str, Any]] | None:
    """Last `days` sessions of 1-minute bars, oldest-first. None when unavailable."""
    return await _get("1min", ticker, days, sessions)


async def get_daily_bars(ticker: str, days: int = 60,
                         sessions: str = "regular") -> list[dict[str, Any]] | None:
    """Last `days` daily bars, oldest-first. None when unavailable."""
    return await _get("daily", ticker, days, sessions)


async def get_adv_21d(ticker: str) -> float | None:
    """21-session average daily share volume. None when history is thin."""
    bars = await get_daily_bars(ticker, days=30)
    if not bars:
        return None
    return _adv_from_daily(bars)
