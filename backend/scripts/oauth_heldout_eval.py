"""Frozen real-evidence evaluation. No app startup, journal, orders or grading.

--bind reads existing acceptance research snapshots and optionally captures missing
IBM/QQQ Public chains. --run uses only the frozen binding and the existing shared
40/day OAuth ledger. Repeated runs never redispatch an admitted evaluation turn.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import logging
import os
import re
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from services.agent.codex_model import DEFAULT_SETTINGS, CodexModel
from services.agent.contracts import canonical, request_spec
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService, deterministic_answer

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / ".planning/eval"
CASES = EVAL / "oauth-heldout-v1-cases.json"
RUBRIC = EVAL / "oauth-heldout-v1-rubric.md"
BINDING = EVAL / "oauth-heldout-v1-binding.json"
RESULTS = EVAL / "oauth-heldout-v1-results.json"
SOURCE = EVAL / "oauth-heldout-v1-sources.json"
EXPECTED_CASE_HASH = "58A18634EB3A458E467D144E981A2CEA73B9B8C8722602FA967126261676E2C1"
EXPECTED_RUBRIC_HASH = "26D53CB7E489B0DBABEAD6CF5BC0EC0DB17AD149BA8640399117A430E56D8230"
DATABASE = "floww_public_research_acceptance"
CODE_FILES = [
    "backend/services/agent/codex_bridge.py", "backend/services/agent/codex_model.py",
    "backend/services/agent/research.py", "backend/services/agent/contracts.py",
    "backend/services/agent/narrative.py", "backend/services/agent/spend.py",
]
PRICE = {"Underlying price"}
COVERAGE = {"Available contracts", "Available expiry dates"}
STRUCTURE = {"Gamma exposure strikes", "Estimated gamma exposure", "Total estimated gamma exposure", "Estimated flip levels"}
FLOW = {"Signed alert reading", "Weighted directional agreement"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, default=json_value, allow_nan=False)
        stream.write("\n")


def update_results(value):
    temporary = RESULTS.with_suffix(".json.pending")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, default=json_value, allow_nan=False)
        stream.write("\n")
    temporary.replace(RESULTS)


def frozen_protocol():
    if digest(CASES) != EXPECTED_CASE_HASH or digest(RUBRIC) != EXPECTED_RUBRIC_HASH:
        raise RuntimeError("Frozen cases or rubric changed")
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if len(cases["cases"]) != 30:
        raise RuntimeError("Expected all thirty cases")
    return cases


def code_hashes():
    return {name: digest(ROOT / name) for name in CODE_FILES}


def client():
    return AsyncIOMotorClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=2000,
                              connectTimeoutMS=2000, socketTimeoutMS=5000, tz_aware=True)


async def quota(db):
    model = CodexModel(AgentRepository(db), db.agent_oauth_usage)
    return await model.spend.state()


async def capture_missing(ticker, audit):
    # Read only the explicitly needed credential; never print or persist it.
    from dotenv import dotenv_values
    key = os.getenv("PUBLIC_API_KEY") or dotenv_values(ROOT / "backend/.env").get("PUBLIC_API_KEY")
    if not key:
        return None, "Public credential unavailable"
    os.environ["PUBLIC_API_KEY"] = key
    os.environ["FLOWW_MARKET_DATA_PROVIDER"] = "public"
    os.environ["FLOWW_ENABLE_LIVE_PUBLIC"] = "0"
    original = httpx.AsyncHTTPTransport.handle_async_request

    async def market_only(transport, request):
        path = request.url.path
        kind = None
        if request.url.host == "api.public.com":
            if request.method == "POST" and path == "/userapiauthservice/personal/access-tokens":
                kind = "authentication"
            elif request.method == "GET" and path == "/userapigateway/trading/account":
                kind = "account_metadata"
            elif request.method == "POST" and re.fullmatch(
                r"/userapigateway/marketdata/[^/]+/(quotes|option-expirations|option-chain)", path
            ):
                kind = path.rsplit("/", 1)[-1]
        if kind is None:
            raise RuntimeError("Evaluation blocked a non-market request")
        audit.append({"ticker": ticker, "kind": kind, "method": request.method})
        return await original(transport, request)

    httpx.AsyncHTTPTransport.handle_async_request = market_only
    try:
        from services.public_api_adapter import fetch_chain_from_public_api
        async with asyncio.timeout(70):
            raw = await fetch_chain_from_public_api(ticker, max_expiries=2)
        if not raw or raw.get("data_source") != "public_api":
            return None, "Actual Public chain unavailable"
        # This deliberately does not read alerts or maps from any live store.
        reads = ResearchReads(lambda *_: raw, lambda *_: None, lambda *_: [])
        snap = await reads.snapshot(ticker, "all", now=datetime.now(UTC))
        return {"snapshot": snap, "raw_public_chain": raw, "origin": "direct Public data-only capture",
                "alert_binding": "no alert facts supplied; not a claim about actual alert-store contents"}, None
    except Exception as exc:
        return None, "Public capture failed: " + type(exc).__name__
    finally:
        httpx.AsyncHTTPTransport.handle_async_request = original


def project(source, profile):
    snap = copy.deepcopy(source["snapshot"])
    facts = snap.get("facts", [])
    selected = None
    if profile in {"price", "price_only", "price_without_flip", "price_without_option_quote", "no_history"}:
        selected = PRICE
    elif profile in {"structure", "price_structure", "unknown_chain", "stale_or_unknown"}:
        selected = PRICE | COVERAGE | STRUCTURE
    elif profile == "coverage":
        selected = PRICE | COVERAGE
    elif profile in {"no_alerts", "alert_store_error"}:
        selected = {f["metric"] for f in facts} - FLOW
    if selected is not None:
        snap["facts"] = [f for f in facts if f["metric"] in selected]
    if not any(f["metric"] in FLOW for f in snap["facts"]):
        snap["flow"] = []
        snap["agreement"] = None
    if profile == "no_alerts":
        snap["alerts_status"] = "ok"
        snap["gaps"] = list(snap.get("gaps", [])) + ["No eligible directional alerts are supplied in this frozen evidence"]
    if profile == "alert_store_error":
        snap["alerts_status"] = "error"
        snap["gaps"] = list(snap.get("gaps", [])) + ["Alert storage could not be read (declared evaluation control state)"]
    return snap


async def bind(db):
    protocol = frozen_protocol()
    if BINDING.exists() or SOURCE.exists():
        raise RuntimeError("Frozen evidence already exists; refusing to replace it")
    sources, audit, missing = {}, [], {}
    # Only read saved market evidence, never session capabilities or prompts.
    cursor = db.agent_turns.find(
        {"status": "completed", "answer.snapshots.ticker": {"$in": ["SPY", "IBM", "QQQ"]}},
        {"turn_id": 1, "answer.snapshots": 1},
    ).sort("created_at", -1).limit(60)
    async for doc in cursor:
        for snap in doc.get("answer", {}).get("snapshots", []):
            ticker = snap.get("ticker")
            price_sources = [str(f.get("source", "")) for f in snap.get("facts", []) if f.get("metric") == "Underlying price"]
            if ticker in {"SPY", "IBM", "QQQ"} and ticker not in sources and any(s.startswith("public") for s in price_sources):
                sources[ticker] = {"snapshot": snap, "origin": "saved actual Public research turn",
                                   "source_turn_id": doc["turn_id"]}
    try:
        for ticker in ("IBM", "QQQ"):
            if ticker not in sources:
                data, reason = await capture_missing(ticker, audit)
                if data:
                    sources[ticker] = data
                else:
                    missing[ticker] = reason
    finally:
        from services.public_api_adapter import close_broker
        await close_broker()
    source_doc = {"frozen_at": datetime.now(UTC), "sources": sources, "missing": missing,
                  "public_request_audit": audit, "model_calls": 0}
    write_new(SOURCE, source_doc)
    # Read the serialized form so exact persisted inputs, not Python objects,
    # become the source for both arms.
    sources = json.loads(SOURCE.read_text(encoding="utf-8"))["sources"]
    binding = {"version": "oauth-heldout-binding-v1", "frozen_at": datetime.now(UTC),
               "cases_sha256": digest(CASES), "rubric_sha256": digest(RUBRIC),
               "sources_sha256": digest(SOURCE), "code_sha256": code_hashes(),
               "quota_before_binding": await quota(db), "evaluation_owner": "oauth-eval-" + uuid.uuid4().hex,
               "cases": []}
    for case in protocol["cases"]:
        entry = {"id": case["id"], "case": case, "status": "bound", "snapshots": []}
        profile, ticker = case["evidence_profile"], case["requested_ticker"]
        screen = {"ticker": case["screen_ticker"], "horizon": "all"}
        spec = request_spec({"question": case["question"], "screen": screen})
        spec["ai_settings"] = dict(DEFAULT_SETTINGS)
        entry["spec"] = spec
        reason = None
        if ticker not in sources:
            reason = "No actual frozen target-ticker snapshot"
        elif profile in {"selected_expiry", "uncovered_expiry"}:
            reason = "No independently frozen exact-expiry screen and matching scoped facts; aggregate evidence not widened"
        elif profile == "compatible_pair":
            reason = "Only one independently frozen IBM observation; no second price invented"
        else:
            snap = project(sources[ticker], profile)
            if profile == "unknown_chain" and snap.get("observed_at") is not None:
                reason = "Actual frozen chain does not have unknown observation time"
            elif profile == "stale_or_unknown" and not any(f.get("status") in {"stale", "degraded"} for f in snap["facts"]):
                reason = "No actual stale or unknown-age fact in frozen source"
            entry["snapshots"] = [snap]
            # Preserve actual request classification, including conflicts it
            # fails to recognize. Do not repair the product to match a rubric.
            for other in spec["tickers"]:
                if other != ticker and other in sources:
                    entry["snapshots"].append(project(sources[other], profile))
        if reason:
            entry.update(status="not_assessable", reason=reason)
        entry["request_id"] = f"{int(time.time() * 1000)}-{uuid.uuid4()}"
        entry["input_sha256"] = hashlib.sha256(canonical({"spec": spec, "snapshots": entry["snapshots"]}).encode()).hexdigest()
        binding["cases"].append(entry)
    write_new(BINDING, binding)
    print(json.dumps({"phase": "bound", "binding_sha256": digest(BINDING),
                      "counts": dict(Counter(c["status"] for c in binding["cases"])),
                      "source_tickers": list(sources), "public_requests": len(audit),
                      "quota": binding["quota_before_binding"]}), flush=True)


async def run(db):
    frozen_protocol()
    binding = json.loads(BINDING.read_text(encoding="utf-8"))
    if digest(SOURCE) != binding["sources_sha256"] or code_hashes() != binding["code_sha256"]:
        raise RuntimeError("Evidence or product code changed after binding")
    if RESULTS.exists():
        raise RuntimeError("Results already exist; no automatic retry of evaluated work")
    repo = AgentRepository(db)  # Never initialize: do not interrupt other live turns.
    model = CodexModel(repo, db.agent_oauth_usage)
    service = ResearchService(repo, None, model=model)
    output = {"version": "oauth-heldout-results-v1", "started_at": datetime.now(UTC),
              "binding_sha256": digest(BINDING), "candidate": dict(DEFAULT_SETTINGS),
              "quota_before": await model.spend.state(), "graded": False, "denominator": 30,
              "results": []}
    write_new(RESULTS, output)
    lock, slots = asyncio.Lock(), asyncio.Semaphore(2)

    async def one(entry):
        result = {"id": entry["id"], "input_sha256": entry["input_sha256"], "status": entry["status"],
                  "expected_model_dispatch": entry["case"]["expected_model_dispatch"]}
        if entry["status"] == "not_assessable":
            result["reason"] = entry["reason"]
        else:
            snapshots, spec = copy.deepcopy(entry["snapshots"]), copy.deepcopy(entry["spec"])
            began = time.monotonic()
            baseline = deterministic_answer(snapshots, spec)
            result["deterministic_latency_ms"] = (time.monotonic() - began) * 1000
            result["deterministic_answer"] = baseline
            candidate = copy.deepcopy(baseline)
            if not entry["case"]["expected_model_dispatch"]:
                result.update(status="assessed_factual_bypass", model_dispatches=0,
                              product_price_only=bool(spec.get("price_only")), candidate_answer=candidate,
                              dispatch_routing_matches=bool(spec.get("price_only")))
            elif not any(f["metric"] == "Underlying price" for f in candidate["facts"]):
                result.update(status="assessed_no_price_model_bypass", model_dispatches=0,
                              candidate_answer=candidate)
            else:
                async with slots:
                    if code_hashes() != binding["code_sha256"]:
                        result.update(status="code_changed_not_run", reason="Frozen product changed; no dispatch")
                    else:
                        doc, created = await repo.admit(binding["evaluation_owner"], entry["request_id"], spec)
                        result["turn_id"] = doc["turn_id"]
                        if not created:
                            result.update(status="previously_admitted_not_retried", reason="Never replay uncertain evaluation work")
                        else:
                            began = time.monotonic()
                            try:
                                async with asyncio.timeout(120):
                                    await service._interpret(binding["evaluation_owner"], doc["turn_id"], spec, candidate, snapshots)
                                result["candidate_answer"] = candidate
                                result["candidate_latency_ms"] = (time.monotonic() - began) * 1000
                                result["model_dispatches"] = sum(bool(u.get("reservation_id")) for u in candidate.get("usage", []))
                                result["status"] = "assessed_model_assisted" if candidate.get("mode") == "model-assisted" else "assessed_deterministic_fallback"
                                await repo.finish(binding["evaluation_owner"], doc["turn_id"], "completed", answer=candidate)
                            except Exception as exc:
                                result.update(status="transport_failed", error_type=type(exc).__name__,
                                              candidate_answer=candidate, candidate_latency_ms=(time.monotonic()-began)*1000)
                                await repo.finish(binding["evaluation_owner"], doc["turn_id"], "failed", error="Frozen evaluation did not complete")
        async with lock:
            output["results"].append(result)
            output["results"].sort(key=lambda r: r["id"])
            update_results(output)
            print(json.dumps({"case": result["id"], "status": result["status"],
                              "completed": len(output["results"])}), flush=True)

    try:
        await asyncio.gather(*(one(entry) for entry in binding["cases"]))
    finally:
        output["finished_at"] = datetime.now(UTC)
        output["quota_after"] = await model.spend.state()
        output["counts"] = dict(Counter(row["status"] for row in output["results"]))
        output["actual_cost"] = None
        output["accounting"] = "Shared subscription dispatch quota; actual dollar cost not reported"
        update_results(output)
        await service.close()
    print(json.dumps({"phase": "complete", "counts": output["counts"], "quota_after": output["quota_after"],
                      "results_sha256": digest(RESULTS), "graded": False}), flush=True)


async def main(args):
    logging.disable(logging.CRITICAL)
    mongo = client()
    try:
        db = mongo[DATABASE]
        print(json.dumps({"quota_preflight": await quota(db)}), flush=True)
        if args.bind:
            await bind(db)
        elif args.run:
            await run(db)
    finally:
        mongo.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bind", action="store_true")
    group.add_argument("--run", action="store_true")
    asyncio.run(main(parser.parse_args()))
