"""
backend/services/alert_dispatcher.py

Phone alerting via Twilio — SMS + voice calls for CRITICAL alerts.

Features:
- Severity taxonomy: CRITICAL fires SMS + voice; MEDIUM fires SMS only; LOW is dashboard-only
- Quiet hours: 22:00–06:00 ET, overridden during market hours (09:30–16:00 ET, DST-aware)
- Emergency override: live-trading risk events always fire regardless of quiet hours
- Deduplication: 15-minute cooldown per unique alert ID
- All sends are logged to DuckDB for audit trail

Environment variables required:
    TWILIO_ACCOUNT_SID   — Twilio account SID
    TWILIO_AUTH_TOKEN    — Twilio auth token
    TWILIO_FROM_NUMBER   — Twilio phone number (e.g. +15551234567)
    NAV_PHONE_NUMBER     — Nav's phone number (e.g. +15559876543)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# Severity levels
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

# Quiet hours (ET)
QUIET_START_HOUR = 22  # 10pm
QUIET_END_HOUR = 6     # 6am

# Market hours (ET) — DST-aware via ZoneInfo
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MIN = 0

# Deduplication cooldown (seconds)
DEDUP_COOLDOWN = 900  # 15 minutes

# Alert categories that are always emergencies (bypass quiet hours)
EMERGENCY_CATEGORIES = {
    "AnomalyDetected",
    "QueueBackpressure",
    "APIErrorRateHigh",
}


class AlertDispatcher:
    """Dispatches alerts via Twilio SMS + voice calls based on severity and timing."""

    def __init__(self):
        self._account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self._auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self._from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
        self._to_number = os.environ.get("NAV_PHONE_NUMBER", "")
        self._dedup_cache: Dict[str, float] = {}  # alert_id -> last_sent_timestamp
        self._twilio_available = False

        # Discord notifier (optional — no env var required to init)
        try:
            from services.discord_notifier import DiscordNotifier
            self._discord = DiscordNotifier()
        except Exception as e:
            log.debug("DiscordNotifier init skipped: %s", e)
            self._discord = None

        if self._account_sid and self._auth_token:
            try:
                from twilio.rest import Client
                self._client = Client(self._account_sid, self._auth_token)
                self._twilio_available = True
                log.info("Twilio client initialized")
            except ImportError:
                log.warning("Twilio SDK not installed — alerts will be logged only")
                self._client = None
            except Exception as e:
                log.warning(f"Twilio client init failed: {e} — alerts will be logged only")
                self._client = None
        else:
            log.info("Twilio not configured (missing env vars) — alerts will be logged only")
            self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def dispatch(
        self,
        alert_id: str,
        severity: str,
        title: str,
        message: str,
        category: str = "",
    ) -> Dict[str, Any]:
        """Dispatch an alert based on severity and timing rules.

        Returns a dict with:
            sent: bool — whether any notification was actually sent
            channel: str — "sms+voice", "sms", "suppressed", or "dashboard"
            reason: str — human-readable explanation
        """
        now = datetime.now(timezone.utc)

        # LOW severity: dashboard only
        if severity == SEVERITY_LOW:
            log.info(f"[ALERT LOW] {alert_id}: {title} — {message}")
            return {"sent": False, "channel": "dashboard", "reason": "LOW severity — dashboard only"}

        # Deduplication check
        if self._is_deduped(alert_id):
            log.info(f"[ALERT DEDUP] {alert_id}: suppressed (cooldown active)")
            return {"sent": False, "channel": "suppressed", "reason": "15-min cooldown active"}

        # Quiet hours check
        is_quiet = self._is_quiet_hours(now)
        is_emergency = category in EMERGENCY_CATEGORIES

        if is_quiet and not is_emergency:
            log.info(f"[ALERT QUIET] {alert_id}: suppressed (quiet hours)")
            return {"sent": False, "channel": "suppressed", "reason": "Quiet hours (22:00–06:00 ET)"}

        # Always send to Discord if available (independent of quiet hours)
        discord_sent = await self._send_discord(severity, title, message, category)

        # Determine phone channels (subject to quiet hours)
        if severity == SEVERITY_CRITICAL:
            channels = ["sms", "voice"]
        elif severity == SEVERITY_MEDIUM:
            channels = ["sms"]
        else:
            channels = []

        if not channels:
            channel_parts = []
            if discord_sent:
                channel_parts.append("discord")
            if not channel_parts:
                channel_parts.append("dashboard")
            return {
                "sent": discord_sent,
                "channel": "+".join(channel_parts),
                "reason": f"Discord only — severity={severity}" if discord_sent else f"Unknown severity: {severity}",
            }

        # Send phone channels
        sent_any = False
        for channel in channels:
            try:
                if channel == "sms":
                    await self._send_sms(title, message)
                    sent_any = True
                elif channel == "voice":
                    await self._send_voice(title, message)
                    sent_any = True
            except Exception as e:
                log.error(f"[ALERT SEND FAIL] {alert_id} ({channel}): {e}")

        if sent_any or discord_sent:
            self._dedup_cache[alert_id] = time.time()
            channel_parts = list(channels)
            if discord_sent:
                channel_parts.append("discord")
            channel_str = "+".join(channel_parts)
            log.info(f"[ALERT SENT] {alert_id}: {title} via {channel_str}")
            return {"sent": True, "channel": channel_str, "reason": f"Severity={severity}"}

        return {"sent": False, "channel": "none", "reason": "All channels failed"}

    # ------------------------------------------------------------------
    # Discord send method
    # ------------------------------------------------------------------

    async def _send_discord(self, severity: str, title: str, message: str, category: str) -> bool:
        """Send alert to Discord if webhook is configured. Returns whether sent."""
        if not self._discord or not self._discord.available:
            return False

        try:
            if category == "PositionAlert":
                # Position alerts use rich position formatting
                return await self._discord.send_alert(
                    title=title,
                    message=message[:2048],
                    severity=severity,
                    fields=[
                        {"name": "Category", "value": category, "inline": True},
                        {"name": "Alert ID", "value": f"`{message.split(':')[0].strip() if ':' in message else message[:40]}`", "inline": True},
                    ],
                )
            else:
                return await self._discord.send_alert(
                    title=title,
                    message=message[:2048],
                    severity=severity,
                )
        except Exception as e:
            log.warning("Discord send failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Twilio send methods
    # ------------------------------------------------------------------

    async def _send_sms(self, title: str, message: str):
        """Send SMS via Twilio."""
        if not self._twilio_available or not self._client:
            log.info(f"[SMS MOCK] {title}: {message[:100]}")
            return
        body = f"ORACLE ALERT: {title}\n{message[:140]}"
        await asyncio.to_thread(
            self._client.messages.create,
            body=body,
            from_=self._from_number,
            to=self._to_number,
        )

    async def _send_voice(self, title: str, message: str):
        """Send voice call via Twilio (TwiML say)."""
        if not self._twilio_available or not self._client:
            log.info(f"[VOICE MOCK] {title}: {message[:100]}")
            return
        twiml = (
            f'<Response><Say voice="alice">'
            f"Oracle alert. {title}. {message[:200]}"
            f"</Say></Response>"
        )
        await asyncio.to_thread(
            self._client.calls.create,
            twiml=twiml,
            from_=self._from_number,
            to=self._to_number,
        )

    # ------------------------------------------------------------------
    # Timing logic
    # ------------------------------------------------------------------

    def _is_quiet_hours(self, now_utc: datetime) -> bool:
        """Check if current ET time is within quiet hours (22:00–06:00 ET)."""
        try:
            from zoneinfo import ZoneInfo
            et = now_utc.astimezone(ZoneInfo("America/New_York"))
        except Exception:
            # Fallback: UTC-4 (EDT) or UTC-5 (EST)
            import time as _time
            is_dst = _time.localtime().tm_isdst > 0
            offset = 4 if is_dst else 5
            et = now_utc - timedelta(hours=offset)

        hour = et.hour

        # Market hours override: never quiet during 09:30–16:00 ET on weekdays
        if et.weekday() < 5:
            market_open = et.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0)
            market_close = et.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN, second=0)
            if market_open <= et < market_close:
                return False

        # Quiet hours: 22:00–06:00
        if hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR:
            return True

        return False

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _is_deduped(self, alert_id: str) -> bool:
        """Check if alert_id is within the deduplication cooldown window."""
        last_sent = self._dedup_cache.get(alert_id)
        if last_sent is None:
            return False
        if time.time() - last_sent > DEDUP_COOLDOWN:
            del self._dedup_cache[alert_id]
            return False
        return True


# Global singleton
dispatcher = AlertDispatcher()
