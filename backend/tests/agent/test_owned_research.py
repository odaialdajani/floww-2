import asyncio
import time
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from routes.agent import router
from services.agent.local_access import AgentCORSMiddleware
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService


@pytest.mark.asyncio
async def test_open_observer_stops_after_session_revocation(monkeypatch):
    from starlette.requests import Request

    from routes.agent import stream
    from services.agent.local_access import COOKIE

    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    repo, service = await setup()
    who, token = await repo.session()
    turn, _ = await repo.admit(who, identity(), {"ticker": "SPY", "horizon": "all", "question": "Private"})
    await repo.progress(who, turn["turn_id"], "Private progress")
    app = FastAPI()
    app.state.research_service = service
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/api/agent/stream/" + turn["turn_id"],
            "query_string": b"",
            "headers": [(b"host", b"localhost:8000"), (b"cookie", f"{COOKIE}={token}".encode())],
            "client": ("127.0.0.1", 123),
            "server": ("localhost", 8000),
            "app": app,
        }
    )

    async def connected():
        return False

    request.is_disconnected = connected
    response = await stream(turn["turn_id"], request)
    iterator = response.body_iterator
    assert await anext(iterator)
    await repo.revoke_session(token)
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)


def identity():
    return f"{int(time.time() * 1000)}-{uuid.uuid4()}"


async def setup():
    repo = AgentRepository(AsyncMongoMockClient()["test"])
    await repo.initialize()
    reads = ResearchReads(lambda *a: None, lambda *a: None, lambda *a: [])
    service = ResearchService(repo, reads)
    return repo, service


@pytest.mark.asyncio
async def test_slow_maintenance_is_single_tracked_task_and_shutdown_cancels_it():
    _, service = await setup()
    entered = asyncio.Event()

    async def slow():
        entered.set()
        await asyncio.Event().wait()

    service.maintenance = slow
    first = service.schedule_maintenance()
    await asyncio.wait_for(entered.wait(), 1)
    assert service.schedule_maintenance() is first
    assert not first.done()
    await service.close()
    assert first.cancelled()


@pytest.mark.asyncio
async def test_rotation_logout_and_recovery_keep_history_private():
    repo, _ = await setup()
    identity_owner, token = await repo.session()
    await repo.admit(identity_owner, identity(), {"ticker": "SPY", "question": "Saved question", "horizon": "all"})
    same_owner, rotated = await repo.rotate_session(token)
    assert same_owner == identity_owner and token != rotated
    assert await repo.owner(token) is None
    assert await repo.owner(rotated) == identity_owner
    await repo.revoke_session(rotated)
    assert await repo.owner(rotated) is None
    recovered = await repo.recover_session(identity_owner)
    assert await repo.owner(recovered) == identity_owner
    with pytest.raises(ValueError):
        await repo.recover_session(str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_server_key_is_required_for_budget_and_owner_recovery(monkeypatch):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    monkeypatch.setenv("API_SECRET_KEY", "fixture-only-key")
    repo, service = await setup()
    identity_owner, _ = await repo.session()
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(AgentCORSMiddleware)
    app.state.research_service = service
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 123)),
        base_url="http://localhost:8000",
        headers={"Origin": "http://localhost:3000"},
    ) as client:
        preflight = await client.options(
            "/api/agent/session/recover",
            headers={
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-api-key",
            },
        )
        assert preflight.status_code == 204
        assert "x-api-key" in preflight.headers["access-control-allow-headers"].lower()
        assert (await client.get("/api/agent/budget")).status_code == 401
        assert (await client.post("/api/agent/session/recover", json={"owner": identity_owner})).status_code == 401
        recovery = await client.post(
            "/api/agent/session/recover", json={"owner": identity_owner}, headers={"X-API-Key": "fixture-only-key"}
        )
        assert recovery.status_code == 200
        assert (await client.get("/api/agent/history")).status_code == 200


@pytest.mark.asyncio
async def test_restart_marks_unfinished_and_replays_final_event_without_work():
    repo, _ = await setup()
    spec = {
        "ticker": "SPY",
        "tickers": ["SPY"],
        "horizon": "all",
        "screen": {},
        "context_conflict": False,
        "question": "Explain",
    }
    original, _ = await repo.admit("alice", identity(), spec)
    await repo.progress("alice", original["turn_id"], "started")
    await repo.initialize()
    recovered = await repo.read("alice", original["turn_id"])
    assert recovered["status"] == "interrupted"
    assert recovered["events"][-1]["type"] == "error"
    assert recovered["events"][-1]["id"] == 2
    await repo.initialize()
    assert (await repo.read("alice", original["turn_id"]))["events"] == recovered["events"]


@pytest.mark.asyncio
async def test_queue_bound_replay_and_queued_cancellation():
    repo, original_service = await setup()
    waiting = asyncio.Event()

    class SlowReads:
        async def snapshot(self, *args, **kwargs):
            await waiting.wait()
            return await original_service.reads.snapshot(*args, **kwargs)

    service = ResearchService(repo, SlowReads(), concurrent=1, queued=1)
    spec = {
        "ticker": "SPY",
        "tickers": ["SPY"],
        "horizon": "all",
        "screen": {},
        "context_conflict": False,
        "question": "Explain",
    }
    first_id = identity()
    first = await service.ask("alice", first_id, spec)
    second = await service.ask("alice", identity(), spec)
    with pytest.raises(OverflowError):
        await service.ask("alice", identity(), spec)
    assert (await service.ask("alice", first_id, spec))["turn_id"] == first["turn_id"]
    cancelled = await service.cancel("alice", second["turn_id"])
    assert cancelled["status"] == "cancelled"
    waiting.set()
    await asyncio.gather(*list(service.tasks.values()), return_exceptions=True)
    assert (await repo.read("alice", second["turn_id"]))["answer"] is None
    assert (await repo.read("alice", first["turn_id"]))["status"] == "completed"


@pytest.mark.asyncio
async def test_failed_final_save_never_publishes_a_completed_answer(monkeypatch):
    repo, service = await setup()
    real_finish = repo.finish

    async def fail_completion(owner, turn_id, status, **kwargs):
        if status == "completed":
            raise RuntimeError("fixture save failure")
        return await real_finish(owner, turn_id, status, **kwargs)

    monkeypatch.setattr(repo, "finish", fail_completion)
    spec = {
        "ticker": "SPY",
        "tickers": ["SPY"],
        "horizon": "all",
        "screen": {},
        "context_conflict": False,
        "question": "Explain",
    }
    turn = await service.ask("alice", identity(), spec)
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repo.read("alice", turn["turn_id"])
    assert saved["status"] == "failed" and saved["answer"] is None
    assert all(event["type"] != "done" for event in saved["events"])


@pytest.mark.asyncio
async def test_owner_idempotency_conflict_and_expired_identity():
    repo, service = await setup()
    spec = {
        "ticker": "SPY",
        "tickers": ["SPY"],
        "horizon": "all",
        "screen": {},
        "context_conflict": False,
        "question": "Explain",
    }
    request_id = identity()
    a, b = await asyncio.gather(service.ask("alice", request_id, spec), service.ask("alice", request_id, spec))
    assert a["turn_id"] == b["turn_id"]
    with pytest.raises(ValueError):
        await service.ask("alice", request_id, {**spec, "question": "Other"})
    assert await repo.read("bob", a["turn_id"]) is None
    with pytest.raises(ValueError):
        await service.ask("alice", f"1000000000000-{uuid.uuid4()}", spec)
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repo.read("alice", a["turn_id"])
    assert saved["status"] == "completed"
    assert saved["answer"]["facts"]
    assert not await repo.finish("alice", a["turn_id"], "cancelled")
    assert (await repo.read("alice", a["turn_id"]))["answer"] == saved["answer"]


@pytest.mark.asyncio
async def test_disabling_new_research_preserves_history_replay_and_logout(monkeypatch):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    monkeypatch.delenv("FLOWW_AGENT_DISABLED", raising=False)
    repo, service = await setup()
    app = FastAPI()
    app.include_router(router)
    app.state.research_service = service
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 123)),
        base_url="http://localhost:8000",
        headers={"Origin": "http://localhost:3000"},
    ) as client:
        assert (await client.post("/api/agent/session")).status_code == 200
        response = await client.post("/api/agent/ask", json={"question": "SPY structure", "request_id": identity()})
        turn_id = response.json()["turn_id"]
        await asyncio.gather(*list(service.tasks.values()))
        monkeypatch.setenv("FLOWW_AGENT_DISABLED", "1")
        assert (
            await client.post("/api/agent/ask", json={"question": "SPY structure", "request_id": identity()})
        ).status_code == 503
        history = await client.get("/api/agent/history")
        assert history.status_code == 200
        assert [turn["turn_id"] for turn in history.json()["turns"]] == [turn_id]
        assert (await client.get(f"/api/agent/turn/{turn_id}")).json()["status"] == "completed"
        assert "event: done" in (await client.get(f"/api/agent/stream/{turn_id}")).text
        assert not service.tasks
        assert (await client.post("/api/agent/session/logout")).status_code == 200
        assert (await client.get("/api/agent/history")).status_code == 401
        assert await repo.turns.count_documents({}) == 1


@pytest.mark.asyncio
async def test_transport_starts_on_post_and_stream_replay_does_not_repeat(monkeypatch):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    repo, service = await setup()
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(AgentCORSMiddleware)
    app.state.research_service = service
    transport = ASGITransport(app=app, client=("127.0.0.1", 123))
    async with AsyncClient(
        transport=transport, base_url="http://localhost:8000", headers={"Origin": "http://localhost:3000"}
    ) as client:
        session = await client.post("/api/agent/session")
        assert session.status_code == 200
        assert "httponly" in session.headers["set-cookie"].lower()
        response = await client.post("/api/agent/ask", json={"question": "SPY structure", "request_id": identity()})
        assert response.status_code == 200
        turn_id = response.json()["turn_id"]
        await asyncio.gather(*list(service.tasks.values()))
        turn = (await client.get(f"/api/agent/turn/{turn_id}")).json()
        assert turn["status"] == "completed"
        assert "owner" not in turn
        events = await client.get(f"/api/agent/stream/{turn_id}")
        assert "event: done" in events.text
        replay = await client.get(
            f"/api/agent/stream/{turn_id}", headers={"Last-Event-ID": str(turn["events"][-1]["id"])}
        )
        assert replay.text == ""
        assert not service.tasks
        denied = await client.post("/api/agent/session", headers={"X-Forwarded-For": "10.0.0.1"})
        assert denied.status_code == 403
        cors = await client.options("/api/agent/ask", headers={"Access-Control-Request-Method": "POST"})
        assert cors.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert cors.headers["access-control-allow-credentials"] == "true"
