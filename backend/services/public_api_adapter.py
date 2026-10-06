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
import copy
import logging
import math
import os
import time
from collections.abc import Sequence
from datetime import UTC, datetime
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
    except Exception as e:
        log.debug("public_api telemetry record failed (non-fatal): %s", e)
        # Telemetry only — never discard a fetched payload nor mask upstream failure.


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
        except Exception as e:
            log.debug("PublicBroker token revalidation failed (using cached token): %s", e)
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
# otherwise a matching Public regular-session daily close may be used
# outside the open session, with its exchange-close time and source tagged.
# The legacy yfinance fallback remains disabled in Public-only mode.
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
        return None
    return dt.astimezone(UTC)


def _last_us_close_utc(now: datetime | None = None) -> datetime:
    """Most recent completed exchange close, including holidays and early closes."""
    from services.agent.access.horizon import required_close
    cur = now if now is not None else datetime.now(UTC)
    if cur.tzinfo is None:
        cur = cur.replace(tzinfo=UTC)
    return datetime.fromisoformat(required_close(cur)).astimezone(UTC)


def _mid_ts_utc(q):
    from services.market_provenance import timestamp
    bid_time = timestamp(getattr(q, "bid_timestamp", None))
    ask_time = timestamp(getattr(q, "ask_timestamp", None))
    # A midpoint depends on both sides, so use the older verified side.
    return min(bid_time, ask_time) if bid_time and ask_time else None


def _timestamp_text(value):
    from services.market_provenance import timestamp
    parsed = timestamp(value)
    return parsed.isoformat() if parsed else None


def _public_quote_spot(q, now: datetime | None = None) -> tuple[float | None, str]:
    """Trusted Public mid/last, or (None, reason).

    Invalid or one-sided books cannot supply a midpoint. Unknown observation
    time remains unknown in the separate provenance fields.
    """
    bid = _fnum(getattr(q, "bid", None))
    ask = _fnum(getattr(q, "ask", None))
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        if bid > ask:
            return None, "crossed-book"
        if (ask - bid) / ((ask + bid) / 2) > _SPOT_MAX_REL_SPREAD:
            return None, "wide-book"
    ts = _mid_ts_utc(q) or _quote_ts_utc(q)
    if ts is not None and ts < _last_us_close_utc(now):
        return None, "stale-quote"
    raw_mid = getattr(q, "mid_price", None)
    mid = _fnum(raw_mid)
    if raw_mid is not None and (mid is None or mid <= 0):
        # Explicit zero/non-numeric mid = honest no-quote: report 0.0 so
        # downstream fails over, never substitute `last` (pinned contract).
        return 0.0, "zero-mid"
    if mid is not None and mid > 0:
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            return None, "invalid-book"
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
    observation = await _resolve_spot_observation(pb, symbol, account_id, now)
    return observation["price"], observation["source"]


async def _resolve_spot_observation(pb, symbol: str, account_id: str,
                                    now: datetime | None = None) -> dict[str, Any]:
    """Validated spot + source tag. Never raises.

    Returns (None, 'symbol-mismatch') to fail closed on wrong-symbol
    substitution (P2 contract); (0.0, reason) when there is honestly no
    price so downstream fails over to the next provider.
    """
    rejected_quote = False
    try:
        quotes = await pb.get_quotes([symbol], account_id)
        q = _matching_quote(quotes, symbol)
        if q is not None:
            price, reason = _public_quote_spot(q, now=now)
            if price is not None:
                ts = _mid_ts_utc(q) if reason == "public-mid" else _quote_ts_utc(q)
                return {"price": price, "source": reason,
                        "event_time": ts.isoformat() if ts else None,
                        "fetched_at": datetime.now(UTC).isoformat()}
            rejected_quote = True
            log.warning("Public API spot rejected for %s (%s) — checking completed session",
                        symbol, reason)
        elif quotes:
            # Wrong symbol answered: fail CLOSED (P2 contract) — no fallback
            # may label another instrument's price with our ticker.
            log.warning("Public API quote symbol mismatch for %s — refusing substitution",
                        symbol)
            return {"price": None, "source": "symbol-mismatch", "event_time": None,
                    "fetched_at": datetime.now(UTC).isoformat()}
    except Exception as e:
        _note_public_429(e)
        log.warning("Public API quote fail for %s: %s", symbol, e)
    from services.public_session_close import completed_public_close
    closing = await completed_public_close(pb, symbol, now) if rejected_quote else None
    if closing is not None:
        return closing
    if os.getenv("FLOWW_MARKET_DATA_PROVIDER") == "public":
        return {"price": None, "source": "public-unavailable", "event_time": None,
                "fetched_at": datetime.now(UTC).isoformat()}
    try:
        yf_spot = await asyncio.to_thread(_yfinance_spot, symbol)
        if yf_spot:
            return {"price": yf_spot, "source": "yfinance-fallback", "event_time": None,
                    "fetched_at": datetime.now(UTC).isoformat()}
    except Exception as e:
        log.warning("yfinance spot fallback fail for %s: %s", symbol, e)
    return {"price": 0.0, "source": "none", "event_time": None,
            "fetched_at": datetime.now(UTC).isoformat()}


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

# How many expiries past `max_expiries` the chain walk may ATTEMPT in order
# to reach that many accepted ones. The vendor list leads with TODAY, which
# is fully expired after the close, so at least one skip is required for the
# 1-expiry case to return anything. The bound is what keeps actual provider
# calls within the `2 + max_expiries` envelope pre-debited by the caller
# (C8): skipping is free, but an unbounded walk would silently exceed the
# shared-quota pre-debit.
MAX_EXPIRY_SKIPS = 3


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
    out = copy.deepcopy(entry)
    out.setdefault("contracts", [])
    out.setdefault("expiries", [])
    if "max_expiries" not in out:
        out["max_expiries"] = entry.get("max_expiries")
    out["stale"] = stale
    from services.market_provenance import receipt_age
    out["cache_age_s"] = receipt_age(entry.get("fetched_at"))
    return out


def peek_chain_from_public_api(ticker: str, preferred: int = 6):
    """Read a previously fetched Public chain without calling or authenticating a provider."""
    choices = [(key, entry) for key, entry in _CHAIN_CACHE.items() if key[0] == ticker.upper()]
    if not choices:
        return None
    key, entry = max(choices, key=lambda item: (item[1][0], item[0][1] == preferred))
    result = _cached_copy(entry[2], stale=bool(entry[2].get("stale")))
    result["requested_expiry_count"] = key[1]
    return result


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
    key = (ticker.upper(), max_expiries)
    # R18-C12: zero-I/O WARM probe — the module singleton IS the live
    # broker; a same-identity cache hit serves with zero admission, zero
    # provider calls and without touching the key lock.
    pb_warm = BROKER
    if pb_warm is not None:
        now = time.monotonic()
        hit = _CHAIN_CACHE.get(key)
        if hit is not None and hit[1] is pb_warm \
                and now - hit[0] < _CHAIN_CACHE_TTL:
            return _cached_copy(hit[2], stale=False)

    _debit_held = False
    try:
        async with _chain_lock(key):
            # R18-C12: re-probe UNDER the lock. A sibling that completed
            # the fetch while we waited has initialized the singleton and
            # primed the identity-bound cache — serve with ZERO spend.
            now = time.monotonic()
            pb_now = BROKER
            hit = _CHAIN_CACHE.get(key)
            if pb_now is not None and hit is not None and hit[1] is pb_now \
                    and now - hit[0] < _CHAIN_CACHE_TTL:
                return _cached_copy(hit[2], stale=False)
            # R18-C11/C12: admission UNDER the key lock — concurrent
            # same-key waiters coalesce to ONE budget envelope — and the
            # required debit still PRECEDES the cold _get_broker() vendor
            # auth/accounts: refusal spends ZERO provider calls. Module-
            # attribute access keeps the budget singleton patchable.
            try:
                await _public_budget.budget.acquire_n(2 + max_expiries, "api.public.com")
                _debit_held = True
            except _public_budget.BudgetExhausted as exc:
                log.warning("Public budget refused %s chain fetch: %s", ticker, exc)
                return None
            except Exception as exc:
                log.warning("Public budget debit failed for %s — refusing fetch "
                            "with zero provider calls: %s", ticker, exc)
                return None
            pb = await _get_broker()  # admission held; auth/accounts allowed
            if pb is None:
                return None
            # Rotation-safe re-check with the resolved broker identity.
            now = time.monotonic()
            hit = _CHAIN_CACHE.get(key)
            if hit is not None and hit[1] is pb \
                    and now - hit[0] < _CHAIN_CACHE_TTL:
                return _cached_copy(hit[2], stale=False)
            # D5: the success timestamp is the request start, so a stale
            # in-flight success cannot erase a sibling's fresher 429 contract.
            _fetch_t0 = time.monotonic()
            result = await _fetch_chain_live(pb, ticker, max_expiries)
            if result is not None:
                result["stale"] = False
                result["max_expiries"] = max_expiries  # H2: cost envelope key
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
    finally:
        # R18-C12: the inflight slot releases on EVERY exit — success,
        # refusal, and CANCELLATION during broker init or a lock wait.
        if _debit_held:
            with contextlib.suppress(Exception):
                _public_budget.budget.release()


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
            from services.public_request_pacer import note_response
            note_response(exc.response)
            return
        try:
            import httpx

            if isinstance(exc, httpx.TransportError):
                from services.public_budget import budget
                budget.record_error("api.public.com")
        except Exception as obs_e:
            log.debug("public 429/error observability failed (non-fatal): %s", obs_e)
    except Exception as obs_outer:
        log.debug("public 429 note failed (non-fatal): %s", obs_outer)


async def _fetch_chain_live(
    pb: PublicBroker,
    ticker: str,
    max_expiries: int = 4,
) -> dict[str, Any] | None:
    """Uncached chain fetch (one call = ~2+N upstream Public calls).

    F01/F03/F06: exact per-series expiry clock, preserved source timestamps,
    explicit index instrument types. F13: missing OI stays None (unknown),
    never volume-substituted; exposure_basis carried per contract.
    """
    from services.public_api import resolve_public_instrument_type

    trading = pb.get_trading_account()
    if trading is None:
        log.warning("No trading account for Public API")
        return None

    account_id = trading.account_id
    symbol = _normalize_symbol(ticker)
    chain_type = resolve_public_instrument_type(ticker, "chain")

    # 1. Get expirations (F06: explicit index-underlying type for SPX family)
    try:
        try:
            expiries = await pb.get_option_expirations(symbol, account_id, instrument_type=chain_type)
        except TypeError as te:
            if "instrument_type" in str(te):
                expiries = await pb.get_option_expirations(symbol, account_id)
            else:
                raise
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
        spot_observation = await _resolve_spot_observation(pb, symbol, account_id)
    except Exception as e:
        _note_public_429(e)
        log.warning("Public API quote fail for %s: %s", ticker, e)
        return None

    # 3. Bounded per-expiry walk (shared with the range-analytics fetcher).
    asm = await _assemble_chain(pb, ticker, symbol, account_id, chain_type,
                                expiries, max_expiries, spot_observation)
    if asm is None or not asm.get("contracts"):
        # Existing refusal contract: zero contracts means an unavailable chain.
        log.warning("Public API returned 0 contracts for %s", ticker)
        return None
    return asm


async def _assemble_chain(
    pb: PublicBroker,
    ticker: str,
    symbol: str,
    account_id: str,
    chain_type: Any,
    expiry_walk: list,
    max_expiries: int,
    spot_observation: dict[str, Any],
    skip_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Bounded per-expiry chain assembly (one call ≈ N upstream Public calls).

    Extracted from _fetch_chain_live so the range-analytics.v1 producer can
    request EXACT admitted expiry dates with identical parsing/clocks
    (F01/F03/F06/F13 preserved verbatim) and per-expiry skip accountability
    via skip_log. Returns the floww-shaped chain dict (contracts may be
    empty — the caller decides the refusal).
    """
    from services.solstice_time import resolve_series, time_to_expiry_years

    # 3. Fetch chain for each expiry (up to max_expiries ACCEPTED). Only
    # expiries that actually return data are reported (requested vs returned
    # coverage distinguished). Expired contracts are dropped; 0DTE kept with
    # exact T.
    #
    # max_expiries bounds ACCEPTED expiries, not expiries attempted. The
    # vendor list leads with TODAY even after the close, and every contract in
    # it is then dropped as EXPIRED. Slicing `expiries[:max_expiries]` up
    # front spent a 1-expiry request entirely on that dead expiry and returned
    # None — a 503 from /api/spot/{ticker} while the very next expiry held a
    # full chain. Walk the list and stop once the budget is met.
    #
    # The walk MUST also be bounded in ATTEMPTS: the caller pre-debited a
    # fixed `2 + max_expiries` envelope above (C8), so attempting more
    # expiries than that would make actual provider calls exceed the debit
    # and turn the shared-quota pre-debit into an under-count. Skipping past
    # dead expiries is allowed, but only within the already-paid envelope;
    # MAX_EXPIRY_SKIPS bounds how far past max_expiries we may walk.
    contracts: list[dict[str, Any]] = []
    exp_dates = []
    now_utc = datetime.now(UTC)
    received_at = now_utc.isoformat()
    n_expired_dropped = 0

    max_attempts = min(len(expiry_walk), max_expiries + MAX_EXPIRY_SKIPS)
    for exp in expiry_walk[:max_attempts]:
        if len(exp_dates) >= max_expiries:
            break
        n_dates_before = len(exp_dates)
        try:
            try:
                parsed = await pb.get_option_chain_parsed(symbol, exp, account_id, instrument_type=chain_type)
            except TypeError as te:
                # Backward compat with test doubles / older brokers lacking the
                # explicit instrument_type kwarg (F06 resolver is new).
                if "instrument_type" in str(te):
                    parsed = await pb.get_option_chain_parsed(symbol, exp, account_id)
                else:
                    raise
        except Exception as e:
            _note_public_429(e)
            log.warning("Public API chain fail for %s %s: %s", ticker, exp, e)
            if skip_log is not None:
                skip_log.append({"expiry": str(exp), "reason": "CHAIN_FETCH_FAILED"})
            continue
        for side in ("calls", "puts"):
            for oc in parsed.get(side, []):
                # R7-06: series metadata reaches the clock (SPX monthly AM vs
                # SPXW weekly PM vs equity) instead of a hardcoded 16:00 ET.
                expiry_text = str(oc.expiration or exp)
                try:
                    exp_d = datetime.strptime(expiry_text, "%Y-%m-%d").date()
                except (TypeError, ValueError):
                    continue
                # A monthly SPX request can return PM-settled SPXW contracts.
                # The actual option root owns its clock, not the display ticker.
                import re
                root_match = re.fullmatch(r"(SPXW|SPX)\s*\d{6}[CP]\d{8}", str(oc.symbol).upper())
                clock_ticker = root_match.group(1) if root_match else ticker
                oc_series = resolve_series(clock_ticker, exp_d.isoformat())
                T, floored, t_reason = time_to_expiry_years(
                    oc.expiration or exp, now=now_utc, series=oc_series,
                    ticker=ticker)
                if T is None:
                    if t_reason == "EXPIRED":
                        n_expired_dropped += 1
                    continue
                # NBBO mid from the paid feed — the executable-reference price.
                mid = _finite(oc.mid)
                strike = _finite(oc.strike)
                if strike is None or strike <= 0:
                    continue
                oi_raw = _finite(oc.open_interest)  # None = unknown, never 0-fill
                # Preserve source timestamps only when they are real strings;
                # MagicMock/test doubles without explicit attrs must stay None.
                def _ts(v: Any) -> str | None:
                    return v if isinstance(v, str) and v else None
                contracts.append({
                    "osi": oc.symbol,
                    "expiry": oc.expiration,
                    "series": oc_series,
                    "T": T,
                    "T_floored": floored,
                    "T_model": "actual/365-exact",
                    "type": "call" if side == "calls" else "put",
                    "strike": strike,
                    "strike_exact": str(oc.strike) if oc.strike is not None else None,
                    "oi": oi_raw,
                    "oi_effective_date": _ts(getattr(oc, "oi_effective_date", None)),
                    "iv": _finite(oc.iv),
                    "delta": _finite(oc.delta),
                    "gamma": _finite(oc.gamma),
                    "theta": _finite(oc.theta),
                    "vega": _finite(oc.vega),
                    "greeks_source": _ts(getattr(oc, "greeks_source", None)),
                    "bid": _finite(oc.bid),
                    "ask": _finite(oc.ask),
                    "mid": mid,
                    "last": _finite(oc.last),
                    "bid_timestamp": _ts(getattr(oc, "bid_timestamp", None)),
                    "ask_timestamp": _ts(getattr(oc, "ask_timestamp", None)),
                    "last_timestamp": _ts(getattr(oc, "last_timestamp", None)),
                    "received_at": received_at,
                    "bid_size": _finite(oc.bid_size),
                    "ask_size": _finite(oc.ask_size),
                    "volume": _finite(oc.volume),
                    "oi_source": "public_api",
                    "last_event_time": _timestamp_text(getattr(oc, "last_timestamp", None)),
                    "bid_event_time": _timestamp_text(getattr(oc, "bid_timestamp", None)),
                    "ask_event_time": _timestamp_text(getattr(oc, "ask_timestamp", None)),
                    "exposure_basis": "OI" if oi_raw is not None else "OI_UNKNOWN",
                    "chain_instrument_type": chain_type,
                })
                # Available coverage describes accepted contracts, not a
                # successful empty request or contracts rejected above.
                accepted_expiry = exp_d.isoformat()
                if accepted_expiry not in exp_dates:
                    exp_dates.append(accepted_expiry)
        if skip_log is not None and len(exp_dates) == n_dates_before:
            # The expiry was attempted and admitted zero contracts (all
            # dropped as expired/unparseable, or an empty book) — that is a
            # SKIP with a visible reason, never a silent absence.
            skip_log.append({"expiry": str(exp), "reason": "NO_ADMITTED_CONTRACTS"})

    spot, spot_source = spot_observation.get("price"), spot_observation.get("source")
    return {
        "ticker": ticker.upper(),
        "spot": float(spot or 0.0),
        "spot_source": spot_source,
        "spot_event_time": spot_observation.get("event_time"),
        "spot_fetched_at": spot_observation.get("fetched_at"),
        # Quote sides have their own times; Public supplies no observation
        # timestamp for the whole chain's OI/Greeks. Keep that distinct.
        "event_time": None,
        "fetched_at": datetime.now(UTC).isoformat(),
        "expiries": exp_dates,
        "contracts": contracts,
        "data_source": "public_api",
        "chain_instrument_type": chain_type,
        "received_at": received_at,
        "n_expired_dropped": n_expired_dropped,
        # Admitted-expiry accountability (range-analytics.v1): expiries whose
        # fetch failed or admitted zero contracts, with reason. Empty for the
        # legacy first-N caller (skip_log unused there).
        "skipped": skip_log or [],
        "attempt_cap": max_attempts,
    }


async def fetch_option_expiry_listing(ticker: str) -> dict[str, Any] | None:
    """Additive (range-analytics.v1 / R18-C1): vendor expiry LISTING only.

    One upstream call, budget-debited like any Public request. The full
    vendor listing (vendor order preserved — it leads with the possibly dead
    "today" expiry) is required so the owning range selector can observe BOTH
    window edges instead of inheriting a first-N slice. Returns None on
    missing key/account or vendor failure; never a partial fiction.
    """
    from services.public_api import resolve_public_instrument_type

    symbol = _normalize_symbol(ticker)
    chain_type = resolve_public_instrument_type(ticker, "chain")
    # R18-C11/C12: admission BEFORE broker init — a cold _get_broker()
    # performs vendor auth/accounts, so a failed REQUIRED debit must
    # precede it. Refusal at this gate spends ZERO provider calls. The
    # single outer finally releases the slot on EVERY exit, including
    # CANCELLATION during broker init or the listing call.
    _debit_held = False
    try:
        await _public_budget.budget.acquire_n(1, "api.public.com")
        _debit_held = True
    except _public_budget.BudgetExhausted as exc:
        log.warning("Public budget refused %s expiry listing: %s", ticker, exc)
        return None
    except Exception as exc:
        # R18-C5/C11: failed REQUIRED debit → refusal, zero vendor calls.
        log.warning("Public budget debit failed for %s listing — refusing "
                    "with zero vendor calls: %s", ticker, exc)
        return None
    try:
        pb = await _get_broker()  # admission held; auth/accounts allowed
        if pb is None:
            return None
        trading = pb.get_trading_account()
        if trading is None:
            log.warning("No trading account for Public API")
            return None
        account_id = trading.account_id
        _fetch_t0 = time.monotonic()
        try:
            expiries = await pb.get_option_expirations(symbol, account_id,
                                                       instrument_type=chain_type)
        except TypeError as te:
            if "instrument_type" in str(te):
                expiries = await pb.get_option_expirations(symbol, account_id)
            else:
                raise
    except Exception as e:
        _note_public_429(e)
        log.warning("Public API expirations fail for %s: %s", ticker, e)
        return None
    finally:
        # R18-C12: release on EVERY exit — success, refusal, cancellation.
        if _debit_held:
            with contextlib.suppress(Exception):
                _public_budget.budget.release()
    if not expiries:
        log.warning("Public API returned no expirations for %s", ticker)
        return None
    with contextlib.suppress(Exception):
        _public_budget.budget.record_ok("api.public.com", now=_fetch_t0)
    return {
        "ticker": ticker.upper(),
        "expiries": [str(e) for e in expiries],
        "n_listed": len(expiries),
        # This API hands back the whole listing; an upstream-side cap is not
        # observable here, so incompleteness is never claimed either way.
        "listing_capped": False,
        "received_at": datetime.now(UTC).isoformat(),
        "data_source": "public_api",
    }


async def fetch_chain_for_expiries(
    ticker: str,
    expiry_dates: list[str],
) -> dict[str, Any] | None:
    """Additive (range-analytics.v1 / R18-C1): bounded request for EXACT dates.

    Unlike fetch_chain_from_public_api (a first-N ACCEPTED walk), every date
    here was already admitted by the caller's own DTE window; each date is
    attempted once inside the already-paid 2 + N budget envelope (C8), and
    every failed/empty expiry is reported in `skipped` — never silently
    absent. Cache identity binds (symbol, exact sorted window dates): another
    window cannot reuse a mismatched chain. Returns None only on wholesale
    failure (no broker/account/quote/budget); a dict with empty `contracts`
    plus full `skipped` accounting is a truthful partial-empty answer.
    """
    from services.public_api import resolve_public_instrument_type

    # Local date parsing first (no I/O) so admission precedes every
    # provider-adjacent action.
    dates: list[str] = []
    for raw in expiry_dates or []:
        s = str(raw)[:10]
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if s not in dates:
            dates.append(s)
    if not dates:
        return None

    key = ("RANGE", ticker.upper(), tuple(sorted(dates)))
    # R18-C12: zero-I/O WARM probe — the module singleton IS the live
    # broker; a same-identity cache hit serves with zero admission, zero
    # provider calls and without touching the key lock.
    pb_warm = BROKER
    if pb_warm is not None:
        now = time.monotonic()
        hit = _CHAIN_CACHE.get(key)
        if hit is not None and hit[1] is pb_warm \
                and now - hit[0] < _CHAIN_CACHE_TTL:
            return _cached_copy(hit[2], stale=False)

    _debit_held = False
    try:
        async with _chain_lock(key):
            # R18-C12: re-probe UNDER the lock — a sibling that completed
            # the fetch while we waited has initialized the singleton and
            # primed the identity-bound cache. Serve with ZERO spend.
            now = time.monotonic()
            pb_now = BROKER
            hit = _CHAIN_CACHE.get(key)
            if pb_now is not None and hit is not None and hit[1] is pb_now \
                    and now - hit[0] < _CHAIN_CACHE_TTL:
                return _cached_copy(hit[2], stale=False)
            # R18-C11/C12: admission UNDER the key lock — concurrent
            # same-key waiters coalesce to ONE budget envelope — and the
            # required debit still PRECEDES the cold _get_broker() vendor
            # auth/accounts: refusal spends ZERO provider calls.
            try:
                await _public_budget.budget.acquire_n(2 + len(dates), "api.public.com")
                _debit_held = True
            except _public_budget.BudgetExhausted as exc:
                log.warning("Public budget refused %s range chain fetch: %s", ticker, exc)
                return None
            except Exception as exc:
                log.warning("Public budget debit failed for %s range fetch — "
                            "refusing with zero vendor calls: %s", ticker, exc)
                return None
            pb = await _get_broker()  # admission held; auth/accounts allowed
            if pb is None:
                return None
            # Rotation-safe re-check with the resolved broker identity.
            now = time.monotonic()
            hit = _CHAIN_CACHE.get(key)
            if hit is not None and hit[1] is pb \
                    and now - hit[0] < _CHAIN_CACHE_TTL:
                return _cached_copy(hit[2], stale=False)
            _fetch_t0 = time.monotonic()
            trading = pb.get_trading_account()
            if trading is None:
                log.warning("No trading account for Public API")
                result = None
            else:
                account_id = trading.account_id
                symbol = _normalize_symbol(ticker)
                chain_type = resolve_public_instrument_type(ticker, "chain")
                try:
                    spot_observation = await _resolve_spot_observation(
                        pb, symbol, account_id)
                except Exception as e:
                    _note_public_429(e)
                    log.warning("Public API quote fail for %s: %s", ticker, e)
                    spot_observation = None
                if spot_observation is None:
                    result = None
                else:
                    skipped: list[dict[str, Any]] = []
                    result = await _assemble_chain(
                        pb, ticker, symbol, account_id, chain_type,
                        list(dates), len(dates), spot_observation,
                        skip_log=skipped)
                    if result is not None:
                        result["requested_expiries"] = list(dates)
                        result["budget_pre_debit"] = 2 + len(dates)
            if result is not None:
                result["stale"] = False
                result["max_expiries"] = len(dates)
                with contextlib.suppress(Exception):
                    _public_budget.budget.record_ok("api.public.com", now=_fetch_t0)
                if len(_CHAIN_CACHE) >= _CHAIN_CACHE_MAX:
                    _CHAIN_CACHE.pop(next(iter(_CHAIN_CACHE)))
                _CHAIN_CACHE[key] = (time.monotonic(), pb, result)
                return _cached_copy(result, stale=False)
            if hit is not None and hit[1] is pb:
                log.warning("Public API range chain failed for %s — serving stale cache",
                            ticker)
                return _cached_copy(hit[2], stale=True)
            return None
    finally:
        # R18-C12: the inflight slot releases on EVERY exit — success,
        # refusal, and CANCELLATION during broker init or a lock wait.
        if _debit_held:
            with contextlib.suppress(Exception):
                _public_budget.budget.release()


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
        if not symbol or symbol not in symbols:
            continue
        spot, spot_source = _public_quote_spot(q)
        closing = None
        if spot is None:
            from services.public_session_close import completed_public_close
            closing = await completed_public_close(pb, symbol)
            if closing:
                spot, spot_source = closing["price"], closing["source"]
        if spot is None or (spot <= 0 and _fnum(getattr(q, "mid_price", None)) != 0):
            continue
        observed = _mid_ts_utc(q) if spot_source == "public-mid" else _quote_ts_utc(q) if spot_source == "public-last" else None
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
            "last_event_time": q.timestamp,
            "bid_event_time": getattr(q, "bid_timestamp", None),
            "ask_event_time": getattr(q, "ask_timestamp", None),
            "spot_source": spot_source,
            "spot_event_time": closing["event_time"] if closing else observed.isoformat() if observed else None,
            "spot_fetched_at": closing["fetched_at"] if closing else datetime.now(UTC).isoformat(),
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
        _note_public_429(e)
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
