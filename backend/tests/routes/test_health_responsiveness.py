"""Health probes must not wait on the ingestion writer in the event loop."""
from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import duckdb
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def probe(monkeypatch):
    import routes.flowseeker as flowseeker
    import routes.health as health

    connection = duckdb.connect(":memory:", config={"threads": "1"})
    connection.execute("CREATE TABLE flow_alerts_daily (id INTEGER)")
    connection.execute("INSERT INTO flow_alerts_daily VALUES (1)")
    lock = threading.RLock()
    monkeypatch.setattr(health, "duckdb_engine", SimpleNamespace(_conn=connection, _conn_lock=lock))
    monkeypatch.setattr(health, "ws_manager", SimpleNamespace(_all={}))
    monkeypatch.setattr(health, "av_circuit", SimpleNamespace(
        state=SimpleNamespace(value="closed"), failure_count=0, success_count=0,
    ))
    monkeypatch.setattr(flowseeker, "get_calibration_status", lambda: {
        "stage": None, "n": None, "method_note": None, "age_s": None,
    })
    monkeypatch.setenv("PUBLIC_API_KEY", "offline-health-fixture")
    app = FastAPI()
    app.include_router(health.router)
    yield SimpleNamespace(module=health, connection=connection, lock=lock, app=app)
    connection.close()


@contextmanager
def held_by_writer(lock, begin=None):
    """A different OS thread owns the real RLock; timeout prevents a RED hang."""
    holding, release = threading.Event(), threading.Event()

    def writer():
        if begin is not None:
            begin.wait(timeout=2)
        with lock:
            holding.set()
            release.wait(timeout=1.5)
            holding.clear()

    thread = threading.Thread(target=writer)
    thread.start()
    if begin is None:
        assert holding.wait(timeout=1)
    try:
        yield holding
    finally:
        release.set()
        if begin is not None:
            begin.set()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["first_probe", "institutional_alerts"])
async def test_busy_store_preserves_liveness_and_returns_degraded(probe, monkeypatch, phase):
    """Both DB reads must refuse contention before the writer releases its lock."""
    begin = threading.Event() if phase == "institutional_alerts" else None
    original_section = probe.module._institutional_section
    task = None
    async with AsyncClient(transport=ASGITransport(app=probe.app), base_url="http://health-test") as client:
        try:
            with held_by_writer(probe.lock, begin) as holding:
                if begin is not None:
                    def contested_section(feed_status):
                        begin.set()
                        assert holding.wait(timeout=1)
                        return original_section(feed_status)

                    monkeypatch.setattr(probe.module, "_institutional_section", contested_section)
                task = asyncio.create_task(client.get("/api/health"))
                await asyncio.sleep(0)
                if begin is not None:
                    assert await asyncio.to_thread(holding.wait, 0.5)
                liveness = await client.get("/health")
                assert liveness.json()["status"] == "ok"
                assert holding.is_set(), "health blocked the event loop until the writer released"
                response = await task
                assert holding.is_set(), "health waited for the writer instead of reporting busy"
                body = response.json()
                assert body["status"] == "degraded"
                assert body["institutional"]["alerts"]["stored"] is None
                if phase == "first_probe":
                    assert body["checks"]["duckdb"]["status"] == "unhealthy"
                else:
                    assert body["checks"]["duckdb"]["status"] == "healthy"
        finally:
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            monkeypatch.setattr(probe.module, "_institutional_section", original_section)
        recovered = (await client.get("/api/health")).json()
        assert recovered["status"] == "healthy"
        assert recovered["institutional"]["alerts"]["stored"] == 1


@pytest.mark.asyncio
async def test_uncontended_probe_keeps_real_database_counts(probe):
    async with AsyncClient(transport=ASGITransport(app=probe.app), base_url="http://health-test") as client:
        body = (await client.get("/api/health")).json()
    assert body["status"] == "healthy"
    assert body["checks"]["duckdb"]["status"] == "healthy"
    assert body["institutional"]["alerts"]["stored"] == 1


@pytest.mark.asyncio
async def test_database_failure_does_not_leak_the_connection_lock(probe):
    probe.connection.close()
    async with AsyncClient(transport=ASGITransport(app=probe.app), base_url="http://health-test") as client:
        body = (await client.get("/api/health")).json()
    assert body["status"] == "degraded"
    assert body["checks"]["duckdb"]["status"] == "unhealthy"
    acquired = []

    def another_reader():
        got_lock = probe.lock.acquire(blocking=False)
        acquired.append(got_lock)
        if got_lock:
            probe.lock.release()

    reader = threading.Thread(target=another_reader)
    reader.start()
    reader.join(timeout=1)
    assert acquired == [True]


@pytest.mark.asyncio
async def test_running_version_does_not_follow_later_checkout_changes(probe, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=probe.app), base_url="http://health-test") as client:
        before = (await client.get("/api/version")).json()
        monkeypatch.setattr(probe.module, "_git_sha", lambda: "different-checkout")
        after = (await client.get("/api/version")).json()
    assert after == before, "a running process must report its startup source, not a later checkout"
