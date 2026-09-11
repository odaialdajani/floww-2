"""Three exposed-case development checks, never a held-out acceptance claim.

Uses the prior immutable real evidence and existing global subscription quota.
No new market reads, orders, journal writes or automatic retries.
"""
import asyncio
import copy
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime

from scripts.oauth_heldout_eval import DATABASE, EVAL, client, digest, write_new
from services.agent.codex_model import DEFAULT_SETTINGS, CodexModel
from services.agent.contracts import canonical
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService, deterministic_answer


async def main():
    binding = json.loads((EVAL / "oauth-heldout-v1-binding.json").read_text(encoding="utf-8"))
    target = EVAL / "oauth-development-20260911.json"
    if target.exists():
        raise RuntimeError("Development results already exist; refusing retry")
    selected = [copy.deepcopy(c) for c in binding["cases"] if c["id"] in {"OH1-13", "OH1-15", "OH1-29"}]
    assert len(selected) == 3 and all(c["status"] != "not_assessable" for c in selected)
    inputs = dict(kind="exposed development, not unseen acceptance", cases=selected,
                  original_binding_sha256=digest(EVAL / "oauth-heldout-v1-binding.json"),
                  frozen_at=datetime.now(UTC), candidate=dict(DEFAULT_SETTINGS))
    write_new(EVAL / "oauth-development-20260911-inputs.json", inputs)
    mongo = client()
    db = mongo[DATABASE]
    repo = AgentRepository(db)
    model = CodexModel(repo, db.agent_oauth_usage)
    service = ResearchService(repo, None, model=model)
    output = dict(kind=inputs["kind"], quota_before=await model.spend.state(), results=[])
    write_new(target, output)
    owner = "development-" + str(uuid.uuid4())
    try:
        for entry in selected:
            snapshots, spec = entry["snapshots"], entry["spec"]
            spec["ai_settings"] = dict(DEFAULT_SETTINGS)
            request_id = f"{int(time.time()*1000)}-{uuid.uuid4()}"
            doc, created = await repo.admit(owner, request_id, spec)
            assert created
            baseline = deterministic_answer(snapshots, spec)
            candidate = copy.deepcopy(baseline)
            started = time.monotonic()
            await service._interpret(owner, doc["turn_id"], spec, candidate, snapshots)
            await repo.finish(owner, doc["turn_id"], "completed", answer=candidate)
            output["results"].append(dict(case=entry["id"], question=spec["question"],
                input_sha256=hashlib.sha256(canonical({"spec":spec,"snapshots":snapshots}).encode()).hexdigest(),
                deterministic_answer=baseline, candidate_answer=candidate,
                elapsed_ms=(time.monotonic()-started)*1000))
            output["quota_after"] = await model.spend.state()
            pending = target.with_suffix(".pending")
            pending.write_text(json.dumps(output, indent=2, allow_nan=False), encoding="utf-8")
            pending.replace(target)
            print(json.dumps({"case":entry["id"], "mode":candidate.get("mode"),
                              "explanations":len(candidate.get("model_explanations",[]))}), flush=True)
    finally:
        await service.close()
        mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
