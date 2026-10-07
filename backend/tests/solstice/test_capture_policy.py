"""Regular-session background capture uses the maintained exchange calendar."""
import importlib
from datetime import UTC, datetime

import pytest


@pytest.fixture
def policy():
    return importlib.import_module("services.solstice_capture_policy")


def test_capture_starts_at_regular_open_not_early_morning(policy):
    assert policy.capture_market_hours("2026-10-07T13:29:59Z") is False
    assert policy.capture_market_hours("2026-10-07T13:30:00Z") is True


def test_capture_stops_at_actual_close_without_after_hours_buffer(policy):
    assert policy.capture_market_hours("2026-10-07T19:59:59Z") is True
    assert policy.capture_market_hours("2026-10-07T20:00:00Z") is False
    assert policy.capture_market_hours("2026-10-07T20:20:00Z") is False


def test_capture_is_off_on_exchange_holiday_even_when_weekday(policy):
    assert policy.capture_market_hours("2026-11-26T15:30:00Z") is False


def test_capture_is_off_on_weekends(policy):
    assert policy.capture_market_hours("2026-10-10T15:30:00Z") is False


def test_half_day_capture_stops_at_one_pm_eastern(policy):
    assert policy.capture_market_hours("2026-11-27T17:59:59Z") is True
    assert policy.capture_market_hours("2026-11-27T18:00:00Z") is False
    assert policy.capture_market_hours("2026-11-27T19:00:00Z") is False


def test_utc_aware_datetimes_and_daylight_time_follow_local_exchange_open(policy):
    assert policy.capture_market_hours(datetime(2026, 1, 7, 14, 29, 59, tzinfo=UTC)) is False
    assert policy.capture_market_hours(datetime(2026, 1, 7, 14, 30, tzinfo=UTC)) is True
    assert policy.capture_market_hours(datetime(2026, 7, 7, 13, 29, 59, tzinfo=UTC)) is False
    assert policy.capture_market_hours(datetime(2026, 7, 7, 13, 30, tzinfo=UTC)) is True
    assert policy.capture_market_hours("2026-07-07T09:30:00-04:00") is True


def test_naive_missing_and_invalid_time_cannot_start_capture(policy):
    for value in (None, datetime(2026, 10, 7, 10), "2026-10-07T10:00:00", "bad-time", 123):
        assert policy.capture_market_hours(value) is False


def test_missing_unknown_or_broken_calendar_cannot_start_capture(policy, monkeypatch):
    def failure(day):
        raise RuntimeError("calendar unavailable")
    for result in (
        None,
        {"date": "2026-10-07", "is_open": False, "reason": "CALENDAR_UNKNOWN"},
        {"date": "2026-10-07", "is_open": True, "open_et": None, "close_et": None},
        {"date": "2026-10-08", "is_open": True, "open_et": "09:30", "close_et": "16:00"},
        {"date": "2026-10-07", "is_open": True, "open_et": "16:00", "close_et": "09:30"},
        {"date": "2026-10-07", "is_open": "unknown", "open_et": "09:30", "close_et": "16:00"},
    ):
        monkeypatch.setattr(policy, "exchange_day_info", lambda day, result=result: result)
        assert policy.capture_market_hours("2026-10-07T15:30:00Z") is False
    monkeypatch.setattr(policy, "exchange_day_info", failure)
    assert policy.capture_market_hours("2026-10-07T15:30:00Z") is False
