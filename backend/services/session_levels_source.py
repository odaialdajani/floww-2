"""Async source for the session exposure-weighted level (Command Code C1.2).

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

NESTED EVENT LOOPS
==================
This is an `async def` that AWAITS the adapter. It never calls `asyncio.run`,
`loop.run_until_complete`, or `new_event_loop`, because all three are
unavailable-or-wrong inside a running loop: `asyncio.run` raises
`RuntimeError: asyncio.run() cannot be called from a running event loop`, and
the workarounds people reach for instead (a dedicated thread, `new_event_loop`
per call) detach the coroutine from the caller's cancellation and timeout
context. The adapter is a coroutine, so awaiting it is both the simplest and
the only correct composition. `tests/services/test_session_levels_source.py`
asserts this by calling this function from inside an already-running loop and
by statically rejecting the forbidden symbols.

LABELING
========
This is an EXPOSURE-WEIGHTED level over the bars this platform fetched. It is
not market VWAP: market VWAP is a whole-market print-weighted average, and this
rests on a single venue's bars, on a typical-price proxy rather than trade
prices, and only on the regular session. The packet says so in words and in
fields, so a consumer cannot read the number without the caveat.
"""

from __future__ import annotations

from typing import Any

# Imported at module scope on purpose. A local import inside a broad `except`
# is precisely what hid the missing symbol this module replaces.
from domain.session_levels import SESSION_LEVEL_VERSION, session_exposure_level
from services.public_api_adapter import fetch_bars_from_public_api

# The public label for this quantity. It deliberately does not contain "VWAP".
SESSION_LEVEL_LABEL = "session_exposure_level"

_NOT_MARKET_VWAP = (
    "Exposure-weighted level over one venue's regular-session bars, using "
    "(H+L+C)/3 as the price proxy. This is NOT market VWAP: it is not "
    "print-weighted, not whole-market, and not computed from trade prices."
)

# Bar timeframe whose aggregation is a single regular-session day. Intraday
# timeframes would make "one session date" ambiguous, so they are not accepted.
_SESSION_TIMEFRAME = "1Day"


async def session_exposure_level_for_ticker(
    ticker: str,
    session_date: str,
    *,
    limit: int = 30,
    sessions: str = "regular",
) -> dict[str, Any]:
    """Fetch canonical bars and reduce them to one session exposure level.

    ``session_date`` is an ISO date prefix (``YYYY-MM-DD``). ``limit`` caps how
    many most-recent daily bars are requested, so the date is guaranteed to be
    inside the fetched window; the pure reducer still filters on the date and
    reports how many bars it actually used.

    Returns the reducer's packet plus provenance. On any unavailable path the
    ``value`` is ``None`` with a reason code -- never zero, and never a
    substituted price.
    """
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return _unavailable("NO_TICKER", bars=0)
    date = str(session_date or "").strip()
    if len(date) < 10:
        return _unavailable("NO_SESSION_DATE", bars=0)

    # Awaited directly. No run_until_complete, no new loop, no thread.
    bars = await fetch_bars_from_public_api(
        symbol,
        timeframe=_SESSION_TIMEFRAME,
        limit=limit,
        sessions=sessions,
    )

    packet = session_exposure_level(bars, session_date=date, session=sessions)
    packet["label"] = SESSION_LEVEL_LABEL
    packet["is_market_vwap"] = False
    packet["not_market_vwap_because"] = _NOT_MARKET_VWAP
    packet["ticker"] = symbol
    packet["session_date"] = date
    packet["timeframe"] = _SESSION_TIMEFRAME
    packet["bar_source"] = "public_api_adapter.fetch_bars_from_public_api"
    return packet


def _unavailable(reason: str, *, bars: int) -> dict[str, Any]:
    """An honest unavailable packet, shaped exactly like a successful one."""
    return {
        "version": SESSION_LEVEL_VERSION,
        "label": SESSION_LEVEL_LABEL,
        "value": None,
        "status": "unavailable",
        "reason": reason,
        "is_market_vwap": False,
        "not_market_vwap_because": _NOT_MARKET_VWAP,
        "bars_used": 0,
        "bars_skipped": 0,
        "source_dates": [],
        "bars_fetched": bars,
        "bar_source": "public_api_adapter.fetch_bars_from_public_api",
    }


__all__ = [
    "SESSION_LEVEL_LABEL",
    "SESSION_LEVEL_VERSION",
    "session_exposure_level_for_ticker",
]
