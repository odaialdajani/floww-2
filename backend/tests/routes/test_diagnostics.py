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
