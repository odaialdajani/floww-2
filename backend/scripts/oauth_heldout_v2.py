"""Frozen recorded-input replay, isolated storage, and unchanged shared AI quota.

prepare materializes declared failure recipes, without answers or model calls.
check runs all thirty real research routes with the deterministic baseline.
run requires the entire candidate allowance before admission; never raises quota.
Original questions, sources, proposal and failed earlier evaluations are immutable.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from services.agent.codex_bridge import executable
from services.agent.codex_model import DEFAULT_SETTINGS, CodexModel
from services.agent.contracts import canonical
from services.agent.local_access import COOKIE
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / ".planning/eval"
PROPOSAL = EVAL / "oauth-heldout-v2-binding-proposal.json"
PROPOSAL_HASH = "c015fbabdcab76d9b750ae1df1945b0f56628050f704d2a2023ff575b63f1dd8"
BOUND = EVAL / "oauth-heldout-v2-inputs.json"
SEAL = EVAL / "oauth-heldout-v2-execution-seal.json"
SHARED_USAGE_DB = "floww_public_research_acceptance"
DATA_URI = "mongodb://127.0.0.1:27017"
USAGE_URI = DATA_URI
EXTERNAL_FILES = (
    "backend/scripts/oauth_heldout_v2.py", "backend/services/heatseeker.py",
    "backend/services/market_provenance.py", "backend/services/gex_core.py",
    "backend/services/realized_volatility.py", "backend/bs_greeks.py",
    "backend/auth.py", "config/agent_weights_v1.json",
)
PACKAGES = ("exchange-calendars", "numpy", "pandas", "scipy", "pydantic", "fastapi",
            "starlette", "motor", "pymongo", "httpx")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False, default=str)
        stream.write("\n")


def reference(path, pointer=""):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path), "pointer": pointer}


def resolve(ref):
    path = ROOT / ref["path"]
    if sha(path) != ref["sha256"]:
        raise ValueError(f"Frozen input changed: {ref['path']}")
    data = read(path)
    for part in ref.get("pointer", "").split("/")[1:]:
        data = data[int(part)] if isinstance(data, list) else data[part]
    return copy.deepcopy(data)


def execution_seal():
    binary = Path(executable())
    return {"inputs_sha256": sha(BOUND), "python": platform.python_version(),
            "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
            "external_files": {name: sha(ROOT / name) for name in EXTERNAL_FILES},
            "codex_executable_sha256": sha(binary),
            "storage": {"data_uri": DATA_URI, "usage_uri": USAGE_URI, "usage_database": SHARED_USAGE_DB}}


def seal():
    write_new(SEAL, execution_seal())
    return {"status": "execution_sealed", "model_calls": 0}


def select_revision(revision, usage_uri):
    """Select new artifact names; old frozen evidence is never overwritten."""
    global BOUND, SEAL, USAGE_URI
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", revision):
        raise ValueError("Revision must be a simple lowercase label")
    if not re.fullmatch(r"mongodb://127\.0\.0\.1:(?:27017|27018)", usage_uri):
        raise ValueError("Evaluation usage storage must be an explicit local endpoint")
    BOUND = EVAL / f"oauth-heldout-v2-{revision}-inputs.json"
    SEAL = EVAL / f"oauth-heldout-v2-{revision}-execution-seal.json"
    USAGE_URI = usage_uri


def refreeze():
    """Preserve every question/source/criterion; bind updated executable code."""
    original = EVAL / "oauth-heldout-v2-inputs.json"
    old_seal = EVAL / "oauth-heldout-v2-execution-seal.json"
    if original == BOUND or BOUND.exists() or SEAL.exists():
        raise ValueError("A new unused revision is required")
    prior = read(original)
    if read(old_seal).get("inputs_sha256") != sha(original):
        raise ValueError("Original prepared inputs differ from their preserved seal")
    resolve(prior["proposal"])
    refreshed = copy.deepcopy(prior)
    refreshed["code"] = {name: sha(ROOT / name) for name in prior["code"]}
    refreshed["resumption"] = {
        "previous_inputs": reference(original), "previous_execution_seal": reference(old_seal),
        "reason": "Main integration changed code; all original cases and sources retained",
        "changed_code": {name: {"before": prior["code"][name], "after": current}
                         for name, current in refreshed["code"].items() if current != prior["code"][name]},
        "usage_anchor": {"_id": "day:2026-09-11", "minimum_calls": 34},
    }
    if len(refreshed["cases"]) != 30:
        raise ValueError("All original cases must remain")
    write_new(BOUND, refreshed)
    seal()
    return {"status": "RESUMPTION_SEALED", "cases": 30, "model_calls": 0}


def prepare():
    if BOUND.exists():
        raise ValueError("Prepared inputs already exist; refusing replacement")
    if sha(PROPOSAL) != PROPOSAL_HASH:
        raise ValueError("Independent proposal changed")
    proposal = read(PROPOSAL)
    for ref in proposal["source_files"].values():
        if sha(ROOT / ref["path"]) != ref["sha256"]:
            raise ValueError("Original frozen protocol/source changed")
    sources_path = EVAL / "oauth-heldout-v2-sources.json"
    maps_path = EVAL / "oauth-heldout-v2-maps.json"
    aapl_path = EVAL / "oauth-heldout-v2-aapl-source.json"
    aapl = read(aapl_path)
    if not aapl.get("source", {}).get("raw_public_chain"):
        raise ValueError("AAPL recorded source is missing")
    sources = read(sources_path)
    maps = read(maps_path)
    derived_path = EVAL / "oauth-heldout-v2-derived-inputs.json"
    prior = copy.deepcopy(sources["sources"]["IWM"]["source"]["raw_public_chain"])
    current = copy.deepcopy(prior)
    map_iwm = maps["maps"]["IWM"]["body"]
    for field in ("spot", "spot_source", "spot_event_time", "spot_fetched_at"):
        current[field] = map_iwm[field]
    prior["contracts"] = [c for c in prior["contracts"] if c["expiry"] == "2026-09-14"]
    prior["expiries"] = ["2026-09-14"]
    stale_map = copy.deepcopy(maps["maps"]["SPY"]["body"])
    recipe = next(c for c in proposal["cases"] if c["case_id"] == "source_24")["synthetic_recipes"][0]
    for field, change in recipe["changes"].items():
        stale_map[field] = change["after"]
    write_new(derived_path, {
        "label": "SYNTHETIC failure conditions assembled from recorded Public inputs",
        "proposal": reference(PROPOSAL), "history_prior": prior,
        "history_current": current, "stale_map": stale_map,
        "recipes": [c["synthetic_recipes"] for c in proposal["cases"] if c["synthetic_recipes"]],
    })
    cases = []
    for index, case in enumerate(proposal["cases"]):
        item = {
            "id": case["case_id"], "body": case["request_body_proposal"],
            "clock": case["evaluation_clock_utc"], "route": case["original_route_expectation"],
            "evidence_class": case["evidence_class"],
            "expected": reference(PROPOSAL, f"/cases/{index}/independent_expected"),
            "chains": {ticker: reference(sources_path, f"/sources/{ticker}/source/raw_public_chain")
                       for ticker in case["independent_expected"]["tickers"] if ticker in sources["sources"]},
            "maps": {ticker: reference(maps_path, f"/maps/{ticker}/body")
                     for ticker in case["independent_expected"]["tickers"] if ticker in maps["maps"]},
            "prior": None, "events": case["independent_expected"].get("event_order", []),
            "alerts": "No recorded alert store supplied; read unavailable, never asserted empty",
        }
        if item["id"] == "map_18":
            item["maps"] = {}
        elif item["id"] == "history_22":
            item["chains"]["IWM"] = reference(derived_path, "/history_current")
            item["prior"] = reference(derived_path, "/history_prior")
        elif item["id"] == "source_24":
            item["maps"]["SPY"] = reference(derived_path, "/stale_map")
        elif item["id"] == "unsupported_27":
            item["chains"]["AAPL"] = reference(aapl_path, "/source/raw_public_chain")
            item["clock"] = aapl["captured_at"]
            item["supplement"] = "Actual AAPL capture replaces proposal's missing input only; company/news remain unavailable. Separate later recorded clock."
        cases.append(item)
    code = {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path)
            for path in sorted((ROOT / "backend/services/agent").rglob("*.py"))}
    code["backend/routes/agent.py"] = sha(ROOT / "backend/routes/agent.py")
    write_new(BOUND, {
        "status": "INPUTS_FROZEN_ROUTE_CHECK_REQUIRED", "proposal": reference(PROPOSAL),
        "cases": cases, "candidate": DEFAULT_SETTINGS, "code": code,
        "required_model_allowance": 26, "quota_policy": "Existing shared40/day; no override or reset",
        "comparison": "One production candidate versus deterministic baseline; second candidate is optional, not a plan gate",
        "model_calls": 0,
    })
    return {"prepared_cases": len(cases), "model_calls": 0, "status": "route_check_required"}


class ReplayReads(ResearchReads):
    def __init__(self, item):
        self.item = item
        self.release = asyncio.Event()
        chains = {ticker: resolve(ref) for ticker, ref in item["chains"].items()}
        maps = {ticker: resolve(ref) for ticker, ref in item["maps"].items()}
        def alerts(_ticker):
            raise RuntimeError("No recorded alert store supplied")
        super().__init__(lambda ticker, _: chains.get(ticker), lambda ticker, _: maps.get(ticker), alerts)

    async def snapshot(self, *args, **kwargs):
        await self.release.wait()
        kwargs["now"] = datetime.fromisoformat(self.item["clock"])
        return await super().snapshot(*args, **kwargs)


def close_number(actual, expected):
    return isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isclose(
        actual, float(expected), rel_tol=1e-10, abs_tol=1e-8)


def check_facts(item, doc):
    """Fixed input/grounding checks, not an automated usefulness grader."""
    expected = resolve(item["expected"])
    answer = doc["answer"]
    facts = answer["facts"]
    errors = []
    def require(condition, reason):
        if not condition:
            errors.append(reason)
    require(doc["spec"]["tickers"] == expected["tickers"], "requested ticker scope")
    require(answer["context"] == item["body"]["screen"], "frozen screen context")
    for snap in answer["snapshots"]:
        ticker = snap["ticker"]
        require(snap["captured_at"] == item["clock"], "recorded clock")
        by_metric = {f["metric"]: f for f in snap["facts"]}
        quote = expected.get("quotes", {}).get(ticker)
        if item["id"] == "history_22":
            quote = expected["history"]["current_quote"]
        if quote:
            price = by_metric.get("Underlying price", {})
            require(close_number(price.get("value"), quote["value"]), f"{ticker} price")
            require(price.get("unit") == quote["unit"], f"{ticker} price unit")
            require(price.get("event_time") == quote["source_observed_at"], f"{ticker} source time")
            require(price.get("status") == quote["expected_quality"], f"{ticker} source quality")
        if item["id"] == "unsupported_27":
            raw = resolve(item["chains"]["AAPL"])
            price = by_metric.get("Underlying price", {})
            require(close_number(price.get("value"), raw["spot"]), "AAPL actual captured price")
            require(price.get("event_time") == raw["spot_event_time"], "AAPL actual quote time")
        contract = expected.get("contracts_by_ticker", {}).get(ticker)
        if contract and not doc["spec"].get("price_only"):
            require(by_metric.get("Available contracts", {}).get("value") == contract["contract_count"], f"{ticker} contract coverage")
            require(by_metric.get("Available expiry dates", {}).get("value") == contract["available_expiry_dates"], f"{ticker} expiry coverage")
    if item["id"].startswith("history_"):
        require(not any(f["metric"] == "Price change since saved observation" for f in facts), "unsupported historical change")
        # Whether the answer explains the seeded mismatch is a usefulness
        # criterion for the independent grader, not an input-setup gate.
    if "display_map_unavailable" in expected:
        require(not any(f["metric"].startswith("Displayed") for f in facts), "missing map substituted")
    display = expected.get("display_map")
    if display:
        chosen = next((f for f in facts if f["metric"] == "Selected display cell"), None)
        cell = display.get("selected_nonempty_cell")
        if cell and cell.get("selected_in_request"):
            require(chosen is not None, "selected map cell absent")
            if chosen:
                require(close_number(chosen["value"], cell["value"]), "selected map cell value")
                require(chosen["unit"] == display["display_unit"], "selected map cell unit")
                parts = chosen.get("contract", "").split(":")
                require(len(parts) == 3 and parts[0] == cell["expiry"]
                        and close_number(float(parts[1]), cell["strike"])
                        and parts[2] == cell["metric"], "selected map cell identity")
        elif cell:
            require(chosen is None, "unselected cell was invented")
        flip = next((f for f in facts if f["metric"] == "Displayed flip"), None)
        if display.get("map_level_flip") is not None:
            require(flip is not None and close_number(flip["value"], display["map_level_flip"]), "whole map flip")
        for fact in facts:
            if fact["metric"].startswith("Displayed"):
                require(fact["status"] == display["expected_map_quality"], "map source quality")
        # Solstice displays cells; only Tidehunter displays these summed bars.
        if item["body"]["screen"].get("page") == "flowseeker-pro":
            strikes = next((f["value"] for f in facts if f["metric"] == "Displayed strikes"), [])
            bars = next((f["value"] for f in facts if f["metric"] == "Displayed net gamma"), [])
            expected_rows = {row["strike"]: row["net"] for row in display["display_rows"]}
            require(len(strikes) == len(bars) == len(expected_rows), "displayed bar coverage")
            for strike, value in zip(strikes, bars, strict=False):
                target = expected_rows.get(strike)
                require(value is None if target is None else close_number(value, target), "displayed bar value")
    return errors


async def exercise(item, repository, model):
    # Mount only the production research routes, never server/background feeds.
    from routes.agent import router
    reads = ReplayReads(item)
    service = ResearchService(repository, reads, model=model)
    app = FastAPI()
    app.include_router(router)
    app.state.research_service = service
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000",
                                headers={"Origin": "http://localhost:8000"}) as browser:
        session = await browser.post("/api/agent/session")
        if session.status_code != 200:
            raise RuntimeError("Isolated owner creation failed")
        owner = await repository.owner(browser.cookies.get(COOKIE))
        if await repository.turns.count_documents({"owner": owner}) != 0:
            raise RuntimeError("Expected a new empty owner")
        history_setup = {"owned_turns_before_seed": 0, "prior_coverage_id": None}
        if item["prior"]:
            prior_raw = resolve(item["prior"])
            prior_reads = ResearchReads(lambda *_: prior_raw, lambda *_: None, lambda *_: [])
            prior = await prior_reads.snapshot("IWM", "all", now=datetime.fromisoformat(item["clock"]))
            if len(prior_raw["contracts"]) != 166:
                raise ValueError("Frozen prior coverage differs from the independent proposal")
            history_setup["prior_coverage_id"] = prior["coverage_id"]
            # Controlled owned earlier observation, with actual older quote and
            # explicitly synthetic reduced coverage. No model or inferred fill.
            await repository.turns.insert_one({
                "owner": owner, "turn_id": str(uuid.uuid4()),
                "request_id": f"{int(time.time()*1000)}-{uuid.uuid4()}",
                "status": "completed", "created_at": datetime.now(UTC),
                "answer": {"snapshots": [prior]},
            })
        body = copy.deepcopy(item["body"])
        body["request_id"] = f"{int(time.time()*1000)}-{uuid.uuid4()}"
        started = time.monotonic()
        admission = await browser.post("/api/agent/ask", json=body)
        if item["route"] == "reject":
            reads.release.set()
            return {"id": item["id"], "http_status": admission.status_code,
                    "errors": [] if admission.status_code == 422 else ["ticker limit did not refuse"],
                    "elapsed_s": time.monotonic() - started, "route_rejection": admission.json()}
        if admission.status_code != 200:
            reads.release.set()
            return {"id": item["id"], "http_status": admission.status_code,
                    "errors": ["ask admission failed"], "admission": admission.json()}
        turn_id = admission.json()["turn_id"]
        if item["events"]:
            body["screen"] = copy.deepcopy(item["events"][1]["screen"])
        reads.release.set()
        await asyncio.wait_for(asyncio.gather(*list(service.tasks.values())), timeout=135)
        response = await browser.get(f"/api/agent/turn/{turn_id}")
        if response.status_code != 200:
            raise RuntimeError("Saved answer could not be reopened")
        doc = response.json()
        if doc.get("status") != "completed" or not doc.get("answer"):
            return {"id": item["id"], "errors": ["research did not complete"], "saved_turn": doc}
        again = (await browser.get(f"/api/agent/turn/{turn_id}")).json()
        errors = check_facts(item, doc)
        if item["prior"] and doc["answer"]["snapshots"][0]["coverage_id"] == history_setup["prior_coverage_id"]:
            errors.append("Seeded prior coverage does not differ")
        if doc != again:
            errors.append("reloaded answer changed")
        history = (await browser.get("/api/agent/history")).json()
        if not any(t["turn_id"] == turn_id for t in history.get("turns", [])):
            errors.append("saved answer missing from owned history")
        # A distinct owner cannot read this turn. Do not serialize capabilities.
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000",
                                     headers={"Origin": "http://localhost:8000"}) as stranger:
            await stranger.post("/api/agent/session")
            if (await stranger.get(f"/api/agent/turn/{turn_id}")).status_code != 404:
                errors.append("owner isolation failed")
        return {"id": item["id"], "http_status": response.status_code, "errors": errors,
                "elapsed_s": time.monotonic()-started, "saved_turn": doc,
                "fact_hash": hashlib.sha256(canonical(doc["answer"]["facts"]).encode()).hexdigest(),
                "history_reopen": not errors, "events": item["events"], "history_setup": history_setup}


def validate_resumption(bound):
    original = EVAL / "oauth-heldout-v2-inputs.json"
    if original == BOUND:
        return None
    metadata = bound.get("resumption")
    anchor = {"_id": "day:2026-09-11", "minimum_calls": 34}
    if not isinstance(metadata, dict) or metadata.get("usage_anchor") != anchor:
        raise ValueError("Revision requires the preserved usage anchor")
    parent = resolve(metadata["previous_inputs"])
    previous_seal = resolve(metadata["previous_execution_seal"])
    if previous_seal.get("inputs_sha256") != metadata["previous_inputs"]["sha256"]:
        raise ValueError("Original inputs do not match their preserved execution seal")
    for key, value in parent.items():
        if key != "code" and bound.get(key) != value:
            raise ValueError(f"Resumption changed an original evaluation field: {key}")
    return anchor


async def execute(mode, output, baseline=None):
    if output.exists():
        raise ValueError("Run output exists; no repeat dispatch or overwrite")
    bound = read(BOUND)
    if read(SEAL) != execution_seal():
        raise ValueError("Execution code, dependencies or managed binary changed after sealing")
    anchor = validate_resumption(bound)
    resolve(bound["proposal"])
    for name, expected in bound["code"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"Frozen research code changed: {name}")
    if len(bound["cases"]) != 30:
        raise ValueError("Every frozen case must stay in the denominator")
    for item in bound["cases"]:
        for ref in [*item["chains"].values(), *item["maps"].values(), item["expected"], item["prior"]]:
            if ref:
                resolve(ref)
    original_http = httpx.AsyncHTTPTransport.handle_async_request
    async def no_http(*_args, **_kwargs):
        raise RuntimeError("Recorded replay forbids external HTTP")
    connection = AsyncIOMotorClient(DATA_URI, tz_aware=True,
                                    serverSelectionTimeoutMS=2000, socketTimeoutMS=5000)
    usage_connection = AsyncIOMotorClient(USAGE_URI, tz_aware=True,
                                         serverSelectionTimeoutMS=2000, socketTimeoutMS=5000)
    try:
        database = "test_floww_v2_" + uuid.uuid4().hex
        repository = AgentRepository(connection[database])
        usage_collection = usage_connection[SHARED_USAGE_DB].agent_oauth_usage
        if anchor:
            observed = await usage_collection.find_one({"_id": anchor["_id"]})
            if not observed or observed.get("calls", 0) < anchor["minimum_calls"]:
                raise ValueError("Preserved shared usage ledger was not found; no quota reset allowed")
        model = CodexModel(repository, usage_collection)
        state = await model.spend.state()
        baseline_rows = {}
        if mode == "run":
            if baseline is None:
                raise ValueError("A passed frozen route baseline is required")
            report = read(baseline)
            if (report.get("status") != "ROUTE_CHECKS_PASSED" or report.get("inputs_sha256") != sha(BOUND)
                    or report.get("execution_seal_sha256") != sha(SEAL)):
                raise ValueError("Baseline did not pass against these exact inputs")
            if state["daily_limit"] - state["calls"] < bound["required_model_allowance"]:
                raise ValueError("Insufficient existing daily allowance for the complete candidate; no calls made")
            await model.validate_settings(bound["candidate"])
            baseline_rows = {r["id"]: r for r in report["cases"]}
        await repository.initialize()
        results = {"mode": mode, "status": "RUNNING", "inputs_sha256": sha(BOUND),
                   "execution_seal_sha256": sha(SEAL),
                   "database": database, "started_at": datetime.now(UTC).isoformat(),
                   "candidate": bound["candidate"] if mode == "run" else None,
                   "quota_before": state, "cases": [], "provider_requests": 0,
                   "usefulness_assessment": "NOT_GRADED; requires independent frozen-rubric review"}
        write_new(output, results)
        def checkpoint():
            temporary = output.with_suffix(".pending")
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(results, stream, indent=2, allow_nan=False, default=str)
                stream.write("\n")
            temporary.replace(output)
        try:
            httpx.AsyncHTTPTransport.handle_async_request = no_http
            with patch.dict(os.environ, {"FLOWW_AGENT_DEPLOYMENT": "local",
                                         "FLOWW_AGENT_ORIGINS": "http://localhost:8000",
                                         "FLOWW_AGENT_DISABLED": "0"}):
                for item in bound["cases"]:
                    result = await exercise(item, repository, model if mode == "run" else None)
                    if mode == "run" and result.get("fact_hash") != baseline_rows[item["id"]].get("fact_hash"):
                        result["errors"].append("Candidate and baseline facts differ")
                    answer = result.get("saved_turn", {}).get("answer", {})
                    uses = answer.get("usage", [])
                    if mode == "run" and item["route"] == "interpretation":
                        if answer.get("mode") != "model-assisted" or not any(u.get("reservation_id") for u in uses):
                            result["errors"].append("Candidate interpretation incomplete; retained in denominator")
                        for use in uses:
                            if any(use.get(k) != bound["candidate"][k] for k in ("model", "effort", "speed")):
                                result["errors"].append("Candidate settings differ from frozen settings")
                    elif any(u.get("reservation_id") for u in uses):
                        result["errors"].append("Unexpected model dispatch on bypass/rejection/baseline")
                    results["cases"].append(result)
                    checkpoint()
            results["quota_after"] = await model.spend.state()
            results["shared_quota_change"] = results["quota_after"]["calls"] - state["calls"]
            reservations = {u["reservation_id"] for c in results["cases"]
                            for u in c.get("saved_turn", {}).get("answer", {}).get("usage", [])
                            if u.get("reservation_id")}
            results["model_calls"] = len(reservations)
            results["model_accounting"] = "Unique saved application dispatch reservations; not upstream attempt count or dollar cost"
            results["errors"] = sum(len(c["errors"]) for c in results["cases"])
            results["status"] = ("ROUTE_CHECKS_PASSED" if mode == "check" else "CANDIDATE_RECORDED_NOT_GRADED") if not results["errors"] else "FAILED"
            checkpoint()
            return {"status": results["status"], "cases": len(results["cases"]),
                    "errors": results["errors"], "model_calls": results["model_calls"]}
        finally:
            httpx.AsyncHTTPTransport.handle_async_request = original_http

    finally:
        connection.close()
        usage_connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "seal", "check", "run", "refreeze"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--usage-uri", default=DATA_URI)
    args = parser.parse_args()
    if args.revision:
        if args.mode in {"prepare", "seal"}:
            parser.error("Revisions must use refreeze to preserve the original cases and usage anchor")
        select_revision(args.revision, args.usage_uri)
    elif args.mode == "refreeze" or args.usage_uri != DATA_URI:
        parser.error("A new --revision is required for resumption or separate usage storage")
    if args.mode == "refreeze":
        result = refreeze()
    elif args.mode == "prepare":
        result = prepare()
    elif args.mode == "seal":
        result = seal()
    else:
        if args.output is None:
            parser.error("--output is required and must not exist")
        result = asyncio.run(execute(args.mode, args.output, args.baseline))
    print(json.dumps(result))
    if result.get("status") == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
