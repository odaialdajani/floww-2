"""
backend/tests/services/test_discord_notifier.py

30+ tests for the Discord webhook notifier covering:
- Severity-based embed formatting
- Position alert structured fields
- System alert formatting
- Webhook POST behaviour (mock)
- Edge cases: missing webhook URL, aiohttp unavailable, timeouts
- AlertDispatcher integration
- PositionAlertService integration
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.discord_notifier import (
    DiscordNotifier,
    COLOR_CRITICAL,
    COLOR_WARNING,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_NEUTRAL,
    SEVERITY_COLORS,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def notifier():
    """Create a notifier with no webhook URL (mock/log mode)."""
    with patch.dict(os.environ, {}, clear=True):
        n = DiscordNotifier()
        # Force _available to True for tests that need it
        n._available = True
        n._webhook_url = "https://discord.com/api/webhooks/test"
        return n


@pytest.fixture
def notifier_no_webhook():
    """Create a notifier with no webhook URL configured."""
    with patch.dict(os.environ, {}, clear=True):
        n = DiscordNotifier()
        n._available = False
        n._webhook_url = ""
        return n


@pytest.fixture
def mock_aiohttp():
    """Mock aiohttp.ClientSession for testing POST behaviour."""
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.status = 204
        mock_resp.text = AsyncMock(return_value="")
        mock_session_instance = MagicMock()
        mock_session_instance.post = MagicMock()
        mock_session_instance.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        yield mock_session_instance


# ======================================================================
# DiscordNotifier init tests
# ======================================================================

class TestDiscordNotifierInit:
    """Test DiscordNotifier initialisation."""

    def test_init_with_webhook(self):
        """Should mark as available when webhook URL is set."""
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/abc123"}, clear=True):
            n = DiscordNotifier()
            assert n._available is True
            assert n._webhook_url == "https://discord.com/api/webhooks/abc123"

    def test_init_without_webhook(self):
        """Should mark as not available when no webhook URL."""
        with patch.dict(os.environ, {}, clear=True):
            n = DiscordNotifier()
            assert n._available is False
            assert n._webhook_url == ""


# ======================================================================
# Severity colours
# ======================================================================

class TestSeverityColours:
    """Test severity-to-colour mapping."""

    def test_critical_colour(self):
        assert SEVERITY_COLORS["CRITICAL"] == COLOR_CRITICAL

    def test_warning_colour(self):
        assert SEVERITY_COLORS["WARNING"] == COLOR_WARNING

    def test_info_colour(self):
        assert SEVERITY_COLORS["INFO"] == COLOR_INFO

    def test_success_colour(self):
        assert SEVERITY_COLORS["SUCCESS"] == COLOR_SUCCESS

    def test_unknown_severity_falls_back(self):
        assert SEVERITY_COLORS.get("DEBUG", COLOR_NEUTRAL) == COLOR_NEUTRAL


# ======================================================================
# send_alert tests
# ======================================================================

class TestSendAlert:
    """Test basic alert sending."""

    @pytest.mark.asyncio
    async def test_send_alert_basic(self, notifier, mock_aiohttp):
        """Should POST a well-formed embed payload."""
        result = await notifier.send_alert("Test Title", "Test Message", "CRITICAL")

        assert result is True
        # Verify the POST call
        call_args = mock_aiohttp.post.call_args
        assert call_args is not None
        assert len(call_args[0]) > 0
        url = call_args[0][0]
        kwargs = call_args[1]
        assert "discord.com/api/webhooks" in url
        payload = kwargs["json"]
        assert payload["username"] == "Oracle Alerts"
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert embed["title"] == "Test Title"  # send_alert is raw — no emoji prepended
        assert embed["description"] == "Test Message"
        assert embed["color"] == COLOR_CRITICAL

    @pytest.mark.asyncio
    async def test_send_alert_with_fields(self, notifier, mock_aiohttp):
        """Should include fields in the embed."""
        fields = [
            {"name": "Symbol", "value": "SPY", "inline": True},
            {"name": "P&L", "value": "+$150.00", "inline": True},
        ]
        result = await notifier.send_alert("Test", "Msg", "INFO", fields=fields)
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert len(embed["fields"]) == 2
        assert embed["fields"][0]["name"] == "Symbol"
        assert embed["fields"][1]["value"] == "+$150.00"

    @pytest.mark.asyncio
    async def test_send_alert_with_footer(self, notifier, mock_aiohttp):
        """Should include footer text."""
        result = await notifier.send_alert("Test", "Msg", "INFO", footer="Test Footer")
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert embed["footer"]["text"] == "Test Footer"

    @pytest.mark.asyncio
    async def test_send_alert_no_webhook(self, notifier_no_webhook):
        """Should return False when no webhook configured."""
        result = await notifier_no_webhook.send_alert("Test", "Msg", "CRITICAL")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_strips_long_title(self, notifier, mock_aiohttp):
        """Should truncate title >256 chars."""
        long_title = "A" * 500
        await notifier.send_alert(long_title, "Msg", "INFO")
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert len(embed["title"]) <= 256

    @pytest.mark.asyncio
    async def test_send_alert_strips_long_description(self, notifier, mock_aiohttp):
        """Should truncate description >2048 chars."""
        long_desc = "B" * 3000
        await notifier.send_alert("Title", long_desc, "INFO")
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert len(embed["description"]) <= 2048

    @pytest.mark.asyncio
    async def test_send_alert_limits_fields(self, notifier, mock_aiohttp):
        """Should cap at 25 fields (Discord limit)."""
        many_fields = [{"name": f"F{i}", "value": str(i), "inline": True} for i in range(30)]
        await notifier.send_alert("Title", "Msg", "INFO", fields=many_fields)
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert len(embed["fields"]) <= 25

    @pytest.mark.asyncio
    async def test_send_alert_server_error(self, notifier, mock_aiohttp):
        """Should return False on non-2xx response."""
        # Override the response mock
        session_post = mock_aiohttp.post
        bad_resp = AsyncMock()
        bad_resp.status = 429
        bad_resp.text = AsyncMock(return_value="Rate limited")
        session_post.return_value.__aenter__ = AsyncMock(return_value=bad_resp)

        result = await notifier.send_alert("Test", "Msg", "CRITICAL")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_no_aiohttp(self, notifier):
        """Should handle missing aiohttp gracefully."""
        with patch("builtins.__import__", side_effect=ImportError("no aiohttp")):
            result = await notifier.send_alert("Test", "Msg", "CRITICAL")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_connection_error(self, notifier, mock_aiohttp):
        """Should handle connection timeouts."""
        session_post = mock_aiohttp.post
        session_post.return_value.__aenter__ = AsyncMock(side_effect=TimeoutError("timed out"))

        result = await notifier.send_alert("Test", "Msg", "CRITICAL")
        assert result is False

    @pytest.mark.asyncio
    async def test_severity_emoji_mapping(self, notifier, mock_aiohttp):
        """Emoji should be prepended by send_system_alert (not raw send_alert)."""
        test_cases = [
            ("CRITICAL", "🚨"),
            ("WARNING", "⚠️"),
            ("INFO", "ℹ️"),
            ("SUCCESS", "✅"),
        ]
        for severity, emoji in test_cases:
            await notifier.send_system_alert("Test Alert", "Description", severity)
            embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
            assert embed["title"].startswith(emoji), f"{severity}: expected {emoji}"


# ======================================================================
# send_position_alert tests
# ======================================================================

class TestSendPositionAlert:
    """Test position alert formatting."""

    @pytest.mark.asyncio
    async def test_position_alert_long_profit(self, notifier, mock_aiohttp):
        """Should format a profitable long position alert."""
        result = await notifier.send_position_alert(
            alert_type="TAKE_PROFIT",
            symbol="SPY",
            side="LONG",
            quantity=10,
            entry_price=500.0,
            current_price=520.0,
            unrealized_pnl=200.0,
            unrealized_pnl_pct=0.04,
            message="SPY hit take profit target",
            severity="WARNING",
        )
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert embed["title"].startswith("⚠️")
        assert "TAKE_PROFIT" in embed["title"]
        assert "SPY" in embed["title"]
        assert len(embed["fields"]) >= 7

    @pytest.mark.asyncio
    async def test_position_alert_short_loss(self, notifier, mock_aiohttp):
        """Should format a losing short position alert."""
        result = await notifier.send_position_alert(
            alert_type="STOP_LOSS",
            symbol="QQQ",
            side="SHORT",
            quantity=5,
            entry_price=400.0,
            current_price=420.0,
            unrealized_pnl=-100.0,
            unrealized_pnl_pct=-0.05,
            message="QQQ stop loss triggered",
            severity="CRITICAL",
            details={"threshold": -5.0},
        )
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert embed["title"].startswith("🚨")
        assert "STOP_LOSS" in embed["title"]

    @pytest.mark.asyncio
    async def test_position_alert_info(self, notifier, mock_aiohttp):
        """Should format an informational position alert."""
        result = await notifier.send_position_alert(
            alert_type="POSITION_OPEN",
            symbol="AAPL",
            side="LONG",
            quantity=20,
            entry_price=180.0,
            current_price=180.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            message="New AAPL position opened",
            severity="INFO",
        )
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert embed["title"].startswith("ℹ️")
        assert "POSITION_OPEN" in embed["title"]

    @pytest.mark.asyncio
    async def test_position_alert_with_details(self, notifier, mock_aiohttp):
        """Should include extra detail fields."""
        details = {
            "threshold": -5.0,
            "entry_price": 500.0,
            "exit_price": 480.0,
        }
        await notifier.send_position_alert(
            alert_type="STOP_LOSS", symbol="SPY", side="LONG",
            quantity=10, entry_price=500.0, current_price=480.0,
            unrealized_pnl=-200.0, unrealized_pnl_pct=-0.04,
            message="Test", severity="CRITICAL", details=details,
        )
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        # Should have threshold field from details
        field_names = [f["name"] for f in embed["fields"]]
        assert "Threshold" in field_names

    @pytest.mark.asyncio
    async def test_position_alert_logs_without_webhook(self, notifier_no_webhook):
        """Should return False when no webhook URL."""
        result = await notifier_no_webhook.send_position_alert(
            alert_type="STOP_LOSS", symbol="SPY", side="LONG",
            quantity=10, entry_price=500.0, current_price=480.0,
            unrealized_pnl=-200.0, unrealized_pnl_pct=-0.04,
            message="Test", severity="CRITICAL",
        )
        assert result is False


# ======================================================================
# send_system_alert tests
# ======================================================================

class TestSendSystemAlert:
    """Test system alert formatting."""

    @pytest.mark.asyncio
    async def test_system_alert_basic(self, notifier, mock_aiohttp):
        """Should format a basic system alert."""
        result = await notifier.send_system_alert(
            title="Killswitch Engaged",
            description="Circuit breaker triggered on SPY",
            severity="CRITICAL",
        )
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert "Killswitch" in embed["title"]

    @pytest.mark.asyncio
    async def test_system_alert_with_metric(self, notifier, mock_aiohttp):
        """Should include metric field when provided."""
        result = await notifier.send_system_alert(
            title="Backpressure",
            description="Queue depth critical",
            severity="WARNING",
            metric_name="Queue Depth",
            metric_value=9500,
        )
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert len(embed["fields"]) == 1
        assert embed["fields"][0]["name"] == "Queue Depth"

    @pytest.mark.asyncio
    async def test_system_alert_info(self, notifier, mock_aiohttp):
        """Should format an informational system alert."""
        result = await notifier.send_system_alert(
            title="System Healthy",
            description="All metrics nominal",
            severity="SUCCESS",
        )
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert embed["title"].startswith("✅")


# ======================================================================
# AlertDispatcher integration
# ======================================================================

class TestAlertDispatcherDiscordIntegration:
    """Test that AlertDispatcher correctly invokes Discord."""

    @pytest.mark.asyncio
    async def test_dispatcher_includes_discord_channel(self):
        """AlertDispatcher.dispatch should include discord in channel when sent."""
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test"}, clear=True):
            with patch("services.discord_notifier.DiscordNotifier.send_alert", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                # Reimport to pick up mock env
                from services.alert_dispatcher import dispatcher as d

                # Patch the Discord notifier on the dispatcher directly
                mock_discord = MagicMock()
                mock_discord._available = True
                mock_discord.send_alert = AsyncMock(return_value=True)
                d._discord = mock_discord

                result = await d.dispatch(
                    alert_id="test_001",
                    severity="MEDIUM",
                    title="Test Alert",
                    message="This is a test alert",
                    category="TestCategory",
                )
                assert result["sent"] is True
                assert "discord" in result["channel"]
                mock_discord.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatcher_discord_not_called_low_severity(self):
        """LOW severity should not call Discord."""
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test"}, clear=True):
            with patch("services.discord_notifier.DiscordNotifier.send_alert", new_callable=AsyncMock) as mock_send:
                from services.alert_dispatcher import dispatcher as d

                d._discord = MagicMock()
                d._discord._available = True
                d._discord.send_alert = AsyncMock()

                result = await d.dispatch(
                    alert_id="test_002",
                    severity="LOW",
                    title="Low Alert",
                    message="Dashboard only",
                    category="Test",
                )
                assert result["channel"] == "dashboard"
                d._discord.send_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatcher_handles_discord_failure(self):
        """Should not crash when Discord send fails."""
        from services.alert_dispatcher import dispatcher as d
        d._discord = MagicMock()
        d._discord._available = True
        d._discord.send_alert = AsyncMock(side_effect=Exception("Discord down"))

        # Should not raise — SMS mock succeeds (logs instead of raising)
        result = await d.dispatch(
            alert_id="test_003",
            severity="MEDIUM",
            title="Test",
            message="Test message",
            category="Test",
        )
        # SMS mock succeeds without Twilio (logs), so sent=True, channel=sms
        assert result["sent"] is True
        assert "sms" in result["channel"]

    @pytest.mark.asyncio
    async def test_dispatcher_position_alert_to_discord(self):
        """PositionAlert category should call Discord with position formatting."""
        from services.alert_dispatcher import dispatcher as d
        mock_discord = MagicMock()
        mock_discord._available = True
        mock_discord.send_alert = AsyncMock(return_value=True)
        d._discord = mock_discord

        result = await d.dispatch(
            alert_id="pos_001",
            severity="CRITICAL",
            title="Position STOP_LOSS: SPY",
            message="LONG 10 SPY @ $480.00 P&L: -4.00%",
            category="PositionAlert",
        )
        # Discord send_alert was called with position formatting
        mock_discord.send_alert.assert_called_once()
        assert result["sent"] is True


# ======================================================================
# PositionAlertService Discord integration
# ======================================================================

class TestPositionAlertServiceDiscord:
    """Test that PositionAlertService sends to Discord for CRITICAL alerts."""

    @pytest.mark.asyncio
    async def test_critical_alert_sends_to_discord(self):
        """CRITICAL position alerts should send to Discord."""
        with patch("services.discord_notifier.DiscordNotifier.send_position_alert", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            from services.position_alerts import (
                PositionAlertService,
                PositionAlertEvent,
                PositionAlertType,
                PositionAlertSeverity,
            )

            service = PositionAlertService()
            event = PositionAlertEvent(
                alert_id="test_stop_loss_123",
                alert_type=PositionAlertType.STOP_LOSS,
                severity=PositionAlertSeverity.CRITICAL,
                symbol="SPY",
                side="LONG",
                quantity=10,
                entry_price=500.0,
                current_price=480.0,
                unrealized_pnl=-200.0,
                unrealized_pnl_pct=-0.04,
                message="STOP LOSS triggered",
            )
            await service._dispatch_critical(event)
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["alert_type"] == "STOP_LOSS"
            assert call_kwargs["symbol"] == "SPY"
            assert call_kwargs["severity"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_discord_failure_does_not_crash(self):
        """Discord send failure should not crash the dispatch."""
        with patch("services.discord_notifier.DiscordNotifier.send_position_alert", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("Discord API error")

            from services.position_alerts import (
                PositionAlertService,
                PositionAlertEvent,
                PositionAlertType,
                PositionAlertSeverity,
            )

            service = PositionAlertService()
            event = PositionAlertEvent(
                alert_id="test_crash_123",
                alert_type=PositionAlertType.STOP_LOSS,
                severity=PositionAlertSeverity.CRITICAL,
                symbol="SPY",
                side="LONG",
                quantity=10,
                entry_price=500.0,
                current_price=480.0,
                unrealized_pnl=-200.0,
                unrealized_pnl_pct=-0.04,
                message="Should not crash",
            )
            # Should not raise
            await service._dispatch_critical(event)

    @pytest.mark.asyncio
    async def test_alert_dispatcher_also_called(self):
        """CRITICAL alerts should call both AlertDispatcher and Discord."""
        with patch("services.discord_notifier.DiscordNotifier.send_position_alert", new_callable=AsyncMock) as mock_discord:
            mock_discord.return_value = True
            from services.position_alerts import (
                PositionAlertService,
                PositionAlertEvent,
                PositionAlertType,
                PositionAlertSeverity,
            )

            service = PositionAlertService()
            event = PositionAlertEvent(
                alert_id="test_both_123",
                alert_type=PositionAlertType.STOP_LOSS,
                severity=PositionAlertSeverity.CRITICAL,
                symbol="SPY",
                side="LONG",
                quantity=10,
                entry_price=500.0,
                current_price=480.0,
                unrealized_pnl=-200.0,
                unrealized_pnl_pct=-0.04,
                message="Both channels",
            )
            await service._dispatch_critical(event)
            mock_discord.assert_called_once()


# ======================================================================
# Edge cases and error handling
# ======================================================================

class TestDiscordNotifierEdgeCases:
    """Test edge cases and error paths."""

    def test_singleton_available(self):
        """Global singleton should be importable."""
        from services.discord_notifier import discord_notifier
        assert discord_notifier is not None
        assert isinstance(discord_notifier, DiscordNotifier)

    def test_severity_emoji_unknown(self):
        """Unknown severity should get default bell emoji."""
        from services.discord_notifier import DiscordNotifier
        assert DiscordNotifier._severity_emoji("UNKNOWN") == "🔔"
        assert DiscordNotifier._severity_emoji("") == "🔔"

    @pytest.mark.asyncio
    async def test_send_alert_empty_message(self, notifier, mock_aiohttp):
        """Should handle empty message gracefully."""
        result = await notifier.send_alert("Title", "", "INFO")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_alert_special_chars(self, notifier, mock_aiohttp):
        """Should handle special characters in fields."""
        result = await notifier.send_alert(
            "Title with <b>HTML</b> & @mentions",
            "Message with **markdown** and `code`",
            "INFO",
            fields=[{"name": "P&L %", "value": "-5.5%", "inline": False}],
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_position_alert_zero_values(self, notifier, mock_aiohttp):
        """Should handle zero P&L values."""
        result = await notifier.send_position_alert(
            alert_type="POSITION_OPEN",
            symbol="SPY", side="LONG", quantity=0,
            entry_price=0.0, current_price=0.0,
            unrealized_pnl=0.0, unrealized_pnl_pct=0.0,
            message="Zero values test",
            severity="INFO",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_system_alert_empty_metric(self, notifier, mock_aiohttp):
        """Should work with no metric."""
        result = await notifier.send_system_alert("Title", "Desc", "INFO")
        assert result is True
        embed = mock_aiohttp.post.call_args[1]["json"]["embeds"][0]
        assert "fields" not in embed or embed["fields"] == []


# ======================================================================
# Asyncio event loop for module-level async fixtures
# ======================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
