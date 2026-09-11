"""D2 regression: fair scanner cursor under low affordability.

- Trimmed sweeps advance the cursor only by actually-scanned tickers
  (no starvation of the trimmed tail).
- An unaffordable sweep raises WITHOUT moving the cursor.
- scan_slice performs zero budget acquisition itself (the adapter is
  the C8 choke point; scanner-side reserve would double-debit).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import services.public_scanner as scanner
from services.public_budget import BudgetExhausted, PublicBudget

UNI10 = [f"T{i:02d}" for i in range(10)]


@pytest.fixture
def fresh_budget():
    b = PublicBudget(capacity=12, refill_per_sec=0.0, max_inflight=99)
    with patch("services.public_budget.budget", b):
        yield b


@pytest.fixture
def clean_state():
    scanner._reset_state()
    yield
    scanner._reset_state()


def null_chain():
    return {"contracts": [], "spot": 100.0, "stale": False}


@pytest.mark.asyncio
async def test_trimmed_sweep_advances_only_scanned(fresh_budget, clean_state):
    seen = []

    async def fake_fetch(ticker, max_expiries=2):
        seen.append(ticker)
        return dict(null_chain())

    with patch(
        "services.public_api_adapter.fetch_chain_from_public_api",
        side_effect=fake_fetch,
    ):
        await scanner.scan_next(slice_size=8, max_expiries=2, universe=list(UNI10))
        first = list(seen)
        assert first == UNI10[:3]
        fresh_budget.reset()
        seen.clear()
        await scanner.scan_next(slice_size=8, max_expiries=2, universe=list(UNI10))
        second = list(seen)
    assert second == UNI10[3:6]


@pytest.mark.asyncio
async def test_unaffordable_sweep_keeps_cursor(fresh_budget, clean_state):
    fresh_budget._tokens = 0.0
    before = scanner._cursor
    with pytest.raises(BudgetExhausted):
        await scanner.scan_next(slice_size=8, max_expiries=2, universe=list(UNI10))
    assert scanner._cursor == before


@pytest.mark.asyncio
async def test_scan_slice_does_not_acquire(fresh_budget, clean_state):
    calls = []
    real_acquire = fresh_budget.acquire_n

    async def spy(n, host="public", now=None):
        calls.append(n)
        return await real_acquire(n, host, now)

    async def fake_fetch(ticker, max_expiries=2):
        return dict(null_chain())

    with (
        patch.object(fresh_budget, "acquire_n", side_effect=spy),
        patch(
            "services.public_api_adapter.fetch_chain_from_public_api",
            side_effect=fake_fetch,
        ),
    ):
        out = await scanner.scan_slice(["T00", "T01"], max_expiries=2)
    assert set(out) == {"T00", "T01"}
    assert calls == []


@pytest.mark.asyncio
async def test_full_coverage_no_starvation(fresh_budget, clean_state):
    scanned: list = []

    async def fake_fetch(ticker, max_expiries=2):
        scanned.append(ticker)
        return dict(null_chain())

    with patch(
        "services.public_api_adapter.fetch_chain_from_public_api",
        side_effect=fake_fetch,
    ):
        for _ in range(4):
            fresh_budget.reset()
            await scanner.scan_next(
                slice_size=8, max_expiries=2, universe=list(UNI10)
            )
    assert sorted(set(scanned)) == sorted(UNI10)
