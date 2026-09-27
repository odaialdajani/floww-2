"""Unavailable reads never trigger an implicit provider call."""

import pytest

import services.agent.tools as tools
from services.agent.registry import get_tool


@pytest.mark.asyncio
async def test_bundle_survives_chain_outage(monkeypatch):
    monkeypatch.setattr(tools, "_reads", None)
    result = await get_tool("gex_profile").fn("SPY", horizon="all")
    assert result == {"status": "unavailable", "reason": "Research data source is not connected", "data": None}
