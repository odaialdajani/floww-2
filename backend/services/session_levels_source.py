"""Async sources for the session reference level (S5 / R10-09).

`domain/session_levels.py` holds the pure math. This module owns the part the
domain layer deliberately refuses: obtaining canonical bars over the platform's
actual supported async bar path.

WHY THIS EXISTS
===============
The private branch had a session-level helper that imported
`public_api.fetch_public_bars`. That symbol does not exist in current main --
the supported path is `services.public_api_adapter.fetch_bars_from_public_api`.
The import sat inside a broad `except`, so the AttributeError was swallowed, the
helper returned a permanent `NO_BARS`, and the level never rendered while
looking like an honest "no data" answer. This module names the real coroutine
at import time, so a rename fails loudly at startup instead of degrading every
call.

R10-09 — WHAT THIS NUMBER IS NOT
================================
The old function requested `1Day` bars and called the result an
"exposure-weighted level". Neither word was true:

- One daily row reduced to (H+L+C)/3. The volume weight had exactly one
  term, so multiplying volume by 100x changed nothing. That is a daily
  TYPICAL PRICE, not a volume-weighted price, and not intraday VWAP.
- Nothing in the computation is exposure-weighted. There is no gamma, no
  OI, no contract population anywhere in the input.

So this module now names exactly what it computes, in two explicit modes:

1. `session_bar_vwap_for_ticker` — the DEFAULT and the only mode that
   describes a volume-weighted price. It requests the finest supported
   REGULAR-SESSION intraday granularity that the platform's bar adapter
   actually exposes (`15Min`, period DAY), reduces Σ(typical·V)/ΣV over
   the requested session date, and reports the real granularity, bar
   count, coverage, provider and timestamp convention. It is a bar-based
   approximation over ONE venue's regular-session aggregated bars: not
   print-level market VWAP, not whole-market, and it says so in the
   packet on every path including failures.

2. `session_daily_typical_price_for_ticker` — the retained daily path,
   now honestly named. It is a session typical price (H+L+C)/3 with no
   volume weighting and no exposure weighting. It is NOT deprecated, it
   is just no longer called "exposure-weighted".

Neither mode asserts exchange-holiday or early-close knowledge: a
timezone/offset rule is not a trading calendar. A holiday or an early
close shows up as zero usable bars for that date, which is reported
(`NO_VOLUME`), never substituted with the prior session's value.

NESTED EVENT LOOPS
==================
These are `async def` functions that AWAIT the adapter. They never call
`asyncio.run`, `loop.run_until_complete`, or `new_event_loop`, because all
three are unavailable-or-wrong inside a running loop: `asyncio.run` raises
`RuntimeError: asyncio.run() cannot be called from a running event loop`, and
the workarounds people reach for instead (a dedicated thread, `new_event_loop`
per call) detach the coroutine from the caller's cancellation and timeout
context. The adapter is a coroutine, so awaiting it is both the simplest and
the only correct composition. `tests/services/test_session_levels_source.py`
asserts this by calling these functions from inside an already-running loop
and by statically rejecting the forbidden symbols.

LEGACY NAME
===========
`session_exposure_level_for_ticker` is retained as an explicit alias of the
daily typical-price mode, because "exposure-weighted" was never accurate for
it and a rename is a consumer decision. New code must choose a mode by name.
"""

from __future__ import annotations

from typing import Any

# Imported at module scope on purpose. A local import inside a broad `except`
# is precisely what hid the missing symbol this module replaces.
from domain.session_levels import SESSION_LEVEL_VERSION, session_exposure_level
from services.public_api_adapter import fetch_bars_from_public_api

# Public labels. Neither contains "VWAP" in a false sense, and neither
# contains "exposure".
SESSION_BAR_VWAP_LABEL = "session_bar_vwap"
SESSION_DAILY_TYPICAL_LABEL = "session_daily_typical_price"
SESSION_LEVEL_LABEL = SESSION_DAILY_TYPICAL_LABEL  # legacy constant, honest value

# Granularity actually used per mode. 15Min is the finest supported
# regular-session intraday aggregation in the bar adapter's exposed
# timeframes that still covers a full session in a bounded request; 1Min/5Min
# are supported by the adapter but cost many more rows per session for a
# price this approximates. Declared here so the packet and the test agree.
_BAR_VWAP_TIMEFRAME = "15Min"
_DAILY_TIMEFRAME = "1Day"

# Timestamp convention: the adapter returns the provider's own stamp string on
# each row; this reducer only does a date-prefix match. No timezone conversion,
# no session-boundary reconstruction, no holiday table.
_TIMESTAMP_CONVENTION = (
    "provider bar timestamp, ISO date-prefix match against the requested "
    "session date; no timezone conversion and no exchange calendar"
)

_NOT_MARKET_VWAP = (
    "Bar-weighted approximation over ONE venue's regular-session aggregated "
    "bars using (H+L+C)/3 as the price proxy. This is NOT market VWAP: it is "
    "not print-weighted, not whole-market, not computed from trade prices, and "
    "not an exposure-weighted quantity (no gamma, OI or contract population "
    "enters the computation)."
)

_NOT_EXPOSURE_WEIGHTED = (
    "A daily session typical price (H+L+C)/3. NOT volume-weighted (a single "
    "daily bar makes the volume weight vacuous: scaling volume changes "
    "nothing) and NOT exposure-weighted (no Greek, OI or contract population "
    "enters the computation)."
)


def _shared_provenance(symbol: str, date: str, timeframe: str, granularity_note: str) -> dict[str, Any]:
    return {
        "ticker": symbol,
        "session_date": date,
        "timeframe": timeframe,
        "granularity_note": granularity_note,
        "bar_source": "public_api_adapter.fetch_bars_from_public_api",
        "timestamp_convention": _TIMESTAMP_CONVENTION,
        "is_market_vwap": False,
        "not_market_vwap_because": _NOT_MARKET_VWAP,
        "venue_scope": "single_venue_single_provider",
    }


def _unavailable(
    reason: str,
    *,
    label: str,
    bars: int,
    symbol: str,
    date: str,
    timeframe: str,
    granularity_note: str,
    why: str,
) -> dict[str, Any]:
    """An honest unavailable packet, shaped exactly like a successful one."""
    out = {
        "version": SESSION_LEVEL_VERSION,
        "label": label,
        "value": None,
        "status": "unavailable",
        "reason": reason,
        "value_kind": "unavailable",
        "bars_used": 0,
        "bars_skipped": 0,
        "bars_fetched": bars,
        "source_dates": [],
        "not_computed_because": why,
    }
    out.update(_shared_provenance(symbol, date, timeframe, granularity_note))
    return out


async def session_bar_vwap_for_ticker(
    ticker: str,
    session_date: str,
    *,
    limit: int = 400,
    sessions: str = "regular",
) -> dict[str, Any]:
    """Regular-session intraday bar-VWAP approximation for one session date.

    Σ(typical·V)/ΣV over the finest supported regular-session intraday
    aggregation. This is the default session reference: it is the only mode
    whose arithmetic actually depends on volume. It reports the granularity
    used, the bar count, coverage and the provider, and states on every path
    that it is not print-level market VWAP.
    """
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return _unavailable("NO_TICKER", label=SESSION_BAR_VWAP_LABEL, bars=0, symbol="",
                            date=str(session_date or ""), timeframe=_BAR_VWAP_TIMEFRAME,
                            granularity_note="", why="no ticker")
    date = str(session_date or "").strip()
    if len(date) < 10:
        return _unavailable("NO_SESSION_DATE", label=SESSION_BAR_VWAP_LABEL, bars=0,
                            symbol=symbol, date=date, timeframe=_BAR_VWAP_TIMEFRAME,
                            granularity_note="", why="session date is not an ISO date")

    granularity = "intraday bar VWAP approximation (not market VWAP)"
    bars = await fetch_bars_from_public_api(
        symbol, timeframe=_BAR_VWAP_TIMEFRAME, limit=limit, sessions=sessions,
    )
    packet = session_exposure_level(bars, session_date=date, session=sessions)
    packet["label"] = SESSION_BAR_VWAP_LABEL
    packet["value_kind"] = "volume_weighted_bar_typical_price"
    packet["ticker"] = symbol
    packet["session_date"] = date
    packet["timeframe"] = _BAR_VWAP_TIMEFRAME
    packet["granularity_note"] = granularity
    packet["is_market_vwap"] = False
    packet["not_market_vwap_because"] = _NOT_MARKET_VWAP
    packet["venue_scope"] = "single_venue_single_provider"
    packet["bar_source"] = "public_api_adapter.fetch_bars_from_public_api"
    packet["timestamp_convention"] = _TIMESTAMP_CONVENTION
    if packet.get("status") == "ok":
        packet["coverage"] = {
            "bars_used": packet["bars_used"],
            "bars_skipped": packet["bars_skipped"],
            "session_date_matched": date,
        }
    else:
        packet["not_computed_because"] = (
            "no usable regular-session bars with positive volume for this date; "
            "a holiday, early close or stale prior-session row all land here and "
            "are never substituted"
        )
    return packet


async def session_daily_typical_price_for_ticker(
    ticker: str,
    session_date: str,
    *,
    limit: int = 30,
    sessions: str = "regular",
) -> dict[str, Any]:
    """Daily session typical price (H+L+C)/3 — honestly named, not VWAP.

    Retained because it is cheap and unambiguous, but it is NOT
    volume-weighted (one daily bar) and NOT exposure-weighted (no Greeks).
    """
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return _unavailable("NO_TICKER", label=SESSION_DAILY_TYPICAL_LABEL, bars=0, symbol="",
                            date=str(session_date or ""), timeframe=_DAILY_TIMEFRAME,
                            granularity_note="", why="no ticker")
    date = str(session_date or "").strip()
    if len(date) < 10:
        return _unavailable("NO_SESSION_DATE", label=SESSION_DAILY_TYPICAL_LABEL, bars=0,
                            symbol=symbol, date=date, timeframe=_DAILY_TIMEFRAME,
                            granularity_note="", why="session date is not an ISO date")

    granularity = "daily bar typical price (H+L+C)/3; no volume or exposure weighting"
    bars = await fetch_bars_from_public_api(
        symbol, timeframe=_DAILY_TIMEFRAME, limit=limit, sessions=sessions,
    )
    packet = session_exposure_level(bars, session_date=date, session=sessions)
    packet["label"] = SESSION_DAILY_TYPICAL_LABEL
    packet["value_kind"] = "daily_typical_price"
    packet["not_computed_because"] = _NOT_EXPOSURE_WEIGHTED
    packet.update(_shared_provenance(symbol, date, _DAILY_TIMEFRAME, granularity))
    packet["not_market_vwap_because"] = (
        _NOT_MARKET_VWAP + " This mode is not even volume-weighted: one daily bar."
    )
    return packet


async def session_exposure_level_for_ticker(
    ticker: str,
    session_date: str,
    *,
    limit: int = 30,
    sessions: str = "regular",
) -> dict[str, Any]:
    """LEGACY ALIAS -> session_daily_typical_price_for_ticker.

    Kept because "exposure-weighted" was never accurate for this quantity
    (R10-09). It now returns the honestly-labelled daily typical-price
    packet. New code should call session_bar_vwap_for_ticker (the default
    session reference) or name the daily mode explicitly.
    """
    return await session_daily_typical_price_for_ticker(
        ticker, session_date, limit=limit, sessions=sessions
    )


__all__ = [
    "SESSION_BAR_VWAP_LABEL",
    "SESSION_DAILY_TYPICAL_LABEL",
    "SESSION_LEVEL_LABEL",
    "SESSION_LEVEL_VERSION",
    "session_bar_vwap_for_ticker",
    "session_daily_typical_price_for_ticker",
    "session_exposure_level_for_ticker",
]
