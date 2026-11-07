"""Shared offline harness for the Task 4 runtime characterization tests.

Every test in this lane runs against three doubles and one isolated store:

  * a Public.com vendor double (no socket, deterministic series),
  * a private PublicBudget instance (real logic, no shared process state),
  * an isolated DuckDB file under the test's own temporary directory.

Nothing here starts a service, opens a persistent store, or spends a provider
call. The recorded numbers characterize this repository's code path, not the
vendor's latency, and every consumer of these numbers must say so.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import routes.health as health_routes
import routes.price_history as price_history
import services.agent.daily_bar_evidence as daily_bar_evidence
import services.duckdb_engine as duckdb_engine_module
import services.public_api_adapter as public_api_adapter
import services.public_budget as public_budget_module

# The four stages this lane keeps apart. A change that collapses them into one
# number (or hides one behind a cache) fails these tests.
PUBLIC_READ = "public_read"
DAILY_BARS = "daily_bars"
CALCULATION = "calculation"
DUCKDB = "duckdb"
# Two surrounding measurements that are NOT part of the four: the route's whole
# bars step, and the budget admission inside it.
BARS_STEP = "bars_step"
ADMISSION = "admission"

CHART_PATH = "/api/heatseeker/price-history/{ticker}"
VERSION_PATH = "/api/version"

VENDOR_DELAY_S = 0.30
TICKERS = ("SPY", "AMD")

# How a poller behaves: a bounded wait between probes and a hard bound per
# probe, so a stalled read fails the test instead of hanging the run. An
# in-process probe loop that never yields starves the requests it observes.
PROBE_INTERVAL_S = 0.01
PROBE_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 20.0

SNAPSHOT_SCHEMA = """
        CREATE TABLE IF NOT EXISTS heatmap_snapshots_v2 (
            snapshot_id VARCHAR PRIMARY KEY, ticker VARCHAR, query_key VARCHAR,
            expiries VARCHAR, spot DOUBLE, data_source VARCHAR, exposure_basis VARCHAR,
            formula_version VARCHAR, asof_ts VARCHAR, received_at VARCHAR,
            n_contracts INTEGER, n_usable INTEGER, digest VARCHAR,
            strikes_json VARCHAR, walls_json VARCHAR
        )
    """

GREEKS_SCHEMA = """
        CREATE TABLE IF NOT EXISTS gflows_greeks (
            ticker VARCHAR, strike DOUBLE, delta_absolute DOUBLE,
            gamma_total DOUBLE, vanna DOUBLE, charm DOUBLE, expiry VARCHAR
        )
    """


class StageRecorder:
    """One wall-clock span per stage, with the OS thread that ran it."""

    def __init__(self) -> None:
        self.spans: list[dict] = []
        self._lock = threading.Lock()

    def record(self, stage: str, label: str | None, elapsed: float,
               started: float | None = None) -> None:
        with self._lock:
            self.spans.append({
                "stage": stage,
                "label": label,
                "elapsed_s": round(elapsed, 6),
                "thread": threading.current_thread().name,
                "started_at": round(started if started is not None
                                    else time.monotonic(), 6),
            })

    def stage(self, name: str) -> list[dict]:
        return [span for span in self.spans if span["stage"] == name]

    def total(self, name: str) -> float:
        return round(sum(span["elapsed_s"] for span in self.stage(name)), 6)

    def maximum(self, name: str) -> float:
        spans = self.stage(name)
        return round(max(span["elapsed_s"] for span in spans), 6) if spans else 0.0

    def labels(self, name: str) -> list[str]:
        return [span["label"] for span in self.stage(name) if span["label"]]

    def threads(self, name: str) -> list[str]:
        return sorted({span["thread"] for span in self.stage(name)})

    def windows(self, name: str) -> list[tuple[float, float]]:
        """(start, end) monotonic windows per span, for overlap checks."""
        return [(span["started_at"], span["started_at"] + span["elapsed_s"])
                for span in self.stage(name)]

    @staticmethod
    def _overlaps(first: tuple[float, float], second: tuple[float, float]) -> bool:
        return first[0] < second[1] and second[0] < first[1]

    def any_overlap(self, name: str) -> bool:
        """True when two spans of one stage were in flight at the same time."""
        windows = self.windows(name)
        return any(self._overlaps(windows[index], windows[other])
                   for index in range(len(windows))
                   for other in range(index + 1, len(windows)))


def _timed(recorder: StageRecorder, stage: str, function, *, label=None):
    """Wrap one callable and record its wall-clock span under `stage`."""
    if inspect.iscoroutinefunction(function):
        async def wrapper(*args, **kwargs):
            started = time.perf_counter()
            at = time.monotonic()
            try:
                return await function(*args, **kwargs)
            finally:
                recorder.record(stage, label(args, kwargs) if label else None,
                                time.perf_counter() - started, at)
        return wrapper

    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        at = time.monotonic()
        try:
            return function(*args, **kwargs)
        finally:
            recorder.record(stage, label(args, kwargs) if label else None,
                            time.perf_counter() - started, at)
    return wrapper


def ticker_of(args, kwargs) -> str | None:
    """First argument that looks like a plain ticker (no path, no SQL)."""
    for value in list(args) + list(kwargs.values()):
        if isinstance(value, str) and value and not value.startswith(("/", "SELECT")) \
                and " " not in value and len(value) <= 8 and value.upper() == value:
            return value
    return None


class OfflineBroker:
    """Vendor double for the Public bars read: no socket, synthetic series.

    `delay` is the wait a real round trip would occupy, so a request's event-loop
    behaviour under load is observable. `gates` lets a test hold one ticker's
    vendor read open (cancellation and shared-work evidence). The payload shape
    is the real Bars-v2 shape, so the route's own normalization and evidence code
    run unchanged.
    """

    def __init__(self, recorder: StageRecorder, delay: float = VENDOR_DELAY_S,
                 bars: int = 260) -> None:
        self._recorder = recorder
        self._delay = delay
        self._bars = bars
        self._token_expires_at = time.time() + 3600
        self.calls: list[str] = []
        self.gates: dict[str, threading.Event] = {}
        self.entered: dict[str, threading.Event] = {}

    def gate(self, ticker: str) -> threading.Event:
        """A gate that holds `ticker`'s vendor read until it is set."""
        event = threading.Event()
        self.gates[ticker] = event
        return event

    def get_trading_account(self):
        return SimpleNamespace(trade_permissions="BUY_AND_SELL")

    async def get_bars(self, symbol, period, instrument_type="EQUITY",
                      aggregation=None, **kwargs):
        self.calls.append(symbol)
        entered = self.entered.setdefault(symbol, threading.Event())
        entered.set()
        started = time.perf_counter()
        at = time.monotonic()
        try:
            gate = self.gates.get(symbol)
            if gate is not None:
                # Held open on purpose: a real vendor read that never returns
                # while a browser walks away.
                await asyncio.get_running_loop().run_in_executor(None, gate.wait)
            else:
                await asyncio.sleep(self._delay)
            return self._payload(symbol)
        finally:
            self._recorder.record(PUBLIC_READ, symbol,
                                  time.perf_counter() - started, at)

    def _payload(self, symbol: str) -> dict:
        rows = []
        base = datetime.now(UTC) - timedelta(days=self._bars)
        for index in range(self._bars):
            at = base + timedelta(days=index)
            close = 100.0 + (index % 7) * 0.5
            rows.append({
                "t": int(at.timestamp() * 1000),
                "open": round(close - 0.2, 2),
                "high": round(close + 0.4, 2),
                "low": round(close - 0.5, 2),
                "close": round(close, 2),
                "v": 1_000_000 + index,
            })
        return {"symbol": symbol, "regularMarket": {"bars": rows}}

    async def close(self):
        return None


def _seed_snapshots(engine) -> None:
    """Recorded node history for the chart read, on the isolated store."""
    engine.conn.execute(SNAPSHOT_SCHEMA)
    for ticker in TICKERS:
        for index in range(6):
            at = datetime.now(UTC) - timedelta(minutes=30 - index * 5)
            engine.conn.execute(
                "INSERT INTO heatmap_snapshots_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [f"{ticker}-{index}", ticker, "scope-a", '["2026-12-18"]',
                 100.0 + index, "public_api", "dealer", "v1", at.isoformat(),
                 at.isoformat(), 10, 10, "digest",
                 json.dumps([{"strike": 100.0, "gex": 1.0}]),
                 json.dumps([{"wall_id": "w1", "mid": 100.0, "low": 99.0,
                              "high": 101.0}])],
            )


_MISSING = object()


class EnvironmentPatch:
    """Manual save/restore of the module attributes this harness replaces.

    The pytest fixture uses monkeypatch; the standalone benchmark script has no
    monkeypatch, so both go through this one restore path. An attribute that did
    not exist before (a method shadowed on one instance) is removed again rather
    than restored, so no instance keeps a permanent shadow of its class.
    """

    def __init__(self) -> None:
        self._saved: list[tuple[object, str, object]] = []
        self._extra: list = []

    def setattr(self, owner: object, name: str, value) -> None:
        try:
            original = getattr(owner, name)
        except AttributeError:
            original = _MISSING
        self._saved.append((owner, name, original))
        setattr(owner, name, value)

    def note(self, closer) -> None:
        self._extra.append(closer)

    def restore(self) -> None:
        for closer in self._extra:
            with contextlib.suppress(Exception):
                closer()
        for owner, name, original in reversed(self._saved):
            with contextlib.suppress(Exception):
                if original is _MISSING:
                    delattr(owner, name)
                else:
                    setattr(owner, name, original)


def _instrument(recorder: StageRecorder, patch: EnvironmentPatch,
                broker: OfflineBroker, budget: object) -> None:
    """Time each stage where the route itself calls it."""
    patch.setattr(public_api_adapter, "BROKER", broker)
    patch.setattr(public_api_adapter, "_extract_bars",
                  _timed(recorder, DAILY_BARS,
                         public_api_adapter._extract_bars,
                         label=lambda a, k: "extract"))
    patch.setattr(daily_bar_evidence, "cache_public_daily_payload",
                  _timed(recorder, DAILY_BARS,
                         daily_bar_evidence.cache_public_daily_payload,
                         label=lambda a, k: "evidence"))
    patch.setattr(price_history, "build_history",
                  _timed(recorder, CALCULATION, price_history.build_history))
    patch.setattr(price_history, "recording_summary",
                  _timed(recorder, DUCKDB, price_history.recording_summary))
    patch.setattr(price_history, "read_snapshots",
                  _timed(recorder, DUCKDB, price_history.read_snapshots))
    # The whole bars step of the route, and inside it the budget admission that
    # has to succeed before the vendor read is allowed to start. The route
    # resolves the governor by name at call time, so the private instance has to
    # be published under that name for the admission to be observed at all.
    patch.setattr(price_history, "_history_bars",
                  _timed(recorder, BARS_STEP, price_history._history_bars,
                         label=ticker_of))
    patch.setattr(public_budget_module, "budget", budget)
    patch.setattr(budget, "acquire",
                  _timed(recorder, ADMISSION, budget.acquire,
                         label=lambda a, k: "public"))


def build_environment(store_dir, *, delay: float = VENDOR_DELAY_S,
                      bars: int = 260, seed: bool = True):
    """Wire the offline doubles around one isolated store directory.

    Returns (recorder, broker, budget, engine, application, patch). Nothing here
    touches a running service or a persistent store: `store_dir` is the only
    place a file is written, and the caller owns its lifetime.
    """
    from services.duckdb_engine import DuckDBEngine

    recorder = StageRecorder()
    broker = OfflineBroker(recorder, delay=delay, bars=bars)
    budget = public_budget_module.PublicBudget()
    patch = EnvironmentPatch()
    _instrument(recorder, patch, broker, budget)

    store_path = Path(store_dir) / "floww-runtime-store.duckdb"
    engine = DuckDBEngine(str(store_path))
    if seed:
        _seed_snapshots(engine)
    patch.setattr(duckdb_engine_module, "db", engine)
    patch.note(engine.close)
    price_history._bar_reads.clear()

    application = FastAPI()
    application.include_router(price_history.router)
    application.include_router(health_routes.router)
    return recorder, broker, budget, engine, application, patch


@pytest.fixture
def runtime_env(tmp_path):
    """Offline chart-read harness: vendor double, isolated store, timed stages."""
    recorder, broker, budget, engine, application, patch = build_environment(tmp_path)
    yield SimpleNamespace(recorder=recorder, broker=broker, engine=engine,
                          app=application, budget=budget,
                          client=lambda: client_for(application),
                          version=version_probe)
    price_history._bar_reads.clear()
    patch.restore()


@pytest.fixture
def greeks_env(monkeypatch, tmp_path):
    """Isolated gflows store for the store-pool backed Greeks read."""
    import duckdb

    recorder = StageRecorder()
    path = tmp_path / "gflows.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute(GREEKS_SCHEMA)
    for strike in (98.0, 99.0, 100.0, 101.0, 102.0):
        connection.execute(
            "INSERT INTO gflows_greeks VALUES (?,?,?,?,?,?,?)",
            ["SPY", strike, 1.0 * strike, 0.5 * strike, 0.25, 0.1, "2026-12-18"],
        )
    connection.close()
    monkeypatch.setenv("GFLOWS_DUCKDB_PATH", str(path))

    from server import app as server_app

    yield SimpleNamespace(recorder=recorder, path=path, app=server_app)
    with contextlib.suppress(Exception):
        if path.exists():
            path.unlink()


def store_slots(loop) -> int:
    """Admission slots currently free on this loop's gate (0 when saturated)."""
    from services import store_executor

    return store_executor._slots_for(loop)._value


def store_slots(loop) -> int:
    """Admission slots currently free on this loop's gate (0 when saturated)."""
    from services import store_executor

    return store_executor._slots_for(loop)._value


async def chart_read(client, ticker: str, days: int = 260, params: dict | None = None):
    """One chart read, returning (response, wall seconds)."""
    started = time.perf_counter()
    response = await client.get(CHART_PATH.format(ticker=ticker),
                                params={"days": days, **(params or {})})
    return response, time.perf_counter() - started


async def version_probe(client) -> tuple[int, dict, float]:
    """One /api/version probe, returning (status, body, seconds)."""
    started = time.perf_counter()
    response = await client.get(VERSION_PATH)
    return response.status_code, response.json(), time.perf_counter() - started


def client_for(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app),
                      base_url="http://runtime-task4-test")


def hold_pool(store_executor, started: threading.Event,
              release: threading.Event) -> list:
    """Admit exactly the pool's whole budget and hold every call open.

    Returns the holder tasks; `started` is set once the workers are running and
    `release` ends every held call.
    """
    admitted = store_executor.STORE_WORKERS + store_executor.STORE_QUEUE_SLOTS

    def _hold():
        started.set()
        release.wait(timeout=30)
        return "held"

    return [asyncio.create_task(store_executor.run_store(_hold))
            for _ in range(admitted)]
