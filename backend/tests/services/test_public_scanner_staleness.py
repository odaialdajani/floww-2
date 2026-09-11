"""D3 regression: success-empty vs failed/stale slices + finite JSON.

- A successful fresh scan with zero unusual rows clears the ticker's
  prior rows (obsolete rows must not pose as current).
- A failed refresh keeps the prior slice with its age; past-TTL it is
  dropped and named in coverage.
- Rows/extras never carry NaN/Infinity (strict JSON serializable).
"""

import json
import math
import time
from unittest.mock import patch

import pytest

import services.public_scanner as scanner
from services.public_budget import PublicBudget

UNI = ["T00", "T01"]


@pytest.fixture
def fresh_budget():
    b = PublicBudget(capacity=60, refill_per_sec=60.0, max_inflight=99)
    with patch("services.public_budget.budget", b):
        yield b


@pytest.fixture
def clean_state():
    scanner._reset_state()
    yield
    scanner._reset_state()


def empty_chain():
    return {"ticker": "T00", "spot": 100.0, "contracts": [], "stale": False}


def seed_prior(rows, age_s=10.0):
    scanner._slices["T00"] = {
        "ts": time.time() - age_s,
        "rows": rows,
        "extras": {},
        "dealer": None,
    }


OLD_ROWS = [["T00", "O:T00", "call", 100.0, "2026-09-18", 500, 100, 0.4, 0.4, 99.0]]


@pytest.mark.asyncio
async def test_success_empty_clears_prior_rows(fresh_budget, clean_state):
    seed_prior([list(r) for r in OLD_ROWS])

    async def fake_fetch(ticker, max_expiries=2):
        return dict(empty_chain()) | {"ticker": ticker}

    with patch(
        "services.public_api_adapter.fetch_chain_from_public_api",
        side_effect=fake_fetch,
    ):
        view = await scanner.scan_next(
            slice_size=2, max_expiries=2, universe=list(UNI)
        )
    tickers_in_rows = {r[0] for r in view["rows"]}
    assert "T00" not in tickers_in_rows


@pytest.mark.asyncio
async def test_failed_refresh_keeps_prior_with_age(fresh_budget, clean_state):
    seed_prior([list(r) for r in OLD_ROWS], age_s=10.0)

    async def fake_fetch(ticker, max_expiries=2):
        return None

    with patch(
        "services.public_api_adapter.fetch_chain_from_public_api",
        side_effect=fake_fetch,
    ):
        view = await scanner.scan_next(
            slice_size=2, max_expiries=2, universe=list(UNI)
        )
    assert [r for r in view["rows"] if r[0] == "T00"] != []
    assert view["coverage"]["fresh"] >= 1
    assert view["coverage"]["max_age_s"] >= 10.0


@pytest.mark.asyncio
async def test_stale_failure_dropped_and_named(fresh_budget, clean_state):
    seed_prior([list(r) for r in OLD_ROWS], age_s=3600.0)

    async def fake_fetch(ticker, max_expiries=2):
        return None

    with patch(
        "services.public_api_adapter.fetch_chain_from_public_api",
        side_effect=fake_fetch,
    ):
        view = await scanner.scan_next(
            slice_size=2, max_expiries=2, universe=list(UNI)
        )
    assert [r for r in view["rows"] if r[0] == "T00"] == []
    assert "T00" in view["coverage"]["stale_dropped"]


def test_rows_and_extras_strict_json_finite(clean_state):
    chain = {
        "ticker": "T00",
        "spot": 100.0,
        "contracts": [
            {
                "osi": "O:T00",
                "type": "call",
                "strike": 100.0,
                "expiry": "2026-09-18",
                "volume": 500,
                "oi": 100,
                "iv": "nan",
                "delta": float("nan"),
                "bid": "nan",
                "ask": "inf",
                "last": "-inf",
                "mid": "nan",
            }
        ],
    }
    rows, extras = scanner.unusual_rows_from_chain(chain)
    blob = json.dumps({"rows": rows, "extras": extras}, allow_nan=False)
    assert blob
    for r in rows:
        for v in r:
            if isinstance(v, float):
                assert math.isfinite(v)
    for e in extras.values():
        for v in e.values():
            if isinstance(v, float):
                assert math.isfinite(v)
