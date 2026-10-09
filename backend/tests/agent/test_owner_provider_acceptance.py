"""Offline owner/settings acceptance; scripted RPC is not host/provider proof."""

import asyncio
import copy
import json
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

pytest.importorskip("mongomock_motor", reason="mongo mock unavailable in this env")
from mongomock_motor import AsyncMongoMockClient

from routes.agent import router
from services.agent.codex_bridge import CodexBridge
from services.agent.codex_model import DEFAULT_SETTINGS, POLICY_VERSION, CodexModel
from services.agent.local_access import COOKIE
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService
from tests.agent.test_exact_contract_admission import OSI, record, screen
from tests.offline_network import deny_external_network  # noqa: F401

SETTINGS = {"model": "gpt-6.1-sol", "effort": "xhigh", "speed": "default"}


class ScriptedProvider:
    """Run the actual bridge catalog/answer validation, replacing only RPC I/O."""

    def __init__(self):
        self.requests = []
        self.catalog_calls = 0
        self.dispatches = 0
        self.failure = None
        self.fresh_efforts = ["low", "medium", "high", "xhigh"]
        self.fresh_speeds = ["priority"]
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = 0

    def bridge(self):
        provider = self

        class Bridge(CodexBridge):
            async def __aenter__(self):
                self._temporary = SimpleNamespace(name="/offline-scripted-workspace")
                return self

            async def __aexit__(self, *_):
                provider.closed += 1

            async def request(self, method, params):
                provider.requests.append((method, copy.deepcopy(params)))
                if method == "account/read":
                    return {"account": {"type": "chatgpt"}}
                if method == "model/list":
                    provider.catalog_calls += 1
                    if provider.failure == "catalog":
                        raise RuntimeError("fixture-private-provider-detail")
                    fresh = provider.catalog_calls > 1
                    return {"data": [{
                        "model": SETTINGS["model"], "displayName": "Scripted Sol",
                        "defaultReasoningEffort": "low",
                        "supportedReasoningEfforts": [
                            {"reasoningEffort": effort}
                            for effort in (provider.fresh_efforts if fresh else ["low", "medium", "high", "xhigh"])
                        ],
                        "serviceTiers": [{"id": speed} for speed in (provider.fresh_speeds if fresh else ["priority"])],
                    }]}
                if method == "thread/start":
                    result = dict(model=params["model"], modelProvider="openai",
                                  reasoningEffort=params["config"]["model_reasoning_effort"],
                                  serviceTier=params["serviceTier"], thread={"id": "scripted-thread"})
                    if provider.failure in {"model", "effort", "speed"}:
                        result[{"model": "model", "effort": "reasoningEffort", "speed": "serviceTier"}[provider.failure]] = "different"
                    return result
                if method == "mcpServerStatus/list":
                    return {"data": []}
                if method == "turn/start":
                    provider.dispatches += 1
                    provider.entered.set()
                    if provider.failure == "cancel":
                        await provider.release.wait()
                    if provider.failure == "timeout":
                        raise TimeoutError("fixture-private-provider-detail")
                    if provider.failure == "error":
                        raise RuntimeError("fixture-private-provider-detail")
                    facts = json.loads(params["input"][0]["text"])["facts"]
                    data = {"sections": [{"name": "Structure", "fact_ids": [facts[0]["id"]],
                                          "interpretation": "limited"}], "relationships": [], "explanations": []}
                    self.events = [
                        {"method": "model/rerouted"} if provider.failure == "reroute" else
                        {"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"total": {"totalTokens": 99}}}},
                        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": json.dumps(data)}}},
                        {"method": "turn/completed", "params": {"turn": {"id": "scripted-generation", "status": "completed"}}},
                    ]
                    return {"turn": {"id": "scripted-generation"}}
                raise AssertionError(f"Unexpected offline RPC: {method}")

        return Bridge()


def request_body():
    return {"request_id": f"{int(time.time() * 1000)}-{uuid.uuid4()}",
            "question": "Explain SPY structure", "screen": screen()}


@asynccontextmanager
async def harness(monkeypatch):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    monkeypatch.delenv("FLOWW_AGENT_DISABLED", raising=False)
    db = AsyncMongoMockClient()["r18_owner_provider"]
    repo = AgentRepository(db)
    await repo.initialize()
    provider = ScriptedProvider()
    model = CodexModel(repo, db.usage, bridge_factory=provider.bridge)
    recorded = record()
    upstream = Mock(side_effect=AssertionError("Must use the owning saved record"))
    reads = ResearchReads(upstream, upstream, upstream, read_recorded_map=lambda *_: recorded)
    service = ResearchService(repo, reads, model=model)
    app = FastAPI()
    app.include_router(router)
    app.state.research_service = service
    transport = ASGITransport(app=app, client=("127.0.0.1", 123), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://localhost:8000",
                           headers={"Origin": "http://localhost:3000"}) as alice, AsyncClient(
        transport=transport, base_url="http://localhost:8000", headers={"Origin": "http://localhost:3000"}
    ) as bob:
        try:
            yield SimpleNamespace(db=db, repo=repo, model=model, provider=provider,
                                  service=service, alice=alice, bob=bob, upstream=upstream)
        finally:
            await service.close()


async def login_and_save(h):
    assert (await h.alice.post("/api/agent/session")).status_code == 200
    assert (await h.alice.put("/api/agent/prefs", json={"ai_settings": SETTINGS})).json() == {"saved": True}


async def settle(h):
    await asyncio.gather(*list(h.service.tasks.values()))


async def usage_entry(h, turn_id):
    identity = await h.db.usage.find_one({"_id": "turn:" + turn_id})
    day = await h.db.usage.find_one({"_id": "day:" + identity["day"]})
    return day["entries"][identity["request_id"]]


@pytest.mark.asyncio
async def test_authenticated_save_load_dispatch_history_and_review_only_linkage(monkeypatch):
    async with harness(monkeypatch) as h:
        for method, path, payload in [
            ("GET", "/api/agent/prefs", None), ("GET", "/api/agent/models", None),
            ("PUT", "/api/agent/prefs", {"ai_settings": SETTINGS}),
        ]:
            assert (await h.alice.request(method, path, json=payload)).status_code == 401
        assert h.provider.requests == []
        await login_and_save(h)
        assert (await h.bob.post("/api/agent/session")).status_code == 200
        assert (await h.alice.get("/api/agent/prefs")).json()["ai_settings"] == SETTINGS
        assert "ai_settings" not in (await h.bob.get("/api/agent/prefs")).json()
        assert (await h.bob.get("/api/agent/models")).json()["selected"] == DEFAULT_SETTINGS
        assert (await h.alice.get("/api/agent/models")).json()["selected"] == SETTINGS
        body = request_body()
        response = await h.alice.post("/api/agent/ask", json=body)
        assert response.status_code == 200
        turn_id = response.json()["turn_id"]
        await settle(h)
        saved = (await h.alice.get(f"/api/agent/turn/{turn_id}")).json()
        assert saved["status"] == "completed"
        assert saved["spec"]["ai_settings"] == SETTINGS
        assert "owner" not in saved
        answer = saved["answer"]
        assert answer["mode"] == "model-assisted"
        usage = answer["usage"][0]
        trace = usage["trace"]
        assert trace["requested"] == trace["effective"] == SETTINGS
        assert trace["status"] == "completed"
        assert trace["correlation_id"] == turn_id
        assert trace["tokens"] == {"total": {"totalTokens": 99}}
        assert usage["policy_version"] == trace["policy_version"] == POLICY_VERSION
        assert usage["actual_cost"] is None
        entry = await usage_entry(h, turn_id)
        assert entry["trace"] == trace
        assert entry["settings"] == SETTINGS and entry["status"] == "completed"
        assert entry["owner"] == await h.repo.owner(h.alice.cookies.get(COOKIE))
        draft = answer["plan_draft"]
        assert draft["contract"]["osi"] == OSI and draft["contract"]["snapshot_id"] == "snap1"
        assert draft["correlation_id"] == trace["correlation_id"]
        assert draft["context_hash"] == trace["context_hash"]
        assert draft["evidence_ids"] == trace["evidence_ids"]
        assert draft["observation_ids"] == trace["observation_ids"]
        assert draft["executable"] is False and draft["status"] == "review_only"
        assert draft["approval"] is draft["execution_owner"] is draft["account_id"] is None
        assert "AUTHENTICATED_INTENT_APPROVAL_REQUIRED" in draft["blockers"]
        assert "COMMISSIONING_POLICY_UNSET" in draft["blockers"]
        assert (await h.alice.get("/api/agent/history")).json()["turns"] == [saved]
        assert (await h.bob.get("/api/agent/history")).json() == {"turns": []}
        for path in (f"/api/agent/turn/{turn_id}", f"/api/agent/stream/{turn_id}"):
            assert (await h.bob.get(path)).status_code == 404
        assert (await h.bob.post(f"/api/agent/cancel/{turn_id}")).status_code == 404
        original_calls = len(h.provider.requests)
        assert "event: done" in (await h.alice.get(f"/api/agent/stream/{turn_id}")).text
        assert (await h.alice.post("/api/agent/session/rotate")).status_code == 200
        assert (await h.alice.get("/api/agent/prefs")).json()["ai_settings"] == SETTINGS
        assert len(h.provider.requests) == original_calls
        assert (await h.alice.put("/api/agent/prefs", json={"ai_settings": {**SETTINGS, "effort": "low"}})).status_code == 200
        replay = await h.alice.post("/api/agent/ask", json=body)
        assert replay.json()["turn_id"] == turn_id
        assert (await h.alice.get(f"/api/agent/turn/{turn_id}")).json() == saved
        assert h.provider.dispatches == 1 and (await h.model.spend.state())["calls"] == 1
        thread = next(params for method, params in h.provider.requests if method == "thread/start")
        turn = next(params for method, params in h.provider.requests if method == "turn/start")
        assert thread["model"] == turn["model"] == SETTINGS["model"]
        assert thread["config"]["model_reasoning_effort"] == turn["effort"] == "xhigh"
        assert thread["serviceTier"] == turn["serviceTier"] == "default"
        assert thread["approvalPolicy"] == "never" and thread["sandbox"] == "read-only"
        assert thread["dynamicTools"] == thread["environments"] == []
        assert json.loads(turn["input"][0]["text"])["facts"] == answer["facts"]
        h.upstream.assert_not_called()
        assert (await h.alice.post("/api/agent/session/logout")).status_code == 200
        assert (await h.alice.get("/api/agent/prefs")).status_code == 401
        assert (await h.alice.get("/api/agent/history")).status_code == 401
        assert (await h.alice.get("/api/agent/models")).status_code == 401
        assert (await h.alice.put("/api/agent/prefs", json={"ai_settings": SETTINGS})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("setting", [{**SETTINGS, "model": "GPT-6.1-Sol"}, {**SETTINGS, "effort": "max"},
                                     {**SETTINGS, "speed": "fast"}])
async def test_unsupported_exact_selection_does_not_overwrite_owner_preferences(monkeypatch, setting):
    async with harness(monkeypatch) as h:
        await login_and_save(h)
        assert (await h.alice.put("/api/agent/prefs", json={"ai_settings": setting})).status_code == 422
        assert (await h.alice.get("/api/agent/prefs")).json()["ai_settings"] == SETTINGS
        assert h.provider.dispatches == 0 and (await h.model.spend.state())["calls"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/agent/prefs", "/api/agent/models"])
async def test_catalog_failure_is_sanitized_unavailable_and_preserves_saved_settings(monkeypatch, path):
    async with harness(monkeypatch) as h:
        await login_and_save(h)
        h.model._catalog = None
        h.provider.failure = "catalog"
        response = await (h.alice.put(path, json={"ai_settings": SETTINGS}) if path.endswith("prefs") else h.alice.get(path))
        assert response.status_code == 503
        assert "fixture-private-provider-detail" not in response.text
        assert (await h.alice.get("/api/agent/prefs")).json()["ai_settings"] == SETTINGS
        assert (await h.model.spend.state())["calls"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawn", ["effort", "speed"])
async def test_fresh_catalog_withdrawal_refuses_before_reservation_or_dispatch(monkeypatch, withdrawn):
    async with harness(monkeypatch) as h:
        chosen = {**SETTINGS, "speed": "priority"} if withdrawn == "speed" else SETTINGS
        assert (await h.alice.post("/api/agent/session")).status_code == 200
        assert (await h.alice.put("/api/agent/prefs", json={"ai_settings": chosen})).status_code == 200
        if withdrawn == "effort":
            h.provider.fresh_efforts = ["low"]
        else:
            h.provider.fresh_speeds = []
        response = await h.alice.post("/api/agent/ask", json=request_body())
        await settle(h)
        saved = (await h.alice.get("/api/agent/turn/" + response.json()["turn_id"])).json()
        assert h.provider.dispatches == 0
        assert (await h.model.spend.state())["calls"] == 0
        assert saved["status"] == "completed" and saved["answer"]["mode"] == "deterministic"
        assert saved["answer"]["usage"][0]["trace"]["effective"] is None
        assert not any(method == "thread/start" for method, _ in h.provider.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "error", "reroute", "model", "effort", "speed"])
async def test_failed_dispatch_saves_truthful_terminal_trace_without_retry(monkeypatch, failure):
    async with harness(monkeypatch) as h:
        await login_and_save(h)
        h.provider.failure = failure
        body = request_body()
        response = await h.alice.post("/api/agent/ask", json=body)
        turn_id = response.json()["turn_id"]
        await settle(h)
        saved = (await h.alice.get(f"/api/agent/turn/{turn_id}")).json()
        assert saved["status"] == "completed" and saved["answer"]["mode"] == "deterministic"
        usage = saved["answer"]["usage"][0]
        trace = usage["trace"]
        assert trace["requested"] == SETTINGS and trace["effective"] is None
        assert trace["status"] == "unavailable" and trace["actual_cost"] is None
        assert "model" not in usage and trace["tokens"] is None
        assert "fixture-private-provider-detail" not in json.dumps(saved)
        entry = await usage_entry(h, turn_id)
        assert entry["trace"] == trace
        assert entry["status"] == trace["status"]
        assert entry["actual_cost"] is None
        before = len(h.provider.requests)
        assert (await h.alice.post("/api/agent/ask", json=body)).json()["turn_id"] == turn_id
        assert (await h.alice.get("/api/agent/history")).json()["turns"] == [saved]
        assert len(h.provider.requests) == before
        assert (await h.model.spend.state())["calls"] == 1
        assert h.provider.dispatches == (0 if failure in {"model", "effort", "speed"} else 1)


@pytest.mark.asyncio
async def test_cancel_inflight_is_owner_only_and_retains_unknown_counted_dispatch(monkeypatch):
    async with harness(monkeypatch) as h:
        await login_and_save(h)
        assert (await h.bob.post("/api/agent/session")).status_code == 200
        h.provider.failure = "cancel"
        body = request_body()
        response = await h.alice.post("/api/agent/ask", json=body)
        turn_id = response.json()["turn_id"]
        worker = h.service.tasks[turn_id]
        await asyncio.wait_for(h.provider.entered.wait(), 5)
        assert (await h.bob.post(f"/api/agent/cancel/{turn_id}")).status_code == 404
        assert not worker.done()
        cancelled = await h.alice.post(f"/api/agent/cancel/{turn_id}")
        assert cancelled.json()["status"] == "cancelled"
        await asyncio.gather(worker, return_exceptions=True)
        saved = (await h.alice.get(f"/api/agent/turn/{turn_id}")).json()
        assert saved["status"] == "cancelled" and saved["answer"] is None
        assert not any(event["type"] == "done" for event in saved["events"])
        entry = await usage_entry(h, turn_id)
        assert entry["trace"]["status"] == "cancelled_dispatch_unknown"
        assert entry["trace"]["requested"] == SETTINGS and entry["trace"]["effective"] is None
        assert entry["actual_cost"] is None
        assert entry["status"] == entry["trace"]["status"]
        assert h.provider.closed == 2
        assert worker.cancelled()
        assert (await h.alice.post("/api/agent/ask", json=body)).json()["turn_id"] == turn_id
        assert h.provider.dispatches == 1 and (await h.model.spend.state())["calls"] == 1


@pytest.mark.asyncio
async def test_wall_time_limit_stops_inflight_work_without_effective_or_completed_answer(monkeypatch):
    async with harness(monkeypatch) as h:
        await login_and_save(h)
        h.service.timeout = 0.2
        h.provider.failure = "cancel"
        body = request_body()
        response = await h.alice.post("/api/agent/ask", json=body)
        turn_id = response.json()["turn_id"]
        await asyncio.wait_for(h.provider.entered.wait(), 5)
        await asyncio.wait_for(settle(h), 5)
        saved = (await h.alice.get(f"/api/agent/turn/{turn_id}")).json()
        assert saved["status"] == "failed" and saved["answer"] is None
        assert not any(event["type"] == "done" for event in saved["events"])
        entry = await usage_entry(h, turn_id)
        assert entry["trace"]["status"] == "cancelled_dispatch_unknown"
        assert entry["trace"]["effective"] is None and entry["actual_cost"] is None
        assert entry["status"] == entry["trace"]["status"]
        assert h.provider.closed == 2
        assert (await h.alice.post("/api/agent/ask", json=body)).json()["turn_id"] == turn_id
        assert h.provider.dispatches == 1 and (await h.model.spend.state())["calls"] == 1
