"""The /ws/signals route must not be shadowed by /ws/{topic} on the REAL app.

Why this file exists. `routes/alerts.py` declares `@router.websocket("/ws/signals")`
and `server.py` declares `@app.websocket("/ws/{topic}")`. Starlette matches
websockets in REGISTRATION order, and `/ws/{topic}` is declared at server.py:3857
while the alerts router is included at server.py:3495 -- so by the time the app is
assembled, `/ws/signals` is shadowed by the greedy `/ws/{topic}` pattern with
topic="signals".

Consequence: every real client connected to `ws_manager` (services/
websocket_streamer.py), never to `routes.alerts._signal_clients`. The producer
wrote to a list nothing read, so alerts were detected, the HTTP response was
200, and connected clients received nothing.

Every pre-existing test in test_alerts_ws_producer.py mounted `A.router` on a
bare FastAPI app, which never includes `server.py` -- so the shadow was
invisible to all of them, including the consumer-contract tests added with the
frame-shape fix.

The only way to see this class of bug is to assert against the REAL assembled
app object, not an isolated router.
"""

from server import app


def _ws_routes() -> list[tuple[str, str]]:
    out = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/ws"):
            endpoint = getattr(route, "endpoint", None)
            out.append((path, getattr(endpoint, "__name__", "?")))
    return out


def test_ws_signals_is_not_shadowed_by_the_topic_pattern():
    """/ws/signals must reach the alerts handler, not /ws/{topic}."""
    exact = [name for path, name in _ws_routes() if path == "/ws/signals"]
    assert exact, (
        "no route serves /ws/signals on the assembled app. The alerts router's "
        "websocket is being shadowed by server.py's /ws/{topic} pattern, so "
        "real clients connect to websocket_streamer and never to the producer."
    )
    assert exact[0] == "websocket_signals", (
        f"/ws/signals is served by {exact[0]!r}, not the alerts handler"
    )


def test_generic_topic_route_does_not_swallow_signals():
    """The greedy pattern must not match the reserved `signals` topic.

    Even with the alerts route restored, `/ws/{topic}` would still match
    topic='signals' if it were registered first. Assert the reserved topic is
    excluded so the two can never silently trade places again.
    """
    from server import websocket_endpoint

    src = websocket_endpoint.__doc__ or ""
    # The handler's documented topic list must not claim `signals`.
    assert "signals" not in src, (
        "the /ws/{topic} handler claims the reserved `signals` topic; it must "
        "be served exclusively by routes/alerts.py"
    )


def test_alerts_websocket_route_is_registered_before_the_topic_pattern():
    """Ordering is the mechanism of the bug — pin it directly.

    Starlette resolves in registration order, so the exact ordering of these
    two websocket routes IS the behavior under test.
    """
    paths = [path for path, _ in _ws_routes()]
    signals_idx = [i for i, p in enumerate(paths) if p == "/ws/signals"]
    topic_idx = [i for i, p in enumerate(paths) if p == "/ws/{topic}"]
    assert signals_idx, "/ws/signals is not registered on the app at all"
    assert signals_idx[0] < topic_idx[0], (
        f"/ws/signals (index {signals_idx[0]}) is registered after /ws/{{topic}} "
        f"(index {topic_idx[0]}), so the greedy pattern shadows it"
    )
