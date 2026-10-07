"""Additional serial requests spend tokens without taking another admitted job slot."""
import pytest

from services.public_budget import BudgetExhausted, PublicBudget


@pytest.mark.asyncio
async def test_extra_debit_preserves_four_job_limit():
    budget = PublicBudget(capacity=20, refill_per_sec=0, max_inflight=4)
    for _ in range(4):
        await budget.acquire_n(3, "api.public.com", now=1000)
    await budget.debit_additional(1, "api.public.com", now=1000)
    assert budget._inflight == 4
    assert await budget.peek_available(now=1000) == 7
    with pytest.raises(BudgetExhausted) as exc:
        await budget.acquire_n(1, "api.public.com", now=1000)
    assert exc.value.reason == "inflight_cap"
    for _ in range(4):
        budget.release()
    assert budget._inflight == 0
    assert await budget.peek_available(now=1000) == 7


@pytest.mark.asyncio
async def test_extra_debit_requires_existing_admission():
    budget = PublicBudget(capacity=20, refill_per_sec=0)
    with pytest.raises(BudgetExhausted) as exc:
        await budget.debit_additional(1, "api.public.com", now=1000)
    assert exc.value.reason == "missing_job_admission"
    assert budget._inflight == 0
    assert await budget.peek_available(now=1000) == 20


@pytest.mark.asyncio
async def test_extra_debit_refuses_insufficient_tokens_atomically():
    budget = PublicBudget(capacity=3, refill_per_sec=0)
    await budget.acquire_n(3, "api.public.com", now=1000)
    with pytest.raises(BudgetExhausted) as exc:
        await budget.debit_additional(1, "api.public.com", now=1000)
    assert exc.value.reason == "token_bucket"
    assert budget._inflight == 1
    assert await budget.peek_available(now=1000) == 0
    budget.release()
    assert budget._inflight == 0


@pytest.mark.asyncio
async def test_extra_debit_honors_cooldown_without_refunding_or_changing_slots():
    budget = PublicBudget(capacity=10, refill_per_sec=0)
    await budget.acquire_n(3, "api.public.com", now=1000)
    budget.record_429("api.public.com", now=1000)
    with pytest.raises(BudgetExhausted) as exc:
        await budget.debit_additional(1, "api.public.com", now=1001)
    assert exc.value.reason == "host_cooldown"
    assert budget._inflight == 1
    assert await budget.peek_available(now=1001) == 7
    budget.release()
