"""Opt-in fixture for real HTTP tests; external and unrelated local reads stay blocked."""
from contextlib import asynccontextmanager

import pytest

from tests.offline_network import permit_owned_loopback


@pytest.fixture(autouse=True)
def allow_owned_loopback(monkeypatch, request):
    from scripts import research_comparison_transport as transport

    original = transport.local_server

    @asynccontextmanager
    async def scoped(*args, **kwargs):
        async with original(*args, **kwargs) as url:
            with permit_owned_loopback(url):
                yield url

    monkeypatch.setattr(transport, "local_server", scoped)
    if getattr(request.module, "local_server", None) is original:
        monkeypatch.setattr(request.module, "local_server", scoped)
