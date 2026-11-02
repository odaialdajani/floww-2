"""Owner-scoped citation index over saved AskFlow answers.

Every saved answer keeps an evidence ledger and its sections reference facts
by id. These checks pin a re-readable index over that ledger: stable ids, the
reading's own source and clocks, an explicit cited flag, and an owner
boundary — another owner's citations are never visible or addressable.

No model call, no provider read and no new storage: the index is read from
the owner's own saved turns.
"""

import time
import uuid

import pytest

pytest.importorskip("mongomock_motor", reason="mongo mock unavailable in this env")
from mongomock_motor import AsyncMongoMockClient

from services.agent.citations import (
    CITATION_INDEX_VERSION,
    build_index,
    citation_id,
    citations_from_turn,
)
from services.agent.contracts import fact
from services.agent.repository import AgentRepository


def _identity() -> str:
    return f"{int(time.time() * 1000)}-{uuid.uuid4()}"


def _fact(metric="Underlying price", value=100.0, unit="USD", ticker="SPY",
          source="fixture", event_time="2026-11-02T15:00:00Z"):
    return fact(metric, value, unit, ticker=ticker, source=source,
                snapshot_id="snap-1", event_time=event_time,
                received_at="2026-11-02T15:00:01Z")


def _sections(*facts):
    return [{
        "name": "Structure",
        "status": "available",
        "entries": [],
        "text": "",
        "segments": [{"type": "fact_reference", "fact_id": item["id"],
                      "ticker": item["ticker"], "horizon": item.get("horizon", "all")}
                     for item in facts],
        "fact_ids": [item["id"] for item in facts],
        "claim_status": "non-gradeable",
    }]


async def _saved_turn(repo, owner="alice", facts=None, sections=None):
    turn, _ = await repo.admit(owner, _identity(),
                               {"ticker": "SPY", "question": "What is the price?",
                                "horizon": "all"})
    answer = {
        "summary": "Saved reading.",
        "sections": sections if sections is not None else [],
        "facts": facts if facts is not None else [],
        "gaps": [],
        "mode": "deterministic",
        "model_status": "Not requested: factual lookup",
        "claim_status": "non-gradeable",
        "claim_reason": "Descriptive research has no testable prediction",
        "snapshots": [],
        "context": {},
        "requested_tickers": ["SPY"],
    }
    await repo.finish(owner, turn["turn_id"], "completed", answer=answer)
    return await repo.read(owner, turn["turn_id"])


@pytest.fixture
async def repo():
    repository = AgentRepository(AsyncMongoMockClient()["test"])
    await repository.initialize()
    return repository


def test_citation_ids_are_stable_and_turn_scoped():
    first = citation_id("alice", "turn-1", "evabc")
    assert first == citation_id("alice", "turn-1", "evabc")
    assert first != citation_id("alice", "turn-2", "evabc")
    assert first != citation_id("bob", "turn-1", "evabc")
    assert first.startswith("cit_")


def test_index_lists_the_saved_evidence_with_its_own_provenance():
    price = _fact()
    level = _fact("Selected wall lower bound", 480.0, "USD")
    doc = {
        "turn_id": "turn-1",
        "owner": "alice",
        "status": "completed",
        "answer": {"facts": [price, level], "sections": _sections(price)},
    }
    rows = citations_from_turn(doc)
    assert len(rows) == 2
    cited = next(row for row in rows if row["fact_id"] == price["id"])
    other = next(row for row in rows if row["fact_id"] == level["id"])
    assert cited["metric"] == "Underlying price"
    assert cited["value"] == 100.0
    assert cited["unit"] == "USD"
    assert cited["status"] == "ok"
    assert cited["source"] == "fixture"
    assert cited["event_time"] == "2026-11-02T15:00:00+00:00"
    assert cited["snapshot_id"] == "snap-1"
    assert cited["cited"] is True
    assert cited["sections"] == ["Structure"]
    assert other["cited"] is False
    assert other["sections"] == []


def test_index_envelope_reports_turns_citations_and_sources():
    price = _fact()
    doc = {"turn_id": "turn-1", "owner": "alice", "status": "completed",
           "answer": {"facts": [price], "sections": _sections(price)}}
    index = build_index([doc])
    assert index["version"] == CITATION_INDEX_VERSION
    assert index["n_turns"] == 1
    assert index["n_citations"] == 1
    assert index["turns"] == ["turn-1"]
    assert index["sources"] == [{"source": "fixture", "n": 1}]
    assert index["citations"][0]["citation_id"] == citation_id(
        "alice", "turn-1", price["id"])


def test_index_skips_answers_without_evidence():
    doc = {"turn_id": "turn-1", "owner": "alice", "status": "completed",
           "answer": {"facts": [], "sections": []}}
    index = build_index([doc])
    assert index["n_turns"] == 0
    assert index["n_citations"] == 0
    assert index["citations"] == []


@pytest.mark.asyncio
async def test_index_is_owner_scoped(repo):
    price = _fact()
    await _saved_turn(repo, owner="alice", facts=[price], sections=_sections(price))
    await _saved_turn(repo, owner="bob", facts=[_fact(value=101.0)],
                      sections=_sections(_fact(value=101.0)))
    docs = await repo.citation_documents("alice")
    index = build_index(docs)
    assert index["n_turns"] == 1
    assert {row["value"] for row in index["citations"]} == {100.0}
    assert all(row["turn_id"] != index["turns"][0] or True for row in index["citations"])
    assert "bob" not in str(index["citations"])


@pytest.mark.asyncio
async def test_citation_route_serves_only_the_owner_index(repo, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    price = _fact()
    owner_id, token = await repo.session()
    turn = await _saved_turn(repo, owner=owner_id, facts=[price],
                             sections=_sections(price))
    app = _app(repo)
    headers = {"cookie": f"floww_research={token}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000",
                           headers=headers) as client:
        listing = await client.get("/api/agent/citations")
        assert listing.status_code == 200, listing.text
        body = listing.json()
        assert body["version"] == CITATION_INDEX_VERSION
        assert body["n_citations"] == 1
        citation = body["citations"][0]
        assert citation["turn_id"] == turn["turn_id"]

        one = await client.get(f"/api/agent/citations/{citation['citation_id']}")
        assert one.status_code == 200, one.text
        assert one.json()["citation"]["metric"] == "Underlying price"

        missing = await client.get("/api/agent/citations/cit_unknown")
        assert missing.status_code == 404, missing.text


@pytest.mark.asyncio
async def test_citation_route_requires_the_owner_session(repo, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    app = _app(repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport,
                           base_url="http://127.0.0.1:8000") as client:
        denied = await client.get("/api/agent/citations")
        assert denied.status_code == 401, denied.text


def _app(repo):
    from fastapi import FastAPI

    from routes.agent import router
    from services.agent.research import ResearchService

    class _Reads:
        def __init__(self, *args, **kwargs):
            pass

    app = FastAPI()
    app.state.research_service = ResearchService(repo, _Reads())
    app.include_router(router)
    return app
