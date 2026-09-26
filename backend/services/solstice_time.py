"""
backend/services/solstice_time.py — exact instrument-specific expiration clock (F01).

Replaces T=max(calendar_days,1)/365 everywhere in the Solstice path.

Rules:
- Timezone-aware UTC storage; America/New_York session logic.
- Per-series last-trading time from the maintained XNYS calendar
  (clock.v2): expiry-day close (16:00 regular, 13:00 half-day), closed
  expiry days fall back to the last open session; AM-settled SPX monthly
  uses the preceding open session (17:00 ET per spec, reverify).
- Distinguish AM-settled SPX last-trade from settlement-day valuation:
  09:30 is never a trading deadline here.
- Exact remaining calendar time in years (actual/365); numerical floor only
  while contract remains tradable and disclosed via `floored` flag.
- Expired contracts → None (callers drop them; never revive with floor).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
YEAR_DAYS = 365.0
# Numerical floor while still tradable (avoids 1/T blowup in last seconds).
MIN_T_YEARS = 1.0 / (365.0 * 24.0 * 60.0)  # ~1 minute in years
# Clock construction version. Bump when product/series rules change.
CLOCK_VERSION = "clock.v2"


def third_friday(year: int, month: int) -> int:
    """Day-of-month of the third Friday (SPX monthly AM cadence)."""
    import calendar as _cal
    month_cal = _cal.monthcalendar(year, month)
    fridays = [week[_cal.FRIDAY] for week in month_cal if week[_cal.FRIDAY] != 0]
    return fridays[2]


def resolve_series(ticker: str | None, expiry: str) -> str:
    """Series tag for clock/settlement rules from display ticker + expiry.

    SPX-family monthly (third-Friday) → "SPX" (AM-settled); all other
    SPX-family expiries → "SPXW" (PM-settled); everything else → "EQUITY".
    Pure date/root derivation — no vendor call, no entitlement claim.
    """
    t = str(ticker or "").upper().replace("^", "")
    if t not in ("SPX", "SPXW"):
        return "EQUITY"
    try:
        y, m, d = (int(x) for x in str(expiry).split("-"))
    except (ValueError, TypeError, AttributeError):
        return "SPXW" if t == "SPXW" else "SPX"
    if t == "SPXW":
        return "SPXW"
    return "SPX" if d == third_friday(y, m) else "SPXW"


def parse_expiry_date(expiry: str) -> datetime | None:
    """Parse YYYY-MM-DD to midnight ET date. None when malformed."""
    try:
        y, m, d = (int(x) for x in str(expiry).split("-"))
        return datetime(y, m, d, tzinfo=ET)
    except (ValueError, TypeError, AttributeError):
        return None


def _open_day_info(day: str) -> dict[str, Any] | None:
    """Calendar info for a date, or None when the calendar is unavailable."""
    try:
        from services.solstice_calendar import exchange_day_info
        return exchange_day_info(day)
    except Exception:
        return None


def _last_open_on_or_before(day_et: datetime) -> tuple[str, str] | None:
    """(date, close_et) of the last open session on/before day_et (≤12 back)."""
    for back in range(13):
        d = (day_et - timedelta(days=back)).strftime("%Y-%m-%d")
        info = _open_day_info(d)
        if info and info.get("is_open") and info.get("close_et"):
            return d, info["close_et"]
    return None


def last_trading_utc(expiry: str, series: str | None = None, ticker: str | None = None) -> datetime | None:
    """Last tradable instant for an expiry date, as UTC (R7-06, clock.v2).

    Separate product/series clocks (never one hardcoded 16:00):
    - AM-settled SPX monthly (series "SPX"): last trading is the close of
      the last OPEN session strictly before expiry (17:00 ET per the
      exchange specification in force; reverify against current Cboe
      notices — series exceptions stay series metadata, not code edits
      here). Settlement-day 09:30 is valuation, NOT a trading deadline.
    - Everything else (equities/ETFs, SPXW weeklies): the expiry day's own
      calendar close (16:00 regular, 13:00 half-day); a closed expiry day
      (weekend/holiday) falls back to the last open session's close.
    - Unknown series → equity default with caller-visible behavior (no
      silent AM/PM swap). Unknown calendar → 16:00 ET expiry-day fallback,
      documented as degraded (calendar unknown blocks ENTRY at the
      session gate; the clock keeps a readable desk, not a tradable one).
    """
    day_et = parse_expiry_date(expiry)
    if day_et is None:
        return None
    s = str(series or "").upper()
    t = str(ticker or "").upper()
    is_spx = "SPX" in t or "SPX" in s
    is_am = is_spx and ("AM" in s or s.strip() == "SPX")
    if is_am:
        from datetime import timedelta
        prev = _last_open_on_or_before(day_et - timedelta(days=1))
        if prev is not None:
            _d, _close = prev
            y, m, d = (int(x) for x in _d.split("-"))
            # Exchange specification: preceding-business-day 17:00 ET.
            close_et = datetime(y, m, d, 17, 0, tzinfo=ET)
        else:
            close_et = (day_et - timedelta(days=1)).replace(hour=17, minute=0)
        return close_et.astimezone(UTC)
    info = _open_day_info(day_et.strftime("%Y-%m-%d"))
    if info and info.get("is_open") and info.get("close_et"):
        try:
            ch, cm = (int(x) for x in info["close_et"].split(":"))
            return day_et.replace(hour=ch, minute=cm).astimezone(UTC)
        except (TypeError, ValueError):
            pass
    prev = _last_open_on_or_before(day_et)
    if prev is not None:
        _d, _close = prev
        try:
            y, m, d = (int(x) for x in _d.split("-"))
            ch, cm = (int(x) for x in _close.split(":"))
            return datetime(y, m, d, ch, cm, tzinfo=ET).astimezone(UTC)
        except (TypeError, ValueError):
            pass
    return day_et.replace(hour=16, minute=0).astimezone(UTC)


def time_to_expiry_years(expiry: str, now: datetime | None = None, series: str | None = None,
                         ticker: str | None = None) -> tuple[float | None, bool, str | None]:
    """Return (T_years | None, floored, reason).

    - Expired (now >= last trading) → (None, False, 'EXPIRED').
    - Malformed expiry → (None, False, 'INVALID_EXPIRY').
    - Sub-floor positive remaining → (MIN_T_YEARS, True, None).
    """
    now_utc = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    end = last_trading_utc(expiry, series=series, ticker=ticker)
    if end is None:
        return None, False, "INVALID_EXPIRY"
    remaining_s = (end - now_utc).total_seconds()
    if remaining_s <= 0:
        return None, False, "EXPIRED"
    t = remaining_s / (86400.0 * YEAR_DAYS)
    if t < MIN_T_YEARS:
        return MIN_T_YEARS, True, None
    return t, False, None


def is_expired(expiry: str, now: datetime | None = None, **kw) -> bool:
    t, _, reason = time_to_expiry_years(expiry, now=now, **kw)
    return t is None and reason == "EXPIRED"
