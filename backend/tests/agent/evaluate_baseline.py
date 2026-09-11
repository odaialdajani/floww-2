"""Offline functional baseline capture; no model or market network requests.

Run from backend: python -m tests.agent.evaluate_baseline
Human usefulness and production-store recovery remain explicitly unscored.
"""

import argparse
import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from mongomock_motor import AsyncMongoMockClient

from services.agent.contracts import canonical, request_spec
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService

ROOT = Path(__file__).resolve().parents[3] / ".planning" / "eval" / "lodestar-research-v1"


def fixture_reads(case, observed):
    variant = case["fixture"]

    def chain(ticker, count):
        if variant == "missing":
            return None
        stamp = observed
        if variant == "unknown_time":
            stamp = None
        elif variant == "stale":
            stamp = "2026-09-10T15:00:00+00:00"
        elif variant == "future":
            stamp = "2026-09-12T15:00:00+00:00"
        spot = {"SPY": 500, "QQQ": 450, "IWM": 210, "AAPL": 220, "SPX": 5000}[ticker]
        contracts = [
            {"strike": spot, "type": "C", "gamma": 0.01, "open_interest": 100, "expiry": "2026-09-18"},
            {"strike": spot + 5, "type": "P", "gamma": 0.02, "open_interest": 80, "expiry": "2026-09-18"},
        ]
        if variant == "empty":
            contracts = []
        elif variant == "partial_gamma":
            contracts[0].pop("gamma")
        elif variant == "zero_oi":
            for contract in contracts:
                contract["open_interest"] = 0
        return {
            "spot": spot,
            "contracts": contracts,
            "source": "synthetic frozen functional fixture",
            "event_time": stamp,
            "fetched_at": observed,
        }

    def alerts(ticker):
        if variant == "flow_error":
            raise RuntimeError("Synthetic unavailable store")
        if variant == "mixed_flow":
            return [
                {"under": ticker, "bias": bias, "conviction": 80, "asof_ts": observed}
                for bias in ("bullish", "bearish")
            ]
        return []

    class FrozenReads(ResearchReads):
        async def snapshot(self, ticker, horizon, **kwargs):
            kwargs["now"] = datetime.fromisoformat(observed)
            return await super().snapshot(ticker, horizon, **kwargs)

    return FrozenReads(chain, lambda ticker: None, alerts)


async def capture(output):
    if output.exists():
        raise FileExistsError("Evaluation output already exists; choose a new named output to preserve prior evidence")
    raw = (ROOT / "questions.json").read_text(encoding="utf-8").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != (ROOT / "SHA256.txt").read_text().split()[0]:
        raise ValueError("Frozen prompt manifest changed")
    manifest = json.loads(raw)
    results = []
    for case in manifest["cases"]:
        entry = {"case": case["case"], "human_usefulness": "unscored", "human_rubric": case["human_rubric"]}
        try:
            spec = request_spec(case["request"])
        except ValueError as exc:
            entry.update(
                admission="rejected",
                reason=str(exc),
                automatic_contract="pass" if case["expected_rejection"] else "fail",
            )
            results.append(entry)
            continue
        repository = AgentRepository(AsyncMongoMockClient().test)
        await repository.initialize()
        service = ResearchService(repository, fixture_reads(case, manifest["fixture_observed_at"]))
        started = time.perf_counter()
        first_progress = None
        original_progress = repository.progress

        async def measured_progress(*args, _progress=original_progress, _started=started):
            nonlocal first_progress
            accepted = await _progress(*args)
            if accepted and first_progress is None:
                first_progress = round((time.perf_counter() - _started) * 1000, 3)
            return accepted

        repository.progress = measured_progress
        turn = await service.ask("functional-owner", f"{int(time.time() * 1000)}-{uuid.uuid4()}", spec)
        task = service.tasks[turn["turn_id"]]
        await asyncio.wait_for(task, 5)
        saved = await repository.read("functional-owner", turn["turn_id"])
        answer = saved.get("answer")
        reloaded = await repository.read("functional-owner", turn["turn_id"])
        good = (
            not case["expected_rejection"]
            and saved["status"] == "completed"
            and answer["requested_tickers"] == case["expected_tickers"]
            and canonical(answer) == canonical(reloaded["answer"])
            and await repository.read("another-owner", turn["turn_id"]) is None
        )
        entry.update(
            admission="accepted",
            automatic_contract="pass" if good else "fail",
            final_status=saved["status"],
            final_answer=answer,
            first_progress_ms=first_progress,
            final_saved_ms=round((time.perf_counter() - started) * 1000, 3),
            provider_requests=0,
            actual_model_cost="0",
            production_storage_proof=False,
        )
        results.append(entry)
        await service.close()
    report = {
        "version": "deterministic-functional-1",
        "questions_sha256": digest,
        "storage": "in-memory Mongo-compatible fixture; NOT production persistence proof",
        "measurement": "Offline contract and saved-answer capture only; not model usefulness or trading evidence",
        "latency_scope": "Local fixture storage; first accepted progress write and final saved answer. Not browser or production latency.",
        "model": None,
        "provider": None,
        "model_prompt": None,
        "source_sha256": {
            str(path.relative_to(Path(__file__).resolve().parents[2])): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((Path(__file__).resolve().parents[2] / "services" / "agent").rglob("*.py"))
        },
        "automatic_pass": sum(r["automatic_contract"] == "pass" for r in results),
        "automatic_fail": sum(r["automatic_contract"] == "fail" for r in results),
        "human_unscored": len(results),
        "results": results,
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(
        f"Captured {len(results)} baseline cases: {report['automatic_pass']} contract passes, "
        f"{report['automatic_fail']} failures; all human usefulness scores remain unscored"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "baseline-offline.json")
    asyncio.run(capture(parser.parse_args().output))
