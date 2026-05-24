"""
backend/services/discord_notifier.py

Discord webhook notifier for Oracle alerts — sends rich embed messages
to any Discord channel via incoming webhook.

Features:
- Severity-based embed colors (CRITICAL=red, WARNING=amber, INFO=blue)
- Position alert formatting with P&L, symbol, side, price
- System alert formatting (killswitch, backpressure, anomalies)
- Markdown support (Discord flavoured)
- Configurable username + avatar via webhook settings

Environment:
    DISCORD_WEBHOOK_URL — Discord channel webhook URL
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Embed colour constants (decimal)
COLOR_CRITICAL = 0xE74C3C   # Red
COLOR_WARNING = 0xF39C12    # Amber/Orange
COLOR_INFO = 0x3498DB       # Blue
COLOR_SUCCESS = 0x2ECC71    # Green
COLOR_NEUTRAL = 0x95A5A6    # Grey

# Alert type -> colour mapping
SEVERITY_COLORS = {
    "CRITICAL": COLOR_CRITICAL,
    "WARNING": COLOR_WARNING,
    "INFO": COLOR_INFO,
    "SUCCESS": COLOR_SUCCESS,
}


class DiscordNotifier:
    """Sends formatted messages to Discord via webhook.

    Usage:
        notifier = DiscordNotifier()
        await notifier.send_alert("STOP LOSS", "SPY", "CRITICAL", "message...")
        await notifier.send_position_alert(position_data)
        await notifier.send_system_alert(title, description, severity)
    """

    def __init__(self):
        self._webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
        self._available = bool(self._webhook_url)
        if self._available:
            log.info("DiscordNotifier initialized (webhook configured)")
        else:
            log.info("DiscordNotifier: DISCORD_WEBHOOK_URL not set — alerts logged only")

    @property
    def available(self) -> bool:
        """Whether this notifier has a configured webhook URL."""
        return self._available

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "INFO",
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None,
    ) -> bool:
        """Send a simple alert to Discord with an embed.

        Args:
            title: Embed title (bold heading)
            message: Embed description text
            severity: One of CRITICAL, WARNING, INFO, SUCCESS
            fields: Optional list of {"name": ..., "value": ..., "inline": bool}
            footer: Optional footer text (e.g. timestamp)

        Returns:
            bool — whether the send succeeded
        """
        if not self._available:
            log.info("[DISCORD MOCK] %s [%s]: %s", title, severity, message[:100])
            return False

        colour = SEVERITY_COLORS.get(severity.upper(), COLOR_NEUTRAL)

        embed = {
            "title": title[:256],
            "description": message[:2048],
            "color": colour,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if fields:
            embed["fields"] = [{
                "name": f["name"][:256],
                "value": f["value"][:1024],
                "inline": f.get("inline", False),
            } for f in fields[:25]]  # Discord max 25 fields

        if footer:
            embed["footer"] = {"text": footer[:2048]}

        payload = {
            "username": "Oracle Alerts",
            "avatar_url": "https://raw.githubusercontent.com/navhitsj/floww/main/assets/oracle.png",
            "embeds": [embed],
        }

        return await self._post(payload)

    async def send_position_alert(
        self,
        alert_type: str,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: float,
        current_price: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
        message: str,
        severity: str = "INFO",
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a position alert to Discord with structured fields."""
        colour = SEVERITY_COLORS.get(severity.upper(), COLOR_NEUTRAL)

        # Colour the P&L value
        pnl_emoji = "🟢" if unrealized_pnl >= 0 else "🔴"

        fields = [
            {"name": "Symbol", "value": f"`{symbol}`", "inline": True},
            {"name": "Side", "value": f"`{side}`", "inline": True},
            {"name": "Qty", "value": f"`{quantity}`", "inline": True},
            {"name": "Entry", "value": f"`${entry_price:.2f}`", "inline": True},
            {"name": "Current", "value": f"`${current_price:.2f}`", "inline": True},
            {"name": f"P&L {pnl_emoji}", "value": f"`${unrealized_pnl:+.2f}`", "inline": True},
            {"name": "P&L %", "value": f"`{unrealized_pnl_pct:+.2%}`", "inline": True},
        ]

        if details:
            # Fields that are monetary (price, pnl, value)
            monetary_keys = {"entry_price", "exit_price", "current_price", "portfolio_value", "peak_value"}
            for k, v in details.items():
                display_name = k.replace("_", " ").title()
                if isinstance(v, float):
                    if k in monetary_keys:
                        fields.append({"name": display_name, "value": f"`${v:.2f}`", "inline": True})
                    elif "pct" in k.lower() or "threshold" in k.lower():
                        fields.append({"name": display_name, "value": f"`{v:.2%}`", "inline": True})
                    else:
                        fields.append({"name": display_name, "value": f"`{v:.2f}`", "inline": True})
                else:
                    fields.append({"name": display_name, "value": f"`{v}`", "inline": True})

        return await self.send_alert(
            title=f"{self._severity_emoji(severity)} {alert_type}: {symbol}",
            message=message[:2048],
            severity=severity,
            fields=fields,
            footer=f"Oracle Alert • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        )

    async def send_system_alert(
        self,
        title: str,
        description: str,
        severity: str = "WARNING",
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
    ) -> bool:
        """Send a system/infrastructure alert (killswitch, backpressure, anomaly)."""
        fields = []
        if metric_name and metric_value is not None:
            fields.append({"name": metric_name, "value": f"`{metric_value}`", "inline": True})

        return await self.send_alert(
            title=f"{self._severity_emoji(severity)} {title}",
            message=description[:2048],
            severity=severity,
            fields=fields if fields else None,
            footer=f"System Alert • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _post(self, payload: Dict[str, Any]) -> bool:
        """POST payload to Discord webhook."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 204):
                        log.debug("Discord webhook sent (status=%d)", resp.status)
                        return True
                    else:
                        body = await resp.text()
                        log.warning("Discord webhook failed (status=%d): %s", resp.status, body[:200])
                        return False
        except ImportError:
            log.warning("aiohttp not installed — Discord alerts unavailable")
            return False
        except Exception as e:
            log.warning("Discord webhook error: %s", e)
            return False

    @staticmethod
    def _severity_emoji(severity: str) -> str:
        """Get emoji for severity level."""
        return {
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "INFO": "ℹ️",
            "SUCCESS": "✅",
        }.get(severity.upper(), "🔔")


# Global singleton
discord_notifier = DiscordNotifier()
