"""Bounded Public daily-close evidence, warmed outside copy-only research reads.

The provider does not document an adjustment guarantee. These prices therefore
remain provider_reported with degraded quality; neither raw nor adjusted is
claimed. The event clock is the completed XNYS close, never the receipt clock.
"""
from __future__ import annotations

import asyncio
import copy
import math
import re
import time
from collections import OrderedDict
from datetime import UTC, date, datetime
from weakref import WeakValueDictionary

from services.agent.access.horizon import ET, _calendar, required_close
from services.agent.contracts import instant

_MAX_TICKERS = 128
_MAX_ROWS = 512
_WINDOW_CLOSES = 21
_NEGATIVE_SECONDS = 30.0
_CACHE = OrderedDict()
_NEGATIVE = OrderedDict()
_LOCKS = WeakValueDictionary()
_REASON = "Completed Public daily closes; provider adjustment policy is unknown"


def _utc_now():
    return datetime.now(UTC)


def _ticker(value):
    if not isinstance(value, str):
        return None
    cleaned = value.strip().upper()
    return cleaned if re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,15}", cleaned) else None


def _clock(value):
    parsed = instant(value)
    return datetime.fromisoformat(parsed) if parsed else None


def _positive(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _daily_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    parsed = _clock(value)
    if parsed is None:
        return None
    local = parsed.astimezone(ET)
    if any((local.hour, local.minute, local.second, local.microsecond)):
        return None
    return local.date().isoformat()


def build_daily_bar_evidence(ticker, rows, *, now, received_at):
    """Validate an entire bounded regular series, then retain 21 closed sessions.

    A still-open bar for today's session is excluded. Future days, explicit
    incomplete/fill rows, duplicate days and incoherent prices fail closed.
    No provider access and no cache mutations happen here.
    """
    symbol, current, receipt = _ticker(ticker), _clock(now), _clock(received_at)
    if (symbol is None or current is None or receipt is None or receipt > current
            or not isinstance(rows, list) or not _WINDOW_CLOSES <= len(rows) <= _MAX_ROWS):
        return None
    try:
        cal = _calendar()
        today = current.astimezone(ET).date().isoformat()
        dated = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            if (row.get("session") != "regular" or row.get("complete", True) is not True
                    or row.get("leadingFill", False) or row.get("leading_fill", False)
                    or row.get("ticker", symbol) != symbol or row.get("symbol", symbol) != symbol
                    or row.get("source", "public_api") != "public_api"
                    or row.get("price_basis", "provider_reported") != "provider_reported"):
                return None
            day = _daily_date(row.get("date", row.get("timestamp")))
            if day is None or day > today or not cal.is_session(day):
                return None
            if row.get("date") is not None and row.get("timestamp") is not None:
                if _daily_date(row["date"]) != _daily_date(row["timestamp"]):
                    return None
            prices = [_positive(row.get(key)) for key in ("open", "high", "low", "close")]
            if any(value is None for value in prices):
                return None
            opening, high, low, closing = prices
            if not low <= min(opening, closing) <= max(opening, closing) <= high:
                return None
            if "volume" in row:
                volume = row["volume"]
                if isinstance(volume, bool) or volume is None:
                    return None
                try:
                    if not math.isfinite(float(volume)) or float(volume) < 0:
                        return None
                except (ValueError, TypeError, OverflowError):
                    return None
            session_close = cal.session_close(day).to_pydatetime()
            if session_close > current:
                # Only today's scheduled session can legitimately be in progress.
                if day != today:
                    return None
                continue
            dated.append({"date": day, "close": closing})
        dates = [row["date"] for row in dated]
        if len(dates) < _WINDOW_CLOSES or dates != sorted(set(dates)):
            return None
        expected = [session.date().isoformat() for session in cal.sessions_in_range(dates[0], dates[-1])]
        if dates != expected:
            return None
        selected = dated[-_WINDOW_CLOSES:]
        observed = cal.session_close(selected[-1]["date"]).to_pydatetime().astimezone(UTC)
        stale = observed < datetime.fromisoformat(required_close(current)).astimezone(UTC)
    except (ValueError, KeyError, TypeError, IndexError, OverflowError):
        return None
    return dict(ticker=symbol, interval="1d", source="public_api", complete=True,
                price_basis="provider_reported", adjustment_policy="unknown", price_basis_verified=False,
                status="stale" if stale else "degraded", reason=_REASON, bars=selected,
                event_time=observed.isoformat(), received_at=receipt.isoformat())


def _remember(mapping, key, value):
    mapping[key] = value
    mapping.move_to_end(key)
    while len(mapping) > _MAX_TICKERS:
        mapping.popitem(last=False)


def cache_public_daily_bars(ticker, rows, *, now=None, received_at=None):
    """Admit verified Public rows only; callers cannot obtain mutable cache data."""
    current = now or _utc_now()
    result = build_daily_bar_evidence(ticker, rows, now=current, received_at=received_at or current)
    if result is None:
        return None
    symbol = result["ticker"]
    prior = _CACHE.get(symbol)
    if prior is None or result["event_time"] >= prior["event_time"]:
        _remember(_CACHE, symbol, copy.deepcopy(result))
        _NEGATIVE.pop(symbol, None)
    return peek_daily_bars(symbol)


def cache_public_daily_payload(ticker, payload, *, now=None, received_at=None):
    """Read the original explicit regular bucket, before deduplication/drop logic."""
    symbol = _ticker(ticker)
    if (symbol is None or not isinstance(payload, dict) or payload.get("symbol") != symbol
            or not isinstance(payload.get("regularMarket"), dict)):
        return None
    # Top-level leading fill can describe synthetic pre-IPO flat history.
    # Only an absent marker or explicit False establishes no contamination.
    if any(payload.get(key, False) is not False for key in ("leadingFill", "leading_fill")):
        return None
    raw = payload["regularMarket"].get("bars")
    if not isinstance(raw, list) or not _WINDOW_CLOSES <= len(raw) <= _MAX_ROWS:
        return None
    rows = []
    for row in raw:
        if not isinstance(row, dict):
            return None
        # Preserve all supplied row identity/quality fields for validation.
        rows.append({**row, "date": row.get("date", row.get("timestamp")),
                     "session": row.get("session", "regular")})
    return cache_public_daily_bars(symbol, rows, now=now, received_at=received_at)


def peek_daily_bars(ticker):
    """Copy-only lookup: no authentication, provider calls, warming or mutation."""
    result = _CACHE.get(_ticker(ticker))
    return copy.deepcopy(result) if result is not None else None


def clear_daily_bar_evidence():
    """Clear bounded evidence and failed-attempt entries for tests/admin use."""
    _CACHE.clear()
    _NEGATIVE.clear()


def _current_cached(ticker, now):
    cached = _CACHE.get(ticker)
    if cached is None:
        return None
    closing = instant(required_close(now))
    return copy.deepcopy(cached) if cached["event_time"] == closing else None


async def ensure_public_daily_bars(ticker, *, now=None):
    """Normal desktop warm only; research consumes peek_daily_bars instead.

    One request per ticker is coalesced. Success is reused until the next
    completed exchange session; failure retries no sooner than 30 seconds.
    The adapter performs shared admission before even authenticating.
    """
    symbol, current = _ticker(ticker), _clock(now or _utc_now())
    if symbol is None or current is None:
        return None
    hit = _current_cached(symbol, current)
    if hit is not None:
        return hit
    if time.monotonic() < _NEGATIVE.get(symbol, 0):
        return peek_daily_bars(symbol)
    # Weak locks remain alive through local holders/waiters and disappear when
    # the last request leaves; historical ticker use cannot leak a lock table.
    lock = _LOCKS.get(symbol)
    if lock is None:
        if len(_LOCKS) >= _MAX_TICKERS:
            return peek_daily_bars(symbol)
        lock = asyncio.Lock()
        _LOCKS[symbol] = lock
    async with lock:
        hit = _current_cached(symbol, current)
        if hit is not None:
            return hit
        if time.monotonic() < _NEGATIVE.get(symbol, 0):
            return peek_daily_bars(symbol)
        from services.public_api_adapter import fetch_daily_bar_evidence_from_public_api
        result = await fetch_daily_bar_evidence_from_public_api(symbol, now=now)
        if result is None or result["event_time"] != instant(required_close(current)):
            _remember(_NEGATIVE, symbol, time.monotonic() + _NEGATIVE_SECONDS)
        return result if result is not None else peek_daily_bars(symbol)
