"""Explicit alert formatting/sending, recovered from a5e7369a.

No singleton, environment-driven activation, polling, or dispatcher wiring.
Constructing this helper performs no I/O. Only an explicit send method sends.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)
SEVERITY_COLORS = {"CRITICAL": 0xE74C3C, "WARNING": 0xF39C12, "INFO": 0x3498DB, "SUCCESS": 0x2ECC71}


def _display(value: Any, kind: str = "number") -> str:
    if value is None or isinstance(value, bool):
        return "Unavailable"
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return "Unavailable"
    if not math.isfinite(number):
        return "Unavailable"
    if kind == "money":
        return f"${number:,.2f}"
    if kind == "ratio":
        return f"{number:+.2%}"
    return f"{number:g}"


class DiscordNotifier:
    def __init__(self, webhook_url: str | None = None, *, transport: httpx.AsyncBaseTransport | None = None):
        self._webhook_url = webhook_url
        self._transport = transport

    @property
    def available(self) -> bool:
        return bool(self._webhook_url and self._webhook_url.strip())

    @staticmethod
    def build_payload(title: str, message: str, severity="INFO", fields=None, footer=None) -> dict[str, Any]:
        """Pure formatting; respect per-field and complete-embed text limits."""
        embed: dict[str, Any] = {
            "title": str(title)[:256], "description": str(message)[:2048],
            "color": SEVERITY_COLORS.get(str(severity).upper(), 0x95A5A6),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        budget = 6000 - len(embed["title"]) - len(embed["description"])
        if footer:
            text = str(footer)[:min(2048, budget)]
            embed["footer"] = {"text": text}
            budget -= len(text)
        formatted = []
        for item in (fields or [])[:25]:
            if budget < 2:
                break
            name = str(item.get("name") or "Value")[:min(256, budget - 1)]
            raw = item.get("value")
            if isinstance(raw, float) and not math.isfinite(raw):
                raw = None
            value = ("Unavailable" if raw is None else str(raw)) or "Unavailable"
            value = value[:min(1024, budget - len(name))]
            formatted.append({"name": name, "value": value, "inline": bool(item.get("inline", False))})
            budget -= len(name) + len(value)
        if formatted:
            embed["fields"] = formatted
        return {"username": "Oracle Alerts", "allowed_mentions": {"parse": []}, "embeds": [embed]}

    async def send_alert(self, title, message, severity="INFO", fields=None, footer=None) -> bool:
        if not self.available:
            return False
        return await self._post(self.build_payload(title, message, severity, fields, footer))

    async def send_position_alert(self, alert_type, symbol, side, quantity, entry_price, current_price,
                                  unrealized_pnl, unrealized_pnl_pct, message, severity="INFO", details=None) -> bool:
        """unrealized_pnl_pct is a ratio (0.1 = 10%); details retain their own units."""
        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Side", "value": side, "inline": True},
            {"name": "Qty", "value": _display(quantity), "inline": True},
            {"name": "Entry", "value": _display(entry_price, "money"), "inline": True},
            {"name": "Current", "value": _display(current_price, "money"), "inline": True},
            {"name": "P&L", "value": _display(unrealized_pnl, "money"), "inline": True},
            {"name": "P&L %", "value": _display(unrealized_pnl_pct, "ratio"), "inline": True},
        ]
        for key, value in (details or {}).items():
            # Never reinterpret arbitrary "threshold" values as percentages.
            fields.append({"name": str(key).replace("_", " "), "value": value, "inline": True})
        return await self.send_alert(f"{alert_type}: {symbol}", message, severity, fields)

    async def send_system_alert(self, title, description, severity="WARNING", metric_name=None, metric_value=None):
        fields = [{"name": metric_name, "value": _display(metric_value)}] if metric_name else None
        return await self.send_alert(title, description, severity, fields)

    async def _post(self, payload) -> bool:
        # AsyncClient logs the full URL (including webhook secrets) at INFO.
        # Use its public transport interface directly, with explicit timeouts.
        transport = self._transport or httpx.AsyncHTTPTransport()
        try:
            request = httpx.Request("POST", self._webhook_url, json=payload,
                extensions={"timeout": {name: 10.0 for name in ("connect", "read", "write", "pool")}})
            response = await transport.handle_async_request(request)
            try:
                status = response.status_code
            finally:
                await response.aclose()
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            # Exception strings/response bodies may contain the secret webhook URL.
            log.warning("Discord send failed (%s)", type(exc).__name__)
            return False
        finally:
            if self._transport is None:
                await transport.aclose()
        if status in (200, 204):
            return True
        log.warning("Discord send failed (status=%d)", status)
        return False
