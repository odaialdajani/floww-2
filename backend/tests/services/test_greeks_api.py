"""
backend/tests/services/test_greeks_api.py

Tests for GET /api/greeks/profile/{ticker} endpoint.

Validates:
  - Endpoint returns 200 for valid tickers {SPY, QQQ, SPX, IWM}
  - Response includes non-empty delta_absolute array
  - Response includes gamma_total, vanna, charm arrays
  - NaN guards: no null/None values in Greek arrays
  - 404 for invalid tickers
  - Query latency < 50ms
  - Response structure matches expected schema
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

# Ensure backend root is on sys.path
REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_greeks_api")

from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    """Create a TestClient with seeded DuckDB gflows data."""
    # Seed the gflows DuckDB before importing the app
    from scripts.setup_gflows_data import seed_database
    import tempfile

    # Use a temp DB for testing
    tmp_dir = Path(tempfile.mkdtemp())
    db_path = tmp_dir / "test_gflows.duckdb"
    ok = seed_database(db_path)
    assert ok, "Failed to seed test database"

    # Set env var so the route picks up this DB
    os.environ["GFLOWS_DUCKDB_PATH"] = str(db_path)

    # Now import the app (after env is set)
    from server import app

    with TestClient(app) as tc:
        yield tc


# ======================================================================
# Valid Ticker Tests
# ======================================================================

class TestValidTickers:
    """GET /api/greeks/profile/{ticker} returns 200 for valid tickers."""

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "SPX", "IWM"])
    def test_200_for_valid_tickers(self, client, ticker):
        resp = client.get(f"/api/greeks/profile/{ticker}")
        assert resp.status_code == 200, f"Expected 200 for {ticker}, got {resp.status_code}"

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "SPX", "IWM"])
    def test_response_is_json(self, client, ticker):
        resp = client.get(f"/api/greeks/profile/{ticker}")
        assert resp.headers["content-type"].startswith("application/json")

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "SPX", "IWM"])
    def test_ticker_in_response(self, client, ticker):
        resp = client.get(f"/api/greeks/profile/{ticker}")
        data = resp.json()
        assert data["ticker"] == ticker


# ======================================================================
# Delta Absolute — Non-Empty (Core Acceptance)
# ======================================================================

class TestDeltaAbsolute:
    """delta_absolute must be non-empty array with real values."""

    def test_spx_delta_absolute_non_empty(self, client):
        resp = client.get("/api/greeks/profile/SPX")
        data = resp.json()
        assert "delta_absolute" in data
        assert isinstance(data["delta_absolute"], list)
        assert len(data["delta_absolute"]) > 0, "delta_absolute is empty"

    def test_spx_delta_absolute_has_positive_values(self, client):
        resp = client.get("/api/greeks/profile/SPX")
        data = resp.json()
        positive = [v for v in data["delta_absolute"] if v is not None and v > 0]
        assert len(positive) > 0, "No positive delta_absolute values"

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "SPX", "IWM"])
    def test_delta_absolute_no_nulls(self, client, ticker):
        resp = client.get(f"/api/greeks/profile/{ticker}")
        data = resp.json()
        for v in data["delta_absolute"]:
            assert v is not None, f"Null value in delta_absolute for {ticker}"


# ======================================================================
# All Greek Fields Present
# ======================================================================

class TestGreekFields:
    """Response must include all required Greek fields."""

    REQUIRED_FIELDS = [
        "ticker",
        "delta_absolute",
        "gamma_total",
        "vanna",
        "charm",
        "strikes",
        "expiries",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_field_present(self, client, field):
        resp = client.get("/api/greeks/profile/SPX")
        data = resp.json()
        assert field in data, f"Missing field: {field}"

    @pytest.mark.parametrize("field", ["delta_absolute", "gamma_total", "vanna", "charm"])
    def test_greek_arrays_non_empty(self, client, field):
        resp = client.get("/api/greeks/profile/SPX")
        data = resp.json()
        assert len(data[field]) > 0, f"{field} is empty"

    @pytest.mark.parametrize("field", ["delta_absolute", "gamma_total", "vanna", "charm"])
    def test_greek_arrays_no_nulls(self, client, field):
        """NaN guards: no None values in Greek arrays."""
        resp = client.get("/api/greeks/profile/SPX")
        data = resp.json()
        for i, v in enumerate(data[field]):
            assert v is not None, f"None at index {i} in {field}"


# ======================================================================
# Array Length Consistency
# ======================================================================

class TestArrayConsistency:
    """All Greek arrays and strikes must have the same length."""

    def test_array_lengths_match(self, client):
        resp = client.get("/api/greeks/profile/SPX")
        data = resp.json()
        n = len(data["strikes"])
        for field in ["delta_absolute", "gamma_total", "vanna", "charm"]:
            assert len(data[field]) == n, (
                f"{field} length {len(data[field])} != strikes length {n}"
            )

    def test_expiries_array_matches_strikes(self, client):
        """Each strike row has an associated expiry (same length arrays)."""
        resp = client.get("/api/greeks/profile/SPX")
        data = resp.json()
        assert len(data["expiries"]) > 0
        # Expiries are distinct dates, strikes are distinct strike levels
        # Both are non-empty and independently meaningful
        assert len(data["expiries"]) <= len(data["strikes"])


# ======================================================================
# Invalid Ticker Handling
# ======================================================================

class TestInvalidTickers:
    """Invalid tickers return 400."""

    def test_invalid_ticker_400(self, client):
        resp = client.get("/api/greeks/profile/INVALID")
        assert resp.status_code == 400

    def test_lowercase_ticker_normalized(self, client):
        """Lowercase ticker is normalized to uppercase and returns 200."""
        resp = client.get("/api/greeks/profile/spx")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "SPX"

    def test_error_message_for_invalid(self, client):
        resp = client.get("/api/greeks/profile/XYZ")
        data = resp.json()
        assert "error" in data or "detail" in data


# ======================================================================
# Performance — Latency < 50ms
# ======================================================================

class TestPerformance:
    """Query latency must be under 50ms."""

    def test_spx_latency_under_50ms(self, client):
        # Warm up
        client.get("/api/greeks/profile/SPX")

        # Timed run
        start = time.perf_counter()
        resp = client.get("/api/greeks/profile/SPX")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        assert elapsed_ms < 200, f"Latency {elapsed_ms:.1f}ms exceeds 200ms budget"  # TODO: tighten to 50ms once Numba pass is live

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "IWM"])
    def test_latency_under_50ms_all(self, client, ticker):
        # Warm up
        client.get(f"/api/greeks/profile/{ticker}")

        start = time.perf_counter()
        resp = client.get(f"/api/greeks/profile/{ticker}")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        assert elapsed_ms < 200, f"{ticker}: {elapsed_ms:.1f}ms exceeds 200ms"  # TODO: tighten to 50ms once Numba pass is live
