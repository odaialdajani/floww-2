import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.agent.claims import claim_seed, resolve_claim
from services.agent.contracts import fact
from services.agent.repository import AgentRepository


async def saved_claim(finalized_at=None, missing_evidence=False):
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    fixture_time = datetime(2026, 9, 11, 15, tzinfo=UTC)
    with patch("services.agent.repository.utcnow", return_value=fixture_time):
        turn, _ = await repo.admit(
            "alice",
            f"{int(fixture_time.timestamp() * 1000)}-{uuid.uuid4()}",
            {"ticker": "SPY", "question": "Fixture prediction", "horizon": "all"},
        )
    seed = claim_seed(
        turn_id=turn["turn_id"],
        ticker="SPY",
        issued_at="2026-09-11T15:00:00Z",
        deadline="2026-09-11T15:01:00Z",
        reference=100,
        target=103,
        invalidation=97,
        direction="up",
        evidence=[
            fact(
                "Underlying price",
                100,
                "USD",
                ticker="SPY",
                source="fixture",
                snapshot_id="fixture",
                event_time="2026-09-11T15:00:00Z",
                received_at="2026-09-11T15:00:00Z",
            )
        ],
    )
    # Explicit frozen clock for historical fixture construction only.
    with patch("services.agent.repository.utcnow", return_value=finalized_at or fixture_time):
        await repo.finish(
            "alice",
            turn["turn_id"],
            "completed",
            answer={"facts": [] if missing_evidence else seed["evidence"]},
            claim_seed=seed,
        )
    return repo, turn, (await repo.read("alice", turn["turn_id"]))["claim_seed"]


@pytest.mark.asyncio
async def test_claim_projection_recovers_after_saved_answer_and_is_idempotent():
    repo, turn, seed = await saved_claim()
    await repo.project_claims()
    await repo.project_claims()
    assert await repo.claims.count_documents({}) == 1
    stored = await repo.claims.find_one({"claim_id": seed["claim_id"]})
    assert stored["owner"] == "alice" and stored["seed"] == seed
    assert (await repo.read("alice", turn["turn_id"]))["projection_pending"] is False


@pytest.mark.asyncio
async def test_failed_projection_keeps_committed_seed_for_restart(monkeypatch):
    repo, turn, seed = await saved_claim()
    original = repo.claims.update_one
    monkeypatch.setattr(repo.claims, "update_one", AsyncMock(side_effect=RuntimeError("offline fixture")))
    with pytest.raises(RuntimeError):
        await repo.project_claims()
    assert (await repo.read("alice", turn["turn_id"]))["projection_pending"] is True
    monkeypatch.setattr(repo.claims, "update_one", original)
    await repo.initialize()
    assert await repo.claims.count_documents({"claim_id": seed["claim_id"]}) == 1


@pytest.mark.asyncio
async def test_repeated_open_gap_advances_schedule_without_creating_versions():
    repo, _, seed = await saved_claim()
    await repo.project_claims()
    for now in ("2026-09-11T15:00:10Z", "2026-09-11T15:00:20Z"):
        await repo.record_claim_path("alice", seed["claim_id"], [], now=now, source_available=False)
    doc = await repo.claims.find_one({"claim_id": seed["claim_id"]})
    assert doc["version"] == 1
    assert doc["next_due"].replace(tzinfo=UTC) == datetime(2026, 9, 11, 15, 15, 20, tzinfo=UTC)


@pytest.mark.asyncio
async def test_finalization_reissues_backdated_seed_and_refuses_elapsed_event_or_missing_ledger():
    _, _, seed = await saved_claim(datetime(2026, 9, 11, 15, 0, 30, tzinfo=UTC))
    assert seed["issued_at"] == "2026-09-11T15:00:30+00:00"
    with pytest.raises(ValueError):
        await saved_claim(datetime(2026, 9, 11, 15, 2, tzinfo=UTC))
    with pytest.raises(ValueError):
        await saved_claim(missing_evidence=True)


@pytest.mark.asyncio
async def test_stored_path_reproduces_digest_after_bson_roundtrip():
    from bson import BSON

    repo, _, seed = await saved_claim()
    await repo.project_claims()
    bars = [
        {
            "ticker": "SPY",
            "source": "fixture",
            "start": datetime(2026, 9, 11, 15, tzinfo=UTC),
            "end": datetime(2026, 9, 11, 15, 1, tzinfo=UTC),
            "open": 100,
            "close": 100,
            "high": 104,
            "low": 98,
        }
    ]
    result = await repo.record_claim_path("alice", seed["claim_id"], bars, now="2026-09-11T15:02:00Z")
    stored = await repo.claim_paths.find_one({"claim_id": seed["claim_id"]})
    recovered = BSON.encode(stored).decode()
    replay = resolve_claim(seed, recovered["bars"], now="2026-09-11T15:02:00Z")
    assert replay["path_digest"] == result["path_digest"] and replay["status"] == result["status"]


@pytest.mark.asyncio
async def test_duplicate_poll_cannot_block_inflight_new_correction(monkeypatch):
    repo, _, seed = await saved_claim()
    await repo.project_claims()
    bars = [
        {
            "ticker": "SPY",
            "source": "fixture",
            "start": "2026-09-11T15:00:00Z",
            "end": "2026-09-11T15:01:00Z",
            "open": 100,
            "close": 100,
            "high": 104,
            "low": 98,
        }
    ]
    await repo.record_claim_path("alice", seed["claim_id"], bars, now="2026-09-11T15:03:00Z")
    inserted, release = asyncio.Event(), asyncio.Event()
    original = repo.claim_paths.find_one

    async def delayed(*args, **kwargs):
        value = await original(*args, **kwargs)
        if value and value["resolution"]["status"] == "ambiguous":
            inserted.set()
            await release.wait()
        return value

    monkeypatch.setattr(repo.claim_paths, "find_one", delayed)
    correction = asyncio.create_task(
        repo.record_claim_path("alice", seed["claim_id"], [{**bars[0], "low": 96}], now="2026-09-11T15:05:00Z")
    )
    await asyncio.wait_for(inserted.wait(), 1)
    await repo.record_claim_path("alice", seed["claim_id"], bars, now="2026-09-11T15:06:00Z")
    release.set()
    await correction
    assert (await repo.claims.find_one({"claim_id": seed["claim_id"]}))["status"] == "ambiguous"


@pytest.mark.asyncio
async def test_missing_path_is_honest_and_corrected_resolutions_are_preserved():
    repo, _, seed = await saved_claim()
    await repo.project_claims()
    claim_id = seed["claim_id"]
    missing = await repo.record_claim_path("alice", claim_id, [], now="2026-09-11T15:02:00Z", source_available=False)
    assert missing["status"] == "missing_data"
    bars = [
        {
            "ticker": "SPY",
            "source": "fixture",
            "start": "2026-09-11T15:00:00Z",
            "end": "2026-09-11T15:01:00Z",
            "open": 100,
            "close": 100,
            "high": 104,
            "low": 98,
        }
    ]
    win = await repo.record_claim_path("alice", claim_id, bars, now="2026-09-11T15:03:00Z")
    assert win["status"] == "win"
    await repo.record_claim_path("alice", claim_id, bars, now="2026-09-11T15:04:00Z")
    corrected = await repo.record_claim_path("alice", claim_id, [{**bars[0], "low": 96}], now="2026-09-11T15:05:00Z")
    assert corrected["status"] == "ambiguous"
    await repo.record_claim_path("alice", claim_id, bars, now="2026-09-11T15:06:00Z")
    assert (await repo.claims.find_one({"claim_id": claim_id}))["status"] == "ambiguous"
    assert await repo.claim_paths.count_documents({"owner": "alice", "claim_id": claim_id}) == 3
    with pytest.raises(ValueError):
        await repo.record_claim_path("bob", claim_id, bars, now="2026-09-11T15:06:00Z")
