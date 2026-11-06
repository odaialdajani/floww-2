"""Regression checks for the store offload fixes.

Six failure modes are pinned here:

- a cold node tracker must be shared by concurrent readers, never rebuilt
  once per request;
- the durable node snapshot must be taken on the request thread, where it is
  atomic with the tracker update;
- a cancelled Greeks read must not strand a DuckDB read-only handle;
- a store call the bounded pool refuses must answer 503, never an opaque
  500, and a Greeks store file that disappears must still answer the
  documented 503;
- a refused store call must never put the pool's own refusal text into a
  degraded response body - every such handler answers the same fixed
  constant the global 503 handler uses;
- the same fixed constant has to hold for every degraded handler that can
  see a refused store call.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from services.node_lifecycle import NodeLifecycleTracker
from services.store_executor import STORE_BUSY_MESSAGE, StoreBusy


@pytest.mark.asyncio
async def test_concurrent_cold_readers_share_one_node_tracker(monkeypatch):
    """Concurrent cold readers must not hydrate the tracker twice."""
    import routes.microstructure as microstructure

    monkeypatch.setattr(microstructure, "_node_trackers", {})
    monkeypatch.setattr(microstructure, "_node_tracker_pending", {}, raising=False)

    hydrated: list[str] = []
    release = threading.Event()

    def _hydrate(ticker):
        hydrated.append(ticker)
        release.wait(timeout=5)
        return NodeLifecycleTracker()

    monkeypatch.setattr(microstructure, "_hydrate_node_tracker", _hydrate)

    readers = [asyncio.create_task(microstructure._get_node_tracker("SPY"))
               for _ in range(4)]
    for _ in range(200):
        if hydrated:
            break
        await asyncio.sleep(0.01)
    release.set()
    trackers = await asyncio.gather(*readers)

    assert hydrated == ["SPY"], "the tracker was hydrated more than once"
    assert all(tracker is trackers[0] for tracker in trackers)
    assert microstructure._node_trackers["SPY"] is trackers[0]


@pytest.mark.asyncio
async def test_node_snapshot_is_taken_on_the_request_thread(monkeypatch):
    """The durable snapshot is frozen where update() mutates the nodes."""
    import routes.microstructure as microstructure
    from services import heatmap_history

    tracker = NodeLifecycleTracker()
    monkeypatch.setattr(microstructure, "_node_trackers", {"SPY": tracker})

    on_request_thread: list[bool] = []
    recorded: list[tuple] = []

    def _to_dict():
        on_request_thread.append(threading.current_thread() is threading.main_thread())
        return {"nodes": []}

    monkeypatch.setattr(tracker, "to_dict", _to_dict)
    monkeypatch.setattr(heatmap_history, "record_node_lifecycle",
                        lambda conn, ticker, scope, payload: recorded.append(
                            (ticker, scope, payload)))
    monkeypatch.setattr("services.duckdb_engine.db", SimpleNamespace(_conn=None))

    await microstructure._persist_node_tracker("SPY")

    assert on_request_thread == [True], (
        "the tracker snapshot was taken off the request thread, where update() "
        "can mutate the node mapping underneath it")
    assert recorded == [("SPY", "microstructure", {"nodes": []})]


@pytest.mark.asyncio
async def test_cancelled_greeks_read_still_closes_its_handle(tmp_path, monkeypatch):
    """A cancelled profile read must still close the DuckDB handle."""
    import routes.greeks as greeks

    db_path = tmp_path / "gflows.duckdb"
    db_path.write_bytes(b"")

    events: list[str] = []
    entered = threading.Event()
    release = threading.Event()

    class _FakeConn:
        def close(self):
            events.append("close")

    def _connect(*args, **kwargs):
        events.append("connect")
        return _FakeConn()

    def _query(db_path_, ticker, conn=None):
        entered.set()
        release.wait(timeout=5)
        return []

    monkeypatch.setattr(greeks, "duckdb", SimpleNamespace(connect=_connect))
    monkeypatch.setattr(greeks, "_query_greeks", _query)
    monkeypatch.setenv("GFLOWS_DUCKDB_PATH", str(db_path))

    # One default-pool worker: the close that a cancelled request still owes
    # has to queue behind the running query instead of racing it.
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="greeks-cancel-test"))

    task = asyncio.create_task(greeks.get_greeks_profile("SPY"))
    for _ in range(200):
        if entered.is_set():
            break
        await asyncio.sleep(0.01)
    assert entered.is_set(), "the profile read never reached the query"

    task.cancel()
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    release.set()
    await asyncio.sleep(0.3)

    assert "connect" in events
    assert "close" in events, "the cancelled read never closed its DuckDB handle"


@pytest.mark.asyncio
async def test_a_refused_store_call_answers_503_not_an_opaque_500(tmp_path, monkeypatch):
    """A saturated store pool is backpressure: the caller gets a 503.

    Before the mapping existed the refusal escaped to the global handler and
    became a redacted 500 whose body said nothing about the cause.
    """
    import routes.greeks as greeks
    from services.store_executor import StoreBusy

    db_path = tmp_path / "gflows.duckdb"
    db_path.write_bytes(b"")

    async def _busy(*args, **kwargs):
        raise StoreBusy("store pool saturated")

    monkeypatch.setenv("GFLOWS_DUCKDB_PATH", str(db_path))
    monkeypatch.setattr(greeks, "run_store", _busy)

    from server import app as server_app

    transport = ASGITransport(app=server_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get("/api/greeks/profile/SPY")

    assert response.status_code != 500, (
        f"the refused store call answered an opaque 500: {response.text}")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "Store temporarily unavailable"
    assert body["status_code"] == 503
    assert "store pool saturated" not in response.text, (
        "the internal refusal text leaked into the response body")


@pytest.mark.asyncio
async def test_a_greeks_store_that_disappears_answers_503(tmp_path, monkeypatch):
    """The store check must hold in both orderings.

    The route checks the file before it calls the store pool, but the file
    can disappear between that check and the worker. The worker checks again
    before it opens the handle, so the answer is the documented 503 and not
    a bare DuckDB error turned into a 500.
    """
    import routes.greeks as greeks

    db_path = tmp_path / "gflows.duckdb"
    db_path.write_bytes(b"")

    real_run_store = greeks.run_store

    async def _vanish_then_read(function, *args, **kwargs):
        db_path.unlink()
        return await real_run_store(function, *args, **kwargs)

    monkeypatch.setenv("GFLOWS_DUCKDB_PATH", str(db_path))
    monkeypatch.setattr(greeks, "run_store", _vanish_then_read)

    application = FastAPI()
    application.include_router(greeks.router, prefix="/api/greeks")

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://greeks-vanish-test") as client:
        response = await client.get("/api/greeks/profile/SPY")

    assert response.status_code != 500, (
        f"a vanished store answered an opaque 500: {response.text}")
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == (
        "Greeks data not available — run setup_gflows_data.py first")


def _busy_run_store(*args, **kwargs):
    """A store pool that refuses every call."""
    async def _busy(*_args, **_kwargs):
        raise StoreBusy("store pool saturated")

    return _busy


@pytest.mark.asyncio
async def test_a_refused_review_read_never_leaks_the_pool_text(monkeypatch):
    """The decisions list must answer the fixed constant, not the pool text."""
    import routes.solstice_review as solstice_review

    monkeypatch.setattr(solstice_review, "run_store", _busy_run_store())

    application = FastAPI()
    review_router = APIRouter(prefix="/api/solstice")
    solstice_review.register_review_routes(review_router)
    application.include_router(review_router)

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get("/api/solstice/SPY/decisions")

    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body) == ["ticker", "decisions", "error"], body
    assert body["error"] == STORE_BUSY_MESSAGE, body
    assert "store pool saturated" not in response.text, (
        "the internal refusal text leaked into the response body")


@pytest.mark.asyncio
async def test_a_refused_microstructure_read_never_leaks_the_pool_text(monkeypatch):
    """The nodes route must answer the fixed constant, not the pool text."""
    import routes.microstructure as microstructure

    monkeypatch.setattr(microstructure, "run_store", _busy_run_store())
    monkeypatch.setattr(microstructure, "_node_trackers", {})
    monkeypatch.setattr(microstructure, "_node_tracker_pending", {})

    class _Aggregator:
        def compute(self, spot, contracts):
            return {"gex_1d": [1.0, 2.0, 1.0], "strikes": [99.0, 100.0, 101.0]}

    async def _chain(ticker, expiries=5):
        return {"spot": 100.0, "contracts": [{"strike": 100.0}]}

    monkeypatch.setattr(microstructure, "_get_gex_aggregator", lambda: _Aggregator())
    monkeypatch.setattr(microstructure, "_fetch_chain", _chain)

    application = FastAPI()
    application.include_router(microstructure.router)

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get("/api/microstructure/nodes/SPY")

    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body) == ["ticker", "status", "error"], body
    assert body["error"] == STORE_BUSY_MESSAGE, body
    assert "store pool saturated" not in response.text, (
        "the internal refusal text leaked into the response body")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/heatseeker/node-lifecycle?ticker=SPY",
    "/api/heatseeker/node-confluence?ticker=SPY",
])
async def test_a_refused_heatseeker_read_never_leaks_the_pool_text(monkeypatch, path):
    """The degraded heatseeker bodies must answer the fixed constant."""
    import routes.heatseeker as heatseeker

    async def _busy_chain(ticker, expiries):
        raise StoreBusy("store pool saturated")

    monkeypatch.setattr(heatseeker, "_fetch_chain", _busy_chain)

    application = FastAPI()
    application.include_router(heatseeker.router)

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get(path)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded", body
    assert body["error"] == STORE_BUSY_MESSAGE, body
    assert "store pool saturated" not in response.text, (
        "the internal refusal text leaked into the response body")


def _refusing_store(monkeypatch, module):
    """Make every store call in one route module refuse."""
    monkeypatch.setattr(module, "run_store", _busy_run_store())


def _connected_store(monkeypatch):
    """Give the routes a store connection so they reach the store call."""
    import services.duckdb_engine as engine

    monkeypatch.setattr(engine, "db", SimpleNamespace(conn=object()))


@pytest.mark.asyncio
async def test_a_refused_vpin_history_is_never_answered_as_an_empty_history(monkeypatch):
    """A busy pool is backpressure, not an empty history.

    Answering 200 with an empty bucket list would claim the ticker has no
    stored VPIN history, which is a statement about the data that the refusal
    cannot make.
    """
    import routes.vpin as vpin

    _refusing_store(monkeypatch, vpin)

    from server import app as server_app

    transport = ASGITransport(app=server_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get("/api/vpin/SPY/history")

    assert response.status_code == 503, (
        f"a refused store call was answered as an empty history: {response.text}")
    body = response.json()
    assert body["error"] == STORE_BUSY_MESSAGE, body
    assert "buckets" not in body, (
        "the refusal was answered with an empty history instead of backpressure")


@pytest.mark.asyncio
async def test_a_refused_capability_read_is_never_answered_as_no_observations(monkeypatch):
    """A refused capability read must not claim that nothing was observed."""
    import routes.solstice as solstice

    _refusing_store(monkeypatch, solstice)
    _connected_store(monkeypatch)

    from server import app as server_app

    transport = ASGITransport(app=server_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get("/api/solstice/capability")

    assert response.status_code == 503, (
        f"a refused store call was answered as an empty observation list: {response.text}")
    assert response.json()["error"] == STORE_BUSY_MESSAGE, response.text


@pytest.mark.asyncio
async def test_a_refused_price_path_session_read_is_never_answered_as_an_unavailable_recorder(monkeypatch):
    """A busy pool is not a missing recorder."""
    import routes.solstice_price_paths as price_paths

    _refusing_store(monkeypatch, price_paths)
    monkeypatch.setattr(price_paths, "_store_conn", lambda: object())

    from server import app as server_app

    transport = ASGITransport(app=server_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get("/api/solstice/price-paths/sessions?ticker=SPY")

    assert response.status_code == 503, (
        f"a refused store call was answered as an unavailable recorder: {response.text}")
    assert response.json()["error"] == STORE_BUSY_MESSAGE, response.text


@pytest.mark.asyncio
async def test_a_refused_review_contract_read_is_never_answered_as_a_missing_snapshot(monkeypatch):
    """A busy pool must not be reported as 'no recorded snapshot'."""
    import routes.solstice_review as solstice_review

    _refusing_store(monkeypatch, solstice_review)
    _connected_store(monkeypatch)

    from server import app as server_app

    transport = ASGITransport(app=server_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get(
            "/api/solstice/SPY/contract?osi=SPY261106C00500000")

    assert response.status_code == 503, (
        f"a refused store call was answered as a missing snapshot: {response.text}")
    body = response.json()
    assert body["error"] == STORE_BUSY_MESSAGE, body
    assert body.get("reason") != "NO_RECORDED_SNAPSHOT", (
        "the refusal was reported as a missing recorded snapshot")


@pytest.mark.asyncio
async def test_a_refused_heatseeker_store_read_reaches_the_degraded_body(monkeypatch):
    """The refusal has to survive the route's inner best-effort block.

    The durable-memory join is best-effort, so its own failure is tolerated.
    A refusal from the bounded pool is not the same thing: it has to reach
    the route's documented degraded body.
    """
    import routes.heatseeker as heatseeker

    async def _chain(ticker, expiries=2):
        return {"spot": 100.0, "contracts": [{"strike": 100.0}]}

    async def _history(ticker, lookback_mins=1440):
        return []

    _refusing_store(monkeypatch, heatseeker)
    monkeypatch.setattr(heatseeker, "_fetch_chain", _chain)
    monkeypatch.setattr(heatseeker, "_fetch_history", _history)
    monkeypatch.setattr(heatseeker, "calc_node_lifecycle", lambda *a, **k: {})

    application = FastAPI()
    application.include_router(heatseeker.router)

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get("/api/heatseeker/node-lifecycle?ticker=SPY")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded", body
    assert body["error"] == STORE_BUSY_MESSAGE, body


@pytest.mark.asyncio
async def test_a_refused_microstructure_write_is_reported_not_dropped(monkeypatch):
    """A refused durable write must be visible to the caller.

    The write is best-effort for genuine write errors, but a refusal from
    the bounded pool means the durable state was not stored. Answering 'ok'
    would claim the tracker was persisted when it was not.
    """
    import routes.microstructure as microstructure

    real_run_store = microstructure.run_store

    async def _refuse_writes_only(function, *args, **kwargs):
        if getattr(function, "__name__", "") == "_write":
            raise StoreBusy("store pool saturated")
        return await real_run_store(function, *args, **kwargs)

    monkeypatch.setattr(microstructure, "run_store", _refuse_writes_only)
    monkeypatch.setattr(microstructure, "_node_trackers", {})
    monkeypatch.setattr(microstructure, "_node_tracker_pending", {})

    class _Aggregator:
        def compute(self, spot, contracts):
            return {"gex_1d": [1.0, 2.0, 1.0], "strikes": [99.0, 100.0, 101.0]}

    async def _chain(ticker, expiries=5):
        return {"spot": 100.0, "contracts": [{"strike": 100.0}]}

    monkeypatch.setattr(microstructure, "_get_gex_aggregator", lambda: _Aggregator())
    monkeypatch.setattr(microstructure, "_fetch_chain", _chain)

    application = FastAPI()
    application.include_router(microstructure.router)

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport,
                           base_url="http://store-busy-test") as client:
        response = await client.get("/api/microstructure/nodes/SPY")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] == STORE_BUSY_MESSAGE, body
    assert "store pool saturated" not in response.text, (
        "the internal refusal text leaked into the response body")
