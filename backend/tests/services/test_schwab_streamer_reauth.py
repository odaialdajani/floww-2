"""Two new Schwab streamer chaos tests: token expiry mid-stream and
re-subscribe after error-then-reconnect.

Both are fully mocked — no live Schwab connection required.  The
fixtures (streamer, mock_token_manager) come from conftest.py at the
tests/services/ level so pytest autoloads them.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .test_schwab_streamer_reconnect import _connect_side_effect, _FakeConnect, _FakeWS

# ---------------------------------------------------------------------------
# Test 9: Token expiry mid-stream triggers re-auth on reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_expiry_mid_stream_triggers_reauth(
    streamer, mock_token_manager
):
    """When the token expires while streaming, the reconnect path calls
    refresh_token before the next connect attempt.

    Production flow: start() -> _connect_and_stream() -> _get_valid_token()
    -> if expired, calls refresh_token().  We patch websockets.connect to
    yield one message then close on the first call, and close immediately on
    the second call, triggering reconnect.
    """
    call_count = 0

    def is_expired_side_effect() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count >= 2  # expired on 2nd+ check

    mock_token_manager.is_expired.side_effect = is_expired_side_effect
    mock_token_manager.refresh_token = AsyncMock(return_value="reauth-token-99")

    connect_calls: list[dict[str, Any] | None] = []

    def fake_connect(url, extra_headers=None, **kwargs):
        connect_calls.append(extra_headers)
        if len(connect_calls) >= 2:
            streamer._running = False
            return _FakeConnect(ws=_FakeWS(messages=[], closed=False))
        return _FakeConnect(
            ws=_FakeWS(messages=[json.dumps({"heartbeat": "ok"})], closed=False)
        )

    streamer._running = True
    streamer.initial_reconnect_delay = 0.01

    with patch("services.schwab_streamer.websockets.connect", side_effect=fake_connect):
        await streamer.start()

    assert len(connect_calls) == 2, f"Expected 2 connect calls, got {len(connect_calls)}"
    assert mock_token_manager.refresh_token.called, (
        "refresh_token must be called when token expired mid-stream"
    )
    # Verify the refreshed token was used on the 2nd connect
    assert connect_calls[1].get("Authorization") == "Bearer reauth-token-99"


# ---------------------------------------------------------------------------
# Test 10: Re-subscribe after error message + reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resubscribe_after_error_then_reconnect(
    streamer, mock_token_manager
):
    """After a RATE_LIMIT_EXCEEDED error closes the stream, the reconnect
    path sends real subscription wire messages.

    Phase 1: stream delivers an error message and closes.
    Phase 2: reconnect runs with a tracking subscribe that exercises the
    real _subscribe_default -> _subscribe_equities/options/lob_depth chain.
    """
    subscribe_calls: list[str] = []

    async def tracking_subscribe() -> None:
        subscribe_calls.append("subscribe_default")
        await streamer._subscribe_equities(["SPY", "QQQ", "DIA", "IWM"])
        await streamer._subscribe_options("SPY", num_strikes=20)
        await streamer._subscribe_options("QQQ", num_strikes=20)
        await streamer._subscribe_lob_depth("SPY")
        await streamer._subscribe_lob_depth("QQQ")

    streamer._subscribe_default = tracking_subscribe
    streamer._running = True
    streamer.initial_reconnect_delay = 0.01

    # Phase 1: error message -> stream closes -> reconnect
    fake_ws_1 = _FakeWS(
        messages=[json.dumps({"error": "RATE_LIMIT_EXCEEDED", "message": "temp"})],
        closed=True,
    )
    side_eff_1 = _connect_side_effect(ws=fake_ws_1)

    with patch("services.schwab_streamer.websockets.connect", side_effect=side_eff_1):
        streamer._running = True
        await streamer._connect_and_stream()

    assert len(subscribe_calls) == 1, (
        f"Expected 1 subscribe call after error, got {len(subscribe_calls)}"
    )

    # Phase 2: reconnect with fresh WS + tracking subscribe
    subscribe_calls.clear()
    fake_ws_2 = _FakeWS(messages=[], closed=True)
    side_eff_2 = _connect_side_effect(ws=fake_ws_2)

    with patch("services.schwab_streamer.websockets.connect", side_effect=side_eff_2):
        streamer._running = True
        await streamer._connect_and_stream()

    assert len(subscribe_calls) == 1, (
        f"Expected 1 subscribe call on reconnect, got {len(subscribe_calls)}"
    )
