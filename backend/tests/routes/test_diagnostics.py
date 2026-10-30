import httpx
import pytest
from fastapi import FastAPI

from routes.diagnostics import router
from services.problem_journal import ProblemJournal


@pytest.mark.asyncio
async def test_local_reports_are_saved_and_sensitive_fields_are_refused(monkeypatch, tmp_path):
    import routes.diagnostics as routes
    store = ProblemJournal(tmp_path)
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    monkeypatch.setattr(routes, "journal", lambda: store)
    monkeypatch.setattr(routes, "record_problem", lambda event: store.record(event) is None)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        origin = {"Origin": "http://127.0.0.1:3000"}
        body = {"events": [{"kind": "browser_error", "name": "TypeError"}]}
        assert (await client.post("/api/diagnostics/events", json=body, headers=origin)).status_code == 200
        assert (await client.get("/api/diagnostics/summary", headers=origin)).json()["total_events"] == 1
        assert (await client.post("/api/diagnostics/events", json=body)).status_code == 403
        assert (await client.post("/api/diagnostics/events", json=body, headers={"Origin": "http://other.example"})).status_code == 403
        body["events"][0]["question"] = "sensitive body"
        assert (await client.post("/api/diagnostics/events", json=body, headers=origin)).status_code == 422
        assert (await client.post("/api/diagnostics/events", content="x" * 12001, headers=origin)).status_code == 413
    store.close()


@pytest.mark.asyncio
async def test_reports_stay_local_when_the_research_agent_is_not_deployed(monkeypatch, tmp_path):
    """A read-only workspace has no research agent; problem reports must still work."""
    from fastapi import HTTPException
    from starlette.requests import Request

    import routes.diagnostics as routes
    from services.agent.local_access import require_local, require_loopback

    store = ProblemJournal(tmp_path)
    monkeypatch.delenv("FLOWW_AGENT_DEPLOYMENT", raising=False)
    monkeypatch.delenv("FLOWW_AGENT_ORIGINS", raising=False)
    monkeypatch.setattr(routes, "journal", lambda: store)
    monkeypatch.setattr(routes, "record_problem", lambda event: store.record(event) is None)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        origin = {"Origin": "http://127.0.0.1:3000"}
        body = {"events": [{"kind": "browser_error", "name": "TypeError"}]}
        assert (await client.post("/api/diagnostics/events", json=body, headers=origin)).status_code == 200
        assert (await client.get("/api/diagnostics/summary", headers=origin)).json()["total_events"] == 1
        # Dropping the deployment flag must not weaken the same-origin rule.
        assert (await client.post("/api/diagnostics/events", json=body)).status_code == 403
        assert (await client.post("/api/diagnostics/events", json=body,
                                  headers={"Origin": "http://other.example"})).status_code == 403

    def request(headers=None):
        return Request({
            "type": "http", "method": "POST", "path": "/api/agent/ask",
            "headers": headers or [(b"host", b"127.0.0.1:8213"), (b"origin", b"http://127.0.0.1:3000")],
            "client": ("127.0.0.1", 1234), "query_string": b"",
        })

    # The agent surface keeps its deployment gate; only reporting is decoupled.
    with pytest.raises(HTTPException) as refused:
        require_local(request())
    assert refused.value.status_code == 503
    assert require_loopback(request()) is None
    with pytest.raises(HTTPException) as proxied:
        require_loopback(request([(b"host", b"127.0.0.1:8213"),
                                  (b"origin", b"http://127.0.0.1:3000"),
                                  (b"x-forwarded-for", b"127.0.0.1")]))
    assert proxied.value.status_code == 403
    store.close()


@pytest.mark.asyncio
async def test_mutating_report_passes_the_shared_auth_dependency_without_the_agent(monkeypatch):
    """The live app gates POSTs in verify_api_key; that gate must not need the agent."""
    from fastapi import HTTPException
    from starlette.requests import Request

    from auth import verify_api_key

    monkeypatch.delenv("FLOWW_AGENT_DEPLOYMENT", raising=False)
    monkeypatch.delenv("FLOWW_AGENT_ORIGINS", raising=False)

    def request(headers=None):
        return Request({
            "type": "http", "method": "POST", "path": "/api/diagnostics/events",
            "headers": headers or [(b"host", b"127.0.0.1:8213"),
                                   (b"origin", b"http://127.0.0.1:3000")],
            "client": ("127.0.0.1", 1234), "query_string": b"",
        })

    assert await verify_api_key(request()) is True
    for headers in (
        [(b"host", b"127.0.0.1:8213")],
        [(b"host", b"127.0.0.1:8213"), (b"origin", b"http://other.example")],
        [(b"host", b"127.0.0.1:8213"), (b"origin", b"http://127.0.0.1:3000"),
         (b"x-forwarded-for", b"127.0.0.1")],
    ):
        with pytest.raises(HTTPException) as refused:
            await verify_api_key(request(headers))
        assert refused.value.status_code == 403
