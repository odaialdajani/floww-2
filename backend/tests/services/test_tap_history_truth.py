"""Missing history cannot become a measured zero or bypass provider policy."""
import ast
import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


def tap_reader(payload=None, key="fixture", error=None):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        get = AsyncMock(return_value=SimpleNamespace(json=lambda: payload), side_effect=error)

    factory = Mock(return_value=Client())
    env = {"POLYGON_API_KEY": key, "os": os, "datetime": datetime, "UTC": UTC,
           "timedelta": timedelta, "httpx": SimpleNamespace(AsyncClient=factory),
           "log": logging.getLogger("tap-history-test")}
    source = Path(__file__).resolve().parents[2] / "server.py"
    node = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.AsyncFunctionDef) and n.name == "tap_counts")
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), "exec"), env)
    return env["tap_counts"], factory


def test_missing_key_is_unknown_not_fresh_zero(monkeypatch):
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    read, client = tap_reader(key="")
    assert asyncio.run(read("SPY", [100])) == {}
    client.assert_not_called()


def test_public_only_never_reads_legacy_history(monkeypatch):
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    read, client = tap_reader(payload={"results": [{"l": 90, "h": 110}] * 5})
    assert asyncio.run(read("SPY", [100])) == {}
    client.assert_not_called()


@pytest.mark.parametrize("payload", [None, {}, {"results": []}, {"results": [{"l": 90, "h": 110}]}])
def test_missing_or_partial_history_stays_unknown(monkeypatch, payload):
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    read, _ = tap_reader(payload=payload)
    assert asyncio.run(read("SPY", [100])) == {}


@pytest.mark.parametrize("bar", [{"l": None, "h": 110}, {"l": True, "h": 110}, {"l": 120, "h": 110}])
def test_invalid_bar_cannot_publish_a_partial_count(monkeypatch, bar):
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    read, _ = tap_reader(payload={"results": [{"l": 90, "h": 110}] * 4 + [bar]})
    assert asyncio.run(read("SPY", [100])) == {}


def test_failed_history_stays_unknown(monkeypatch):
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    read, _ = tap_reader(error=RuntimeError("fixture failure"))
    assert asyncio.run(read("SPY", [100])) == {}


def test_observed_zero_and_real_crossings_are_preserved(monkeypatch):
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    read, _ = tap_reader(payload={"results": [{"l": 90, "h": 110}] * 5})
    assert asyncio.run(read("SPY", [100, 120])) == {100: 5, 120: 0}
