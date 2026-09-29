"""DST correctness of the `_in_window_now_et` fallback in server.py.

`_in_window_now_et` prefers `ZoneInfo("America/New_York")`. When that import
fails it falls back to `time.localtime().tm_isdst` to pick a fixed UTC-4/UTC-5
offset. That reads the HOST's DST state, not Eastern's.

Those are different questions. The host may sit in any timezone, and US and EU
DST begin and end on different dates, so there are two windows each year where
the host's answer is wrong about Eastern's:

  * Mar 8-28 2026 -- the US springs forward, the EU has not
  * Oct 25-31 2026 -- the EU falls back, the US has not

The gate controls a 09:00-10:30 ET live window, so one hour of error opens or
closes that window at the wrong time.

Each test drives the real `server._in_window_now_et` with the zoneinfo import
forced to fail, `datetime` pinned to a known instant, and `time.localtime`
reporting a foreign host's DST flag. The assertion is on the function's actual
return value, so a copy of the arithmetic could not pass these.
"""

from __future__ import annotations

import builtins
import time
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from server import LIVE_WINDOW, _eastern_now, _in_window_now_et

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


class _FrozenDatetime(datetime):
    """datetime whose now() is pinned to a fixed instant."""

    _frozen: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls._frozen.astimezone(tz) if tz is not None else cls._frozen.replace(tzinfo=None)


_REAL_IMPORT = builtins.__import__


def _blocked_zoneinfo(name, *args, **kwargs):
    """Make `from zoneinfo import ZoneInfo` fail inside the function."""
    if name == "zoneinfo":
        raise ImportError("simulated: no tzdata on this host")
    return _REAL_IMPORT(name, *args, **kwargs)


def _run_with_host(eastern_wall: datetime, host_tz: str) -> bool:
    """Return what the real `_in_window_now_et` decides.

    `eastern_wall` is the true Eastern wall clock; `host_tz` is the timezone
    the (simulated) machine is configured to, which is what tm_isdst reflects.
    """
    _FrozenDatetime._frozen = eastern_wall.astimezone(UTC)
    host_dst = bool(eastern_wall.astimezone(ZoneInfo(host_tz)).dst().total_seconds())

    def fake_localtime(t=None):
        st = list(time.struct_time((2026, 1, 1, 0, 0, 0, 0, 1, 1)))
        st[8] = 1 if host_dst else 0
        return time.struct_time(tuple(st))

    with (
        patch.object(builtins, "__import__", _blocked_zoneinfo),
        patch("services.eastern_clock.datetime", _FrozenDatetime),
        patch("time.localtime", fake_localtime),
    ):
        return _in_window_now_et()


def _assert_window_opens(eastern_wall: datetime, host_tz: str, when: str) -> None:
    """09:00 ET must be inside the window no matter where the host runs."""
    assert _run_with_host(eastern_wall, host_tz) is True, (
        f"{when}: 09:00 ET was judged OUTSIDE the "
        f"{LIVE_WINDOW['start_hhmm']}-{LIVE_WINDOW['stop_hhmm']} ET window "
        f"on a {host_tz} host -- the fallback read the host's DST flag "
        "instead of Eastern's"
    )


def _eastern_now_with_host(eastern_wall: datetime, host_tz: str) -> datetime:
    """Return the real `_eastern_now()` result for a pinned instant + host tz."""
    _FrozenDatetime._frozen = eastern_wall.astimezone(UTC)
    host_dst = bool(eastern_wall.astimezone(ZoneInfo(host_tz)).dst().total_seconds())

    def fake_localtime(t=None):
        st = list(time.struct_time((2026, 1, 1, 0, 0, 0, 0, 1, 1)))
        st[8] = 1 if host_dst else 0
        return time.struct_time(tuple(st))

    with (
        patch.object(builtins, "__import__", _blocked_zoneinfo),
        patch("services.eastern_clock.datetime", _FrozenDatetime),
        patch("time.localtime", fake_localtime),
    ):
        return _eastern_now()


# Mar 8-28 2026: US is on EDT, EU is not. Oct 25-31 2026: EU is back, US is not.
# 13:00 UTC is 09:00 EDT on both dates -- the live window's opening minute.
_DIVERGENT_UTC = [
    ("early March", datetime(2026, 3, 9, 13, 0, tzinfo=UTC)),
    ("late October", datetime(2026, 10, 28, 13, 0, tzinfo=UTC)),
]


def test_eastern_now_is_0900_for_berlin_host_in_march():
    _, utc_instant = _DIVERGENT_UTC[0]
    got = _eastern_now_with_host(utc_instant, "Europe/Berlin")
    assert got.strftime("%H:%M") == "09:00", (
        f"_eastern_now returned {got:%H:%M} for a Berlin host at 13:00 UTC on "
        "Mar 9 2026; Eastern is on EDT (09:00), not EST (08:00)"
    )


def test_eastern_now_is_0900_for_berlin_host_in_october():
    _, utc_instant = _DIVERGENT_UTC[1]
    got = _eastern_now_with_host(utc_instant, "Europe/Berlin")
    assert got.strftime("%H:%M") == "09:00", (
        f"_eastern_now returned {got:%H:%M} for a Berlin host at 13:00 UTC on "
        "Oct 28 2026; Eastern is still on EDT (09:00), not EST (08:00)"
    )


def test_eastern_now_agrees_across_every_host_timezone():
    """The prefetch and trading-window gates read this helper, so it must be
    independent of where the host machine is configured."""
    for _, utc_instant in _DIVERGENT_UTC:
        times = {
            host: _eastern_now_with_host(utc_instant, host).strftime("%H:%M")
            for host in ("America/New_York", "Europe/Berlin", "Asia/Tokyo", "UTC")
        }
        assert len(set(times.values())) == 1, f"host timezone changed the clock: {times}"


def test_eastern_now_matches_zoneinfo_across_the_year():
    """The arithmetic fallback must equal the tz database all year round."""
    for month, day in [(1, 15), (3, 7), (3, 8), (3, 9), (3, 28), (3, 29), (7, 15),
                       (10, 31), (11, 1), (11, 2), (12, 15)]:
        utc_instant = datetime(2026, month, day, 16, 0, tzinfo=UTC)
        expected = utc_instant.astimezone(ET)
        got = _eastern_now_with_host(utc_instant, "UTC")
        assert got.strftime("%H:%M") == expected.strftime("%H:%M"), (
            f"{month}/{day}: fallback says {got:%H:%M}, tz database says {expected:%H:%M}"
        )


def test_baseline_window_opens_on_an_eastern_host_in_summer():
    _assert_window_opens(datetime(2026, 7, 15, 9, 0, tzinfo=ET), "America/New_York", "summer")


def test_baseline_window_opens_on_an_eastern_host_in_winter():
    _assert_window_opens(datetime(2026, 1, 15, 9, 0, tzinfo=ET), "America/New_York", "winter")


def test_march_us_springs_forward_before_the_eu():
    """Mar 8-28 2026: Eastern is EDT (UTC-4), Berlin is still UTC+1."""
    day = datetime(2026, 3, 9, 9, 0, tzinfo=ET)
    assert day.utcoffset() == timedelta(hours=-4)
    assert day.astimezone(ZoneInfo("Europe/Berlin")).dst().total_seconds() == 0
    _assert_window_opens(day, "Europe/Berlin", "early March")


def test_october_eu_falls_back_before_the_us():
    """Oct 25-31 2026: Eastern is still EDT (UTC-4), Berlin is back to UTC+1."""
    day = datetime(2026, 10, 28, 9, 0, tzinfo=ET)
    assert day.utcoffset() == timedelta(hours=-4)
    assert day.astimezone(ZoneInfo("Europe/Berlin")).dst().total_seconds() == 0
    _assert_window_opens(day, "Europe/Berlin", "late October")


def test_window_closes_correctly_on_a_non_eastern_host():
    """11:00 ET must be outside the window regardless of host timezone."""
    for host in ("America/New_York", "Europe/Berlin", "Asia/Tokyo"):
        got = _run_with_host(datetime(2026, 10, 28, 11, 0, tzinfo=ET), host)
        assert got is False, f"11:00 ET judged INSIDE the window on a {host} host"


def test_utc_host_agrees_with_eastern():
    """A UTC host is permanently UTC+0, so its DST flag is never Eastern's."""
    # 09:00 EDT on Oct 28 is inside the window.
    _assert_window_opens(datetime(2026, 10, 28, 9, 0, tzinfo=ET), "UTC", "UTC host")
