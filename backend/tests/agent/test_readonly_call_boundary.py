"""Every advertised capability runs with real calculators and order/network traps."""

import importlib
from datetime import UTC, datetime

import httpx
import pytest

import services.agent.tools as catalog
from services.agent.reads import ResearchReads
from services.agent.registry import list_tools


@pytest.mark.asyncio
async def test_all_advertised_tools_have_no_order_or_provider_calls(monkeypatch):
    fired = []

    def forbidden(*args, **kwargs):
        fired.append("forbidden")
        raise AssertionError("Research crossed the read-only boundary")

    targets = {
        ("services.public_api", "PublicBroker"): [
            "place_order",
            "place_market_order",
            "place_limit_order",
            "place_stop_order",
            "place_multileg_order",
            "cancel_order",
        ],
        ("alpaca_client", "AlpacaClient"): [
            "place_stock_order",
            "place_option_order",
            "place_bracket_order",
            "close_position",
            "cancel_order",
        ],
        ("services.paper_trading", "PaperTradingEngine"): ["submit_order", "execute_order"],
    }
    for (module, owner), methods in targets.items():
        cls = getattr(importlib.import_module(module), owner)
        for method in methods:
            monkeypatch.setattr(cls, method, forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    now = datetime.now(UTC).isoformat()
    chain = {
        "spot": 100,
        "event_time": now,
        "contracts": [
            {"strike": strike, "type": kind, "gamma": 0.01, "open_interest": 10, "expiry": "2026-09-18"}
            for strike, kind in [(95, "P"), (100, "C"), (105, "C")]
        ],
    }
    reads = ResearchReads(
        lambda *args: chain,
        lambda *args: None,
        lambda *args: [{"asof_ts": now, "expiry": "2026-09-18", "bias": "BULLISH", "conviction": 80}],
    )
    monkeypatch.setattr(catalog, "_reads", reads)
    tools = list_tools()
    assert {tool.name for tool in tools} == {"market_context", "gex_profile", "flip_zones", "alerts_feed"}
    for tool in tools:
        result = await tool.fn("SPY", horizon="all")
        assert result["status"] in {"ok", "degraded", "unavailable"}
        if result["status"] == "ok":
            assert result["data"]
        if tool.name in {"market_context", "gex_profile", "alerts_feed"}:
            assert result["data"], tool.name
    assert fired == []
