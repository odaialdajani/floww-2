"""Stored-only range observations; scripted RPC is not host/production admission."""

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import duckdb
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from routes.agent import router
from services.agent.codex_model import POLICY_VERSION, CodexModel
from services.agent.contracts import request_spec
from services.agent.display_map import display_facts
from services.agent.local_access import COOKIE
from services.agent.plan_draft import build_plan_draft
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService
from services.agent.saved_history import history_facts
from services.heatmap_history import record_range_envelope, replay_range_envelope
from services.solstice_range_analytics import (
    build_range_envelope,
    compute_content_digest,
    record_id_for_digest,
    select_window_expiries,
)
from tests.agent.test_exact_contract_admission import record, screen
from tests.agent.test_owner_provider_acceptance import (
    SETTINGS,
    ScriptedProvider,
    login_and_save,
    request_body,
    settle,
    usage_entry,
)
from tests.offline_network import deny_external_network  # noqa: F401


def envelope():
    fixtures = Path(__file__).parents[1] / "solstice/fixtures/range_analytics_v1"
    listing = json.loads((fixtures / "listing.json").read_text())
    chain = json.loads((fixtures / "chain_complete.json").read_text())
    asof = date(2026, 10, 5)
    selection = select_window_expiries(listing["expiries"], 14, 60, asof)
    return build_range_envelope(symbol="SPY", min_dte=14, max_dte=60, asof=asof,
                                listing=listing, selection=selection, chain=chain)


def wrapper(env):
    return dict(record_id=env["record_id"], digest=env["content_digest"], ticker=env["symbol"],
                window={k: env["query"][k] for k in ("min_dte", "max_dte")},
                asof_date=env["query"]["as_of_ny"], received_at=env["clocks"]["received_at"],
                status=env["status"], recorded_at="2026-10-05T14:00:00+00:00",
                integrity="verified", envelope=env)


def rebind(env):
    env["content_digest"] = compute_content_digest(env)
    env["record_id"] = record_id_for_digest(env["content_digest"])
    return wrapper(env)


def selection(env, metric="delta_weighted"):
    section = env["grids"][metric]
    return dict(contextVersion=2, page="heatseeker", ticker="SPY", activePane="gex",
                displayMode="range-replay", metric="gex", overlayMetric=metric,
                rangeVersion=env["version"], rangeRecordId=env["record_id"],
                rangeDigest=env["content_digest"], rangeMetric=metric,
                rangeBasis=section["basis"], rangeStatus=section["status"],
                snapshotId=env["record_id"], provider=env["provenance"]["data_source"],
                formula=section["formula_version"], mapQuery=copy.deepcopy(env["query"]),
                mapVersion=env["clocks"]["received_at"], observedAt=env["clocks"]["chain_event_time"],
                mapStrikes=list(map(float, env["axes"]["strike_keys"])),
                mapExpiries=[row["expiry"] for row in env["axes"]["expiries"]],
                selectedStrike=590, selectedExpiry="2026-10-26", selectedContract=None,
                contractResolution="RANGE_CONTRACT_UNAVAILABLE")


def body(env, metric="delta_weighted", question="Explain SPY map structure since yesterday"):
    return {**request_body(), "question": question, "screen": selection(env, metric)}


def test_read_side_digest_is_pinned_without_importing_the_analytical_producer():
    from services.agent.range_replay import compute_content_digest as read_digest

    assert read_digest.__module__ == "services.agent.range_replay"
    env = envelope()
    assert read_digest(env) == compute_content_digest(env) == env["content_digest"]
    env["clocks"]["oi_effective_dates"] = []
    assert read_digest(env) == compute_content_digest(env)


@pytest.mark.parametrize("field,value", [("metric", "vex"), ("contractResolution", "resolved")])
def test_range_request_refuses_mislabeled_metric_or_contract_claim(field, value):
    requested = body(envelope())
    requested["screen"][field] = value
    with pytest.raises(ValueError, match="RANGE_"):
        request_spec(requested)


def test_empty_known_oi_date_list_remains_unknown_without_refusing_stored_cells():
    from services.agent.range_replay import range_snapshot

    env = envelope()
    env["clocks"]["oi_effective_dates"] = []
    raw = rebind(env)
    result = range_snapshot(raw, selection(env), "SPY", "range:14:60", datetime(2026, 10, 5, 14, tzinfo=UTC))
    assert result["facts"]
    assert "RANGE_OI_DATE_UNKNOWN" in result["gaps"]
    assert result["range_observation"]["oi_effective_dates"] == []


@pytest.mark.asyncio
async def test_server_composition_injects_only_the_owning_stored_range_reader(monkeypatch):
    import server
    from services import heatmap_history
    from services.agent import codex_model, repository, research, spend, tools

    repo = SimpleNamespace(initialize=AsyncMock(), budgets=object())
    ledger = SimpleNamespace(initialize=AsyncMock(), recover_undispatched=AsyncMock())
    monkeypatch.setattr(repository, "AgentRepository", lambda _: repo)
    monkeypatch.setattr(spend, "SpendLedger", lambda *a, **kw: ledger)
    monkeypatch.setattr(codex_model, "CodexModel", lambda *a, **kw: None)
    monkeypatch.setattr(research, "ResearchService", lambda repo, reads, model: SimpleNamespace(reads=reads))
    monkeypatch.setattr(tools, "configure_reads", lambda reads: None)
    monkeypatch.setitem(server.app.state._state, "research_service", None)
    connection = object()
    monkeypatch.setattr(server.duckdb_engine, "_conn", connection)
    raw = wrapper(envelope())
    reader = Mock(return_value=raw)
    monkeypatch.setattr(heatmap_history, "replay_range_envelope", reader)
    await server.startup_research()
    callback = server.app.state.research_service.reads._read_recorded_range
    assert callback is not None
    assert callback("SPY", raw["record_id"]) == raw
    reader.assert_called_once_with(connection, raw["record_id"])
    monkeypatch.setattr(server.duckdb_engine, "_conn", None)
    assert callback("SPY", raw["record_id"]) is None
    reader.assert_called_once()


@pytest.mark.parametrize("metric", ["raw_oi", "delta_weighted", "volume", "window"])
def test_range_request_is_recorded_not_live_price_lookup(metric):
    spec = request_spec(body(envelope(), metric, "SPY underlying price"))
    assert spec["price_only"] is False
    assert spec["horizon"] == "range:14:60"


@pytest.mark.parametrize("field,value", [
    ("displayMode", "range-live"), ("contextVersion", 1), ("rangeVersion", "v0"),
    ("rangeRecordId", "snap1"), ("rangeDigest", "garbage"), ("rangeMetric", "gex"),
    ("rangeBasis", "OI"), ("rangeStatus", "refused"), ("rangeStatus", []), ("overlayMetric", "raw"),
    ("expiryRange", [0, 1]),
    ("selectedContract", {"osi": "SPY261026C00590000"}), ("mapStrikes", [True]),
    ("mapQuery", {"min_dte": True, "max_dte": 60, "as_of_ny": "2026-10-05"}),
])
def test_invalid_request_refuses_before_read(field, value):
    request = body(envelope())
    request["screen"][field] = value
    with pytest.raises(ValueError):
        request_spec(request)


@pytest.mark.parametrize("question", ["Explain $QQQ map", "Explain SPY 0dte", "Explain SPY expiry 2026-11-09"])
def test_range_scope_does_not_silently_reuse_a_different_cell(question):
    with pytest.raises(ValueError):
        request_spec(body(envelope(), question=question))


@asynccontextmanager
async def harness(monkeypatch, *, env=None, result="stored", metric="delta_weighted"):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")
    monkeypatch.delenv("FLOWW_AGENT_DISABLED", raising=False)
    env = env or envelope()
    if result == "stored":
        with duckdb.connect(":memory:") as conn:
            assert record_range_envelope(conn, env)["status"] == "recorded"
            result = replay_range_envelope(conn, env["record_id"])
    db = AsyncMongoMockClient()["r18_range_agent"]
    repo = AgentRepository(db)
    await repo.initialize()
    provider = ScriptedProvider()
    model = CodexModel(repo, db.usage, bridge_factory=provider.bridge)
    upstream = Mock(side_effect=AssertionError("No live or other recorded fallback"))
    recorded = Mock(return_value=result)
    reads = ResearchReads(upstream, upstream, upstream, read_daily_bars=upstream,
                          read_recorded_map=upstream, read_recorded_range=recorded)
    service = ResearchService(repo, reads, model=model)
    service._history = Mock(side_effect=AssertionError("No current-chain history comparison"))
    app = FastAPI()
    app.include_router(router)
    app.state.research_service = service
    transport = ASGITransport(app=app, client=("127.0.0.1", 123), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://localhost:8000",
                           headers={"Origin": "http://localhost:3000"}) as alice, AsyncClient(
        transport=transport, base_url="http://localhost:8000", headers={"Origin": "http://localhost:3000"}
    ) as bob:
        try:
            yield SimpleNamespace(db=db, repo=repo, provider=provider, model=model, reads=reads,
                                  service=service, alice=alice, bob=bob, upstream=upstream,
                                  recorded=recorded, env=env, body=body(env, metric))
        finally:
            await service.close()


async def ask_saved(h):
    response = await h.alice.post("/api/agent/ask", json=h.body)
    assert response.status_code == 200, response.text
    await settle(h)
    saved = (await h.alice.get("/api/agent/turn/" + response.json()["turn_id"])).json()
    assert saved["status"] == "completed", saved
    return saved


@pytest.mark.asyncio
@pytest.mark.parametrize("metric", ["raw_oi", "delta_weighted", "volume"])
async def test_authenticated_stored_cells_exact_settings_trace_history_and_no_authority(monkeypatch, metric):
    async with harness(monkeypatch, metric=metric) as h:
        assert (await h.alice.post("/api/agent/ask", json=h.body)).status_code == 401
        h.recorded.assert_not_called()
        await login_and_save(h)
        assert (await h.bob.post("/api/agent/session")).status_code == 200
        assert (await h.alice.get("/api/agent/prefs")).json()["ai_settings"] == SETTINGS
        assert "ai_settings" not in (await h.bob.get("/api/agent/prefs")).json()
        saved = await ask_saved(h)
        answer = saved["answer"]
        assert answer["mode"] == "model-assisted"
        cell = next(f for f in answer["facts"] if f["metric"].startswith("Recorded range cell "))
        section = h.env["grids"][metric]
        assert cell["value"] == section["cells"]["2026-10-26"]["590"]
        assert section["metric_id"] in cell["metric"]
        assert cell["contract"] is None and cell["status"] == "degraded"
        assert cell["event_time"] is None
        assert cell["received_at"] == h.env["clocks"]["received_at"]
        assert cell["snapshot_id"] == h.env["record_id"]
        assert "research only" in cell["reason"]
        snapshot = answer["snapshots"][0]
        assert snapshot["anchor_kind"] == "recorded" and snapshot["replay"] is True
        assert snapshot["range_observation"]["metric_id"] == section["metric_id"]
        assert snapshot["range_observation"]["content_digest"] == h.env["content_digest"]
        assert snapshot["range_observation"]["production_admitted"] is False
        assert not any(f["metric"] == "Underlying price" for f in answer["facts"])
        assert await h.repo.snapshots.count_documents({}) == 0
        assert await h.repo.collection_jobs.count_documents({}) == 0
        trace = answer["usage"][0]["trace"]
        draft = answer["plan_draft"]
        assert trace["requested"] == trace["effective"] == SETTINGS
        assert trace["policy_version"] == POLICY_VERSION
        assert trace["context_hash"] == draft["context_hash"]
        assert trace["evidence_ids"] == draft["evidence_ids"]
        assert trace["observation_ids"] == draft["observation_ids"] == [h.env["record_id"]]
        assert (await usage_entry(h, saved["turn_id"]))["trace"] == trace
        assert draft["contract"] is None and draft["approval"] is None
        assert draft["status"] == "review_only" and draft["executable"] is False
        assert {"RANGE_CONTRACT_UNAVAILABLE", "REPLAY_NOT_EXECUTABLE"} <= set(draft["blockers"])
        assert draft["selection"]["rangeMetric"] == metric
        assert draft["selection"]["rangeDigest"] == h.env["content_digest"]
        assert any(cell["id"] in s["fact_ids"] for s in answer["sections"])
        assert (await h.alice.get("/api/agent/history")).json()["turns"] == [saved]
        assert (await h.bob.get("/api/agent/history")).json() == {"turns": []}
        assert (await h.bob.get("/api/agent/turn/" + saved["turn_id"])).status_code == 404
        handoff = dict(turn_id=saved["turn_id"], context_hash=draft["context_hash"],
                       execution_owner="PUBLIC_NATIVE_AGENT", brief="Review only", workflow_reference="",
                       reported_status="prepared")
        assert (await h.alice.post("/api/agent/handoffs", json=handoff)).status_code == 409
        assert (await h.alice.post("/api/agent/handoffs", json={**handoff, "approved": True})).status_code == 422
        assert (await h.alice.post("/api/agent/ask", json=h.body)).json()["turn_id"] == saved["turn_id"]
        assert h.provider.dispatches == 1
        h.recorded.assert_called_once_with("SPY", h.env["record_id"])
        h.upstream.assert_not_called()
        h.service._history.assert_not_called()


DEFECTS = [
    ("missing", "RANGE_RECORD_UNAVAILABLE"), ("corrupt", "RANGE_RECORD_CORRUPT"),
    ("digest", "RANGE_DIGEST_MISMATCH"), ("schema", "RANGE_SCHEMA_MISMATCH"),
    ("header_status", "RANGE_HEADER_MISMATCH"), ("header_clock", "RANGE_HEADER_MISMATCH"),
    ("header_ticker", "RANGE_HEADER_MISMATCH"), ("header_window", "RANGE_HEADER_MISMATCH"),
    ("header_asof", "RANGE_HEADER_MISMATCH"), ("header_record", "RANGE_HEADER_MISMATCH"),
    ("header_window_type", "RANGE_HEADER_MISMATCH"),
    ("model", "RANGE_METRIC_MISMATCH"), ("basis", "RANGE_METRIC_MISMATCH"),
    ("unit", "RANGE_METRIC_MISMATCH"), ("population", "RANGE_POPULATION_INVALID"),
    ("unknown_population", "RANGE_POPULATION_INVALID"), ("count", "RANGE_GRID_INVALID"),
    ("null_count", "RANGE_GRID_INVALID"), ("extra_cell", "RANGE_GRID_INVALID"),
    ("axis", "RANGE_AXES_INVALID"), ("dte", "RANGE_AXES_INVALID"),
    ("unknown_received", "RANGE_CLOCK_INVALID"), ("bad_event", "RANGE_CLOCK_INVALID"),
    ("bad_oi_date", "RANGE_CLOCK_INVALID"), ("selection", "RANGE_SELECTION_MISMATCH"),
    ("null_cell", "RANGE_CELL_UNAVAILABLE"), ("window", "RANGE_WINDOW_UNAVAILABLE"),
]


def defective(defect):
    env = envelope()
    result = wrapper(env)
    screen_metric = "window" if defect == "window" else "delta_weighted"
    section = env["grids"]["delta_weighted"]
    if defect == "missing":
        result = None
    elif defect == "corrupt":
        result = {"error": "CORRUPT_PAYLOAD", "envelope": None}
    elif defect == "digest":
        section["cells"]["2026-10-26"]["590"] += 1
    elif defect.startswith("header_"):
        key, value = {
            "header_status": ("status", "partial"), "header_clock": ("received_at", "2026-10-05T14:01:00Z"),
            "header_ticker": ("ticker", "QQQ"), "header_window": ("window", {"min_dte": 15, "max_dte": 60}),
            "header_asof": ("asof_date", "2026-10-04"), "header_record": ("record_id", "rga1-" + "0" * 24),
            "header_window_type": ("window", {"min_dte": 14.0, "max_dte": 60}),
        }[defect]
        result[key] = value
    elif defect == "schema":
        env["content_schema"] = "legacy"
        result = rebind(env)
    elif defect in {"model", "basis", "unit"}:
        section[defect] = "unregistered"
        env["metric_registry"]["delta_weighted"][defect] = "unregistered"
        result = rebind(env)
    elif defect in {"population", "unknown_population"}:
        section["population"]["usable"] = -1 if defect == "population" else None
        result = rebind(env)
    elif defect == "count":
        section["n_available"] = True
        result = rebind(env)
    elif defect == "null_count":
        section["cells"]["2026-10-26"]["590"] = None
        result = rebind(env)
    elif defect == "extra_cell":
        section["cells"]["2026-10-26"]["601"] = 3
        result = rebind(env)
    elif defect == "axis":
        env["axes"]["expiries"].append(env["axes"]["expiries"][0])
        result = rebind(env)
    elif defect == "dte":
        env["axes"]["expiries"][0]["dte"] = 22
        result = rebind(env)
    elif defect == "unknown_received":
        env["clocks"]["received_at"] = None
        result = rebind(env)
    elif defect == "bad_event":
        env["clocks"]["chain_event_time"] = "2026-10-05T14:00:00"
        result = rebind(env)
    elif defect == "bad_oi_date":
        env["clocks"]["oi_effective_dates"] = ["unknown"]
        result = rebind(env)
    elif defect == "null_cell":
        section["cells"]["2026-10-26"]["590"] = None
        section.update(status="partial", n_available=5, cell_gaps=1, metric_admitted=False)
        result = rebind(env)
    return env, result, screen_metric


@pytest.mark.asyncio
@pytest.mark.parametrize("defect,reason", DEFECTS)
async def test_record_defects_have_no_facts_provider_or_fallback(monkeypatch, defect, reason):
    env, result, metric = defective(defect)
    async with harness(monkeypatch, env=env, result=result, metric=metric) as h:
        await login_and_save(h)
        # For malformed stored axes/clocks preserve a syntactically valid requested context.
        valid = selection(envelope(), metric)
        for key in ("snapshotId", "rangeRecordId", "rangeDigest"):
            valid[key] = h.body["screen"][key]
        h.body["screen"] = valid
        if defect == "null_cell":
            valid["rangeStatus"] = "partial"
        if defect == "selection":
            valid["mapStrikes"] = [590, 601]
        saved = await ask_saved(h)
        assert saved["answer"]["facts"] == []
        assert any(reason in gap for gap in saved["answer"]["gaps"]), saved["answer"]["gaps"]
        assert h.provider.dispatches == 0 and (await h.model.spend.state())["calls"] == 0
        h.upstream.assert_not_called()
        h.service._history.assert_not_called()


@pytest.mark.asyncio
async def test_partial_coverage_and_unbound_top_summary_are_never_admission(monkeypatch):
    env = envelope()
    env["status"] = "partial"
    env["coverage"].update(complete=False, complete_reason="SKIPPED_EXPIRIES", n_returned_expiries=2,
                           n_skipped_expiries=1, skipped=[{"expiry": "2026-12-04", "reason": "offline"}])
    for section in env["grids"].values():
        if section["status"] == "unavailable":
            continue
        section["cells"]["2026-12-04"] = {"590": None, "600": None}
        section.update(status="partial", n_available=4, cell_gaps=2, metric_admitted=False)
    result = rebind(env)
    env["metrics"] = {"admitted": ["window"], "unavailable": ["delta_weighted"]}
    async with harness(monkeypatch, env=env, result=result) as h:
        await login_and_save(h)
        saved = await ask_saved(h)
        assert saved["answer"]["facts"][0]["status"] == "degraded"
        assert any("PARTIAL_COVERAGE" in g for g in saved["answer"]["gaps"])
        assert saved["answer"]["snapshots"][0]["range_observation"]["production_admitted"] is False


@pytest.mark.asyncio
async def test_unknown_oi_and_event_clocks_are_preserved_not_received_time(monkeypatch):
    env = envelope()
    env["clocks"]["oi_effective_dates"] = None
    async with harness(monkeypatch, env=env, result=rebind(env)) as h:
        await login_and_save(h)
        saved = await ask_saved(h)
        assert all(f["event_time"] is None and f["status"] == "degraded" for f in saved["answer"]["facts"])
        assert any("RANGE_OI_DATE_UNKNOWN" in g for g in saved["answer"]["gaps"])


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "error"])
async def test_range_provider_failure_is_terminal_saved_and_not_retried(monkeypatch, failure):
    async with harness(monkeypatch) as h:
        await login_and_save(h)
        h.provider.failure = failure
        saved = await ask_saved(h)
        assert saved["answer"]["mode"] == "deterministic"
        trace = saved["answer"]["usage"][0]["trace"]
        assert trace["requested"] == SETTINGS and trace["effective"] is None
        assert trace["status"] == "unavailable"
        assert trace["observation_ids"] == [h.env["record_id"]]
        assert (await usage_entry(h, saved["turn_id"]))["trace"] == trace
        assert h.provider.dispatches == 1
        assert "fixture-private-provider-detail" not in json.dumps(saved)
        assert (await h.alice.post("/api/agent/ask", json=h.body)).json()["turn_id"] == saved["turn_id"]
        assert h.provider.dispatches == 1


@pytest.mark.asyncio
async def test_range_cancel_retains_linked_unknown_dispatch_and_owner_isolation(monkeypatch):
    async with harness(monkeypatch) as h:
        await login_and_save(h)
        await h.bob.post("/api/agent/session")
        h.provider.failure = "cancel"
        response = await h.alice.post("/api/agent/ask", json=h.body)
        assert response.status_code == 200
        turn_id = response.json()["turn_id"]
        worker = h.service.tasks[turn_id]
        await asyncio.wait_for(h.provider.entered.wait(), 5)
        assert (await h.bob.post(f"/api/agent/cancel/{turn_id}")).status_code == 404
        assert (await h.alice.post(f"/api/agent/cancel/{turn_id}")).json()["status"] == "cancelled"
        await asyncio.gather(worker, return_exceptions=True)
        saved = (await h.alice.get(f"/api/agent/turn/{turn_id}")).json()
        assert saved["answer"] is None and saved["status"] == "cancelled"
        entry = await usage_entry(h, turn_id)
        assert entry["trace"]["status"] == "cancelled_dispatch_unknown"
        assert entry["trace"]["observation_ids"] == [h.env["record_id"]]
        assert entry["trace"]["effective"] is None
        assert (await h.alice.post("/api/agent/ask", json=h.body)).json()["turn_id"] == turn_id
        assert h.provider.dispatches == 1
        h.upstream.assert_not_called()


@pytest.mark.asyncio
async def test_history_entry_point_refuses_recorded_range_without_querying_anchors():
    repository = Mock()
    current = {"anchor_kind": "recorded", "range_observation": {"record_id": "rga1-offline"}}
    facts, note = await history_facts(repository, "owner", current)
    assert facts == [] and "Recorded range" in note
    repository.assert_not_called()
    repository.turns.find.assert_not_called()
    repository.snapshots.find.assert_not_called()


def test_range_draft_cannot_launder_injected_exact_contract_evidence():
    facts, _ = display_facts(record(), screen(), "SPY", datetime.now(UTC))
    context = {**screen(), "displayMode": "range-replay", "rangeVersion": "range-analytics.v1"}
    draft = build_plan_draft({"context": context, "facts": facts}, "turn-offline")
    assert draft["contract"] is None
    assert {"RANGE_CONTRACT_UNAVAILABLE", "REPLAY_NOT_EXECUTABLE"} <= set(draft["blockers"])


@pytest.mark.asyncio
@pytest.mark.parametrize("defect,reason", [
    ("coverage_count", "RANGE_COVERAGE_INVALID"), ("coverage_bool", "RANGE_COVERAGE_INVALID"),
    ("coverage_missing", "RANGE_COVERAGE_INVALID"), ("population_total", "RANGE_POPULATION_INVALID"),
    ("usable_zero", "RANGE_POPULATION_INVALID"), ("ok_null", "RANGE_GRID_INVALID"),
    ("future_event", "RANGE_CLOCK_INVALID"), ("grounding_query", "RANGE_IDENTITY_MISMATCH"),
])
async def test_strict_secondary_record_invariants(monkeypatch, defect, reason):
    env = envelope()
    section = env["grids"]["delta_weighted"]
    if defect == "coverage_count":
        env["coverage"]["n_admitted"] = 2
    elif defect == "coverage_bool":
        env["coverage"]["n_returned_expiries"] = True
    elif defect == "coverage_missing":
        env["coverage"] = {}
    elif defect == "population_total":
        section["population"]["input_contracts"] = 100
    elif defect == "usable_zero":
        section["population"]["usable"] = section["usable"] = 0
    elif defect == "ok_null":
        section["cells"]["2026-10-26"]["600"] = None
        section.update(n_available=5, cell_gaps=1)
    elif defect == "future_event":
        env["clocks"]["chain_event_time"] = "2026-10-05T15:00:00+00:00"
    elif defect == "grounding_query":
        env["grounding"]["record_query_identity"]["symbol"] = "QQQ"
    result = rebind(env)
    async with harness(monkeypatch, env=env, result=result) as h:
        await login_and_save(h)
        saved = await ask_saved(h)
        assert saved["answer"]["facts"] == []
        assert any(reason in gap for gap in saved["answer"]["gaps"])
        assert h.provider.dispatches == 0
        h.upstream.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("error,reason", [
    ("ROW_HEADER_MISMATCH", "RANGE_HEADER_MISMATCH"),
    ("DIGEST_MISMATCH", "RANGE_DIGEST_MISMATCH"),
    ("INCOMPATIBLE_CONTENT_SCHEMA", "RANGE_SCHEMA_MISMATCH"),
    ("STORE_READ_FAILED", "RANGE_READ_UNAVAILABLE"),
])
async def test_typed_store_refusals_keep_safe_semantics(monkeypatch, error, reason):
    async with harness(monkeypatch, result={"error": error, "envelope": None, "detail": "private-store-detail"}) as h:
        await login_and_save(h)
        saved = await ask_saved(h)
        assert saved["answer"]["facts"] == []
        assert any(reason in gap for gap in saved["answer"]["gaps"])
        assert "private-store-detail" not in json.dumps(saved)
        assert h.provider.dispatches == 0
        h.upstream.assert_not_called()


@pytest.mark.asyncio
async def test_direct_range_live_read_refuses_without_any_callback():
    upstream = Mock(side_effect=AssertionError("No live range fallback"))
    reads = ResearchReads(upstream, upstream, upstream)
    context = {**selection(envelope()), "displayMode": "range-live"}
    snapshot = await reads.snapshot("SPY", "all", screen=context)
    assert snapshot["facts"] == []
    assert any("RANGE_LIVE_UNAVAILABLE" in gap for gap in snapshot["gaps"])
    upstream.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_seam", "error", "timeout"])
async def test_unavailable_stored_callback_cannot_start_provider_or_fallback(monkeypatch, failure):
    async with harness(monkeypatch) as h:
        await login_and_save(h)
        if failure == "missing_seam":
            h.reads._read_recorded_range = None
        else:
            h.recorded.side_effect = TimeoutError("private detail") if failure == "timeout" else RuntimeError("private detail")
        saved = await ask_saved(h)
        assert saved["answer"]["facts"] == []
        reason = "RANGE_RECORD_UNAVAILABLE" if failure == "missing_seam" else "RANGE_READ_UNAVAILABLE"
        assert any(reason in gap for gap in saved["answer"]["gaps"])
        assert "private detail" not in json.dumps(saved)
        assert h.provider.dispatches == 0
        h.upstream.assert_not_called()


@pytest.mark.asyncio
async def test_unselected_projection_preserves_distinct_metric_ids_and_no_zero_fill():
    env = envelope()
    upstream = Mock(side_effect=AssertionError("Stored-only"))
    reads = ResearchReads(upstream, upstream, upstream, read_recorded_range=lambda *_: wrapper(env))
    ids = []
    for metric in ("raw_oi", "delta_weighted", "volume"):
        context = selection(env, metric)
        context.update(selectedStrike=None, selectedExpiry=None)
        snapshot = await reads.snapshot("SPY", "range:14:60", screen=context)
        assert len(snapshot["facts"]) == 6
        assert all(f["status"] == "degraded" and f["contract"] is None for f in snapshot["facts"])
        ids.extend(f["id"] for f in snapshot["facts"])
    assert len(set(ids)) == 18
    context = selection(env, "window")
    snapshot = await reads.snapshot("SPY", "range:14:60", screen=context)
    assert snapshot["facts"] == [] and "RANGE_WINDOW_UNAVAILABLE" in snapshot["gaps"][0]
    upstream.assert_not_called()
