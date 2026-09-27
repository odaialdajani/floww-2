"""The /ws/signals channel must have a producer, not just a listener.

`_signal_clients` was appended to on connect and never read. AlertOverlay
connected successfully, sat silent forever, and showed no alerts — a dead
channel that looked healthy because nothing crashed.
"""

from __future__ import annotations

import asyncio

import pytest

from routes import alerts as A


class _FakeWS:
    """Minimal stand-in for a Starlette WebSocket."""

    def __init__(self, *, fail: bool = False) -> None:
        self.frames: list[dict] = []
        self.fail = fail

    async def send_json(self, frame: dict) -> None:
        if self.fail:
            raise RuntimeError("client is gone")
        self.frames.append(frame)


@pytest.fixture
def clean_clients():
    A._signal_clients.clear()
    yield
    A._signal_clients.clear()


def test_broadcast_reaches_every_client(clean_clients):
    a, b = _FakeWS(), _FakeWS()
    A._signal_clients.extend([a, b])
    n = asyncio.run(A.broadcast_signal({"type": "signal", "text": "GEX spike SPY"}))
    assert n == 2
    assert a.frames[0]["text"] == "GEX spike SPY"
    assert b.frames[0]["text"] == "GEX spike SPY"


def test_broadcast_defaults_type_for_the_frontend_filter(clean_clients):
    """AlertOverlay only renders frames whose type is 'signal'."""
    ws = _FakeWS()
    A._signal_clients.append(ws)
    asyncio.run(A.broadcast_signal({"text": "hello"}))
    assert ws.frames[0]["type"] == "signal"


def test_broadcast_stamps_a_timestamp(clean_clients):
    ws = _FakeWS()
    A._signal_clients.append(ws)
    asyncio.run(A.broadcast_signal({"type": "signal"}))
    assert "ts" in ws.frames[0]


def test_broadcast_does_not_mutate_the_caller_payload(clean_clients):
    payload = {"type": "signal"}
    A._signal_clients.append(_FakeWS())
    asyncio.run(A.broadcast_signal(payload))
    assert payload == {"type": "signal"}, "caller's dict was mutated in place"


def test_one_dead_client_cannot_silence_the_channel(clean_clients):
    """A wedged socket must be dropped, not allowed to block the fanout."""
    dead, alive = _FakeWS(fail=True), _FakeWS()
    A._signal_clients.extend([dead, alive])
    n = asyncio.run(A.broadcast_signal({"type": "signal"}))
    assert n == 1
    assert alive.frames, "live client still received the frame"
    assert dead not in A._signal_clients, "dead client should be evicted"


def test_broadcast_with_no_clients_is_a_noop(clean_clients):
    assert asyncio.run(A.broadcast_signal({"type": "signal"})) == 0
