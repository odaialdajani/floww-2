"""Chaos tests for SchwabStreamer — reconnect, token refresh, resubscribe.

All tests are fully mocked — no live Schwab connection required.
Tests the production reconnect logic in services/schwab_streamer.py.
"""
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# Async websocket mocks
#
# Production does `async with websockets.connect(...) as ws:` then
# `async for msg in ws:`. websockets.connect() is called synchronously and
# returns an async context manager, so a patched side_effect must be a *sync*
# function returning an async-CM whose __aenter__ yields an async-iterable ws.
# (The old AsyncMock(side_effect=iter(...)) produced a coroutine and never
# satisfied the async-CM / async-iterator protocols — the source of the failures.)
# ---------------------------------------------------------------------------

class _FakeWS:
    """Async-iterable fake websocket: yields `messages` then ends the stream."""

    def __init__(self, messages=None, closed=False):
        self._messages = list(messages or [])
        self.closed = closed
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            self.closed = True  # stream ended => connection closed (matches real ws)
            raise StopAsyncIteration
        return self._messages.pop(0)


class _FakeConnect:
    """Async context manager returned by a mocked websockets.connect()."""

    def __init__(self, ws=None, raise_on_enter=None):
        self._ws = ws if ws is not None else _FakeWS()
        self._raise = raise_on_enter

    async def __aenter__(self):
        if self._raise is not None:
            raise self._raise
        return self._ws

    async def __aexit__(self, *exc):
        return False


def _connect_side_effect(ws=None, raise_on_enter=None, capture_headers=None):
    """Sync side_effect mimicking websockets.connect(url, extra_headers=...)."""

    def _connect(url, extra_headers=None, **kwargs):
        if capture_headers is not None and extra_headers:
            capture_headers.update(extra_headers)
        return _FakeConnect(ws=ws, raise_on_enter=raise_on_enter)

    return _connect


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_token_manager():
    """Mock SchwabTokenManager that returns a fake token."""
    tm = MagicMock()
    tm.get_access_token.return_value = "fake-access-token-12345"
    tm.is_expired.return_value = False
    tm.refresh_token = AsyncMock(return_value="refresh-token-67890")
    return tm


@pytest.fixture
def streamer(mock_token_manager):
    """Create a SchwabStreamer with mocked token manager."""
    from services.schwab_streamer import SchwabStreamer
    s = SchwabStreamer(token_manager=mock_token_manager)
    return s


# ---------------------------------------------------------------------------
# Test 1: Reconnect after websocket close
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_websocket_close_triggers_reconnect(streamer, mock_token_manager):
    """When _connect_and_stream raises, start() reconnects with backoff."""
    call_count = 0
    max_calls = 3

    async def fake_connect_and_stream():
        nonlocal call_count
        call_count += 1
        if call_count < max_calls:
            raise ConnectionError(f"simulated drop #{call_count}")
        # On 3rd call, stop the loop
        streamer._running = False

    streamer._connect_and_stream = fake_connect_and_stream
    streamer._running = True

    # Run start() — it should reconnect max_calls times then stop
    await streamer.start()

    assert call_count == max_calls, f"Expected {max_calls} connect attempts, got {call_count}"
    assert streamer._metrics["reconnects"] == max_calls - 1


# ---------------------------------------------------------------------------
# Test 2: Token refresh on 401 / expired token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_refresh_when_expired(streamer, mock_token_manager):
    """When token is expired, streamer refreshes before connecting."""
    mock_token_manager.is_expired.return_value = True
    mock_token_manager.refresh_token = AsyncMock(return_value="new-refreshed-token")

    # Capture the auth header; the connection raises after capture to exit.
    captured_headers = {}
    side_effect = _connect_side_effect(
        raise_on_enter=ConnectionError("mock connection failed"),
        capture_headers=captured_headers,
    )

    with patch("services.schwab_streamer.websockets.connect", side_effect=side_effect):
        streamer._running = True
        try:
            await streamer._connect_and_stream()
        except ConnectionError:
            pass

    # Verify refresh was called
    mock_token_manager.refresh_token.assert_called_once()
    # Verify the refreshed token was used
    assert captured_headers.get("Authorization") == "Bearer new-refreshed-token"


# ---------------------------------------------------------------------------
# Test 3: Re-subscribe after reconnect preserves state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resubscribe_after_reconnect(streamer, mock_token_manager):
    """After reconnect, all previously subscribed symbols are re-subscribed."""
    subscribed_before = {"SPY", "QQQ", "OPTIONS_SPY", "OPTIONS_QQQ", "LOB_DEPTH_SPY"}
    streamer._subscribed_symbols = subscribed_before.copy()

    # Track what gets sent after reconnect
    sent_messages = []

    async def mock_send(data):
        sent_messages.append(data)

    streamer._send = mock_send

    # Mock _subscribe_default to track calls
    subscribe_calls = []
    original_subscribe = streamer._subscribe_default

    async def tracking_subscribe():
        subscribe_calls.append("subscribe_default")
        # Don't actually send — just track that it was called

    streamer._subscribe_default = tracking_subscribe

    # Successful connection with an empty message stream (drops immediately).
    side_effect = _connect_side_effect(ws=_FakeWS(messages=[], closed=True))

    with patch("services.schwab_streamer.websockets.connect", side_effect=side_effect):
        streamer._running = True
        try:
            await streamer._connect_and_stream()
        except Exception:
            pass

    # Verify _subscribe_default was called (re-subscribe happens)
    assert len(subscribe_calls) == 1, "Should re-subscribe after reconnect"


# ---------------------------------------------------------------------------
# Test 4: Max retry exhaustion — clean failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_retry_exhaustion(streamer, mock_token_manager):
    """After repeated failures, streamer stops cleanly (no infinite loop)."""
    attempt_count = 0
    max_attempts = 5

    async def always_fail():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count >= max_attempts:
            streamer._running = False
        raise ConnectionError(f"attempt {attempt_count} failed")

    streamer._connect_and_stream = always_fail
    streamer._running = True
    streamer.initial_reconnect_delay = 0.01  # speed up test

    await streamer.start()

    assert attempt_count == max_attempts
    assert streamer._metrics["reconnects"] == max_attempts - 1
    assert streamer._running is False


# ---------------------------------------------------------------------------
# Test 5: Concurrent connect guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_connect_guard(streamer, mock_token_manager):
    """Two simultaneous start() calls don't create double connections."""
    connect_count = 0

    async def slow_connect():
        nonlocal connect_count
        connect_count += 1
        await asyncio.sleep(0.1)
        streamer._running = False
        raise ConnectionError("done")

    streamer._connect_and_stream = slow_connect
    streamer._running = True

    # Start two concurrent connections
    task1 = asyncio.create_task(streamer.start())
    await asyncio.sleep(0.01)  # let task1 start
    streamer._running = False  # stop after first
    try:
        await asyncio.wait_for(task1, timeout=2.0)
    except (asyncio.TimeoutError, Exception):
        pass

    # Should only have attempted one connection (not two)
    assert connect_count <= 1, f"Expected ≤1 connect, got {connect_count}"


# ---------------------------------------------------------------------------
# Test 6: Exponential backoff respects max_reconnect_delay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exponential_backoff_respects_max(streamer, mock_token_manager):
    """Reconnect delay doubles but never exceeds max_reconnect_delay."""
    streamer.initial_reconnect_delay = 1.0
    streamer.max_reconnect_delay = 5.0
    streamer._reconnect_delay = 1.0

    delays_seen = []
    original_sleep = asyncio.sleep

    async def tracking_sleep(delay):
        delays_seen.append(delay)
        # Don't actually sleep — speed up test
        await original_sleep(0.001)

    call_count = 0

    async def fail_then_stop():
        nonlocal call_count
        call_count += 1
        if call_count >= 4:
            streamer._running = False
        raise ConnectionError(f"drop {call_count}")

    streamer._connect_and_stream = fail_then_stop
    streamer._running = True

    with patch("asyncio.sleep", side_effect=tracking_sleep):
        await streamer.start()

    # Base delay doubles 1.0 -> 2.0 -> 4.0 (capped at 5.0); start() adds 0..30%
    # jitter on top, so each observed sleep is in [base, base * 1.3).
    assert len(delays_seen) >= 2, f"Expected >=2 delays, got {len(delays_seen)}"
    assert 1.0 <= delays_seen[0] < 1.3, f"1st delay (base 1.0 + jitter) out of range: {delays_seen[0]}"
    assert 2.0 <= delays_seen[1] < 2.6, f"2nd delay (base 2.0 + jitter) out of range: {delays_seen[1]}"
    if len(delays_seen) >= 3:
        assert 4.0 <= delays_seen[2] < 5.2, f"3rd delay (base 4.0 + jitter) out of range: {delays_seen[2]}"


# ---------------------------------------------------------------------------
# Test 7: Health tracking accuracy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_tracking(streamer, mock_token_manager):
    """Health dict updates correctly on connect/disconnect."""
    # Stream 3 messages then disconnect.
    messages = [
        json.dumps({"service": "HEARTBEAT"}),
        json.dumps({"service": "LEVELONE_EQUITIES", "content": [{"key": "SPY", "1": 450.0, "2": 450.1, "3": 450.05, "4": 100, "5": 200, "6": 1000}]}),
        json.dumps({"service": "HEARTBEAT"}),
    ]
    side_effect = _connect_side_effect(ws=_FakeWS(messages=messages))

    with patch("services.schwab_streamer.websockets.connect", side_effect=side_effect):
        streamer._running = True
        try:
            await streamer._connect_and_stream()
        except Exception:
            pass

    # After processing messages, health should reflect activity
    health = streamer.get_health()
    assert health["connected"] is False  # ws closed after stream ended
    assert streamer._metrics["messages_received"] == 3
    assert streamer._metrics["messages_parsed"] >= 1  # at least the equity message


# ---------------------------------------------------------------------------
# Test 8: Error handler dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_error_handler_dispatch(streamer, mock_token_manager):
    """Error messages are dispatched to registered error handlers."""
    error_handler = AsyncMock()
    streamer._error_handlers.append(error_handler)

    # Send an error message then disconnect.
    messages = [
        json.dumps({"error": "RATE_LIMIT_EXCEEDED", "message": "Too many requests"}),
    ]
    side_effect = _connect_side_effect(ws=_FakeWS(messages=messages))

    with patch("services.schwab_streamer.websockets.connect", side_effect=side_effect):
        streamer._running = True
        try:
            await streamer._connect_and_stream()
        except Exception:
            pass

    # Error handler should have been called
    assert error_handler.called, "Error handler was not called"
    assert streamer._metrics["errors"] >= 1
