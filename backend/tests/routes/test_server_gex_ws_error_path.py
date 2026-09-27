"""The GEX websocket error branch must not send on a dead socket.

server.py:2985 sits in `except Exception` inside websocket_gex and calls
`await websocket.send_json({"error": ...})`. But the exception that got us there
is very often a send failure or an already-gone peer -- the socket is in ERROR
state. Sending on it raises LocalProtocolError ("Can't send data when our state
is ERROR"), which escapes the handler entirely and is logged as

    WebSocket fatal error for SPY: received 1001 (going away); then sent 1001

i.e. an ordinary browser disconnect is reported as a FATAL error on every
reconnect. The live backend emits these continuously.

Fix under test: the error branch tolerates a failed send instead of raising.
"""

import asyncio
import inspect
import logging
from unittest.mock import AsyncMock, patch

import pytest

import server
from server import websocket_gex


class _SocketClosed(Exception):
    """Stands in for websockets' state-ERROR send failure."""


class DeadSocket:
    """Minimal socket whose sends fail, like a real one in ERROR state."""

    def __init__(self, fail_after: int = 0) -> None:
        self.accepted = False
        self.closed = False
        self.send_attempts = 0
        self._fail_after = fail_after

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data) -> None:
        self.send_attempts += 1
        if self.send_attempts > self._fail_after:
            raise _SocketClosed("Can't send data when our state is ERROR")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True

    async def receive_text(self) -> str:
        raise AssertionError("websocket_gex should not poll for text")


@pytest.fixture
def _ws_auth_ok():
    """Bypass the token gate and the network fetch."""
    with patch("server.verify_ws_token", AsyncMock(return_value=True), create=True):
        yield


@pytest.mark.asyncio
async def test_failed_send_is_not_reported_as_fatal(_ws_auth_ok, caplog):
    """A send failure inside the error branch must NOT log a fatal error.

    The outer `except Exception` swallows the escaped LocalProtocolError, so
    the only observable symptom is the log line:

        ERROR WebSocket fatal error for SPY: Can't send data when our state is ERROR

    That is what production emits on every ordinary browser disconnect, which
    is why this test asserts on the log rather than on a raised exception.
    """
    ws = DeadSocket(fail_after=0)

    async def _boom(*a, **k):
        raise RuntimeError("data fetch failed")

    with (
        patch.object(server, "fetch_spot_and_chains_merged", _boom, create=True),
        patch("asyncio.sleep", AsyncMock()),
        caplog.at_level(logging.DEBUG, logger="heatseeker"),
    ):
        await asyncio.wait_for(websocket_gex(ws, "SPY"), timeout=10)

    fatal = [r.getMessage() for r in caplog.records if "fatal error" in r.getMessage()]
    assert not fatal, (
        f"an ordinary socket failure was reported as a fatal error: {fatal}. "
        "The error branch sends on a socket that already failed."
    )
    assert any("WebSocket error for SPY" in r.getMessage() for r in caplog.records), (
        "the real underlying error should still be logged as a warning"
    )


@pytest.mark.asyncio
async def test_midstream_disconnect_is_not_fatal(_ws_auth_ok, caplog):
    """A peer that vanishes mid-stream must not produce a fatal error."""
    ws = DeadSocket(fail_after=0)
    calls = {"n": 0}

    async def _flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"spot": 500.0, "contracts": [{"strike": 500, "gex": 10}]}
        raise _SocketClosed("peer went away")

    with (
        patch.object(server, "fetch_spot_and_chains_merged", _flaky, create=True),
        patch("asyncio.sleep", AsyncMock()),
        caplog.at_level(logging.ERROR, logger="heatseeker"),
    ):
        await asyncio.wait_for(websocket_gex(ws, "SPY"), timeout=10)

    fatal = [r.getMessage() for r in caplog.records if "fatal error" in r.getMessage()]
    assert not fatal, f"disconnect reported as fatal: {fatal}"


def test_error_branch_send_is_guarded():
    """Structural guard: send_json in the error branch sits inside try/except.

    Survives refactors of the surrounding loop where a behavioral test would
    need the network mocked exactly.
    """
    src = inspect.getsource(websocket_gex)
    _, _, tail = src.partition("except Exception as e:")
    assert "send_json" in tail, "error branch no longer reports errors to the client"
    before_send = tail.split("send_json", 1)[0]
    last_except = before_send.rsplit("except", 1)[-1]
    assert "try:" in last_except, (
        "send_json in the websocket_gex error branch is unguarded; on an ERROR "
        "socket it raises and turns an ordinary disconnect into a fatal error"
    )
