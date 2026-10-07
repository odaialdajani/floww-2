"""Owned history listing stays small and stable across ties and new answers."""
import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from routes.agent import router
from services.agent.local_access import COOKIE
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService

BASE = datetime(2026, 10, 1, 15, tzinfo=UTC)


def turn_identity(index):
    return f"{index:08x}-0000-4000-8000-000000000000"


async def store_turn(repo, owner, index, *, created_at=BASE, status="completed", saved=True):
    document = {"turn_id": turn_identity(index), "owner": owner, "created_at": created_at,
                "updated_at": created_at + timedelta(seconds=1), "ticker": "SPY", "horizon": "all",
                "question": f"{owner} saved question {index}", "status": status, "saved": saved,
                "digest": "private digest", "request_id": "private request",
                "spec": {"private_selection": "must not appear in list"},
                "events": [{"type": "progress", "message": "private progress"}],
                "answer": {"summary": "Recorded explanation " + "x" * 10000,
                           "facts": [{"private_fact": "must not appear in list"}]},
                "read_activity": {"attempts": ["private attempt"]}}
    await repo.turns.insert_one(document)
    return document


@pytest.mark.asyncio
async def test_history_pages_preserve_every_owned_tie_without_duplicate_or_foreign_answers():
    repo = AgentRepository(AsyncMongoMockClient().test)
    for index in range(1, 68):
        await store_turn(repo, "alice", index)
    for index in range(200, 240):
        await store_turn(repo, "bob", index, created_at=BASE + timedelta(days=1))
    first = await repo.history_page("alice", limit=20)
    assert first["has_more"] is True and isinstance(first["next_cursor"], str)
    assert len(first["turns"]) == 20
    assert [row["turn_id"] for row in first["turns"]] == [turn_identity(index) for index in range(67, 47, -1)]
    # Newer questions, including an equal-clock answer, cannot shift the next page.
    await store_turn(repo, "alice", 100, created_at=BASE + timedelta(seconds=1))
    await store_turn(repo, "alice", 99)
    rows = list(first["turns"])
    cursor = first["next_cursor"]
    while cursor is not None:
        page = await repo.history_page("alice", limit=20, cursor=cursor)
        assert len(page["turns"]) <= 20
        rows.extend(page["turns"])
        assert page["has_more"] is (page["next_cursor"] is not None)
        cursor = page["next_cursor"]
    assert [row["turn_id"] for row in rows] == [turn_identity(index) for index in range(67, 0, -1)]
    assert len({row["turn_id"] for row in rows}) == 67
    assert "bob" not in json.dumps(rows, default=str)


@pytest.mark.asyncio
async def test_paged_summary_preserves_state_but_does_not_load_answer_details():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await store_turn(repo, "alice", 1, status="cancelled", saved=False)
    page = await repo.history_page("alice")
    row = page["turns"][0]
    assert row["saved"] is False and row["status"] == "cancelled"
    assert {"turn_id", "ticker", "horizon", "question", "status", "saved", "created_at", "updated_at"} <= set(row)
    assert not {"answer", "facts", "spec", "events", "read_activity", "owner", "digest", "request_id", "_id"} & set(row)
    assert page["next_cursor"] is None and page["has_more"] is False
    if "preview" in row:
        assert isinstance(row["preview"], str) and len(row["preview"]) <= 280
    full = await repo.read("alice", row["turn_id"])
    assert full["answer"]["facts"]
    assert await repo.read("bob", row["turn_id"]) is None
    assert len(await repo.history("alice")) == 1
    assert (await repo.history("alice"))[0]["answer"] == full["answer"]


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 31, True, "20"])
async def test_repository_rejects_nonbounded_page_sizes(limit):
    repo = AgentRepository(AsyncMongoMockClient().test)
    with pytest.raises(ValueError):
        await repo.history_page("alice", limit=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", ["", "not-a-cursor", "a" * 1000, "e30", "eyJ2IjoxfQ", 3])
async def test_repository_strictly_rejects_invalid_cursor_values(cursor):
    repo = AgentRepository(AsyncMongoMockClient().test)
    with pytest.raises(ValueError, match="[Cc]ursor"):
        await repo.history_page("alice", cursor=cursor)


@pytest.mark.asyncio
async def test_cursor_is_anchored_to_exact_owner_and_saved_clock():
    repo = AgentRepository(AsyncMongoMockClient().test)
    for owner, base_index in (("alice", 10), ("bob", 30)):
        for offset in range(3):
            await store_turn(repo, owner, base_index + offset)
    page = await repo.history_page("alice", limit=1)
    cursor = page["next_cursor"]
    with pytest.raises(ValueError, match="[Cc]ursor"):
        await repo.history_page("bob", cursor=cursor)
    # Keep the real turn identity but alter its timestamp in otherwise valid JSON.
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    def change_clock(value):
        if isinstance(value, dict):
            return {key: change_clock(item) for key, item in value.items()}
        if isinstance(value, list):
            return [change_clock(item) for item in value]
        if isinstance(value, str) and value.startswith("2026-") and "T" in value:
            return "2025-" + value[5:]
        return value
    tampered = base64.urlsafe_b64encode(json.dumps(change_clock(payload), sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
    with pytest.raises(ValueError, match="[Cc]ursor"):
        await repo.history_page("alice", cursor=tampered)
    # A padded spelling of the same token is noncanonical.
    with pytest.raises(ValueError, match="[Cc]ursor"):
        await repo.history_page("alice", cursor=cursor + "=")


@pytest.mark.asyncio
async def test_trusted_naive_mongo_created_times_can_page_without_becoming_market_times():
    repo = AgentRepository(AsyncMongoMockClient().test)
    naive = BASE.replace(tzinfo=None)
    await store_turn(repo, "alice", 1, created_at=naive)
    await store_turn(repo, "alice", 2, created_at=naive)
    first = await repo.history_page("alice", limit=1)
    second = await repo.history_page("alice", limit=1, cursor=first["next_cursor"])
    assert [first["turns"][0]["turn_id"], second["turns"][0]["turn_id"]] == [turn_identity(2), turn_identity(1)]
    assert "event_time" not in first["turns"][0]
    assert first["turns"][0]["created_at"].tzinfo is not None
    assert first["turns"][0]["updated_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_additive_history_page_route_preserves_owner_and_legacy_route(monkeypatch):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    repo = AgentRepository(AsyncMongoMockClient().test)
    identity, token = await repo.session()
    for index in range(1, 35):
        await store_turn(repo, identity, index)
    await store_turn(repo, "bob", 100)
    app = FastAPI()
    app.include_router(router)
    app.state.research_service = ResearchService(repo, None)
    async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 123)), base_url="http://localhost:8000") as client:
        assert (await client.get("/api/agent/history/page")).status_code == 401
        client.cookies.set(COOKIE, token)
        first = await client.get("/api/agent/history/page", params={"limit": 20})
        assert first.status_code == 200
        data = first.json()
        assert len(data["turns"]) == 20 and data["has_more"] is True
        assert "private_fact" not in first.text and "bob" not in first.text
        second = await client.get("/api/agent/history/page", params={"limit": 20, "cursor": data["next_cursor"]})
        assert second.status_code == 200 and len(second.json()["turns"]) == 14
        assert (await client.get("/api/agent/history/page", params={"cursor": "bad"})).status_code == 422
        assert (await client.get("/api/agent/history/page", params={"limit": 31})).status_code == 422
        legacy = await client.get("/api/agent/history")
        assert legacy.status_code == 200 and len(legacy.json()["turns"]) == 30
        assert legacy.json()["turns"][0]["answer"]["facts"]
        opened = await client.get("/api/agent/turn/" + data["turns"][0]["turn_id"])
        assert opened.status_code == 200 and opened.json()["answer"]["facts"]


@pytest.mark.asyncio
async def test_paged_listing_applies_bounded_database_cursor_deadline():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await store_turn(repo, "alice", 1)
    original = repo.turns
    class Cursor:
        def __init__(self, inner):
            self.inner, self.deadline = inner, None
        def sort(self, *args):
            self.inner = self.inner.sort(*args)
            return self
        def limit(self, amount):
            assert 1 <= amount <= 31
            self.inner = self.inner.limit(amount)
            return self
        def max_time_ms(self, amount):
            self.deadline = amount
            return self
        async def to_list(self, *, length):
            assert type(self.deadline) is int and 0 < self.deadline <= 2000
            return await self.inner.to_list(length=length)
    class Collection:
        def find(self, *args, **kwargs):
            return Cursor(original.find(*args, **kwargs))
    repo.turns = Collection()
    page = await repo.history_page("alice", limit=20)
    assert len(page["turns"]) == 1 and page["has_more"] is False
