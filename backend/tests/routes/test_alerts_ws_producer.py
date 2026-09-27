"""Maximization #6: /ws/signals must have a real producer, not a dead socket.

Before: `POST /api/alerts/snapshot` ran detection, returned the alerts, and
dropped them. `_signal_clients` was only ever appended to — nothing read it,
so a client that connected to /ws/signals waited forever for a push that no
code path could produce.

Two contracts pinned here:
  1. detection result is broadcast to every connected signal client
  2. the socket verifies the same WS token /ws/gex/{ticker} already verifies
     (an unauthenticated signal stream is a worse hole than an
     unauthenticated read-only GEX stream)
"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import alerts as A


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(A.router)
    return app


class _FakeWS:
    """Minimal WebSocket double: records sends, never touches the network."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.query_params: dict[str, str] = {}

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_text(self) -> str:
        await asyncio.sleep(3600)  # never returns; simulates an idle client
        return "ping"


@pytest.fixture(autouse=True)
def _clean_clients():
    A._signal_clients.clear()
    yield
    A._signal_clients.clear()


def test_broadcast_sends_to_connected_clients(monkeypatch):
    """The producer exists and reaches connected clients."""
    ws = _FakeWS()
    A._signal_clients.append(ws)

    async def scenario():
        A.broadcast_signal({"type": "GAMMA_FLIP", "ticker": "SPY"})
        await asyncio.sleep(0)  # let the created send task run

    asyncio.run(scenario())

    assert ws.sent == [{"type": "GAMMA_FLIP", "ticker": "SPY"}]


def test_broadcast_never_raises_on_dead_client(monkeypatch):
    """A client that vanished mid-broadcast is dropped, not raised.

    `_signal_clients` is a plain list mutated from both the reader loop and
    the detector, so a send failure must remove that socket and continue —
    a stale client must not 500 the snapshot route.
    """
    dead = _FakeWS()

    async def _boom(_payload: dict) -> None:
        raise RuntimeError("client gone")

    monkeypatch.setattr(dead, "send_json", _boom)
    A._signal_clients.append(dead)
    good = _FakeWS()
    A._signal_clients.append(good)

    async def scenario():
        A.broadcast_signal({"type": "VOLUME_SPIKE", "ticker": "QQQ"})
        await asyncio.sleep(0)  # let both send tasks run and fail/succeed

    asyncio.run(scenario())

    assert dead not in A._signal_clients, "dead client must be evicted"
    assert good in A._signal_clients, "healthy client must be kept"
    assert good.sent == [{"type": "VOLUME_SPIKE", "ticker": "QQQ"}]


def test_broadcast_with_no_clients_is_a_noop():
    """No subscribers is normal (nobody has the app open) — not an error."""
    A.broadcast_signal({"type": "PIN_RISK", "ticker": "IWM"})  # must not raise


def test_snapshot_route_broadcasts_detected_alerts(monkeypatch):
    """End-to-end: detection result reaches the socket, not just the response.

    Mocked at the engine boundary only — the route's own wiring (parse ->
    detect -> broadcast) is the code under test.
    """
    ws = _FakeWS()
    A._signal_clients.append(ws)

    class _Alert:
        def to_dict(self) -> dict:
            return {"type": "GAMMA_FLIP", "ticker": "SPY", "priority": "HIGH"}

    class _Engine:
        def add_snapshot(self, snap) -> None:
            self.snap = snap

        def detect_alerts(self, ticker: str, momentum_score: int = 50) -> list:
            return [_Alert()]

        def get_alert_summary(self, ticker: str, momentum_score: int = 50) -> dict:
            return {"ticker": ticker, "alerts": []}

    monkeypatch.setattr(A, "get_alert_engine", lambda: _Engine())

    c = TestClient(_app())
    r = c.post("/api/alerts/snapshot", json={"ticker": "SPY", "spot_price": 500.0})

    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["alerts_detected"] == 1
    # The alert reached the response AND the live socket.
    assert len(ws.sent) == 1, f"expected 1 broadcast, got {ws.sent}"
    assert ws.sent[0]["type"] == "GAMMA_FLIP"
    assert ws.sent[0]["ticker"] == "SPY"


def test_snapshot_route_broadcasts_nothing_when_no_alerts(monkeypatch):
    """Silence is a real state: no alerts must NOT push an empty broadcast.

    An overlay that toasts on every snapshot poll is worse than one that
    stays quiet, so the no-alert path must be genuinely silent.
    """
    ws = _FakeWS()
    A._signal_clients.append(ws)

    class _Engine:
        def add_snapshot(self, snap) -> None:
            pass

        def detect_alerts(self, ticker: str, momentum_score: int = 50) -> list:
            return []

    monkeypatch.setattr(A, "get_alert_engine", lambda: _Engine())

    c = TestClient(_app())
    r = c.post("/api/alerts/snapshot", json={"ticker": "SPY", "spot_price": 500.0})

    assert r.status_code == 200
    assert r.json()["alerts_detected"] == 0
    assert ws.sent == [], "no alerts must mean no broadcast"


def test_ws_signals_verifies_token():
    """The signal socket must verify the token, matching /ws/gex/{ticker}.

    Without this, setting WS_API_TOKEN closed one stream and left the
    higher-value one (live signal pushes) open. Asserted on the route body
    so the test does not depend on TestClient's close-code plumbing.
    """
    src = inspect.getsource(A.websocket_signals)
    assert "verify_ws_token" in src, "ws/signals must verify the WS token"
    assert "4001" in src, "unauthorized socket must close with 4001 like /ws/gex"
    # The gate must come BEFORE accept, or an unauthenticated socket is
    # already established when the denial fires.
    assert src.index("verify_ws_token") < src.index("websocket.accept()")
