"""The real `flow_sse` trading-window gate must not depend on the host timezone.

`server.flow_sse` enforces the live trading window before streaming. It reads
Eastern time via `_eastern_now()`, whose fallback used to consult the HOST's
`time.localtime().tm_isdst`. On a non-Eastern host that flag is wrong about
Eastern for roughly Mar 8-28 and Oct 25-31 each year, shifting the gate by an
hour and letting a stream start (or refuse to start) at the wrong time.

These tests drive the real endpoint, not the helper, so reverting the call
site -- rather than the helper -- is what makes them fail.
"""

from __future__ import annotations

import asyncio
import builtins
import time
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import server
from server import PAID_TICKERS, flow_sse

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

_REAL_IMPORT = builtins.__import__


class _FrozenDatetime(datetime):
    _frozen: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls._frozen.astimezone(tz) if tz is not None else cls._frozen.replace(tzinfo=None)


def _blocked_zoneinfo(name, *args, **kwargs):
    if name == "zoneinfo":
        raise ImportError("simulated: no tzdata on this host")
    return _REAL_IMPORT(name, *args, **kwargs)


async def _gate_opens(utc_instant: datetime, host_tz: str) -> bool:
    """True when the real flow_sse window check lets the request through.

    Returns False if the endpoint short-circuits with a window error, True if
    it proceeds past the window gate (we stop it at the paid-ticker check
    ordering by using a ticker that is allowed).
    """
    _FrozenDatetime._frozen = utc_instant
    host_dst = bool(utc_instant.astimezone(ZoneInfo(host_tz)).dst().total_seconds())

    def fake_localtime(t=None):
        st = list(time.struct_time((2026, 1, 1, 0, 0, 0, 0, 1, 1)))
        st[8] = 1 if host_dst else 0
        return time.struct_time(tuple(st))

    # Read PAID_TICKERS at call time: conftest posts a live policy that REBINDS
    # server.PAID_TICKERS, so a module-level import would be stale and the
    # paid-ticker check would fire before the window gate under test.
    ticker = next(iter(sorted(server.PAID_TICKERS)), "SPY")

    with (
        patch.object(builtins, "__import__", _blocked_zoneinfo),
        patch("server.datetime", _FrozenDatetime),
        patch("time.localtime", fake_localtime),
        patch.dict(server.LIVE_WINDOW, {"start_hhmm": "09:00", "stop_hhmm": "10:30"}),
    ):
        resp = await flow_sse(ticker, max_seconds=1, enforce_window=True)
        body = getattr(resp, "body_iterator", None)
        chunks = []
        if body is not None:
            try:
                chunk = await body.__anext__()
                chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace"))
            except StopAsyncIteration:
                pass
            except Exception:
                pass

    return "Outside trading window" not in "".join(chunks)


# 13:00 UTC == 09:00 EDT, the window's opening minute, on both dates below.
_MARCH = datetime(2026, 3, 9, 13, 0, tzinfo=UTC)
_OCTOBER = datetime(2026, 10, 28, 13, 0, tzinfo=UTC)


def test_flow_window_opens_at_0900_on_an_eastern_host():
    assert asyncio.run(_gate_opens(_MARCH, "America/New_York")) is True


def test_flow_window_opens_at_0900_for_a_berlin_host_in_march():
    assert asyncio.run(_gate_opens(_MARCH, "Europe/Berlin")) is True, (
        "a Berlin host must not decide Eastern's DST; 13:00 UTC is 09:00 EDT"
    )


def test_flow_window_opens_at_0900_for_a_berlin_host_in_october():
    assert asyncio.run(_gate_opens(_OCTOBER, "Europe/Berlin")) is True, (
        "a Berlin host must not decide Eastern's DST; 13:00 UTC is 09:00 EDT"
    )


def test_flow_window_opens_at_0900_for_a_utc_host():
    assert asyncio.run(_gate_opens(_OCTOBER, "UTC")) is True


def test_flow_window_closed_outside_hours_on_every_host():
    """18:00 ET (22:00 UTC) is outside the window wherever the host runs."""
    outside = datetime(2026, 10, 28, 22, 0, tzinfo=UTC)
    for host in ("America/New_York", "Europe/Berlin", "Asia/Tokyo", "UTC"):
        with patch.dict(server.LIVE_WINDOW, {"start_hhmm": "09:00", "stop_hhmm": "10:30"}):
            assert asyncio.run(_gate_opens(outside, host)) is False, (
                f"18:00 ET was allowed inside the window on a {host} host"
            )
