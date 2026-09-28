"""Friday-pin entry-window time handling.

The strategy fires in a 10-minute window near the close (15:30-15:40 ET by
default), gated on a flat price over the last 30 bars. That window is expressed
in Eastern time, so the UTC->ET conversion is the difference between firing and
never firing.

This pins the DST behavior. The conversion once hardcoded UTC-5 under a comment
claiming it handled UTC-4 for DST -- the comment was true and the code was not.
For roughly five months a year every bar was read an hour early, so a 15:35 ET
bar evaluated as 14:35 and was rejected by the very window this strategy exists
to catch.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from services.strategies.friday_pin import (
    FridayPinConfig,
    FridayPinStrategy,
)

ET = ZoneInfo("America/New_York")


def _et(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    """Eastern wall-clock time -> UTC instant."""
    return datetime(y, m, d, hh, mm, tzinfo=ET).astimezone(UTC)


def _pinned() -> FridayPinStrategy:
    """A strategy primed with flat prices so the pin condition always passes.

    Flat history makes the 30-bar range 0%, under the 0.5% threshold, so the
    ONLY thing that can reject an in-window bar is the time gate itself. That is
    what lets these tests kill the UTC-5 bug rather than merely restating the
    arithmetic they are supposed to police.
    """
    s = FridayPinStrategy(FridayPinConfig())
    for _ in range(40):
        s.update_price(100.0)
    return s


def _fires(ts: datetime) -> bool:
    return _pinned().check_entry_condition({"price": 100.0, "timestamp": ts})


def test_in_window_friday_bar_triggers_the_entry():
    """A Friday 15:35 ET bar must fire.

    Everything except the clock is pre-satisfied, so a False here means the
    time gate rejected a bar that is genuinely inside the window.
    """
    assert _fires(_et(2026, 9, 25, 15, 35)) is True, (
        "15:35 ET on a Friday is inside the 15:30-15:40 window"
    )


def test_out_of_window_bar_is_still_rejected():
    """14:35 ET is an hour early and must not fire."""
    assert _fires(_et(2026, 9, 25, 14, 35)) is False, (
        "14:35 ET is outside the window and must be rejected"
    )


def test_window_boundaries_are_inclusive():
    """15:30 and 15:40 both fire; 15:29 and 15:41 do not."""
    for hh, mm, expect in ((15, 29, False), (15, 30, True),
                           (15, 40, True), (15, 41, False)):
        got = _fires(_et(2026, 9, 25, hh, mm))
        assert got is expect, f"{hh}:{mm:02d} ET -> {got}, expected {expect}"


def test_window_does_not_move_with_daylight_saving():
    """The same ET wall-clock time must behave identically in EDT and EST.

    A fixed UTC offset passes this in winter and fails it in summer, which is
    exactly the seasonal bug: the window silently shifting an hour with the
    seasons.
    """
    assert _fires(_et(2026, 9, 25, 15, 35)) is True, "EDT (Sep): must fire"
    assert _fires(_et(2026, 1, 23, 15, 35)) is True, "EST (Jan): must fire"


def test_non_friday_is_rejected_regardless_of_time():
    """A Wednesday at 15:35 ET must not fire."""
    assert _fires(_et(2026, 9, 23, 15, 35)) is False, (
        "the weekday gate must still apply"
    )


def test_hardcoded_utc5_would_miss_the_window():
    """Documents the original defect, and stops passing if it stops mattering.

    A 15:35 ET bar is 19:35 UTC under EDT. Subtracting a fixed 5 hours lands on
    14:35 -- 55 minutes before the window opens.
    """
    bar = _et(2026, 9, 25, 15, 35)
    assert bar.hour == 19, "EDT means 15:35 ET is 19:35 UTC"

    mins = (bar - timedelta(hours=5))
    mins = mins.hour * 60 + mins.minute
    assert not (930 <= mins <= 940), (
        "if this now passes, the fixed-offset bug is no longer the failure mode"
    )
