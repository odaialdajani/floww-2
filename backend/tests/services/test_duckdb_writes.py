"""
backend/tests/services/test_duckdb_retry.py
Tests for the retry_on_failure decorator in duckdb_engine.py.
"""
import asyncio
import logging
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest

# Stub services.observability so importing duckdb_engine doesn't pull in the
# real prometheus-backed module. setdefault only — NEVER replace
# sys.modules['services'] itself: clobbering the package strips its __path__ and
# breaks every later `from services.X import ...` in the session (poisons collection).
obs = types.ModuleType('services.observability')
obs.duckdb_queue_depth = type('M', (), {'set': lambda s, v: None})()
obs.duckdb_batch_size = type('M', (), {'observe': lambda s, v: None})()
sys.modules.setdefault('services.observability', obs)

from services.duckdb_engine import retry_on_failure


@pytest.mark.asyncio
async def test_retry_success_first_try():
    calls = 0
    @retry_on_failure(max_retries=3, base_delay=0.01)
    async def ok():
        nonlocal calls
        calls += 1
        return "ok"
    assert await ok() == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_retry_transient_then_success():
    calls = 0
    @retry_on_failure(max_retries=3, base_delay=0.01)
    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("lock contention")
        return "ok"
    assert await flaky() == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_max_retries_exceeded():
    calls = 0
    @retry_on_failure(max_retries=3, base_delay=0.01)
    async def always_fail():
        nonlocal calls
        calls += 1
        raise RuntimeError("persistent error")
    with pytest.raises(RuntimeError, match="persistent error"):
        await always_fail()
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_exponential_backoff():
    calls = 0
    @retry_on_failure(max_retries=3, base_delay=0.01)
    async def measure():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("fail")
        return "done"
    with patch("services.duckdb_engine.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        assert await measure() == "done"
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == pytest.approx(0.01, abs=0.001)
        assert mock_sleep.call_args_list[1][0][0] == pytest.approx(0.02, abs=0.001)


@pytest.mark.asyncio
async def test_retry_preserves_name():
    @retry_on_failure(max_retries=3, base_delay=0.01)
    async def my_write():
        return "ok"
    assert my_write.__name__ == "my_write"


@pytest.mark.asyncio
async def test_retry_preserves_kwargs():
    @retry_on_failure(max_retries=3, base_delay=0.01)
    async def with_kw(a, b=None):
        return a + (b or 0)
    assert await with_kw(1, b=2) == 3
