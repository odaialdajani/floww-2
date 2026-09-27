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

    # The frame is NORMALIZED for the consumer: `type` is the overlay's
    # match key and must be the literal "signal"; the original alert kind is
    # preserved in `signal` (rendered as the badge) and `alert_type`.
    assert len(ws.sent) == 1
    frame = ws.sent[0]
    assert frame["type"] == "signal"
    assert frame["signal"] == "GAMMA_FLIP"
    assert frame["alert_type"] == "GAMMA_FLIP"
    assert frame["ticker"] == "SPY"


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
    assert len(good.sent) == 1
    assert good.sent[0]["type"] == "signal"
    assert good.sent[0]["signal"] == "VOLUME_SPIKE"
    assert good.sent[0]["ticker"] == "QQQ"


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
    # Normalized for the consumer — see _signal_frame in routes/alerts.py.
    assert ws.sent[0]["type"] == "signal"
    assert ws.sent[0]["signal"] == "GAMMA_FLIP"
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


# ---------------------------------------------------------------------------
# Consumer contract
# ---------------------------------------------------------------------------
#
# Every test above asserts on the SOCKET: that a frame reached send_json.
# None of them check whether the one real consumer keeps it.
#
# frontend/src/components/AlertOverlay.js discards any frame failing:
#     if (data.type === 'signal' || data.signal) { addAlert(data); }
#
# alert.to_dict() yields {"type": "GAMMA_FLIP", ...} with no `signal` key, so
# the overlay SILENTLY DROPPED every frame the producer sent. The channel
# looked wired, moved real bytes, and displayed nothing — the exact failure
# the producer was added to fix, reproduced one layer up.


def _overlay_accepts(frame: dict) -> bool:
    """Mirror of AlertOverlay's onmessage filter. Keep in sync with the JSX."""
    return frame.get("type") == "signal" or bool(frame.get("signal"))


def test_snapshot_broadcast_is_renderable_by_the_overlay(monkeypatch):
    """End-to-end: a detected alert must survive the consumer's filter.

    Mocked at the engine boundary only. The route wiring (parse -> detect ->
    broadcast) and the frame SHAPE are the code under test.
    """
    ws = _FakeWS()
    A._signal_clients.append(ws)

    class _Alert:
        def to_dict(self) -> dict:
            return {"type": "GAMMA_FLIP", "ticker": "SPY", "priority": "HIGH",
                    "message": "gamma flip", "data": {"level": 500.0},
                    "timestamp": "2026-09-27T00:00:00Z"}

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
    assert r.json()["alerts_detected"] == 1
    assert len(ws.sent) == 1, f"expected 1 broadcast, got {ws.sent}"
    frame = ws.sent[0]
    assert _overlay_accepts(frame), (
        f"AlertOverlay would DISCARD this frame: {frame!r}. Its filter is "
        "`data.type === 'signal' || data.signal`; a raw alert.to_dict() has "
        "type='GAMMA_FLIP' and no `signal` key, so the channel delivers bytes "
        "the overlay throws away."
    )


def test_broadcast_frame_passes_the_overlay_filter():
    """A direct broadcast must also be a frame the overlay renders."""
    ws = _FakeWS()
    A._signal_clients.append(ws)

    async def scenario():
        A.broadcast_signal({"type": "GAMMA_FLIP", "ticker": "SPY", "message": "flip"})
        await asyncio.sleep(0)

    asyncio.run(scenario())

    assert ws.sent, "nothing was sent"
    for frame in ws.sent:
        assert _overlay_accepts(frame), (
            f"AlertOverlay would discard this frame: {frame!r}"
        )
