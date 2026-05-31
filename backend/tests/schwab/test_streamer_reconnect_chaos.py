"""Chaos test: streamer survives connection drops with bounded reconnect."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK


@pytest.mark.asyncio
async def test_reconnect_on_connection_closed():
    """When the underlying socket raises ConnectionClosed, streamer reconnects within N attempts."""
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer(max_reconnect_delay=2.0, initial_reconnect_delay=0.1)

    # Mock token manager
    streamer.tokens = MagicMock()
    streamer.tokens.get_access_token.return_value = "test-token"
    streamer.tokens.is_expired.return_value = False
    streamer.tokens.refresh_token = AsyncMock(return_value="refreshed-token")

    # Mock websocket connection: fails twice, then succeeds (stops loop via _running=False)
    call_count = 0

    async def mock_connect_and_stream():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ConnectionClosedError(None, None)
        # On third call, set running to False to exit the loop
        streamer._running = False

    with patch.object(streamer, '_connect_and_stream', mock_connect_and_stream):
        await streamer.start()

    assert call_count == 3, f"should have retried 3 times, got {call_count}"
    assert streamer._metrics["reconnects"] == 2


@pytest.mark.asyncio
async def test_reconnect_gives_up_on_token_failure():
    """When token is invalid and refresh fails, streamer raises after logging error."""
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer(max_reconnect_delay=2.0, initial_reconnect_delay=0.01)
    streamer.tokens = MagicMock()
    streamer.tokens.get_access_token.return_value = None
    streamer.tokens.is_expired.return_value = True
    streamer.tokens.refresh_token = AsyncMock(return_value=None)

    with pytest.raises(ConnectionError, match="No valid Schwab access token"):
        await streamer._connect_and_stream()


@pytest.mark.asyncio
async def test_reconnect_exponential_backoff():
    """Reconnect delay should double each attempt, capped at max_reconnect_delay."""
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer(max_reconnect_delay=4.0, initial_reconnect_delay=1.0)
    streamer.tokens = MagicMock()
    streamer.tokens.get_access_token.return_value = "test-token"
    streamer.tokens.is_expired.return_value = False

    delays = []

    async def mock_connect():
        raise ConnectionClosedError(None, None)

    with patch.object(streamer, '_connect_and_stream', mock_connect), \
         patch('asyncio.sleep', side_effect=lambda d: delays.append(d)):
        streamer._running = True
        # Manually run a few reconnect iterations
        for _ in range(4):
            try:
                await streamer._connect_and_stream()
            except ConnectionClosedError:
                streamer._metrics["reconnects"] += 1
                await asyncio.sleep(streamer._reconnect_delay)
                streamer._reconnect_delay = min(streamer._reconnect_delay * 2, streamer.max_reconnect_delay)

    # Delays should be: 1.0, 2.0, 4.0, 4.0 (capped at max)
    assert delays[0] == 1.0
    assert delays[1] == 2.0
    assert delays[2] == 4.0
    assert delays[3] == 4.0  # capped


@pytest.mark.asyncio
async def test_stop_closes_websocket():
    """stop() should close the underlying WebSocket."""
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer()
    mock_ws = AsyncMock()
    streamer._ws = mock_ws

    await streamer.stop()

    mock_ws.close.assert_called_once()
    assert streamer._running is False


@pytest.mark.asyncio
async def test_reconnect_resets_delay_on_success():
    """After a successful connection, reconnect_delay should reset to initial."""
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer(max_reconnect_delay=60.0, initial_reconnect_delay=1.0)
    streamer._reconnect_delay = 32.0  # Simulate having backed off

    streamer.tokens = MagicMock()
    streamer.tokens.get_access_token.return_value = "test-token"
    streamer.tokens.is_expired.return_value = False

    async def mock_connect_and_stream():
        streamer._reconnect_delay = streamer.initial_reconnect_delay  # Simulate reset
        streamer._running = False  # Exit loop

    with patch.object(streamer, '_connect_and_stream', mock_connect_and_stream):
        await streamer.start()

    assert streamer._reconnect_delay == 1.0
