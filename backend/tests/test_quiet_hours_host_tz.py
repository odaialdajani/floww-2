"""The alert dispatcher's quiet-hours gate must not depend on the host timezone.

`AlertDispatcher._is_quiet_hours` decides whether an outbound phone call is
suppressed. Its Eastern-time fallback used to read the HOST's
`time.localtime().tm_isdst`, which is wrong about Eastern for roughly
Mar 8-28 and Oct 25-31 each year on any non-Eastern host.

Quiet hours run 22:00-06:00 ET, so a one-hour error lands directly on the
boundary: 22:00 ET is quiet, 21:00 ET is not. A wrong answer here means
placing or suppressing a real outbound call on the wrong side of that line.
"""

from __future__ import annotations

import builtins
import time
from datetime import UTC, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from services.alert_dispatcher import AlertDispatcher
from services.eastern_clock import eastern_at

ET = ZoneInfo("America/New_York")
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


def _quiet(utc_instant: datetime, host_tz: str) -> bool:
    """Ask the real _is_quiet_hours, with zoneinfo forced to fail."""
    host_dst = bool(utc_instant.astimezone(ZoneInfo(host_tz)).dst().total_seconds())

    def fake_localtime(t=None):
        st = list(time.struct_time((2026, 1, 1, 0, 0, 0, 0, 1, 1)))
        st[8] = 1 if host_dst else 0
        return time.struct_time(tuple(st))

    d = AlertDispatcher.__new__(AlertDispatcher)
    with (
        patch.object(builtins, "__import__", _blocked_zoneinfo),
        patch("services.eastern_clock.datetime", _FrozenDatetime),
        patch("time.localtime", fake_localtime),
    ):
        return d._is_quiet_hours(utc_instant)


# Quiet hours are 22:00-06:00 ET. During EDT that is 02:00-10:00 UTC.
# 02:00 UTC is exactly 22:00 ET -- one minute earlier is 21:59 ET, not quiet.
_QUIET_EDGE = datetime(2026, 10, 28, 2, 0, tzinfo=UTC)   # Wed 22:00 ET -> quiet
_NOT_QUIET = datetime(2026, 10, 28, 1, 59, tzinfo=UTC)   # Wed 21:59 ET -> not quiet

_HOSTS = ("America/New_York", "Europe/Berlin", "Asia/Tokyo", "UTC")


def test_2200_et_is_quiet_on_every_host():
    for host in _HOSTS:
        assert _quiet(_QUIET_EDGE, host) is True, f"22:00 ET was not quiet on a {host} host"


def test_2159_et_is_not_quiet_on_every_host():
    for host in _HOSTS:
        assert _quiet(_NOT_QUIET, host) is False, f"21:59 ET was quiet on a {host} host"


def test_quiet_hours_boundary_is_host_independent():
    """The one-hour DST-divergence date must not move the boundary."""
    # 2026-10-28: US is still on EDT (UTC-4), Berlin is already on CET.
    for host in _HOSTS:
        assert _quiet(datetime(2026, 10, 28, 2, 0, tzinfo=UTC), host) is True
        assert _quiet(datetime(2026, 10, 28, 1, 59, tzinfo=UTC), host) is False


def test_eastern_at_matches_zoneinfo_across_dst_edges():
    """The shared clock must equal the tz database on both DST transition days."""
    for month, day in [(3, 7), (3, 8), (3, 9), (10, 31), (11, 1), (11, 2)]:
        for hour in (0, 6, 13, 20):
            instant = datetime(2026, month, day, hour, 0, tzinfo=UTC)
            expected = instant.astimezone(ET)
            with patch.object(builtins, "__import__", _blocked_zoneinfo):
                got = eastern_at(instant)
            assert got.strftime("%H:%M") == expected.strftime("%H:%M"), (
                f"{month}/{day} {hour}:00 UTC -> fallback {got:%H:%M}, "
                f"tz database {expected:%H:%M}"
            )
