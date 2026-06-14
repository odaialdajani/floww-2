"""
tests/services/test_alert_dispatcher.py

Unit tests for services/alert_dispatcher.py — the Twilio alert dispatch service.

Coverage:
    - LOW severity → dashboard-only, never sent
    - MEDIUM severity → SMS channel selected
    - CRITICAL severity → SMS + voice channels selected
    - Unknown severity → dashboard-only with reason
    - Deduplication: second dispatch within cooldown suppressed
    - Deduplication expiry: dispatch after cooldown window re-sends
    - Quiet hours suppression for MEDIUM/CRITICAL
    - Emergency categories bypass quiet hours
    - Market hours override quiet hours on weekdays
    - _is_quiet_hours boundary values (just inside / just outside)
    - _is_deduped with unknown alert_id returns False
    - dispatch returns correct dict structure for each outcome
    - _send_sms without Twilio client logs mock
    - _send_voice without Twilio client logs mock
    - Empty alert_id handled by dedup cache
    - Multiple alert_ids tracked independently in dedup cache
"""

import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.alert_dispatcher import (
    AlertDispatcher,
    DEDUP_COOLDOWN,
    EMERGENCY_CATEGORIES,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MIN,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MIN,
    QUIET_END_HOUR,
    QUIET_START_HOUR,
    SEVERITY_CRITICAL,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
)


# ---------------------------------------------------------------------------
# Severity routing tests
# ---------------------------------------------------------------------------

class TestSeverityRouting:
    """LOW → dashboard; MEDIUM → sms; CRITICAL → sms+voice."""

    @pytest.fixture
    def dispatcher(self):
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "NAV_PHONE_NUMBER": ""}):
            d = AlertDispatcher()
            return d

    @pytest.mark.asyncio
    async def test_low_severity_dashboard_only(self, dispatcher):
        """LOW severity returns sent=False, channel=dashboard without hitting dedup/quiet path."""
        result = await dispatcher.dispatch("low-1", SEVERITY_LOW, "Test", "msg")
        assert result["sent"] is False
        assert result["channel"] == "dashboard"
        assert "LOW" in result["reason"]

    @pytest.mark.asyncio
    async def test_medium_severity_sms_channel(self, dispatcher):
        """MEDIUM severity outside quiet hours should select sms channel."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=False):
            result = await dispatcher.dispatch("med-1", SEVERITY_MEDIUM, "Test", "msg")
        assert result["sent"] is True
        assert result["channel"] == "sms"

    @pytest.mark.asyncio
    async def test_critical_severity_sms_and_voice(self, dispatcher):
        """CRITICAL severity outside quiet hours selects sms+voice."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=False):
            result = await dispatcher.dispatch("crit-1", SEVERITY_CRITICAL, "Test", "msg")
        assert result["sent"] is True
        assert "sms" in result["channel"]
        assert "voice" in result["channel"]

    @pytest.mark.asyncio
    async def test_unknown_severity_dashboard(self, dispatcher):
        """Unknown severity string returns sent=False, dashboard, with 'Unknown' reason."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=False):
            result = await dispatcher.dispatch("unk-1", "URGENT", "Test", "msg")
        assert result["sent"] is False
        assert result["channel"] == "dashboard"
        assert result["reason"] == "Unknown severity: URGENT"


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplication:
    """15-minute cooldown per alert_id."""

    @pytest.fixture
    def dispatcher(self):
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "NAV_PHONE_NUMBER": ""}):
            d = AlertDispatcher()
            d._dedup_cache.clear()
            return d

    @pytest.mark.asyncio
    async def test_first_dispatch_not_deduped(self, dispatcher):
        """First dispatch of a given alert_id should go through."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=False):
            result = await dispatcher.dispatch("alert-x", SEVERITY_CRITICAL, "T", "M")
        assert result["sent"] is True

    @pytest.mark.asyncio
    async def test_second_dispatch_deduped(self, dispatcher):
        """Second dispatch of the same alert_id within 15 min is suppressed."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=False):
            r1 = await dispatcher.dispatch("alert-x", SEVERITY_CRITICAL, "T", "M")
            r2 = await dispatcher.dispatch("alert-x", SEVERITY_CRITICAL, "T", "M")
        assert r1["sent"] is True
        assert r2["sent"] is False
        assert r2["channel"] == "suppressed"
        assert "cooldown" in r2["reason"]

    @pytest.mark.asyncio
    async def test_dedup_cleared_after_cooldown(self, dispatcher):
        """After cooldown expires, third dispatch should go through again."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=False):
            r1 = await dispatcher.dispatch("alert-x", SEVERITY_CRITICAL, "T", "M")
            dispatcher._dedup_cache["alert-x"] = time.time() - DEDUP_COOLDOWN - 1
            r2 = await dispatcher.dispatch("alert-x", SEVERITY_CRITICAL, "T", "M")
        assert r1["sent"] is True
        assert r2["sent"] is True

    def test_is_deduped_unknown_id(self, dispatcher):
        """An alert_id not in the cache returns False."""
        assert dispatcher._is_deduped("never-seen") is False

    def test_is_deduped_within_window(self, dispatcher):
        """An alert_id set to 'now' is within the cooldown."""
        dispatcher._dedup_cache["fresh"] = time.time()
        assert dispatcher._is_deduped("fresh") is True

    def test_is_deduped_after_window(self, dispatcher):
        """An alert_id older than DEDUP_COOLDOWN seconds is not deduped and removed from cache."""
        dispatcher._dedup_cache["stale"] = time.time() - DEDUP_COOLDOWN - 1
        assert dispatcher._is_deduped("stale") is False
        assert "stale" not in dispatcher._dedup_cache

    def test_dedup_independent_ids(self, dispatcher):
        """Two different alert_ids are tracked independently."""
        dispatcher._dedup_cache["a1"] = time.time()
        assert dispatcher._is_deduped("a1") is True
        assert dispatcher._is_deduped("a2") is False

    @pytest.mark.asyncio
    async def test_empty_alert_id_not_deduped_initially(self, dispatcher):
        """Empty string alert_id is a valid key — first dispatch goes through."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=False):
            result = await dispatcher.dispatch("", SEVERITY_MEDIUM, "T", "M")
        assert result["sent"] is True


# ---------------------------------------------------------------------------
# Quiet hours tests
# ---------------------------------------------------------------------------

class TestQuietHours:
    """_is_quiet_hours checks ET time and market-hours override."""

    @pytest.fixture
    def dispatcher(self):
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "NAV_PHONE_NUMBER": ""}):
            return AlertDispatcher()

    def test_quiet_hours_late_night(self, dispatcher):
        """02:00 ET on a Tuesday → quiet hours."""
        utc = datetime(2026, 6, 16, 6, 0, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is True

    def test_quiet_hours_before_dawn(self, dispatcher):
        """05:59 ET on a Wednesday → quiet hours."""
        utc = datetime(2026, 6, 17, 9, 59, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is True

    def test_not_quiet_hours_morning(self, dispatcher):
        """07:00 ET on a Thursday → not quiet hours."""
        utc = datetime(2026, 6, 18, 11, 0, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is False

    def test_not_quiet_hours_midday(self, dispatcher):
        """12:00 ET on a Friday → not quiet hours."""
        utc = datetime(2026, 6, 20, 16, 0, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is False

    def test_quiet_hours_10pm(self, dispatcher):
        """22:00 ET on a Monday → quiet hours starts."""
        utc = datetime(2026, 6, 16, 2, 0, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is True

    def test_not_quiet_hours_just_before_quiet(self, dispatcher):
        """21:59 ET on a Tuesday → not yet quiet hours."""
        utc = datetime(2026, 6, 17, 1, 59, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is False

    def test_market_hours_override_weekday(self, dispatcher):
        """10:00 ET on a Wednesday (market hours) → not quiet."""
        utc = datetime(2026, 6, 17, 14, 0, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is False

    def test_market_open_boundary_inclusive(self, dispatcher):
        """09:30 ET exactly (market open) → market hours, not quiet."""
        utc = datetime(2026, 6, 18, 13, 30, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is False

    def test_just_before_market_open_quiet(self, dispatcher):
        """09:29 ET on a weekday → not quiet (quiet window is 22:00-06:00)."""
        utc = datetime(2026, 6, 15, 13, 29, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is False

    def test_weekend_midday_not_quiet(self, dispatcher):
        """12:00 ET on a Saturday → NOT quiet (quiet hours are 22:00-06:00 only)."""
        utc = datetime(2026, 6, 20, 16, 0, tzinfo=UTC)
        assert utc.weekday() == 5
        assert dispatcher._is_quiet_hours(utc) is False

    def test_weekend_late_night_quiet(self, dispatcher):
        """02:00 ET on a Sunday → quiet (within 22:00-06:00 window)."""
        utc = datetime(2026, 6, 21, 6, 0, tzinfo=UTC)
        assert utc.weekday() == 6
        assert dispatcher._is_quiet_hours(utc) is True

    def test_weekend_2300_et_quiet(self, dispatcher):
        """23:00 ET on a Saturday → quiet (within 22:00-06:00)."""
        utc = datetime(2026, 6, 21, 3, 0, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is True

    def test_market_close_boundary(self, dispatcher):
        """16:00 ET (market close) → not quiet (hour=16, not >=22, not <6)."""
        utc = datetime(2026, 6, 15, 20, 0, tzinfo=UTC)
        assert dispatcher._is_quiet_hours(utc) is False

    def test_quiet_hours_with_zoneinfo_fallback(self, dispatcher):
        """When ZoneInfo raises, falls back to manual DST offset."""
        utc = datetime(2026, 6, 16, 6, 0, tzinfo=UTC)
        with patch("zoneinfo.ZoneInfo", side_effect=Exception("no zoneinfo")):
            result = dispatcher._is_quiet_hours(utc)
        assert result is True


# ---------------------------------------------------------------------------
# Emergency bypass tests
# ---------------------------------------------------------------------------

class TestEmergencyBypass:
    """Emergency categories bypass quiet hours suppression."""

    @pytest.fixture
    def dispatcher(self):
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "NAV_PHONE_NUMBER": ""}):
            d = AlertDispatcher()
            d._dedup_cache.clear()
            return d

    @pytest.mark.asyncio
    async def test_emergency_bypasses_quiet_hours(self, dispatcher):
        """AnomalyDetected category fires even during quiet hours."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=True):
            result = await dispatcher.dispatch(
                "emg-1", SEVERITY_CRITICAL, "Anomaly!", "Something broke",
                category="AnomalyDetected",
            )
        assert result["sent"] is True
        assert "sms" in result["channel"]

    @pytest.mark.asyncio
    async def test_non_emergency_suppressed_in_quiet_hours(self, dispatcher):
        """Non-emergency category is suppressed during quiet hours."""
        with patch.object(dispatcher, "_is_quiet_hours", return_value=True):
            result = await dispatcher.dispatch(
                "nem-1", SEVERITY_CRITICAL, "Normal alert", "Something happened",
                category="PriceMovement",
            )
        assert result["sent"] is False
        assert result["channel"] == "suppressed"
        assert "Quiet hours" in result["reason"]

    @pytest.mark.asyncio
    async def test_all_emergency_categories_bypass(self, dispatcher):
        """Every category in EMERGENCY_CATEGORIES bypasses quiet hours."""
        for _i, cat in enumerate(EMERGENCY_CATEGORIES):
            dispatcher._dedup_cache.clear()
            with patch.object(dispatcher, "_is_quiet_hours", return_value=True):
                result = await dispatcher.dispatch(
                    f"emg-{cat}", SEVERITY_CRITICAL, "T", "M", category=cat,
                )
            assert result["sent"] is True, f"Category {cat} should bypass quiet hours"


# ---------------------------------------------------------------------------
# Dispatch return structure tests
# ---------------------------------------------------------------------------

class TestDispatchReturnStructure:
    """Verify the dict returned by dispatch has the expected keys."""

    @pytest.fixture
    def dispatcher(self):
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "NAV_PHONE_NUMBER": ""}):
            d = AlertDispatcher()
            d._dedup_cache.clear()
            return d

    @pytest.mark.asyncio
    async def test_return_has_sent_key(self, dispatcher):
        result = await dispatcher.dispatch("k-1", SEVERITY_LOW, "T", "M")
        assert "sent" in result

    @pytest.mark.asyncio
    async def test_return_has_channel_key(self, dispatcher):
        result = await dispatcher.dispatch("k-2", SEVERITY_LOW, "T", "M")
        assert "channel" in result

    @pytest.mark.asyncio
    async def test_return_has_reason_key(self, dispatcher):
        result = await dispatcher.dispatch("k-3", SEVERITY_LOW, "T", "M")
        assert "reason" in result

    @pytest.mark.asyncio
    async def test_all_channels_failed_return(self, dispatcher):
        """When Twilio is available but both sends fail, returns sent=False, channel=none."""
        dispatcher._twilio_available = True
        dispatcher._client = MagicMock()
        with patch.object(dispatcher, "_is_quiet_hours", return_value=False):
            with patch.object(dispatcher, "_send_sms", side_effect=Exception("fail")):
                with patch.object(dispatcher, "_send_voice", side_effect=Exception("fail")):
                    result = await dispatcher.dispatch("fail-1", SEVERITY_CRITICAL, "T", "M")
        assert result["sent"] is False
        assert result["channel"] == "none"
        assert result["reason"] == "All channels failed"


# ---------------------------------------------------------------------------
# SMS / Voice mock send tests (no Twilio client)
# ---------------------------------------------------------------------------

class TestMockSends:
    """When Twilio is not configured, _send_sms and _send_voice log mock entries."""

    @pytest.fixture
    def dispatcher(self):
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "NAV_PHONE_NUMBER": ""}):
            return AlertDispatcher()

    @pytest.mark.asyncio
    async def test_send_sms_without_client(self, dispatcher, caplog):
        """_send_sms with no client logs a mock entry."""
        with caplog.at_level("INFO"):
            await dispatcher._send_sms("Test Title", "Test message body")
        assert any("SMS MOCK" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_send_voice_without_client(self, dispatcher, caplog):
        """_send_voice with no client logs a mock entry."""
        with caplog.at_level("INFO"):
            await dispatcher._send_voice("Test Title", "Test message body")
        assert any("VOICE MOCK" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_send_sms_truncates_message(self, dispatcher, caplog):
        """SMS body is truncated to 100 chars in the mock log path."""
        long_msg = "A" * 300
        with caplog.at_level("INFO"):
            await dispatcher._send_sms("Title", long_msg)
        mock_records = [r for r in caplog.records if "SMS MOCK" in r.message]
        assert len(mock_records) == 1
        assert len(mock_records[0].message) < 200


# ---------------------------------------------------------------------------
# Constructor / env var tests
# ---------------------------------------------------------------------------

class TestConstructor:
    """AlertDispatcher.__init__ reads env vars and handles missing Twilio SDK."""

    def test_no_env_vars(self):
        """With no env vars, _twilio_available is False and _client is None."""
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "NAV_PHONE_NUMBER": ""}):
            d = AlertDispatcher()
        assert d._twilio_available is False
        assert d._client is None

    def test_with_env_vars_but_no_twilio_sdk(self):
        """With env vars set but twilio SDK not installed, falls back gracefully."""
        env = {
            "TWILIO_ACCOUNT_SID": "ACfake",
            "TWILIO_AUTH_TOKEN": "fake_token",
            "TWILIO_FROM_NUMBER": "+155****4567",
            "NAV_PHONE_NUMBER": "+155****6543",
        }
        with patch.dict("os.environ", env):
            with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: (
                __import__(name, *args, **kwargs) if "twilio" not in name
                else (_ for _ in ()).throw(ImportError("No module named 'twilio'"))
            )):
                d = AlertDispatcher()
        assert d._twilio_available is False
        assert d._client is None

    def test_dedup_cache_initially_empty(self):
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "NAV_PHONE_NUMBER": ""}):
            d = AlertDispatcher()
        assert len(d._dedup_cache) == 0

    def test_env_vars_stored(self):
        """Env vars are stored on the instance even when Twilio SDK import fails."""
        env = {
            "TWILIO_ACCOUNT_SID": "ACtest123",
            "TWILIO_AUTH_TOKEN": "tok_test",
            "TWILIO_FROM_NUMBER": "+155****2222",
            "NAV_PHONE_NUMBER": "+155****4444",
        }
        with patch.dict("os.environ", env):
            with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: (
                __import__(name, *args, **kwargs) if "twilio" not in name
                else (_ for _ in ()).throw(ImportError("No module named 'twilio'"))
            )):
                d = AlertDispatcher()
        assert d._account_sid == "ACtest123"
        assert d._auth_token == "tok_test"
        assert d._from_number == "+155****2222"
        assert d._to_number == "+155****4444"
        assert d._twilio_available is False
        assert d._client is None
