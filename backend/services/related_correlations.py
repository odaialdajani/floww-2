"""Exact paired daily returns; never price-level correlation or filled gaps."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

from services.agent.access.horizon import ET, _calendar, required_close

WINDOWS = (30, 90, 252)
MIN_PAIRED_RETURNS = 20


def aware_clock(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return value.astimezone(UTC) if isinstance(value, datetime) and value.tzinfo is not None else None


def completed_window(window, now):
    if type(window) is not int or window not in WINDOWS:
        raise ValueError("Unsupported return window")
    current = aware_clock(now)
    if current is None:
        raise ValueError("A timezone-aware clock is required")
    expected = aware_clock(required_close(current))
    local = expected.astimezone(ET)
    days = [
        session.date().isoformat() for session in _calendar().sessions_window(local.date().isoformat(), -(window + 1))
    ]
    return days, expected.isoformat()


def _closes(series):
    if not isinstance(series, dict) or not isinstance(series.get("bars"), list):
        return {}
    result, conflicts = {}, set()
    for bar in series["bars"]:
        if not isinstance(bar, dict):
            continue
        day, value = bar.get("date"), bar.get("close")
        try:
            valid = (
                isinstance(day, str)
                and date.fromisoformat(day).isoformat() == day
                and type(value) in (int, float)
                and math.isfinite(value)
                and value > 0
            )
        except (ValueError, TypeError):
            valid = False
        if not valid:
            continue
        if day in result and result[day] != value:
            conflicts.add(day)
        result[day] = value
    return {day: value for day, value in result.items() if day not in conflicts}


def _clock(series):
    return {
        "event_time": series.get("event_time") if isinstance(series, dict) else None,
        "received_at": series.get("received_at") if isinstance(series, dict) else None,
        "event_time_basis": "closed_XNYS_session",
        "latest_fetch": series.get("latest_fetch") if isinstance(series, dict) else None,
    }


def compare_series(selected, other, *, window=30, now=None, _window=None):
    current = aware_clock(now or datetime.now(UTC))
    base = {
        "symbol": other.get("ticker") if isinstance(other, dict) else None,
        "coefficient": None,
        "paired_returns": 0,
        "requested_returns": window,
        "start_date": None,
        "end_date": None,
        "status": "unavailable",
        "reason": None,
        "partial": True,
        "stale": False,
        "expected_last_close": None,
        "selected_clock": _clock(selected),
        "comparison_clock": _clock(other),
        "price_basis": "provider_reported",
        "adjustment_policy": "unknown",
        "split_dividend_flag": "unverified",
        "quality": "degraded",
    }
    try:
        days, expected = _window if _window is not None else completed_window(window, current)
    except (ValueError, KeyError, TypeError, OverflowError):
        base["reason"] = "invalid_window_or_clock"
        return base
    base["expected_last_close"] = expected
    if isinstance(selected, dict) and isinstance(other, dict) and selected.get("ticker") == other.get("ticker"):
        base["reason"] = "self_comparison_excluded"
        return base
    left, right = _closes(selected), _closes(other)
    if not left or not right:
        base["reason"] = "selected_series_unavailable" if not left else "comparison_series_unavailable"
        return base
    pairs = []
    for previous, session in zip(days, days[1:], strict=False):
        if not all(day in rows for rows in (left, right) for day in (previous, session)):
            continue
        x, y = left[session] / left[previous] - 1, right[session] / right[previous] - 1
        if math.isfinite(x) and math.isfinite(y):
            pairs.append((previous, session, x, y))
    n = len(pairs)
    base["paired_returns"] = n
    base["partial"] = n < window
    if pairs:
        base.update(start_date=pairs[0][0], end_date=pairs[-1][1])
    expected_clock = aware_clock(expected)
    for item, rows in ((selected, left), (other, right)):
        event = aware_clock(item.get("event_time"))
        receipt = aware_clock(item.get("received_at"))
        if event is None or receipt is None or event > receipt or receipt > current:
            base["reason"] = "invalid_series_clock"
            return base
        last = max(rows)
        try:
            actual = _calendar().session_close(last).to_pydatetime().astimezone(UTC)
        except (ValueError, KeyError, TypeError):
            base["reason"] = "invalid_series_session"
            return base
        if event != actual or actual > current:
            base["reason"] = "invalid_series_clock"
            return base
        base["stale"] = base["stale"] or event < expected_clock or bool(item.get("cache_stale"))
    if n < MIN_PAIRED_RETURNS:
        base["reason"] = "insufficient_paired_returns"
        return base
    x = [pair[2] for pair in pairs]
    y = [pair[3] for pair in pairs]
    try:
        xm, ym = math.fsum(x) / n, math.fsum(y) / n
        dx, dy = [value - xm for value in x], [value - ym for value in y]
        sx, sy = max(abs(value) for value in dx), max(abs(value) for value in dy)
        if sx <= 1e-14 or sy <= 1e-14:
            base["reason"] = "zero_variance"
            return base
        ux, uy = [value / sx for value in dx], [value / sy for value in dy]
        xx, yy = math.fsum(value * value for value in ux), math.fsum(value * value for value in uy)
        coefficient = math.fsum(a * b for a, b in zip(ux, uy, strict=True)) / math.sqrt(xx * yy)
        if not math.isfinite(coefficient):
            base["reason"] = "numeric_unavailable"
            return base
    except (ValueError, OverflowError, ZeroDivisionError):
        base["reason"] = "numeric_unavailable"
        return base
    base["coefficient"] = max(-1.0, min(1.0, coefficient))
    base["status"] = "stale" if base["stale"] else "partial" if base["partial"] else "available"
    base["reason"] = "dated_cache" if base["stale"] else "partial_history" if base["partial"] else None
    return base
