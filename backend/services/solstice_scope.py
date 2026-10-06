"""Bounded server-owned expiry scope; legacy request/cache identities stay intact."""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

EXCHANGE_TZ = ZoneInfo("America/New_York")
NEXT_LISTED_DAYS = 30


def request_query(expiries, mode, dte, scalp, taps, max_strikes, expiry_scope="loaded", session_date=None):
    query = dict(expiries=expiries, mode=mode, dte=dte, scalp=scalp, withTaps=taps, maxStrikes=max_strikes)
    if expiry_scope == "next":
        if dte is not None or scalp or mode != "day":
            raise ValueError("Next listed cannot be combined with DTE, scalp or swing")
        date.fromisoformat(session_date)
        query.update(expiryScope="next", sessionDate=session_date)
    elif expiry_scope != "loaded":
        raise ValueError("Unsupported expiry scope")
    return query


def cache_key(ticker, query):
    key = f"{ticker}:{query['expiries']}:{query['mode']}:{query['dte']}:{query['scalp']}:{query['withTaps']}:{query['maxStrikes']}"
    if query.get("expiryScope") == "next":
        key += f":next:{query['sessionDate']}"
    return key


def next_listed_selection(contracts, session_date):
    start = date.fromisoformat(session_date)
    end = start + timedelta(days=NEXT_LISTED_DAYS)
    dates, invalid = set(), 0
    for row in contracts:
        value = row.get("expiry")
        try:
            expiry = date.fromisoformat(value)
            if value != expiry.isoformat():
                raise ValueError("Noncanonical expiry")
        except (TypeError, ValueError):
            invalid += 1
            continue
        if start <= expiry <= end:
            dates.add(value)
    selected = sorted(dates)[:1]
    return dict(kind="next", session_date=session_date, timezone="America/New_York",
                max_calendar_dte=NEXT_LISTED_DAYS, selected_expiries=selected,
                invalid_listed_dates=invalid, status="ok" if selected else "unavailable",
                reason=None if selected else "NO_LISTED_EXPIRY_IN_BOUND")
