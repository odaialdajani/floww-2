"""Lodestar tool registry — the load-bearing piece (plan v3 L1).

Each tool declares: name, description, JSON-schema params, call_style,
cost_class, max_tokens_out, covers, fn. Registration raises at import
if mutating is anything but False (read-only by construction).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Module paths the research registry may never import (plan v3 L1 proof).
BANNED_MODULE_SUBSTRINGS = (
    "services.order_router",
    "services.public_api",
    "alpaca_client",
    "paper_trading",
    "services.paper_trading",
    "routes.live_trading",
    "services.agent.actions",
)

# Token scan for order-shaped methods (plan v3 L1 proof #4).
BANNED_TOKEN_SUBSTRINGS = (
    "place_order",
    "place_market_order",
    "place_limit_order",
    "place_stop_order",
    "place_multileg_order",
    "place_multi_leg_order",
    "place_stock_order",
    "close_position",
    "cancel_order",
    "submit_order",
    "execute_paper_trade",
    "LIVE_TRADING_ENABLED",
    "FLOWW_ENABLE_LIVE_PUBLIC",
)

CALL_STYLES = ("direct", "enriched", "internal-http")
COST_CLASSES = ("cheap", "normal", "heavy")


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, Any]
    call_style: str
    cost_class: str = "normal"
    max_tokens_out: int = 800
    covers: Any = None  # list[str] | Callable[[str], bool] | None (None = all)
    fn: Callable[..., Any] | None = None
    mutating: bool = False

    def covers_ticker(self, ticker: str) -> bool:
        if self.covers is None:
            return True
        if callable(self.covers):
            try:
                return bool(self.covers(ticker))
            except Exception:
                return False
        try:
            return ticker.upper() in [t.upper() for t in self.covers]
        except Exception:
            return False


_TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    """Register a research tool. Refuses anything mutating."""
    if tool.mutating is not False:
        raise ValueError(f"tool {tool.name!r}: mutating must be False (read-only registry)")
    if tool.call_style not in CALL_STYLES:
        raise ValueError(f"tool {tool.name!r}: unknown call_style {tool.call_style!r}")
    if tool.cost_class not in COST_CLASSES:
        raise ValueError(f"tool {tool.name!r}: unknown cost_class {tool.cost_class!r}")
    if tool.name in _TOOLS:
        raise ValueError(f"tool {tool.name!r} already registered")
    _TOOLS[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def list_tools() -> list[Tool]:
    return [ _TOOLS[k] for k in sorted(_TOOLS) ]


def clear_tools() -> None:
    """Test-only: reset the registry."""
    _TOOLS.clear()
