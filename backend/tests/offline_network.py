"""Fail closed when an offline route test misses a provider mock."""

import os
import socket
import traceback

import httpx
import pytest


@pytest.fixture(scope="session", autouse=True)
def deny_external_network():
    # Install before module-scoped TestClient startup, and retain protection
    # between individual tests while application background tasks are alive.
    monkeypatch = pytest.MonkeyPatch()
    attempts = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def refuse(*args, **kwargs):
        request = next((a for a in args if isinstance(a, httpx.Request)), None)
        # No headers, credentials, query strings or source-code lines in logs.
        attempts.append({
            "test": os.getenv("PYTEST_CURRENT_TEST", "setup or background"),
            "host": request.url.host if request else "socket",
            "stack": [f"{frame.name}:{frame.lineno}" for frame in traceback.extract_stack(limit=7)[:-1]],
        })
        raise AssertionError("Offline test attempted an external connection")

    async def refuse_async(*args, **kwargs):
        refuse(*args, **kwargs)

    def local_connect(sock, address):
        # Windows asyncio creates a loopback socketpair to wake its event loop.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        refuse()

    def local_connect_ex(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect_ex(sock, address)
        refuse()

    monkeypatch.setattr(socket.socket, "connect", local_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", local_connect_ex)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async)
    try:
        yield
    finally:
        monkeypatch.undo()
    assert not attempts, f"Provider mock was missed; external requests were blocked: {attempts[:20]}"
