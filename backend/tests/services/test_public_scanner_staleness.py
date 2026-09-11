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
from datetime import UTC, datetime, timedelta
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
    return {"ticker": "T00", "spot": 100.0, "contracts": [], "stale": False,
            "fetched_at": datetime.now(UTC).isoformat()}


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"stale": True}, {"fetched_at": None},
                                     {"fetched_at": "2020-01-01T00:00:00+00:00"}])
async def test_stale_chain_cannot_reset_slice_or_marks(fresh_budget, clean_state, changes):
    seed_prior([list(r) for r in OLD_ROWS], age_s=100)
    prior_time = scanner._slices["T00"]["ts"]
    chain = empty_chain() | changes
    with patch("services.public_api_adapter.fetch_chain_from_public_api", return_value=chain), \
         patch.object(scanner, "_stamp_marks") as stamp:
        view = await scanner.scan_next(slice_size=1, universe=["T00"])
    assert scanner._slices["T00"]["ts"] == prior_time
    assert view["coverage"]["max_age_s"] >= 100
    stamp.assert_not_called()


@pytest.mark.asyncio
async def test_cached_chain_retains_receipt_age(fresh_budget, clean_state):
    received = datetime.now(UTC) - timedelta(seconds=80)
    chain = empty_chain() | {"fetched_at": received.isoformat()}
    with patch("services.public_api_adapter.fetch_chain_from_public_api", return_value=chain), \
         patch.object(scanner, "_get_adv", None):
        await scanner.scan_next(slice_size=1, universe=["T00"])
    assert scanner._slices["T00"]["ts"] == received.timestamp()
    assert scanner._slices["T00"]["event_time"] is None


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
