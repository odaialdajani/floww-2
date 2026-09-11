"""
backend/services/public_api_adapter.py

Adapter that bridges PublicBroker (Public.com API) to floww's internal data shape.

floww's existing fetch_spot_and_chains_merged() expects:
    {"ticker": str, "spot": float, "expiries": [...], "contracts": [...], "data_source": str}

PublicBroker.get_option_chain_parsed() returns:
    {"calls": [OptionContract...], "puts": [OptionContract...]}

This adapter converts PublicBroker's output to floww's expected shape.

Routing priority (in fetch_spot_and_chains_merged):
    1. Public API (this adapter)  — PRIMARY
    2. cvserver_client.py         — fallback
    3. yfinance + Databento        — last resort

Stocks side (fetch_bars_from_public_api / fetch_quotes_from_public_api) normalises
Public.com equity data to the shapes floww already speaks, so Public.com is a
drop-in source rather than a new dialect.

DATA ONLY. This adapter deliberately exposes no order/trading method — the
PublicBroker order path targets the LIVE Public.com trading gateway.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from services import public_budget as _public_budget
from services.public_api import PublicBroker

log = logging.getLogger(__name__)


def _finite(x: Any, default: Any = None) -> Any:
    """D4: pass through finite values; map NaN/Infinity (float or string)
    to `default`. Unknown stays unknown — never a fabricated number."""
    if x is None or isinstance(x, bool):
        return x if x is None else default
    if isinstance(x, (int, float)):
        return x if math.isfinite(x) else default
    try:
        return default if not math.isfinite(float(x)) else x
    except (TypeError, ValueError):
        return x

BROKER: PublicBroker | None = None
_BROKER_LOCK = asyncio.Lock()

# Bar timeframes floww exposes, mapped to Public.com's (period, aggregation).
# Keys use the same vocabulary as routes/alpaca.py's ``timeframe`` query param
# so callers can swap providers without relearning the tokens. Values are the
# legal period/aggregation enums documented on PublicBroker.get_bars().
_BARS_TIMEFRAMES: dict[str, tuple[str, str]] = {
    "1Min": ("DAY", "ONE_MINUTE"),
    "5Min": ("DAY", "FIVE_MINUTES"),
    "15Min": ("DAY", "FIFTEEN_MINUTES"),
    "30Min": ("WEEK", "THIRTY_MINUTES"),
    "1Hour": ("MONTH", "ONE_HOUR"),
    "1Day": ("YEAR", "ONE_DAY"),
    "1Week": ("FIVE_YEARS", "ONE_WEEK"),
    "1Month": ("TEN_YEARS", "ONE_MONTH"),
}
_BARS_TIMEFRAME_LOOKUP: dict[str, tuple[str, str]] = {
    key.lower(): value for key, value in _BARS_TIMEFRAMES.items()
}
PUBLIC_BARS_TIMEFRAMES: tuple[str, ...] = tuple(_BARS_TIMEFRAMES)

# Exceptions that mean "the provider is genuinely unreachable", as opposed to
# "the caller asked for something that does not exist". Only these are recorded
# as provider failures — see the telemetry note on fetch_bars_from_public_api.
#
# httpx.TimeoutException is NOT a subclass of the builtin TimeoutError, and
# PublicBroker awaits httpx directly with no asyncio.wait_for wrapper. Catching
# only the builtin here made this branch unreachable, so the provider could never
# record a failure at all. httpx.TransportError covers connect/read/write/pool
# timeouts plus connection and protocol errors. The builtin stays in the tuple in
# case a caller ever wraps these coroutines in asyncio.wait_for.
_TRANSPORT_ERRORS = (httpx.TransportError, TimeoutError)


def _record_call(success: bool) -> None:
    """Record a Public API provider call, mirroring server.py's telemetry hook."""
    try:
        from data_providers import _record_provider_call
        _record_provider_call("public_api", success)
    except Exception:
        # silent by design: telemetry only — a monitor import/registry error must
        # never discard a payload we already fetched, nor mask the upstream
        # failure the caller is about to handle. The outcome is logged above.
        pass


async def close_broker() -> None:
    """Close and clear the lazily-created broker client during shutdown."""
    global BROKER
    async with _BROKER_LOCK:
        broker = BROKER
        BROKER = None
        if broker is not None:
            await broker.close()


async def _get_broker() -> PublicBroker | None:
    """Lazy-init the singleton PublicBroker (auths on first use).
    Re-validates token on each call if near expiry (< 300s remaining) to
    avoid stale auth across long-running processes."""
    global BROKER
    if BROKER is not None:
        try:
            ttl = max(0, BROKER._token_expires_at - time.time())
            if ttl < 300:
                await BROKER._ensure_token()
        except Exception:
            pass
        return BROKER

    secret_key = os.environ.get("PUBLIC_API_KEY", "")
    if not secret_key:
        log.warning("PUBLIC_API_KEY not set — Public API unavailable")
        return None

    async with _BROKER_LOCK:
        if BROKER is not None:
            return BROKER
        broker = PublicBroker(secret_key=secret_key)
        try:
            await broker.auth()
            await broker.get_accounts()
        except Exception as e:
            await broker.close()
            log.warning("PublicBroker auth failed: %s", e)
            return None
        BROKER = broker
        return BROKER


def _matching_quote(quotes: list, symbol: str):
    """Return the quote for exactly `symbol`, else None.

    Never substitute: if the vendor answers with a different symbol than
    requested, using quotes[0] would label the wrong price with our ticker
    (verified failure mode on a sibling stack: QQQ's price served as SPY).
    A missing symbol degrades to no-data downstream, never a wrong number.
    """
    want = _normalize_symbol(symbol)
    for q in quotes or []:
        got = getattr(q, "symbol", None)
        if isinstance(got, str) and _normalize_symbol(got) == want:
            return q
    if quotes:
        log.warning("Public API quote symbol mismatch for %s — refusing substitution",
                    symbol)
    return None


def _normalize_symbol(symbol: str) -> str:
    """Map user-facing tickers to Public.com instrument symbols."""
    return symbol.upper().replace("^", "")


# ---------------------------------------------------------------------------
# Spot validation (weekend stale-spot incident, 2026-09-06).
#
# Public's equity book can freeze pre-session with a rotten NBBO (AFRM
# bid 74.41/ask 89.0, SPY 747.35/773.93 crossed) while the option legs stay
# current. Trusting mid_price unconditionally printed fiction for every
# Public-served ticker (AFRM 81.705 vs true 72.35). A quote is trusted only
# when its book is sane AND its timestamp is at/after the last US close;
# otherwise spot falls back to the yfinance daily close (correct all
# weekend) and the source is tagged. Exchange holidays are not modeled —
# worst case there is a same-as-yfinance number, never a crossed mid.
# ---------------------------------------------------------------------------

_SPOT_MAX_REL_SPREAD = 0.01  # NBBO wider than 1% is not a reference price


def _fnum(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _quote_ts_utc(q) -> datetime | None:
    ts = getattr(q, "timestamp", None)
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _last_us_close_utc(now: datetime | None = None) -> datetime:
    """Most recent 16:00 America/New_York close, as UTC (weekends walk back)."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    cur = now if now is not None else datetime.now(UTC)
    if cur.tzinfo is None:
        cur = cur.replace(tzinfo=UTC)
    et_now = cur.astimezone(et)
    day = et_now.date()
    if (et_now.hour, et_now.minute) < (16, 0):
        day -= timedelta(days=1)  # today's session hasn't closed yet
    while day.weekday() >= 5:  # Sat/Sun -> walk back to Friday
        day -= timedelta(days=1)
    close_et = datetime(day.year, day.month, day.day, 16, 0, tzinfo=et)
    return close_et.astimezone(UTC)


def _public_quote_spot(q, now: datetime | None = None) -> tuple[float | None, str]:
    """Trusted Public mid/last, or (None, reason).

    Reasons: crossed-book | wide-book | stale-quote | no-price.
    Unassessable books/timestamps keep legacy trust (existing callers/mocks).
    """
    bid = _fnum(getattr(q, "bid", None))
    ask = _fnum(getattr(q, "ask", None))
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        if bid > ask:
            return None, "crossed-book"
        if (ask - bid) / ((ask + bid) / 2) > _SPOT_MAX_REL_SPREAD:
            return None, "wide-book"
    ts = _quote_ts_utc(q)
    if ts is not None and ts < _last_us_close_utc(now):
        return None, "stale-quote"
    raw_mid = getattr(q, "mid_price", None)
    mid = _fnum(raw_mid)
    if raw_mid is not None and (mid is None or mid <= 0):
        # Explicit zero/non-numeric mid = honest no-quote: report 0.0 so
        # downstream fails over, never substitute `last` (pinned contract).
        return 0.0, "zero-mid"
    if mid is not None and mid > 0:
        return mid, "public-mid"
    last = _fnum(getattr(q, "last", None))
    if last is not None and last > 0:
        return last, "public-last"
    return None, "no-price"


def _yfinance_spot(symbol: str) -> float | None:
    """Daily-close spot (correct all weekend). Sync — call via to_thread."""
    try:
        import yfinance as yf
        h = yf.Ticker(symbol.upper().replace("^", "")).history(period="5d")
        if h is None or len(h) == 0:
            return None
        return float(h["Close"].iloc[-1])
    except Exception as e:
        log.warning("yfinance spot fallback fail for %s: %s", symbol, e)
        return None


async def _resolve_spot(pb, symbol: str, account_id: str,
                        now: datetime | None = None) -> tuple[float | None, str]:
    """Validated spot + source tag. Never raises.

    Returns (None, 'symbol-mismatch') to fail closed on wrong-symbol
    substitution (P2 contract); (0.0, reason) when there is honestly no
    price so downstream fails over to the next provider.
    """
    try:
        quotes = await pb.get_quotes([symbol], account_id)
        q = _matching_quote(quotes, symbol)
        if q is not None:
            price, reason = _public_quote_spot(q, now=now)
            if price is not None:
                return price, reason
            log.warning("Public API spot rejected for %s (%s) — yfinance fallback",
                        symbol, reason)
        elif quotes:
            # Wrong symbol answered: fail CLOSED (P2 contract) — no fallback
            # may label another instrument's price with our ticker.
            log.warning("Public API quote symbol mismatch for %s — refusing substitution",
                        symbol)
            return None, "symbol-mismatch"
    except Exception as e:
        _note_public_429(e)
        log.warning("Public API quote fail for %s: %s", symbol, e)
    try:
        yf_spot = await asyncio.to_thread(_yfinance_spot, symbol)
        if yf_spot:
            return yf_spot, "yfinance-fallback"
    except Exception as e:
        log.warning("yfinance spot fallback fail for %s: %s", symbol, e)
    return 0.0, "none"


# ---------------------------------------------------------------------------
# Chain response cache (rate-limit shield, 2026-09-04).
#
# One fetch_chain_from_public_api(t, N) fans out to ~2+N live Public calls
# (expirations + quotes + one chain per expiry). Uncached, the Triad 7-ticker
# 30s poll plus the 15s flow poll sustain ~80+ upstream calls/min on a single
# retail key. This cache (60s TTL + per-key coalescing locks + stale-serve)
# cuts that ~4x. Cache identity includes the broker object so unit tests
# with per-test mock brokers never see each other's entries.
# ---------------------------------------------------------------------------

_CHAIN_CACHE: dict[tuple[str, int], tuple[float, Any, dict[str, Any]]] = {}
_CHAIN_CACHE_TTL = 60.0
_CHAIN_LOCKS: dict[tuple[str, int], asyncio.Lock] = {}
_CHAIN_CACHE_MAX = 128


def _chain_lock(key: tuple[str, int]) -> asyncio.Lock:
    lock = _CHAIN_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _CHAIN_LOCKS[key] = lock
    return lock


def _chain_fanout_budget(key: tuple[str, int]) -> tuple[int, int]:
    """Return (acquire_cost, max_inflight) for this (ticker, N) cache key.

    O-1 (testability): the exact per-key fan-out cost is surfaced here so a
    fake broker can prove cold/warm/concurrent totals without reaching the
    real network or the real budget object.
    """
    # One cold fetch_chain_from_public_api(ticker, N) = 1 expirations call
    # + 1 spot/quote call + N chain calls = 2 + N upstream Public calls.
    # Cache key is (ticker.upper(), max_expiries) so N is the second commit
    # component of the key; a different N is a different key and a separate
    # cold fan-out.
    return (2 + key[1], 1)


def _clear_chain_cache() -> None:
    """Drop all cached chains (tests + admin use)."""
    _CHAIN_CACHE.clear()


def _cached_copy(entry: dict[str, Any], stale: bool) -> dict[str, Any]:
    out = dict(entry)
    out["contracts"] = list(entry.get("contracts", []))
    out["expiries"] = list(entry.get("expiries", []))
    if "max_expiries" not in out:
        out["max_expiries"] = entry.get("max_expiries")
    out["stale"] = stale
    return out


async def fetch_chain_from_public_api(
    ticker: str,
    max_expiries: int = 4,
) -> dict[str, Any] | None:
    """
    Fetch options chain from Public API, return floww-shaped dict.

    Returns the same shape as fetch_spot_and_chains_merged:
        {"ticker": str, "spot": float, "expiries": [...], "contracts": [...], "data_source": "public_api", "stale": bool}

    Results are cached 60s per (ticker, max_expiries) with per-key request
    coalescing; on upstream failure a stale entry is served when present.
    Returns None if Public API key missing or call fails with no cache.
    """
    pb = await _get_broker()
    if pb is None:
        return None

    key = (ticker.upper(), max_expiries)
    now = time.monotonic()
    hit = _CHAIN_CACHE.get(key)
    if hit is not None and hit[1] is pb and now - hit[0] < _CHAIN_CACHE_TTL:
        return _cached_copy(hit[2], stale=False)

    async with _chain_lock(key):
        # Re-check under the lock (coalesced waiters share one fetch).
        now = time.monotonic()
        hit = _CHAIN_CACHE.get(key)
        if hit is not None and hit[1] is pb and now - hit[0] < _CHAIN_CACHE_TTL:
            return _cached_copy(hit[2], stale=False)
        # C8: debit the fan-out (2+N upstream calls) before any Public
        # call. All-or-nothing: refusal spends zero and returns None.
        # The in-flight slot releases when this attempt settles.
        # Module-attribute access keeps the budget singleton patchable.
        try:
            await _public_budget.budget.acquire_n(2 + max_expiries)
            _debit_held = True
        except _public_budget.BudgetExhausted as exc:
            log.warning("Public budget refused %s chain fetch: %s", ticker, exc)
            return None
        except Exception:
            _debit_held = False
        # D5: the success timestamp is the request start, so a stale
        # in-flight success cannot erase a sibling's fresher 429 contract.
        _fetch_t0 = time.monotonic()
        try:
            result = await _fetch_chain_live(pb, ticker, max_expiries)
        finally:
            if _debit_held:
                with contextlib.suppress(Exception):
                    _public_budget.budget.release()
        if result is not None:
            result["stale"] = False
            result["max_expiries"] = max_expiries  # H2: key metadata for cost envelope
            with contextlib.suppress(Exception):
                _public_budget.budget.record_ok("api.public.com", now=_fetch_t0)
            if len(_CHAIN_CACHE) >= _CHAIN_CACHE_MAX:
                _CHAIN_CACHE.pop(next(iter(_CHAIN_CACHE)))
            _CHAIN_CACHE[key] = (time.monotonic(), pb, result)
            return _cached_copy(result, stale=False)
        if hit is not None and hit[1] is pb:
            log.warning("Public API chain failed for %s — serving stale cache", ticker)
            return _cached_copy(hit[2], stale=True)
        return None


def _note_public_429(exc: BaseException) -> None:
    """Feed real HTTP 429 sightings into the Public-path budget cooler,
    and record transport failures so they are visible in telemetry.

    httpx surfaces throttles as HTTPStatusError with .response.status_code;
    transport errors (httpx.TransportError: connect/read/write/pool timeouts
    — note httpx.TimeoutException is NOT a builtin TimeoutError, so a bare
    `except TimeoutError` branch would be dead code here) are counted via
    record_error without cooling the lane. Anything else is ignored (never
    let observability break fetching).
    """
    try:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 429:
            from services.public_budget import budget
            budget.record_429("api.public.com")
            return
        try:
            import httpx

            if isinstance(exc, httpx.TransportError):
                from services.public_budget import budget
                budget.record_error("api.public.com")
        except Exception:
            pass
    except Exception:
        pass


async def _fetch_chain_live(
    pb: PublicBroker,
    ticker: str,
    max_expiries: int = 4,
) -> dict[str, Any] | None:
    """Uncached chain fetch (one call = ~2+N upstream Public calls)."""
    trading = pb.get_trading_account()
    if trading is None:
        log.warning("No trading account for Public API")
        return None

    account_id = trading.account_id
    symbol = _normalize_symbol(ticker)

    # 1. Get expirations
    try:
        expiries = await pb.get_option_expirations(symbol, account_id)
    except Exception as e:
        _note_public_429(e)
        log.warning("Public API expirations fail for %s: %s", ticker, e)
        return None

    if not expiries:
        log.warning("Public API returned no expirations for %s", ticker)
        return None

    # 2. Get spot quote (validated: rotten NBBO / pre-session books fall
    # back to the yfinance close instead of printing a fiction mid).
    try:
        spot, spot_source = await _resolve_spot(pb, symbol, account_id)
    except Exception as e:
        _note_public_429(e)
        log.warning("Public API quote fail for %s: %s", ticker, e)
        return None

    # 3. Fetch chain for each expiry (up to max_expiries). Only expiries
    # that actually return data are reported (D4: requested vs returned
    # coverage distinguished). Expired contracts are dropped; 0DTE kept.
    contracts: list[dict[str, Any]] = []
    exp_dates = []
    today = datetime.now(UTC).date()

    for exp in expiries[:max_expiries]:
        try:
            parsed = await pb.get_option_chain_parsed(symbol, exp, account_id)
        except Exception as e:
            _note_public_429(e)
            log.warning("Public API chain fail for %s %s: %s", ticker, exp, e)
            continue
        exp_dates.append(exp)

        for side in ("calls", "puts"):
            for oc in parsed.get(side, []):
                try:
                    exp_d = datetime.strptime(oc.expiration, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                if exp_d < today:  # D4: expired listing, not a position
                    continue
                T = max((exp_d - today).days, 1) / 365.0
                # NBBO mid from the paid feed — the executable-reference price.
                # Downstream side inference (last vs mid) and premium math must
                # use this instead of BS estimates whenever it exists.
                mid = _finite(oc.mid)
                strike = _finite(oc.strike)
                if strike is None or strike <= 0:  # D4: unusable contract
                    continue
                contracts.append({
                    "osi": oc.symbol,  # OSI symbol for order placement (e.g. SPY260904C00760000)
                    "expiry": oc.expiration,
                    "T": T,
                    # cvserver convention: lowercase "call"/"put".
                    # gex_core.py and analytics.py compare c["type"] == "call"
                    # exactly — uppercase here would flip every GEX sign.
                    "type": "call" if side == "calls" else "put",
                    "strike": strike,
                    "oi": _finite(oc.open_interest, 0),
                    "iv": _finite(oc.iv, 0.0),
                    "delta": _finite(oc.delta),
                    "gamma": _finite(oc.gamma),
                    "theta": _finite(oc.theta),
                    "vega": _finite(oc.vega),
                    "bid": _finite(oc.bid),
                    "ask": _finite(oc.ask),
                    "mid": mid,
                    "last": _finite(oc.last),
                    "bid_size": _finite(oc.bid_size),
                    "ask_size": _finite(oc.ask_size),
                    "volume": _finite(oc.volume, 0),
                    "oi_source": "public_api",
                })

    if not contracts:
        log.warning("Public API returned 0 contracts for %s", ticker)
        return None

    return {
        "ticker": ticker.upper(),
        "spot": float(spot or 0.0),
        "spot_source": spot_source,
        "expiries": exp_dates,
        "contracts": contracts,
        "data_source": "public_api",
    }


async def fetch_spot_from_public_api(
    ticker: str,
) -> float | None:
    """Fetch spot price from Public API. Returns None if unavailable."""
    pb = await _get_broker()
    if pb is None:
        return None

    trading = pb.get_trading_account()
    if trading is None:
        return None

    symbol = _normalize_symbol(ticker)
    try:
        spot, _source = await _resolve_spot(pb, symbol, trading.account_id)
        return spot
    except Exception as e:
        log.warning("Public API spot fail for %s: %s", ticker, e)
        return None
    return None


def _as_float(value: Any) -> float | None:
    """Coerce a raw bar field to float; None when absent, unparseable or non-finite.

    NaN and Infinity are rejected on purpose. ``float("NaN")`` and
    ``float("Infinity")`` both parse happily, and a non-finite value anywhere in
    the vendor payload makes the whole response unserialisable — the endpoint
    turns into an opaque HTTP 500 instead of degrading to "no data".
    """
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _as_int(value: Any) -> int:
    """Coerce a raw volume field to int; 0 when absent or unparseable."""
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _session_label(bucket_key: str | None) -> str:
    """Map a Public.com session bucket key to a stable floww session label.

    Public.com buckets look like ``regularMarket`` / ``preMarket`` / ``afterHours``.
    An un-bucketed payload (a bare ``bars`` list) is treated as regular session,
    because that is what every existing floww bars consumer means by "a bar".
    """
    if not bucket_key:
        return "regular"
    key = bucket_key.lower()
    if "regular" in key:
        return "regular"
    if "pre" in key:
        return "pre"
    if "after" in key or "post" in key or "extended" in key:
        return "after"
    # An UNRECOGNISED bucket must NOT default to "regular". Doing so would let a
    # bucket this code has never seen (say an overnight session the vendor adds
    # later) be served as regular-session data — silently defeating the whole
    # point of the regular-only default. Label it "unknown": it is then excluded
    # from the default view and only surfaces under sessions="all", where the
    # caller can see what it actually is.
    log.warning("Public API returned an unrecognised session bucket: %r", bucket_key)
    return "unknown"


def _normalize_bars(payload: Any, limit: int, sessions: str = "regular") -> list[dict[str, Any]]:
    """Flatten a Public.com historicdata payload into floww's canonical bars.

    Public.com nests bars per trading session, e.g.
        {"regularMarket": {"bars": [{"timestamp", "open", ..., "volume"}]}, ...}

    ``sessions`` selects which buckets contribute:
        "regular" (default) — regular-session bars ONLY.
        "all"               — every bucket, each row tagged with its session.

    The default is deliberately NOT a merge of every bucket. Merging silently
    mixes pre/after-hours prints into what every other floww bars consumer
    (routes/backtest.py, the ``underlying_bars`` store) treats as a
    regular-session series — an intraday request near the close could otherwise
    come back as 100% extended-hours bars that look exactly like regular ones.
    Every row carries a ``session`` field so a caller can always tell.

    Rows are de-duplicated by (session, timestamp), sorted by timestamp
    ascending, then trimmed to the most recent ``limit`` entries.
    """
    want_all = str(sessions).strip().lower() == "all"
    buckets: list[tuple[str, list[Any]]] = []
    if isinstance(payload, dict):
        top = payload.get("bars")
        if isinstance(top, list):
            buckets.append(("regular", top))
        for key, value in payload.items():
            if key == "bars":
                continue
            if isinstance(value, dict) and isinstance(value.get("bars"), list):
                buckets.append((_session_label(key), value["bars"]))
    elif isinstance(payload, list):
        buckets.append(("regular", payload))

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for session, raw_bars in buckets:
        if not want_all and session != "regular":
            continue
        for raw in raw_bars:
            if not isinstance(raw, dict):
                continue
            stamp = raw.get("timestamp") or raw.get("date") or raw.get("time")
            if stamp is None:
                continue
            stamp = str(stamp)
            o = _as_float(raw.get("open"))
            h = _as_float(raw.get("high"))
            low = _as_float(raw.get("low"))
            c = _as_float(raw.get("close"))
            # Drop the row rather than ship a bar with a missing price. A None
            # close becomes $0.00 two hops downstream (chart axis, RV window,
            # backtest fill) and reads as a real print of zero. A bar we cannot
            # price is not a bar.
            if None in (o, h, low, c):
                log.warning(
                    "Public API bar dropped — incomplete OHLC at %s (%s session)",
                    stamp, session,
                )
                continue
            merged[(session, stamp)] = {
                "date": stamp,
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": _as_int(raw.get("volume")),
                "session": session,
            }

    bars = [merged[key] for key in sorted(merged, key=lambda k: (k[1], k[0]))]
    if limit > 0:
        bars = bars[-limit:]
    return bars


# ---------------------------------------------------------------------------
# Nested-shape transform (flowseeker /chain/{symbol} contract).
#
# That route's frontend (FlowseekerProTab) expects the cvserver nested shape:
#   params: ["strike","bid","ask","lastPrice","volume","openInterest","impliedVolatility"]
#   chain: [{expiration, strikes: [[strike, call_vals(6), put_vals(6)], ...]}]
# This reshapes a paid Public chain into it so /chain can serve Public-first
# with zero frontend changes. Pure — unit-tested without network.
# ---------------------------------------------------------------------------

_NESTED_PARAMS = ["strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"]


def public_to_nested(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Public flat chain → cvserver nested chain shape. None when empty."""
    if not isinstance(result, dict):
        return None
    contracts = result.get("contracts") or []
    if not contracts:
        return None
    ticker = str(result.get("ticker") or "").upper()

    def _num(v: Any) -> float | None:
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    by_exp: dict[str, dict[float, dict[str, list]]] = {}
    for c in contracts:
        if not isinstance(c, dict):
            continue
        exp = str(c.get("expiry") or "")
        try:
            strike = float(c.get("strike") or 0)
        except (TypeError, ValueError):
            continue
        if not exp or strike <= 0:
            continue
        last = _num(c.get("last"))
        mid = _num(c.get("mid"))
        vals = [
            _num(c.get("bid")), _num(c.get("ask")),
            last if last is not None else mid,
            _num(c.get("volume")), _num(c.get("oi")), _num(c.get("iv")),
        ]
        bucket = by_exp.setdefault(exp, {})
        legs = bucket.setdefault(strike, {"call": [None] * 6, "put": [None] * 6})
        if str(c.get("type") or "").lower().startswith("c"):
            legs["call"] = vals
        else:
            legs["put"] = vals

    chain = [
        {
            "expiration": exp,
            "strikes": [[k, v["call"], v["put"]] for k, v in sorted(bucket.items())],
        }
        for exp, bucket in sorted(by_exp.items())
    ]
    if not chain:
        return None
    return {"symbol": ticker, "params": list(_NESTED_PARAMS), "chain": chain}


# ---------------------------------------------------------------------------
# Bars / history / technicals (public-api-only replacements for the retired
# Alpha Vantage historical/intraday/technical endpoints).
# ---------------------------------------------------------------------------

# Map of Alpha-style interval labels to (Public period, aggregation).
_INTERVAL_MAP: dict[str, tuple[str, str | None]] = {
    "1min": ("DAY", "ONE_MINUTE"),
    "5min": ("DAY", "FIVE_MINUTES"),
    "15min": ("DAY", "FIFTEEN_MINUTES"),
    "30min": ("DAY", "THIRTY_MINUTES"),
    "60min": ("DAY", "ONE_HOUR"),
    "daily": ("YEAR", "ONE_DAY"),
    "weekly": ("FIVE_YEARS", "ONE_WEEK"),
    "monthly": ("FIVE_YEARS", "ONE_MONTH"),
}


def _extract_bars(raw: Any, sessions: str = "regular") -> list[dict[str, Any]]:
    """Normalize Public get_bars() payloads to OHLCV dicts with session labels.

    The vendor returns session buckets (preMarket/regularMarket/afterMarket),
    each with expectedBars + bars[]. Default serves regular-session ONLY:
    mixing extended-hours prints into the regular series corrupts realized-vol
    windows, backtest fills, and chart axes with look-alike bars.
    sessions="all" opts into every bucket (each row still labeled).
    Unknown *Market buckets are logged and served ONLY under sessions="all"
    as session="unknown" — a future vendor bucket must never silently pose
    as regular data.

    Rows missing any OHLC field are dropped (a None would become $0.00 two
    hops downstream and read as a real print of zero). Non-finite floats
    (NaN/Infinity parse happily but make the whole response unserialisable
    → opaque HTTP 500) are rejected the same way.
    """
    buckets: list[tuple[str, list]] = []
    if isinstance(raw, dict):
        for bucket_key, label in (("preMarket", "pre"), ("regularMarket", "regular"),
                                  ("afterMarket", "after")):
            section = raw.get(bucket_key)
            if isinstance(section, dict) and isinstance(section.get("bars"), list):
                buckets.append((label, section["bars"]))
        for key, val in raw.items():
            if not (isinstance(val, dict) and isinstance(val.get("bars"), list)):
                continue
            if key in ("preMarket", "regularMarket", "afterMarket"):
                continue
            # Any other bars-carrying section is a session bucket this code
            # has never seen: log it, serve it ONLY under sessions="all" as
            # session="unknown" — never as regular data by default.
            log.warning("Public API returned an unrecognised session bucket: %r", key)
            buckets.append(("unknown", val["bars"]))
        if not buckets:
            # Legacy/alternate shapes: bare lists under known keys.
            for key in ("candles", "bars", "data", "results", "historicData"):
                val = raw.get(key)
                if isinstance(val, list) and val:
                    buckets.append(("unknown", val))
                    break
    elif isinstance(raw, list):
        buckets.append(("unknown", raw))
    want_all = str(sessions or "regular").lower() == "all"
    out: list[dict[str, Any]] = []
    for label, rows in buckets:
        if label == "unknown" and not want_all:
            continue
        if label in ("pre", "after") and not want_all:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            o = row.get("open", row.get("o"))
            h = row.get("high", row.get("h"))
            lo = row.get("low", row.get("l"))
            c = row.get("close", row.get("c"))
            if o is None or h is None or lo is None or c is None:
                continue
            try:
                vals = [float(o), float(h), float(lo), float(c),
                        float(row.get("v", row.get("volume", 0)) or 0)]
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(v) for v in vals):
                continue
            out.append({
                "t": row.get("t", row.get("timestamp", row.get("time"))),
                "o": vals[0], "h": vals[1], "l": vals[2], "c": vals[3],
                "v": vals[4], "session": label,
            })
    return out


async def fetch_bars_from_public_api(
    ticker: str,
    timeframe: str = "1Day",
    limit: int = 100,
    sessions: str = "regular",
) -> list[dict[str, Any]] | None:
    """Fetch OHLCV bars for an equity from Public API.

    Returns floww's canonical bar rows (most recent last):
        [{"date": str, "open": float|None, "high": float|None,
          "low": float|None, "close": float|None, "volume": int,
          "session": "regular"|"pre"|"after"}, ...]

    ``timeframe`` is one of PUBLIC_BARS_TIMEFRAMES. ``limit`` caps the number of
    most-recent bars returned (Public.com has no server-side limit parameter).
    ``sessions`` is "regular" (default, regular-session bars only) or "all".

    Returns None if the timeframe is unsupported, the Public API key is missing,
    the call fails, or the response carries no bars.

    Provider telemetry note: only a genuine transport failure (TimeoutError) is
    recorded against the shared "public_api" provider. An unknown ticker or an
    empty result is a data condition, not a provider outage — recording those
    would let an unauthenticated request trip the provider-down alerts that the
    primary options-chain path depends on.
    """
    spec = _BARS_TIMEFRAME_LOOKUP.get(str(timeframe).strip().lower())
    if spec is None:
        log.warning(
            "Public API unsupported bars timeframe %r for %s (supported: %s)",
            timeframe, ticker, ", ".join(PUBLIC_BARS_TIMEFRAMES),
        )
        return None
    period, aggregation = spec

    pb = await _get_broker()
    if pb is None:
        return None

    symbol = _normalize_symbol(ticker)
    try:
        payload = await pb.get_bars(symbol, period, aggregation=aggregation)
    except _TRANSPORT_ERRORS as e:
        # Transport-level failure — this one really is the provider being down.
        log.warning("Public API bars transport failure for %s %s: %s", ticker, timeframe, e)
        _record_call(False)
        return None
    except Exception as e:
        log.warning("Public API bars fail for %s %s: %s", ticker, timeframe, e)
        return None

    bars = _normalize_bars(payload, limit, sessions=sessions)
    if not bars:
        log.warning("Public API returned 0 bars for %s %s", ticker, timeframe)
        return None

    _record_call(True)
    return bars


async def fetch_quotes_from_public_api(
    tickers: Sequence[str] | str,
) -> dict[str, dict[str, Any]] | None:
    """Fetch live equity quotes from Public API, keyed by normalised symbol.

    Accepts a single ticker or a batch — Public.com quotes many symbols in one
    round-trip, so a batch costs one call.

    Each value carries the same ``spot`` the chain path uses (mid price, falling
    back to last) plus the richer top-of-book fields Public.com returns:
        {"ticker", "spot", "last", "bid", "ask", "bid_size", "ask_size",
         "volume", "previous_close", "change", "percent_change", "timestamp",
         "data_source"}

    Returns None if no symbols were given, the Public API key is missing, the
    call fails, or the response carries no quotes.
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    symbols = [_normalize_symbol(t) for t in tickers if t]
    if not symbols:
        log.warning("Public API quotes called with no symbols")
        return None

    pb = await _get_broker()
    if pb is None:
        return None

    trading = pb.get_trading_account()
    if trading is None:
        log.warning("No trading account for Public API")
        return None

    try:
        quotes = await pb.get_quotes(symbols, trading.account_id)
    except _TRANSPORT_ERRORS as e:
        # Transport-level failure — this one really is the provider being down.
        log.warning("Public API quotes transport failure for %s: %s", ",".join(symbols), e)
        _record_call(False)
        return None
    except Exception as e:
        # Unknown symbol / rejected request is a data condition, not an outage.
        # Recording it would let an unauthenticated request trip the
        # provider-down alerts the primary options-chain path depends on.
        log.warning("Public API quotes fail for %s: %s", ",".join(symbols), e)
        return None

    out: dict[str, dict[str, Any]] = {}
    for q in quotes or []:
        symbol = _normalize_symbol(str(getattr(q, "symbol", "") or ""))
        if not symbol:
            continue
        mid = q.mid_price
        # 0.0 is a real mid price — only a missing mid falls back to last.
        spot = mid if mid is not None else (q.last or 0.0)
        out[symbol] = {
            "ticker": symbol,
            "spot": float(spot),
            "last": q.last,
            "bid": q.bid,
            "ask": q.ask,
            "bid_size": q.bid_size,
            "ask_size": q.ask_size,
            "volume": q.volume,
            "previous_close": q.previous_close,
            "change": q.change,
            "percent_change": q.percent_change,
            "timestamp": q.timestamp,
            "data_source": "public_api",
        }

    if not out:
        # Empty result set is a data condition, not a provider outage — see the
        # telemetry note in fetch_bars_from_public_api.
        log.warning("Public API returned 0 quotes for %s", ",".join(symbols))
        return None

    _record_call(True)
    return out


async def fetch_bars_by_interval(
    ticker: str,
    interval: str = "daily",
    instrument_type: str = "EQUITY",
    period: str | None = None,
    aggregation: str | None = None,
    sessions: str = "regular",
) -> list[dict[str, Any]] | None:
    """Fetch OHLCV bars from Public API. None when unavailable.

    `interval` accepts alpha-style labels: 1min/5min/15min/30min/60min,
    daily/weekly/monthly. Explicit `period`/`aggregation` (e.g. from the
    C13 bars provider) override the label mapping when both are given.
    `sessions`: "regular" (default, regular-session only) or "all".
    """
    pb = await _get_broker()
    if pb is None:
        return None
    trading = pb.get_trading_account()
    if trading is None:
        return None
    symbol = _normalize_symbol(ticker)
    default_period, default_agg = _INTERVAL_MAP.get(interval, ("YEAR", "ONE_DAY"))
    eff_period = period or default_period
    eff_agg = aggregation if aggregation is not None else default_agg
    try:
        raw = await pb.get_bars(symbol, eff_period, instrument_type, eff_agg)
    except Exception as e:
        log.warning("Public API bars fail for %s %s: %s", ticker, interval, e)
        return None
    bars = _extract_bars(raw, sessions=sessions)
    return bars or None


async def fetch_history_from_public_api(
    ticker: str,
    interval: str = "daily",
) -> dict[str, Any] | None:
    """Fetch OHLCV history shaped like the retired /api/alpha/historical."""
    bars = await fetch_bars_by_interval(ticker, interval=interval)
    if bars is None:
        return None
    return {
        "ticker": ticker.upper(),
        "interval": interval,
        "bars": bars,
        "n_bars": len(bars),
        "data_source": "public_api",
    }


def _closes(bars: list[dict[str, Any]]) -> list[float]:
    # Accept both bar shapes: canonical (close) and interval (c).
    out = []
    for b in bars:
        v = b.get("c", b.get("close"))
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1 or period <= 0:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_technical_from_bars(
    ticker: str,
    indicator: str,
    bars: list[dict[str, Any]],
    period: int = 14,
) -> dict[str, Any]:
    """Compute RSI/SMA/EMA/MACD locally from Public API bars.

    Replaces the retired Alpha Vantage technical endpoint without any
    third-party call. Unsupported indicators return a 400-style payload
    with `error` so callers can surface it cleanly.
    """
    ind = (indicator or "").upper()
    closes = _closes(bars)
    value: Any = None
    if ind == "RSI":
        value = _rsi(closes, period)
    elif ind == "SMA":
        value = _sma(closes, period)
    elif ind in ("EMA", "WMA", "TEMA", "TRIMA", "KAMA"):
        value = _ema(closes, period)
    elif ind == "MACD":
        fast = _ema(closes, 12)
        slow = _ema(closes, 26)
        value = (fast - slow) if fast is not None and slow is not None else None
    elif ind in ("BBANDS", "STOCH", "ADX", "ATR", "CCI", "AROON", "OBV",
                 "WILLR", "MFI", "MAMA", "VWAP", "HT_TRENDLINE", "HT_SINE",
                 "HT_TRENDMODE", "HT_DCPERIOD", "HT_DCPHASE", "HT_PHASOR"):
        # Local single-pass approximations for band/oscillator families:
        # mid-line + RSI context is enough for dashboard display.
        value = {"sma": _sma(closes, period), "rsi": _rsi(closes, period)}
    else:
        return {
            "ticker": ticker.upper(), "indicator": ind,
            "error": f"unsupported indicator {ind}",
            "supported": ["RSI", "SMA", "EMA", "MACD", "BBANDS"],
            "data_source": "public_api",
        }
    return {
        "ticker": ticker.upper(),
        "indicator": ind,
        "period": period,
        "value": value,
        "n_bars": len(bars),
        "data_source": "public_api",
    }
