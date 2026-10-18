"""Shared test fixtures."""
import asyncio
import contextlib
import os
import sys

# Skip stale duplicate test directory
collect_ignore = ["service_tests"]

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

try:
    from server import app
except (ImportError, SyntaxError):
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from server import app


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def aclient():
    """Async HTTP client for the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"X-API-Key": "test-secret-key"}) as client:
        yield client


@pytest.fixture(autouse=True)
def _hermetic_market_data_env(monkeypatch):
    """Offline default for every test: host .env market-data policy must not
    leak into test behavior. The canonical checkout runs the service with
    FLOWW_MARKET_DATA_PROVIDER=public and a real PUBLIC_API_KEY; tests written
    against the legacy contract (or the key-less short-circuit those runs
    relied on) then attempt real Public reads mid-suite and the session
    offline guardian records missed-provider attempts. Tests that need the
    public-only policy keys — the dedicated policy tests — set them
    explicitly, and a test-level monkeypatch.setenv still overrides this
    pin. .env values are for the running service, never the test suite."""
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("PUBLIC_API_KEY", raising=False)


@pytest_asyncio.fixture(autouse=True)
async def _reset_event_loop_and_motor(aclient, monkeypatch):
    """Reset event loop AND motor client before each test."""
    from motor.motor_asyncio import AsyncIOMotorClient

    import server

    # Set API_SECRET_KEY for tests so auth doesn't block mutating routes
    # Force-override so .env value (dev-local-testing-key) doesn't win over test key
    os.environ["API_SECRET_KEY"] = "test-secret-key"

    # Step 1: Close old event loop
    try:
        old_loop = asyncio.get_event_loop()
        if not old_loop.is_closed():
            old_loop.close()
    except RuntimeError:
        pass

    # Step 2: Create fresh event loop
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)

    # Step 3: Create fresh motor client bound to the new loop
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_confluence_decoder")

    fresh = AsyncIOMotorClient(
        mongo_url,
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
    )
    monkeypatch.setattr(server, "client", fresh)
    monkeypatch.setattr(server, "db", fresh[db_name])

    # Step 4: Reset error tracking
    try:
        from error_tracking import clear_error_log
        clear_error_log()
    except Exception:
        pass

    # Step 5: Reset live policy to safe defaults
    with contextlib.suppress(Exception):
        await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})

    # Step 6: close any DuckDBEngine instances created during this test.
    # Each live DuckDB connection holds ~ncores spinning scheduler threads;
    # leaked engines made long pytest runs grind to a halt.
    try:
        from services.duckdb_engine import DuckDBEngine
        for eng in list(getattr(DuckDBEngine, "_live_instances", [])):
            with_context = getattr(eng, "close", None)
            if callable(with_context):
                with_context()
        DuckDBEngine._live_instances.clear()
    except Exception:
        pass

    try:
        yield
    finally:
        fresh.close()
        with contextlib.suppress(Exception):
            new_loop.close()
        # Teardown-side sweep too (engines created inside the test body).
        with contextlib.suppress(Exception):
            from services.duckdb_engine import DuckDBEngine as _DuckDBEngine
            for eng in list(getattr(_DuckDBEngine, "_live_instances", [])):
                closer = getattr(eng, "close", None)
                if callable(closer):
                    closer()
            _DuckDBEngine._live_instances.clear()
