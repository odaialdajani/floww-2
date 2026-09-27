"""Fixture verification of the real-store runner, not real Mongo acceptance."""

import pytest
from mongomock_motor import AsyncMongoMockClient

from scripts.verify_agent_storage import (
    PREFIX,
    export_fixture,
    populate_and_race,
    restore_fixture,
    validate_database,
    verify_recovered,
    verify_unique_constraints,
)
from services.agent.repository import AgentRepository


@pytest.mark.parametrize("name", ["floww", "admin", "test_confluence_decoder", PREFIX + "../floww", PREFIX + "0" * 31])
def test_verification_rejects_any_non_generated_database(name):
    with pytest.raises(ValueError):
        validate_database(name)


@pytest.mark.asyncio
async def test_fixture_protocol_retains_answers_privacy_claims_and_uncertain_spend(tmp_path):
    client = AsyncMongoMockClient()
    state = await populate_and_race(client[PREFIX + "a" * 32])
    await verify_recovered(client[state["database"]], state)
    backup = tmp_path / "backup"
    manifest = await export_fixture(client[state["database"]], backup)
    restored = client[PREFIX + "b" * 32]
    await restore_fixture(restored, backup, manifest)
    await verify_recovered(restored, state)
    await verify_unique_constraints(AgentRepository(restored), state)
    assert manifest["agent_turns"]["count"] == 3
    assert await restored.agent_claims.count_documents({}) == 1
    with pytest.raises(AssertionError, match="target must be empty"):
        await restore_fixture(restored, backup, manifest)


@pytest.mark.asyncio
async def test_corrupt_backup_is_refused_before_its_records_are_restored(tmp_path):
    client = AsyncMongoMockClient()
    state = await populate_and_race(client[PREFIX + "c" * 32])
    backup = tmp_path / "backup"
    manifest = await export_fixture(client[state["database"]], backup)
    first = next(iter(manifest))
    (backup / f"{first}.bson").write_bytes(b"corrupt")
    restored = client[PREFIX + "d" * 32]
    with pytest.raises(AssertionError, match="digest differs"):
        await restore_fixture(restored, backup, manifest)
    assert not await restored.list_collection_names()
