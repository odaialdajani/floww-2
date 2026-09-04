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
import logging
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from services.public_api import PublicBroker

log = logging.getLogger(__name__)

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
    """Lazy-init the singleton PublicBroker (auths on first use)."""
    global BROKER
    if BROKER is not None:
        return BROKER

    import os
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


def _normalize_symbol(symbol: str) -> str:
    """Map user-facing tickers to Public.com instrument symbols."""
    return symbol.upper().replace("^", "")


async def fetch_chain_from_public_api(
    ticker: str,
    max_expiries: int = 4,
) -> dict[str, Any] | None:
    """
    Fetch options chain from Public API, return floww-shaped dict.

    Returns the same shape as fetch_spot_and_chains_merged:
        {"ticker": str, "spot": float, "expiries": [...], "contracts": [...], "data_source": "public_api"}

    Returns None if Public API key missing or call fails.
    """
    pb = await _get_broker()
    if pb is None:
        return None

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
        log.warning("Public API expirations fail for %s: %s", ticker, e)
        return None

    if not expiries:
        log.warning("Public API returned no expirations for %s", ticker)
        return None

    # 2. Get spot quote
    try:
        quotes = await pb.get_quotes([symbol], account_id)
        spot = quotes[0].mid_price if quotes else None
        if spot is None:
            spot = quotes[0].last if quotes else None
        if spot is None:
            spot = 0.0
    except Exception as e:
        log.warning("Public API quote fail for %s: %s", ticker, e)
        return None

    # 3. Fetch chain for each expiry (up to max_expiries)
    contracts: list[dict[str, Any]] = []
    exp_dates = []
    today = datetime.now(UTC).date()

    for exp in expiries[:max_expiries]:
        exp_dates.append(exp)
        try:
            parsed = await pb.get_option_chain_parsed(symbol, exp, account_id)
        except Exception as e:
            log.warning("Public API chain fail for %s %s: %s", ticker, exp, e)
            continue

        for side in ("calls", "puts"):
            for oc in parsed.get(side, []):
                try:
                    exp_d = datetime.strptime(oc.expiration, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                T = max((exp_d - today).days, 1) / 365.0
                contracts.append({
                    "expiry": oc.expiration,
                    "T": T,
                    # cvserver convention: lowercase "call"/"put".
                    # gex_core.py and analytics.py compare c["type"] == "call"
                    # exactly — uppercase here would flip every GEX sign.
                    "type": "call" if side == "calls" else "put",
                    "strike": oc.strike,
                    "oi": oc.open_interest or 0,
                    "iv": oc.iv or 0.0,
                    "delta": oc.delta,
                    "gamma": oc.gamma,
                    "theta": oc.theta,
                    "vega": oc.vega,
                    "bid": oc.bid,
                    "ask": oc.ask,
                    "volume": oc.volume or 0,
                    "oi_source": "public_api",
                })

    if not contracts:
        log.warning("Public API returned 0 contracts for %s", ticker)
        return None

    return {
        "ticker": ticker.upper(),
        "spot": float(spot),
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
        quotes = await pb.get_quotes([symbol], trading.account_id)
        if quotes:
            q = quotes[0]
            return q.mid_price if q.mid_price is not None else (q.last or 0.0)
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
