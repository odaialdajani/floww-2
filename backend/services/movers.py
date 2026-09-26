"""backend/services/movers.py — Top Movers v2 (R7-01).

Default mode is the percentage change between the last two COMPLETED
sessions (comparable closes, incomplete current-day bar excluded, weekends /
holidays / half-days resolved through the XNYS calendar). An optional Today
mode compares a source-timed last price against the prior completed close.

Reads reach the provider only through the injected fetch_daily / fetch_quote
seam (default: market_bars daily bars). Completed-session payloads are cached
by (session pair, universe, mode); a total provider failure serves last-good
as stale, else explicit unavailable. Scanner traffic stays bounded: one
universe, bounded concurrency, no per-ticker polling loop here.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "movers.v2"
UNIVERSE_ID = "tracked-options.v1"
VERSION = "movers.v1"
ET = ZoneInfo("America/New_York")
MODES = ("previous_completed_session", "today")
_MAX_CONCURRENCY = 4
_CACHE_TTL_S = 300.0
# R8-01: bound a cold full-universe scan so the route answers (partial if
# needed) instead of blocking the async endpoint under throttling.
_COMPUTE_TIMEOUT_S = 25.0

log = logging.getLogger(__name__)

POPULAR_UNIVERSE = [
    # Mega Cap Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "AVGO", "NFLX",
    "CRM", "INTC", "ORCL", "TXN", "ADBE", "SNAP", "PANW", "TEAM", "DOCU", "NOW",
    # Growth & AI
    "SMCI", "MU", "PLTR", "COIN", "MARA", "RIVN", "LCID", "HOOD", "SOFI", "UPWK",
    "SQ", "PINS", "SHOP", "TWLO", "DDOG", "OKTA", "PSTG", "NET", "PATH", "VEEV",
    # Financials & Industrials
    "JPM", "GS", "MS", "WFC", "BAC", "C", "BLK", "SPGI", "BA", "LMT", "UNP", "UPS", "FDX",
    # Energy & Materials
    "XOM", "CVX", "COP", "SLB", "VLO", "MPC", "PSX", "APD", "NCLH", "GM", "F", "T",
    # Consumer Staples
    "KO", "PEP", "MCD", "WMT", "COST", "BABA", "MRNA", "BIDU", "JD", "PDD",
]

_CACHE: dict[tuple, dict[str, Any]] = {}


def _et_day(ts: Any) -> str | None:
    """Session date (ET) for a bar timestamp; None when unparseable."""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            if not math.isfinite(ts):
                return None
            return datetime.fromtimestamp(float(ts), tz=ET).strftime("%Y-%m-%d")
        s = str(ts)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ET)
        return dt.astimezone(ET).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def completed_session_pair(now: datetime | None = None,
                           day_info: Any | None = None) -> tuple[str | None, str | None]:
    """Last two COMPLETED sessions as (last, prior) YYYY-MM-DD.

    The current session counts only once fully closed (past its calendar
    close, half-day aware). Weekends/holidays are skipped via the calendar.
    Unknown calendar → (None, None): never guess session dates.
    """
    from services.solstice_calendar import exchange_day_info
    day_info = day_info or exchange_day_info
    now_utc = now.astimezone(UTC) if isinstance(now, datetime) else datetime.now(UTC)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    et = now_utc.astimezone(ET)
    opens: list[tuple[str, str]] = []  # (date, close_et)
    for back in range(12):
        d = (et - timedelta(days=back)).strftime("%Y-%m-%d")
        try:
            info = day_info(d)
        except Exception:
            continue
        if info and info.get("is_open") and info.get("close_et"):
            opens.append((d, info["close_et"]))
        if len(opens) >= 3:
            break
    if len(opens) < 2:
        return None, None
    today_s = et.strftime("%Y-%m-%d")
    first_date, first_close = opens[0]
    if first_date == today_s:
        try:
            ch, cm = (int(x) for x in first_close.split(":"))
            closed = (et.hour, et.minute) >= (ch, cm)
        except (TypeError, ValueError):
            closed = False
        if not closed:
            opens = opens[1:]
    if len(opens) < 2:
        return None, None
    return opens[0][0], opens[1][0]


def _pct(last: float, prior: float) -> float | None:
    if prior == 0 or not (math.isfinite(last) and math.isfinite(prior)):
        return None
    out = 100.0 * (last / prior - 1.0)
    return out if math.isfinite(out) else None


async def compute_movers(universe: list[str] | None = None,
                         fetch_daily: Any | None = None,
                         fetch_quote: Any | None = None,
                         now: datetime | None = None,
                         limit: int = 20,
                         mode: str = "previous_completed_session",
                         day_info: Any | None = None,
                         provider: str = "market-bars") -> dict[str, Any]:
    """Rank the universe by completed-session percentage change.

    fetch_daily(sym) -> validated [{t,o,h,l,c,v}] oldest-first (None when
    unavailable). fetch_quote(sym) -> (price, ts) for Today mode; absent
    provider makes Today explicitly unavailable, never silently substituted.
    Sort by absolute percentage (ticker breaks ties), THEN limit.
    """
    if mode not in MODES:
        return _empty(f"unknown mode {mode!r}; expected one of {MODES}")
    universe = list(universe) if universe else list(POPULAR_UNIVERSE)
    if fetch_daily is None:
        from services.market_bars import get_daily_bars

        async def fetch_daily(sym: str, days: int = 10):  # noqa: F811
            return await get_daily_bars(sym, days=days)
    last, prior = completed_session_pair(now=now, day_info=day_info)
    computed_at = (now.astimezone(UTC) if isinstance(now, datetime)
                   else datetime.now(UTC)).isoformat()
    if last is None or prior is None:
        return {"schema_version": SCHEMA_VERSION, "mode": mode, "status": "unavailable",
                "session_date": last, "prior_session_date": prior,
                "universe_id": UNIVERSE_ID,
                "coverage": {"requested": len(universe), "valid": 0, "excluded": len(universe)},
                "source": provider, "computed_at": computed_at, "source_asof": None,
                "results": [], "reason_codes": ["SESSION_DATES_UNKNOWN"]}
    if mode == "today" and fetch_quote is None:
        return {"schema_version": SCHEMA_VERSION, "mode": mode, "status": "unavailable",
                "session_date": last, "prior_session_date": prior,
                "universe_id": UNIVERSE_ID,
                "coverage": {"requested": len(universe), "valid": 0, "excluded": len(universe)},
                "source": provider, "computed_at": computed_at, "source_asof": None,
                "results": [], "reason_codes": ["NO_QUOTE_PROVIDER"]}

    sem = asyncio.Semaphore(_MAX_CONCURRENCY)  # R8-01: 4-way fanout stays
    # under the documented 10 req/s account ceiling with headroom alongside
    # heatseeker polling; the shared public_budget remains the governor.
    # R8-01: the whole-universe scan is bounded — under throttling the route
    # answers partial with what completed instead of blocking minutes.
    compute_timeout_s = float(_COMPUTE_TIMEOUT_S)
    excluded: dict[str, int] = {}

    async def _one(sym: str) -> dict[str, Any] | None:
        async with sem:
            try:
                bars = await fetch_daily(sym)
            except Exception as e:
                log.debug("movers bars fail for %s: %s", sym, e)
                excluded["PROVIDER_FAIL"] = excluded.get("PROVIDER_FAIL", 0) + 1
                return None
        if bars is None:
            # R8-01: the fetch layer returns None on budget exhaustion,
            # transport failure, or fully-quarantined rows — none of which
            # is "the sessions have no closes". Report unavailability
            # honestly so it isn't mistaken for missing market data.
            excluded["PROVIDER_UNAVAILABLE"] = excluded.get("PROVIDER_UNAVAILABLE", 0) + 1
            return None
        by_day: dict[str, float] = {}
        for b in bars or []:
            try:
                d = _et_day((b or {}).get("t"))
                c = float((b or {}).get("c"))
                if d and c > 0 and math.isfinite(c) and d not in by_day:
                    by_day[d] = c
            except (TypeError, ValueError):
                continue
        if mode == "today":
            try:
                price, _ts = await fetch_quote(sym)
                price = float(price)
            except Exception:
                excluded["QUOTE_FAIL"] = excluded.get("QUOTE_FAIL", 0) + 1
                return None
            base = by_day.get(last)
            if base is None or not (price > 0 and math.isfinite(price)):
                excluded["NO_BASELINE"] = excluded.get("NO_BASELINE", 0) + 1
                return None
            pct = _pct(price, base)
            if pct is None:
                excluded["BAD_DENOMINATOR"] = excluded.get("BAD_DENOMINATOR", 0) + 1
                return None
            return {"ticker": sym, "change_pct": pct, "close": price,
                    "previous_close": base, "status": "ok"}
        last_c, prior_c = by_day.get(last), by_day.get(prior)
        if last_c is None or prior_c is None:
            excluded["MISSING_SESSION_CLOSE"] = excluded.get("MISSING_SESSION_CLOSE", 0) + 1
            return None
        pct = _pct(last_c, prior_c)
        if pct is None:
            excluded["BAD_DENOMINATOR"] = excluded.get("BAD_DENOMINATOR", 0) + 1
            return None
        return {"ticker": sym, "change_pct": pct, "close": last_c,
                "previous_close": prior_c, "status": "ok"}

    # R8-01: bounded wait that KEEPS completed rows — under throttling the
    # route answers partial with what resolved instead of blocking minutes
    # (or dropping everything on a gather timeout).
    tasks = {asyncio.ensure_future(_one(s)) for s in universe}
    rows: list[dict[str, Any]] = []
    timed_out = False
    done: set = set()
    pending: set = set(tasks)
    try:
        done, pending = await asyncio.wait(tasks, timeout=compute_timeout_s)
        for t in done:
            try:
                r = t.result()
            except Exception:
                continue
            if r:
                rows.append(r)
        timed_out = bool(pending)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
    rows.sort(key=lambda r: (-abs(r["change_pct"]), r["ticker"]))
    limited = rows[:max(0, limit)]
    # Legacy aliases kept deliberately for the mounted panel transition
    # (App.js reads `change`); canonical field is change_pct.
    for r in limited:
        r["pct"] = r["change_pct"]
        r["change"] = r["change_pct"]
    reasons = sorted(excluded)
    if timed_out:
        reasons.append("COMPUTE_TIMEOUT")
    status = "ok" if not excluded and not timed_out else ("partial" if rows else "unavailable")
    return {"schema_version": SCHEMA_VERSION, "mode": mode, "status": status,
            "session_date": last, "prior_session_date": prior,
            "universe_id": UNIVERSE_ID,
            # Price return on vendor closes as returned (close-to-close).
            # No split/dividend adjustment is applied — a corporate action
            # can print as a large move; basis is declared, not corrected.
            "price_basis": "vendor-close-as-returned-unadjusted",
            "coverage": {"requested": len(universe), "valid": len(rows),
                         "excluded": len(universe) - len(rows)},
            "source": provider, "computed_at": computed_at,
            "source_asof": computed_at,
            "results": limited, "reason_codes": reasons}


def _empty(reason: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "mode": "previous_completed_session",
            "status": "unavailable", "session_date": None, "prior_session_date": None,
            "universe_id": UNIVERSE_ID,
            "coverage": {"requested": 0, "valid": 0, "excluded": 0},
            "source": "market-bars", "computed_at": datetime.now(UTC).isoformat(),
            "source_asof": None, "results": [], "reason_codes": [reason]}


async def get_movers(limit: int = 20, mode: str = "previous_completed_session") -> dict[str, Any]:
    """Cached entry point for the route (completed sessions cache by pair)."""
    if mode not in MODES:
        return _empty(f"unknown mode {mode!r}; expected one of {MODES}")
    now = datetime.now(UTC)
    last, prior = completed_session_pair(now=now)
    key = (last, prior, UNIVERSE_ID, mode)
    hit = _CACHE.get(key)
    if hit and (time.time() - hit["ts"]) < _CACHE_TTL_S:
        out = dict(hit["payload"])
        out["cache"] = "hit"
        return out
    try:
        out = await compute_movers(limit=limit, mode=mode, now=now)
    except Exception as e:
        log.warning("movers compute failed: %s", e)
        if hit:
            out = dict(hit["payload"])
            out["status"] = "stale"
            out.setdefault("reason_codes", []).append("PROVIDER_FAIL")
            return out
        return _empty("PROVIDER_FAIL")
    if out.get("status") in ("ok", "partial"):
        _CACHE[key] = {"ts": time.time(), "payload": out}
    elif hit:
        out = dict(hit["payload"])
        out["status"] = "stale"
        out.setdefault("reason_codes", []).append("PROVIDER_FAIL")
    return out
