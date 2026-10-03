"""Authenticated private handoff history is reporting, not trading permission."""


import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from routes.agent import router
from services.agent.local_access import COOKIE
from tests.agent.test_owned_research import identity, setup


@pytest.mark.asyncio
async def test_native_handoff_is_private_context_bound_and_never_approval(monkeypatch):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    repo, service = await setup()
    alice, alice_token = await repo.session()
    bob, bob_token = await repo.session()
    turn, _ = await repo.admit(alice, identity(), {"ticker": "SPY", "horizon": "all", "question": "Research"})
    draft = {"version": "trade-plan-draft.v1", "draft_id": "draft-1", "context_hash": "a" * 64,
             "contract": {"osi": "SPY261002C00500000"}, "executable": False}
    await repo.finish(alice, turn["turn_id"], "completed", answer={"plan_draft": draft})
    app = FastAPI()
    app.include_router(router)
    app.state.research_service = service
    body = {"turn_id": turn["turn_id"], "context_hash": draft["context_hash"],
            "execution_owner": "PUBLIC_NATIVE_AGENT", "brief": "Review this dated research. Do not activate.",
            "workflow_reference": "builder-reference", "reported_status": "reviewed"}
    async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 123)),
                           base_url="http://localhost:8000", headers={"Origin": "http://localhost:3000"}) as client:

        client.cookies.set(COOKIE, alice_token)
        response = await client.post("/api/agent/handoffs", json=body)
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["version"] == "native-handoff.v1" and saved["broker_verified"] is False
        assert saved["activation"] == "unverified" and saved["approval"] is None
        assert saved["workflow_reference"] == "builder-reference"
        assert "owner" not in saved and "_id" not in saved
        duplicate = await client.post("/api/agent/handoffs", json=body)
        assert duplicate.json()["handoff_id"] == saved["handoff_id"]
        history = (await client.get("/api/agent/handoffs")).json()["handoffs"]
        assert len(history) == 1
        assert (await client.post("/api/agent/handoffs", json={**body, "context_hash": "b" * 64})).status_code == 409
        assert (await client.post("/api/agent/handoffs", json={**body, "approved": True})).status_code == 422
        assert (await client.post("/api/agent/handoffs", json={**body, "execution_owner": "FLOWW_BACKEND"})).status_code == 422
        client.cookies.clear()
        client.cookies.set(COOKIE, bob_token)
        assert (await client.get("/api/agent/handoffs")).json() == {"handoffs": []}
        assert (await client.post("/api/agent/handoffs", json=body)).status_code == 404
        await repo.revoke_session(bob_token)
        assert (await client.get("/api/agent/handoffs")).status_code == 401
    assert (await repo.read(alice, turn["turn_id"]))["answer"]["plan_draft"] == draft
