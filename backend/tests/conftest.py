"""Shared test fixtures."""
import asyncio
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
    try:
        await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})
    except Exception:
        pass

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
        try:
            new_loop.close()
        except Exception:
            pass
        # Teardown-side sweep too (engines created inside the test body).
        try:
            from services.duckdb_engine import DuckDBEngine
            for eng in list(getattr(DuckDBEngine, "_live_instances", [])):
                closer = getattr(eng, "close", None)
                if callable(closer):
                    closer()
            DuckDBEngine._live_instances.clear()
        except Exception:
            pass
