"""Every WebSocket path the frontend opens must reach its intended handler.

Generalizes the /ws/signals defect (1c471b20). That bug was a router prefix
putting the handler at /api/alerts/ws/signals while the client opened
/ws/signals, which server.py's greedy /ws/{topic} then swallowed. Tests that
mounted A.router on a bare FastAPI app could not see it.

The frontend has exactly two WebSocket clients:
  frontend/src/components/AlertOverlay.js  -> ${WS_URL}/ws/signals
  frontend/src/hooks/useWebSocketGex.jsx   -> ${WS_URL}/ws/gex/${ticker}

This asserts both resolve on the ASSEMBLED app, which is where routing,
prefixes, and registration order actually exist.
"""

import re
from pathlib import Path

import pytest

from server import app

FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "src"


def _ws_handlers() -> dict[str, str]:
    """Map path -> 'module.function' for every websocket route on the app."""
    out: dict[str, str] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        if path.startswith("/ws") and endpoint is not None:
            out.setdefault(
                path, f"{endpoint.__module__}.{endpoint.__name__}"
            )
    return out


def _client_ws_paths() -> set[str]:
    """Extract the WS paths the frontend actually opens, from source."""
    found: set[str] = set()
    for js in list(FRONTEND.rglob("*.js")) + list(FRONTEND.rglob("*.jsx")):
        if ".test." in js.name:
            continue
        try:
            text = js.read_text(errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"new WebSocket\([^)]*?`([^`]*?/ws/[^`]*?)`", text):
            raw = m.group(1)
            # Normalize the JS interpolation to a FastAPI-style placeholder.
            norm = re.sub(r"\$\{[^}]+\}", "{x}", raw)
            norm = norm[norm.index("/ws/") :]
            found.add(norm)
    return found


def test_frontend_websocket_clients_are_discovered():
    """Guard the guard: if this finds nothing, every other test here is vacuous."""
    paths = _client_ws_paths()
    assert paths, (
        "no frontend WebSocket paths detected -- the extraction is broken, so "
        "the routing tests below would pass without checking anything"
    )
    assert "/ws/signals" in paths, f"AlertOverlay's socket path not found: {paths}"


@pytest.mark.parametrize(
    ("client_path", "expected_handler"),
    [
        # AlertOverlay's alerts stream. Must NOT fall through to /ws/{topic}.
        ("/ws/signals", "routes.alerts.websocket_signals"),
        # The GEX stream, including the ticker segment.
        ("/ws/gex/{x}", "server.websocket_gex"),
    ],
)
def test_client_ws_path_reaches_its_handler(client_path, expected_handler):
    handlers = _ws_handlers()
    path = client_path.replace("{x}", "{ticker}")
    assert path in handlers, (
        f"no websocket route serves {path}. The client opens it, so it must "
        f"exist on the assembled app. Registered ws paths: {sorted(handlers)}"
    )
    assert handlers[path] == expected_handler, (
        f"{path} is served by {handlers[path]}, not {expected_handler}"
    )


def test_generic_topic_route_does_not_capture_signals():
    """/ws/{topic} must not be what answers the signals client.

    This is the exact mechanism of the original defect: a greedy pattern
    registered on the app swallowed the alerts path.
    """
    handlers = _ws_handlers()
    assert "/ws/{topic}" in handlers, "/ws/{topic} is gone; update this test"
    assert handlers["/ws/{topic}"] != "routes.alerts.websocket_signals", (
        "the greedy topic pattern is now serving /ws/signals; the dedicated "
        "alerts handler has been shadowed"
    )
    assert "/ws/signals" in handlers, (
        "/ws/signals must exist as its OWN route, not only as a /ws/{topic} match"
    )
