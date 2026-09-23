"""
backend/services/solstice_time.py — exact instrument-specific expiration clock (F01).

Replaces T=max(calendar_days,1)/365 everywhere in the Solstice path.

Rules:
- Timezone-aware UTC storage; America/New_York session logic.
- Per-series last-trading time (default 16:00 ET equities/ETFs; 15:00 CT / 16:00 ET
  handling for SPX/SPXW via series metadata when available).
- Distinguish AM-settled SPX (settlement-day open) from PM-settled SPXW.
- Exact remaining calendar time in years (actual/365); numerical floor only while
  contract remains tradable and disclosed via `floored` flag.
- Expired contracts → None (callers drop them; never revive with floor).
"""

from __future__ import annotations

from datetime import UTC, datetime, time as dtime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
YEAR_DAYS = 365.0
# Numerical floor while still tradable (avoids 1/T blowup in last seconds).
MIN_T_YEARS = 1.0 / (365.0 * 24.0 * 60.0)  # ~1 minute in years


def parse_expiry_date(expiry: str) -> datetime | None:
    """Parse YYYY-MM-DD to midnight ET date. None when malformed."""
    try:
        y, m, d = (int(x) for x in str(expiry).split("-"))
        return datetime(y, m, d, tzinfo=ET)
    except (ValueError, TypeError, AttributeError):
        return None


def last_trading_utc(expiry: str, series: str | None = None, ticker: str | None = None) -> datetime | None:
    """Last tradable instant for an expiry date, as UTC.

    Defaults: 16:00 ET for equity/ETF options. SPX (AM-settled monthly) callers
    should pass series metadata; when series indicates AM settlement, use
    09:30 ET open of settlement day. SPXW/weekly and SPY/QQQ default 16:00 ET.
    Unknown series → 16:00 ET with caller-visible default (no silent AM/PM swap).
    """
    day_et = parse_expiry_date(expiry)
    if day_et is None:
        return None
    s = str(series or "").upper()
    t = str(ticker or "").upper()
    if ("SPX" in t or "SPX" in s) and ("AM" in s or s.strip() == "SPX"):
        close_et = day_et.replace(hour=9, minute=30)
    else:
        close_et = day_et.replace(hour=16, minute=0)
    return close_et.astimezone(UTC)


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
