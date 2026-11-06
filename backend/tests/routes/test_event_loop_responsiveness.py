"""Event-loop responsiveness for store-backed and compute-heavy routes.

A recorder write transaction holds the shared DuckDB connection lock for its
whole duration. A read that ran ON the asyncio event loop froze every other
request until that write finished. The same holds for the pure-python chain
and analytics work: while it ran on the loop thread, no other request could
be serviced at all.

These checks hold the real connection lock from a writer thread and require
the loop to keep answering an unrelated request while the store read or the
calculation is still in flight. They use a temporary DuckDB file, never the
live store.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

# Wall-clock budget for the unrelated request while the slow work is pending.
# A frozen loop cannot answer inside it, a healthy loop answers in microseconds.
PROBE_BUDGET_S = 1.0


@contextmanager
def held_by_writer(lock, hold_s: float = 5.0):
    """A different OS thread owns the real connection lock.

    Mirrors the recorder: the writer holds the shared lock for the whole
    transaction, so every reader on that connection has to wait.
    """
    holding = threading.Event()
    release = threading.Event()

    def writer():
        with lock:
            holding.set()
            release.wait(timeout=hold_s)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    assert holding.wait(timeout=2), "the writer thread never took the connection lock"
    try:
        yield release
    finally:
        release.set()
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A temporary file-backed DuckDB store, never the live one."""
    from services.duckdb_engine import DuckDBEngine

    engine = DuckDBEngine(str(tmp_path / "store.duckdb"))
    monkeypatch.setattr("services.duckdb_engine.db", engine)
    yield engine
    engine.close()


@pytest.fixture
def app():
    """The real route modules under test plus one unrelated probe route."""
    from routes.solstice import router as solstice_router
    from routes.solstice_price_paths import router as price_paths_router
    from routes.solstice_review import register_review_routes
    from routes.vpin import router as vpin_router

    application = FastAPI()
    application.include_router(vpin_router)
    application.include_router(solstice_router)
    application.include_router(price_paths_router)
    review_router = APIRouter(prefix="/api/solstice")
    register_review_routes(review_router)
    application.include_router(review_router)

    @application.get("/__loop_probe")
    async def loop_probe():
        return {"probe": "ok"}

    return application


async def _probe_while_pending(client, slow_path, budget_s: float = PROBE_BUDGET_S):
    """Run the slow request and require an unrelated request to be answered.

    Returns the probe response. Raises AssertionError when the loop stayed
    blocked until the slow request finished.
    """
    slow = asyncio.create_task(client.get(slow_path))
    probe = asyncio.create_task(client.get("/__loop_probe"))
    started = time.monotonic()
    try:
        while True:
            if time.monotonic() - started > budget_s:
                raise AssertionError(
                    "the event loop was frozen while the store read was pending")
            if probe.done():
                break
            await asyncio.sleep(0.01)
        response = await probe
        assert response.status_code == 200
        return response
    finally:
        for task in (slow, probe):
            if not task.done():
                task.cancel()
        await asyncio.gather(slow, probe, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("slow_path", [
    "/api/vpin/SPY/history",
    "/api/solstice/manifest/SPY",
    "/api/solstice/replay/missing-snapshot",
    "/api/solstice/recorder_health",
    "/api/solstice/price-paths/points?ticker=SPY",
    "/api/solstice/price-paths/sessions?ticker=SPY",
    "/api/solstice/SPY/contract?osi=X",
    # The comparable/replay/index reads took the shared connection lock on
    # the loop thread: the loop froze for as long as the recorder held it.
    "/api/solstice/price-paths/comparable?baseline_id=missing&snapshot_id=missing",
    "/api/solstice/price-paths/range-records",
    "/api/solstice/price-paths/range-records/rec_missing",
])
async def test_store_read_keeps_the_event_loop_servable(app, store, slow_path):
    """A pending store read must not stop the loop answering other requests."""
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://loop-test") as client:
        with held_by_writer(store._conn_lock, hold_s=2.0) as release:
            try:
                await _probe_while_pending(client, slow_path)
            finally:
                release.set()


@pytest.mark.asyncio
async def test_chain_snapshot_alert_tables_init_keeps_the_event_loop_servable(monkeypatch):
    """The flow-alert DDL must not run on the event loop.

    The alert-table init takes the shared connection lock several times. Run
    on the loop thread it froze every request for as long as the recorder
    held that lock - the reported symptom.
    """
    import server
    from services import flow_alerts, heatseeker_snapshots

    entered = threading.Event()
    release = threading.Event()

    def _blocking_init(engine):
        # Stands in for the DDL: it holds the caller until the test releases.
        entered.set()
        release.wait(timeout=2.0)
        return None

    async def _fetch(ticker, max_expiries=4):
        return {"ticker": ticker, "spot": 100.0, "expiries": [],
                "contracts": [], "data_source": "test"}

    monkeypatch.setattr(server, "fetch_spot_and_chains_merged", _fetch)
    monkeypatch.setattr(server, "compute_gex_grid",
                        lambda spot, contracts, ticker: {"vex_grid": {}, "charm_grid": {}})
    monkeypatch.setattr(flow_alerts, "init_flow_alert_tables", _blocking_init)
    monkeypatch.setattr(flow_alerts, "dedup_filter", lambda engine, alerts, now=None: [])
    monkeypatch.setattr(flow_alerts, "persist_alerts",
                        lambda engine, alerts, snapshot_date=None: 0)
    monkeypatch.setattr(heatseeker_snapshots, "create_snapshot_table", lambda conn: None)
    monkeypatch.setattr(heatseeker_snapshots, "contracts_to_recordbatch", lambda raw: None)
    monkeypatch.setattr(heatseeker_snapshots, "bulk_insert", lambda conn, batch: 0)

    application = FastAPI()

    @application.get("/__loop_probe")
    async def loop_probe():
        # Answer only once the blocking init is actually in flight, so the
        # probe cannot pass before the work it has to overlap ever started.
        for _ in range(500):
            if entered.is_set():
                return {"probe": "ok"}
            await asyncio.sleep(0.01)
        return {"probe": "late"}

    async with AsyncClient(transport=ASGITransport(app=application),
                           base_url="http://loop-test") as client:
        snapshot = asyncio.create_task(server._snapshot_chains())
        probe = asyncio.create_task(client.get("/__loop_probe"))
        started = time.monotonic()
        try:
            while True:
                if time.monotonic() - started > PROBE_BUDGET_S:
                    raise AssertionError(
                        "the event loop was frozen while the alert-table init was pending")
                if probe.done():
                    break
                await asyncio.sleep(0.01)
            response = await probe
            assert response.status_code == 200
        finally:
            release.set()
            for task in (snapshot, probe):
                if not task.done():
                    task.cancel()
            await asyncio.gather(snapshot, probe, return_exceptions=True)


@pytest.mark.asyncio
async def test_greeks_profile_keeps_the_event_loop_servable(tmp_path, monkeypatch):
    """The Greeks profile read must not hold the loop while it opens/scans."""
    import duckdb

    import routes.greeks as greeks

    db_path = tmp_path / "gflows.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE gflows_greeks (
            ticker VARCHAR, expiry VARCHAR, strike DOUBLE, type VARCHAR,
            delta_absolute DOUBLE, gamma_total DOUBLE, vanna DOUBLE, charm DOUBLE
        )
    """)
    conn.execute("INSERT INTO gflows_greeks VALUES ('SPY', '2026-12-18', 100, 'call', 0.5, 0.1, 0.01, 0.001)")
    conn.close()

    real_connect = duckdb.connect
    opened = threading.Event()
    threads: list[bool] = []

    def slow_connect(path, *args, **kwargs):
        threads.append(threading.current_thread() is not threading.main_thread())
        opened.set()
        time.sleep(1.0)
        return real_connect(path, *args, **kwargs)

    monkeypatch.setenv("GFLOWS_DUCKDB_PATH", str(db_path))
    monkeypatch.setattr(greeks, "duckdb", SimpleNamespace(connect=slow_connect))

    application = FastAPI()
    application.include_router(greeks.router, prefix="/api/greeks")

    @application.get("/__loop_probe")
    async def loop_probe():
        return {"probe": "ok"}

    async with AsyncClient(transport=ASGITransport(app=application),
                           base_url="http://loop-test") as client:
        await _probe_while_pending(client, "/api/greeks/profile/SPY", budget_s=0.5)
    assert opened.is_set(), "the Greeks profile never opened its store"
    assert threads, "the Greeks profile never opened its store"
    assert all(threads), "the Greeks profile opened its store on the event-loop thread"


@pytest.mark.asyncio
async def test_chain_read_computation_runs_off_the_event_loop(monkeypatch):
    """The chain rows must be computed off the request thread."""
    import server
    import services.chain_readings as chain_readings
    import services.triad_projection as triad_projection

    contracts = [{
        "strike": 100.0 + index, "expiry": "2026-12-18", "type": "call" if index % 2 else "put",
        "oi": 100.0, "iv": 0.25, "volume": 10.0, "gamma": 0.05, "delta": 0.5,
        "bid": 1.0, "ask": 1.1, "last": 1.05,
    } for index in range(40)]

    async def _fetch(ticker, max_expiries=4):
        return {"ticker": ticker, "spot": 100.0, "expiries": ["2026-12-18"],
                "contracts": [dict(c) for c in contracts], "data_source": "test"}

    threads: list[bool] = []

    _real_chain_readings = chain_readings.chain_readings
    _real_annotate = triad_projection.annotate_contract_exposure

    def _probe_chain_readings(rows, spot, ticker):
        threads.append(threading.current_thread() is not threading.main_thread())
        time.sleep(1.5)
        return _real_chain_readings(rows, spot, ticker)

    def _probe_annotate(rows, spot):
        threads.append(threading.current_thread() is not threading.main_thread())
        return _real_annotate(rows, spot)

    monkeypatch.setattr(server, "fetch_spot_and_chains_merged", _fetch)
    monkeypatch.setattr(chain_readings, "chain_readings", _probe_chain_readings)
    monkeypatch.setattr(triad_projection, "annotate_contract_exposure", _probe_annotate)

    from routes.market_data import router as market_data_router

    application = FastAPI()
    application.include_router(market_data_router, prefix="/api/market_data")

    @application.get("/__loop_probe")
    async def loop_probe():
        return {"probe": "ok"}

    async with AsyncClient(transport=ASGITransport(app=application),
                           base_url="http://loop-test") as client:
        await _probe_while_pending(client, "/api/market_data/chain/SPY", budget_s=0.5)
    assert threads, "the chain rows were never computed"
    assert all(threads), "the chain rows were computed on the event-loop thread"


@pytest.mark.asyncio
async def test_daily_checklist_kernels_run_off_the_event_loop(monkeypatch):
    """The checklist kernels must not run on the request thread."""
    import advanced_analytics
    import routes.analytics as analytics

    contracts = [{
        "strike": 100.0 + index, "expiry": "2026-12-18", "type": "call" if index % 2 else "put",
        "oi": 100.0, "iv": 0.25, "volume": 10.0, "gamma": 0.05, "delta": 0.5,
        "bid": 1.0, "ask": 1.1, "last": 1.05, "T": 0.1,
    } for index in range(40)]

    async def _get_chain(ticker, expiries, max_age_seconds, coordinator):
        return {"ticker": ticker, "spot": 100.0, "expiries": ["2026-12-18"],
                "contracts": [dict(c) for c in contracts], "data_source": "test"}

    threads: list[bool] = []

    _real_flip = advanced_analytics.calc_gamma_flip_levels

    def _probe_flip(spot, chain, ticker):
        threads.append(threading.current_thread() is not threading.main_thread())
        time.sleep(1.5)
        return _real_flip(spot, chain, ticker)

    monkeypatch.setattr(analytics._cache, "get_chain", _get_chain)
    monkeypatch.setattr(advanced_analytics, "calc_gamma_flip_levels", _probe_flip)

    application = FastAPI()
    application.include_router(analytics.router, prefix="/api/analytics")

    @application.get("/__loop_probe")
    async def loop_probe():
        return {"probe": "ok"}

    async with AsyncClient(transport=ASGITransport(app=application),
                           base_url="http://loop-test") as client:
        await _probe_while_pending(client, "/api/analytics/daily-checklist/SPY", budget_s=0.5)
    assert threads, "the checklist kernels were never called"
    assert all(threads), "the checklist kernels ran on the event-loop thread"
