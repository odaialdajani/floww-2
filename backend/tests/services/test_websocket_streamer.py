"""
Tests for services/websocket_streamer.py — ConnectionManager.

Covers: connect, disconnect, broadcast, broadcast_all, close_all.
Uses a mock WebSocket to avoid real network I/O.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.websocket_streamer import ConnectionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeWS:
    """Minimal async WebSocket stand-in."""

    def __init__(self, name="ws"):
        self.name = name
        self.accept = AsyncMock()
        self.send_text = AsyncMock()
        self.close = AsyncMock()
        self.sent_messages: list[str] = []

    def set_fail_send(self, exc=None):
        if exc is None:
            exc = RuntimeError("broken")
        self.send_text.side_effect = exc


@pytest.fixture
def mgr():
    return ConnectionManager()


@pytest.fixture
def ws1():
    return FakeWS("ws1")


@pytest.fixture
def ws2():
    return FakeWS("ws2")


@pytest.fixture
def ws3():
    return FakeWS("ws3")


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_no_topics_adds_to_all(mgr, ws1):
    await mgr.connect(ws1)
    assert ws1 in mgr._active is False or ws1 in mgr._all
    assert ws1 in mgr._all


@pytest.mark.asyncio
async def test_connect_with_topics_registers_per_topic(mgr, ws1):
    with patch("services.websocket_streamer.obs_metrics") as mock_obs:
        mock_obs.websocket_connections.labels.return_value.inc = MagicMock()
        await mgr.connect(ws1, topics=["ticks", "flow"])

    assert "ticks" in mgr._active
    assert "flow" in mgr._active
    assert ws1 in mgr._active["ticks"]
    assert ws1 in mgr._active["flow"]
    assert mock_obs.websocket_connections.labels.call_count == 2


@pytest.mark.asyncio
async def test_connect_accepts_websocket(mgr, ws1):
    await mgr.connect(ws1)
    ws1.accept.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_multiple_clients_same_topic(mgr, ws1, ws2):
    with patch("services.websocket_streamer.obs_metrics"):
        await mgr.connect(ws1, topics=["ticks"])
        await mgr.connect(ws2, topics=["ticks"])

    assert len(mgr._active["ticks"]) == 2
    assert ws1 in mgr._active["ticks"]
    assert ws2 in mgr._active["ticks"]


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_removes_from_all(mgr, ws1):
    await mgr.connect(ws1)
    mgr.disconnect(ws1)
    assert ws1 not in mgr._all


@pytest.mark.asyncio
async def test_disconnect_removes_from_topics(mgr, ws1):
    with patch("services.websocket_streamer.obs_metrics") as mock_obs:
        mock_obs.websocket_connections.labels.return_value.inc = MagicMock()
        mock_obs.websocket_connections.labels.return_value.dec = MagicMock()
        await mgr.connect(ws1, topics=["ticks"])

    mgr.disconnect(ws1)
    assert "ticks" not in mgr._active


@pytest.mark.asyncio
async def test_disconnect_decrements_metric(mgr, ws1):
    with patch("services.websocket_streamer.obs_metrics") as mock_obs:
        mock_obs.websocket_connections.labels.return_value.inc = MagicMock()
        mock_obs.websocket_connections.labels.return_value.dec = MagicMock()
        await mgr.connect(ws1, topics=["ticks"])

    mgr.disconnect(ws1)
    mock_obs.websocket_connections.labels.assert_any_call(topic="ticks")


@pytest.mark.asyncio
async def test_disconnect_empty_topic_is_cleaned_up(mgr, ws1, ws2):
    with patch("services.websocket_streamer.obs_metrics"):
        await mgr.connect(ws1, topics=["ticks"])
        await mgr.connect(ws2, topics=["ticks"])

    mgr.disconnect(ws1)
    assert "ticks" in mgr._active
    assert ws2 in mgr._active["ticks"]

    mgr.disconnect(ws2)
    assert "ticks" not in mgr._active


@pytest.mark.asyncio
async def test_disconnect_unknown_ws_is_noop(mgr, ws1):
    mgr.disconnect(ws1)
    assert len(mgr._all) == 0


# ---------------------------------------------------------------------------
# broadcast
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcast_sends_to_subscribed_clients(mgr, ws1, ws2):
    with patch("services.websocket_streamer.obs_metrics"):
        await mgr.connect(ws1, topics=["ticks"])
        await mgr.connect(ws2, topics=["ticks"])

    data = {"price": 6000.5, "symbol": "SPX"}
    await mgr.broadcast("ticks", data)

    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()

    sent = json.loads(ws1.send_text.call_args[0][0])
    assert sent["price"] == 6000.5
    assert sent["symbol"] == "SPX"


@pytest.mark.asyncio
async def test_broadcast_no_subscribers_is_noop(mgr):
    await mgr.broadcast("ticks", {"price": 1})


@pytest.mark.asyncio
async def test_broadcast_only_reaches_correct_topic(mgr, ws1, ws2):
    with patch("services.websocket_streamer.obs_metrics"):
        await mgr.connect(ws1, topics=["ticks"])
        await mgr.connect(ws2, topics=["flow"])

    await mgr.broadcast("ticks", {"msg": "hello"})

    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_removes_disconnected_client(mgr, ws1, ws2):
    with patch("services.websocket_streamer.obs_metrics"):
        await mgr.connect(ws1, topics=["ticks"])
        await mgr.connect(ws2, topics=["ticks"])

    ws1.set_fail_send()

    await mgr.broadcast("ticks", {"msg": "test"})

    assert ws1 not in mgr._all
    assert ws1 not in mgr._active.get("ticks", set())
    assert ws2 in mgr._all


@pytest.mark.asyncio
async def test_broadcast_json_serializes_with_default_str(mgr, ws1):
    """Non-serializable types (e.g. datetime) should be serialized via default=str."""
    from datetime import datetime

    with patch("services.websocket_streamer.obs_metrics"):
        await mgr.connect(ws1, topics=["ticks"])

    dt = datetime(2026, 1, 15, 10, 30, 0)
    await mgr.broadcast("ticks", {"time": dt})

    raw = ws1.send_text.call_args[0][0]
    parsed = json.loads(raw)
    assert parsed["time"] == "2026-01-15 10:30:00"


# ---------------------------------------------------------------------------
# broadcast_all
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcast_all_sends_to_every_connected_client(mgr, ws1, ws2, ws3):
    await mgr.connect(ws1)
    await mgr.connect(ws2)
    await mgr.connect(ws3)

    data = {"event": "system_update"}
    await mgr.broadcast_all(data)

    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()
    ws3.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_all_no_clients_is_noop(mgr):
    await mgr.broadcast_all({"event": "ping"})


@pytest.mark.asyncio
async def test_broadcast_all_removes_failed_clients(mgr, ws1, ws2):
    await mgr.connect(ws1)
    await mgr.connect(ws2)

    ws2.set_fail_send()

    await mgr.broadcast_all({"msg": "hello"})

    assert ws1 in mgr._all
    assert ws2 not in mgr._all


# ---------------------------------------------------------------------------
# close_all
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_all_closes_every_client(mgr, ws1, ws2):
    await mgr.connect(ws1)
    await mgr.connect(ws2)

    await mgr.close_all()

    ws1.close.assert_awaited_once()
    ws2.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_all_clears_state(mgr, ws1):
    with patch("services.websocket_streamer.obs_metrics"):
        await mgr.connect(ws1, topics=["ticks"])

    await mgr.close_all()

    assert len(mgr._all) == 0
    assert len(mgr._active) == 0


@pytest.mark.asyncio
async def test_close_all_custom_code_and_reason(mgr, ws1):
    await mgr.connect(ws1)
    await mgr.close_all(code=4000, reason="maintenance")

    ws1.close.assert_awaited_once_with(code=4000, reason="maintenance")


@pytest.mark.asyncio
async def test_close_all_suppresses_close_errors(mgr, ws1):
    ws1.close.side_effect = RuntimeError("already closed")
    await mgr.connect(ws1)

    await mgr.close_all()
    assert len(mgr._all) == 0


@pytest.mark.asyncio
async def test_close_all_no_clients_is_noop(mgr):
    await mgr.close_all()


# ---------------------------------------------------------------------------
# module-level singleton
# ---------------------------------------------------------------------------

def test_module_level_manager_exists():
    from services.websocket_streamer import manager
    assert isinstance(manager, ConnectionManager)
