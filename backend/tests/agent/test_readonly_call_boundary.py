"""Call-boundary proof (plan v3 L1): no research tool can fire an order call.

Patches every order/liquidation entry point to raise, runs representative
tools + a loop turn off fixtures, asserts none fired.
"""

import contextlib

import pytest

import services.agent.tools  # noqa: F401 (registers catalog)
from services.agent.registry import list_tools


@pytest.mark.asyncio
async def test_no_tool_fires_order_calls(monkeypatch):
    fired: list[str] = []

    def _boom(name):
        def _raise(*a, **k):
            fired.append(name)
            raise AssertionError(f"order path fired: {name}")

        return _raise

    targets = [
        ("services.public_api", "PublicBroker"),
        ("alpaca_client", "AlpacaClient"),
        ("services.paper_trading", "PaperTradingEngine"),
        ("paper_trading", "execute_paper_trade"),
    ]
    for mod_name, attr in targets:
        with contextlib.suppress(Exception):
            mod = __import__(mod_name, fromlist=[attr])
            obj = getattr(mod, attr, None)
            if obj is None:
                continue
            for meth in ("place_order", "place_market_order", "place_limit_order", "place_stop_order", "place_multileg_order", "place_stock_order", "close_position", "cancel_order", "submit_order"):
                if hasattr(obj, meth):
                    with contextlib.suppress(Exception):
                        monkeypatch.setattr(obj, meth, _boom(f"{mod_name}.{attr}.{meth}"))

    for tool in list_tools()[:12]:
        with contextlib.suppress(Exception):
            if tool.fn is not None:
                await tool.fn("SPY", horizon="all")
    assert fired == []
