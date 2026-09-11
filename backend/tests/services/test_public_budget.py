"""
Tests for services/public_budget.py (Phase 9 rate-limit shield).

Fake-clock driven: no sleeps, no network. Pins the contract Agent 3's
proposal packet specified: burst cap, 429 cooldown + jitter ceiling,
refill, and status shape.
"""
from __future__ import annotations

import asyncio

import pytest

from services.public_budget import BudgetExhausted, PublicBudget


def _budget(**kw) -> PublicBudget:
    return PublicBudget(capacity=kw.get("capacity", 60),
                        refill_per_sec=kw.get("refill_per_sec", 1.0),
                        max_inflight=kw.get("max_inflight", 4))


@pytest.mark.asyncio
async def test_acquire_and_release_cycle():
    b = _budget()
    await b.acquire(host="h", now=1000.0)
    assert b.status(now=1000.0)["inflight"] == 1
    b.release()
    assert b.status(now=1000.0)["inflight"] == 0
    b.release()  # floor at zero, never negative
    assert b.status(now=1000.0)["inflight"] == 0


@pytest.mark.asyncio
async def test_burst_capped_by_inflight():
    b = _budget(max_inflight=4)
    for _ in range(4):
        await b.acquire(host="h", now=1000.0)
    with pytest.raises(BudgetExhausted) as exc:
        await b.acquire(host="h", now=1000.0)
    assert exc.value.reason == "inflight_cap"
    assert exc.value.retry_after > 0


@pytest.mark.asyncio
async def test_token_bucket_exhaustion_and_refill():
    b = _budget(capacity=2, refill_per_sec=1.0, max_inflight=99)
    await b.acquire(host="h", now=1000.0)
    await b.acquire(host="h", now=1000.0)
    b.release()
    b.release()
    with pytest.raises(BudgetExhausted) as exc:
        await b.acquire(host="h", now=1000.0)
    assert exc.value.reason == "token_bucket"
    # +1.5s refills 1.5 tokens -> next acquire succeeds.
    await b.acquire(host="h", now=1001.5)
    assert b.status(now=1001.5)["available"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_429_cooldown_backoff_and_ok_clears():
    b = _budget()
    first = b.record_429("api.public.com", now=1000.0)
    assert 15 <= first <= 20  # base 15s + jitter<=5
    with pytest.raises(BudgetExhausted) as exc:
        await b.acquire(host="api.public.com", now=1001.0)
    assert exc.value.reason == "host_cooldown"
    # Second 429 while cooling doubles the backoff (capped at 300s).
    second = b.record_429("api.public.com", now=1001.0)
    assert second > first
    # Success clears the cooldown.
    b.record_ok("api.public.com")
    await b.acquire(host="api.public.com", now=1002.0)


@pytest.mark.asyncio
async def test_cooldown_expires_on_its_own():
    b = _budget()
    b.record_429("h", now=1000.0)
    await b.acquire(host="h", now=1000.0 + 400.0)


@pytest.mark.asyncio
async def test_status_shape():
    b = _budget()
    await b.acquire(host="h", now=1000.0)
    s = b.status(now=1000.0)
    assert set(s) >= {"capacity", "available", "inflight", "max_inflight",
                      "cooldowns", "totals"}
    assert set(s["totals"]) >= {"ok", "limited", "rate_limited_429"}


@pytest.mark.asyncio
async def test_coordinator_degrades_on_budget_exhaustion():
    """FetchCoordinator refuses BEFORE creating the upstream task."""
    from services import public_budget as pb_mod
    from services.fetch_coordinator import FetchCoordinator

    coord = FetchCoordinator()
    calls = {"n": 0}

    async def fetcher(ticker, expiries):
        calls["n"] += 1
        return {"spot": 1.0, "contracts": []}

    real_acquire = pb_mod.budget.acquire

    async def always_refuse(host="public", now=None):
        raise pb_mod.BudgetExhausted(retry_after=9)

    pb_mod.budget.acquire = always_refuse
    try:
        out = await coord.fetch("SPY", 4, fetcher)
    finally:
        pb_mod.budget.acquire = real_acquire
    assert out["status"] == "degraded"
    assert out["reason"] == "budget_exhausted"
    assert out["retry_after"] == 9
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_coordinator_releases_slot_after_fetch():
    from services import public_budget as pb_mod
    from services.fetch_coordinator import FetchCoordinator

    # Fresh budget so counts are deterministic.
    fresh = PublicBudget()
    old = pb_mod.budget
    pb_mod.budget = fresh
    try:
        coord = FetchCoordinator()

        async def fetcher(ticker, expiries):
            return {"spot": 1.0, "contracts": [{"strike": 1}],
                    "ticker": ticker}

        await coord.fetch("SPY", 4, fetcher)
        assert fresh.status()["inflight"] == 0
    finally:
        pb_mod.budget = old
