from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from services.agent.access.horizon import horizon_window, normalize_horizon, slice_expiries

ET = ZoneInfo("America/New_York")


def test_invalid_scope_is_rejected():
    with pytest.raises(ValueError):
        normalize_horizon("bogus")


def test_absent_today_never_substitutes_tomorrow():
    assert slice_expiries([{"expiry": "2026-09-14"}], "0dte", now=datetime(2026, 9, 11, 11, tzinfo=ET)) == []


def test_holiday_next_session_and_after_close_are_explicit():
    w = horizon_window("1dte", now=datetime(2026, 9, 4, 17, tzinfo=ET))
    assert w["start"] == "2026-09-08"
    assert w["session_state"] == "closed"


def test_week_uses_sessions_not_available_expiry_count():
    rows = [{"expiry": "2026-09-11"}, {"expiry": "2026-09-14"}, {"expiry": "2026-10-16"}]
    assert slice_expiries(rows, "week", now=datetime(2026, 9, 11, 11, tzinfo=ET)) == rows[:2]


def test_early_close_and_missing_expiries():
    w = horizon_window("0dte", now=datetime(2026, 11, 27, 14, tzinfo=ET))
    assert w["session_state"] == "closed"
    assert slice_expiries([{}, {"expiry": "bad"}], "all") == []
