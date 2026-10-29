"""Fail closed when an offline route test misses a provider mock."""

import os
import socket
import traceback
from collections import Counter
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx
import pytest

_owned_loopbacks = set()


@contextmanager
def permit_owned_loopback(url):
    """Only a test's already-started ephemeral fixture server may be reached."""
    parsed = urlsplit(url)
    assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
    assert parsed.port and parsed.port >= 1024
    identity = (parsed.hostname, parsed.port)
    assert identity not in _owned_loopbacks
    _owned_loopbacks.add(identity)
    try:
        yield
    finally:
        _owned_loopbacks.remove(identity)


@pytest.fixture(scope="session", autouse=True)
def deny_external_network():
    # Install before module-scoped TestClient startup, and retain protection
    # between individual tests while application background tasks are alive.
    monkeypatch = pytest.MonkeyPatch()
    attempts = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_http = httpx.HTTPTransport.handle_request
    original_async_http = httpx.AsyncHTTPTransport.handle_async_request

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

    def dispatch_http(transport, request):
        if (request.url.host, request.url.port) in _owned_loopbacks:
            return original_http(transport, request)
        return refuse(transport, request)

    async def dispatch_async_http(transport, request):
        if (request.url.host, request.url.port) in _owned_loopbacks:
            return await original_async_http(transport, request)
        return await refuse_async(transport, request)

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
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", dispatch_http)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", dispatch_async_http)
    try:
        yield
    finally:
        monkeypatch.undo()
    # Keep every originating test visible even when one caller retries heavily.
    # Retain bounded stack examples without hiding later leaking fixtures.
    by_test = dict(Counter(item["test"] for item in attempts))
    assert not attempts, (
        f"Provider mock was missed; external requests were blocked; attempts by test: {by_test}; "
        f"first examples: {attempts[:5]}"
    )
