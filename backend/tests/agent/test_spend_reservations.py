import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.spend import SpendLedger


@pytest.mark.asyncio
async def test_projection_reclaims_capacity_without_losing_duplicate_protection():
    database = AsyncMongoMockClient().test
    ledger = SpendLedger(database.budget, cap_units=100, maximum_entries=1, audit_collection=database.audit)
    await ledger.initialize()
    key = str(uuid.uuid4())
    assert await ledger.reserve(key, 40, "one")
    await ledger.dispatch(key)
    await ledger.settle(key, 30, "generation-first")
    assert await ledger.project_terminal() == 1
    assert await ledger.project_terminal() == 0
    assert not await ledger.settle(key, 30, "generation-first")
    assert not await ledger.reserve(key, 40, "one")
    next_key = str(uuid.uuid4())
    assert await ledger.reserve(next_key, 40, "two")
    await ledger.dispatch(next_key)
    with pytest.raises(ValueError):
        await ledger.settle(next_key, 30, "generation-first")
    assert (await ledger.state())["spent_units"] == 30


@pytest.mark.asyncio
async def test_restart_releases_only_provably_undispatched_work():
    ledger = SpendLedger(AsyncMongoMockClient().test.budget, cap_units=100)
    await ledger.initialize()
    unsent, uncertain = str(uuid.uuid4()), str(uuid.uuid4())
    assert await ledger.reserve(unsent, 30, "one")
    assert await ledger.reserve(uncertain, 40, "two")
    await ledger.dispatch(uncertain)
    assert await ledger.recover_undispatched() == 1
    assert await ledger.recover_undispatched() == 0
    assert (await ledger.state())["reserved_units"] == 40


@pytest.mark.asyncio
async def test_dispatch_after_midnight_charges_dispatch_day():
    now = [datetime(2026, 9, 12, 3, 59, tzinfo=UTC)]
    ledger = SpendLedger(AsyncMongoMockClient().test.budget, cap_units=100, clock=lambda: now[0])
    await ledger.initialize()
    key = str(uuid.uuid4())
    assert await ledger.reserve(key, 80, "turn")
    now[0] += timedelta(minutes=2)
    assert await ledger.dispatch(key)
    assert await ledger.settle(key, 75, "after-midnight")
    assert (await ledger.state())["remaining_units"] == 25


@pytest.mark.asyncio
async def test_race_last_allowance_unknown_cost_midnight_and_duplicate_settlement():
    now = [datetime(2026, 9, 11, 20, tzinfo=UTC)]
    ledger = SpendLedger(AsyncMongoMockClient().test.budget, cap_units=100, clock=lambda: now[0])
    await ledger.initialize()
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    accepted = await asyncio.gather(*(ledger.reserve(key, 80, "turn") for key in ids))
    assert sum(accepted) == 1
    key = ids[accepted.index(True)]
    assert await ledger.dispatch(key)
    assert not await ledger.dispatch(key)
    assert not await ledger.release_undispatched(key)
    now[0] += timedelta(days=2)
    assert (await ledger.state())["remaining_units"] == 20
    assert await ledger.settle(key, 60, "generation-one")
    assert not await ledger.settle(key, 60, "generation-one")
    state = await ledger.state()
    assert state["remaining_units"] == 100
    stored = await ledger.collection.find_one({"_id": "openrouter"})
    assert stored["days"]["2026-09-11"] == 60
    with pytest.raises(ValueError):
        await ledger.settle(key, 50, "generation-one")


@pytest.mark.asyncio
async def test_cap_lowered_restart_and_storage_down_do_not_reset_spend():
    collection = AsyncMongoMockClient().test.budget
    ledger = SpendLedger(collection, cap_units=100)
    await ledger.initialize()
    key = str(uuid.uuid4())
    assert await ledger.reserve(key, 80, "turn")
    await ledger.dispatch(key)
    restarted = SpendLedger(collection, cap_units=50)
    await restarted.initialize()
    assert (await restarted.state())["remaining_units"] == 0
    assert not await restarted.reserve(str(uuid.uuid4()), 1, "other")
    await collection.delete_many({})
    with pytest.raises(RuntimeError):
        await restarted.reserve(str(uuid.uuid4()), 1, "other")
