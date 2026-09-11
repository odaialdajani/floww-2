"""Exchange-session scope. Invalid or missing dates never widen a request."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

ET = ZoneInfo("America/New_York")
HORIZONS = ("0dte", "1dte", "week", "month", "all")


@lru_cache(maxsize=1)
def _calendar():
    return xcals.get_calendar("XNYS")


def normalize_horizon(h: str | None) -> str:
    if h is not None and not isinstance(h, str):
        raise ValueError("Horizon must be an explicit named or day range")
    value = (h or "all").strip().lower()
    if re.fullmatch(r"days:\d{1,4}", value) and int(value.split(":")[1]) <= 3660:
        return value
    if re.fullmatch(r"range:\d{1,4}:\d{1,4}", value):
        lo, hi = map(int, value.split(":")[1:])
        if 0 <= lo <= hi <= 3660:
            return value
    if value not in HORIZONS:
        raise ValueError("Unsupported horizon")
    return value


def _now(now=None):
    value = now or datetime.now(ET)
    if value.tzinfo is None:
        raise ValueError("Time requires a timezone")
    return value.astimezone(ET)


def horizon_window(horizon: str, *, now: datetime | None = None, selected_expiry: str | None = None):
    horizon = normalize_horizon(horizon)
    current = _now(now)
    today = current.date()
    cal = _calendar()
    stamp = pd.Timestamp(today)
    is_session = cal.is_session(stamp)
    state = "closed"
    opening = closing = None
    if is_session:
        opening = cal.session_open(stamp).to_pydatetime()
        closing = cal.session_close(stamp).to_pydatetime()
        state = "pre-open" if current < opening else "open" if current < closing else "closed"
    next_session = cal.next_session(stamp) if is_session else cal.date_to_session(stamp, direction="next")
    start = end = None
    if selected_expiry:
        start = end = date.fromisoformat(selected_expiry).isoformat()
    elif horizon.startswith(("days:", "range:")):
        days = list(map(int, horizon.split(":")[1:]))
        lo, hi = (0, days[0]) if len(days) == 1 else days
        start, end = (today + timedelta(days=lo)).isoformat(), (today + timedelta(days=hi)).isoformat()
    elif horizon == "0dte":
        start = end = today.isoformat()
    elif horizon == "1dte":
        start = end = next_session.date().isoformat()
    elif horizon == "week":
        first = stamp if is_session and state != "closed" else next_session
        sessions = cal.sessions_window(first, 4)
        start, end = sessions[0].date().isoformat(), sessions[-1].date().isoformat()
    elif horizon == "month":
        start = today.isoformat()
        end = (stamp + pd.DateOffset(months=1)).date().isoformat()
    return {
        "requested": horizon,
        "start": start,
        "end": end,
        "session_state": state,
        "is_session": bool(is_session),
        "session_open": opening.isoformat() if opening else None,
        "session_close": closing.isoformat() if closing else None,
        "timezone": "America/New_York",
        "calendar": "XNYS",
        "calendar_version": "exchange-calendars-4.13.2",
    }


def is_prep_mode(now: datetime | None = None) -> bool:
    return horizon_window("all", now=now)["session_state"] != "open"


def slice_expiries(contracts, horizon, *, now=None, selected_expiry=None):
    window = horizon_window(horizon, now=now, selected_expiry=selected_expiry)
    result = []
    for contract in contracts or []:
        try:
            expiry = date.fromisoformat(str(contract.get("expiry") or "")).isoformat()
        except (TypeError, ValueError):
            continue
        if window["start"] and not window["start"] <= expiry <= window["end"]:
            continue
        result.append(contract)
    return result


def fractional_years(expiry_instant: datetime, *, now: datetime | None = None) -> float:
    if expiry_instant.tzinfo is None:
        raise ValueError("Expiry requires an explicit timezone and product cutoff")
    return max(0.0, (expiry_instant - _now(now)).total_seconds() / (365.0 * 86400))
