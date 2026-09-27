"""Opt-in isolated real-store proof of pure risk candidates, not admission."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from scripts.verify_paper_storage import check, client, test_database
from services.agent.paper.execution import new_book, recovery_events
from services.agent.paper.policy import create_policy, prepare_policy_change
from services.agent.paper.repository import PaperConflict, PaperRepository, operation_id
from services.agent.paper.risk import prepare_fill, prepare_stage

# These owner-selected values belong only to a synthetic test fixture.
fixture_path = Path(__file__).resolve().parents[2] / "tests" / "test_agent_paper_risk.py"
spec = importlib.util.spec_from_file_location("paper_risk_fixture", fixture_path)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


async def execute(args):
    connection = client()
    try:
        await connection.admin.command("ping")
        if args.recover:
            saved = json.loads(Path(args.recover).read_text(encoding="utf8"))
            repo = PaperRepository(connection[test_database(saved["database"])])
            doc = await repo.read(saved["owner"], saved["account"])
            check(doc["state"] == saved["state"] and doc["version"] == saved["version"], "exact reopen")
            check(doc["pending_events"] == saved["events"], "exact pending decisions reopened")
            await repo.project(saved["owner"], saved["account"])
            reopened = await repo.read(saved["owner"], saved["account"])
            check(reopened["state"] == saved["state"] and not reopened["pending_events"], "projection preserves state and drains pending events")
            history = await repo.events.find({"scope_id": doc["_id"]}).sort("version", 1).to_list(length=100)
            check(history == saved["events"], "every projected immutable decision is exact")
            return dict(status="recovered", process=os.getpid())
        if not args.run or not args.report:
            raise ValueError("Explicit --run and new report path required")
        report = Path(args.report)
        if report.exists():
            raise ValueError("Evidence cannot be overwritten")
        name = test_database("floww_paper_verify_" + uuid.uuid4().hex)
        check(name not in await connection.list_database_names(), "fresh isolated database")
        repo = PaperRepository(connection[name])
        await repo.initialize()
        owner, account = str(uuid.uuid4()), str(uuid.uuid4())
        await repo.create(owner, account, new_book("1000", currency="USD"))
        doc = await repo.read(owner, account)
        binding = {key: doc[key] for key in ("owner", "account_id", "venue", "epoch")}
        _, template = fixture.policy_fixture()
        policy = create_policy(binding, template["body"], policy_id=str(uuid.uuid4()), policy_version=1,
                               effective_at=fixture.NOW, accepted_at=fixture.NOW, accepted_by=owner,
                               acceptance_evidence=["synthetic-owner"], now=fixture.NOW, verify_acceptance=lambda _: True)
        state, event = prepare_policy_change(doc, policy, expected_version=0, expected_policy_digest=None, now=fixture.NOW)
        key = operation_id(0, epoch=doc["epoch"])
        await repo.commit(owner, account, key, {"kind": "fixture-policy", "policy": policy}, state, event)
        doc = await repo.read(owner, account)
        check(doc["state"]["risk_policy"] == policy and doc["version"] == 1, "full immutable policy saved")
        checks = ["full policy and acceptance provenance saved atomically"]
        params = fixture.parameters()
        evidence = fixture.evidence_fixture(doc, policy, params)
        stage = prepare_stage(doc, params, expected_version=1, trade_evidence=evidence, frame=fixture.frame_fixture(policy), now=fixture.NOW)
        check(stage["status"] == "pass" and not stage["admission_allowed"], "synthetic stage prepared only")
        key = operation_id(1, epoch=doc["epoch"])
        command = {"kind": "fixture-stage", "parameters": params, "evidence": evidence}
        copies = await asyncio.gather(*(repo.commit(owner, account, key, command, stage["state"], stage["event"],
                                                    reserve_events=recovery_events(stage["state"])) for _ in range(12)))
        check(sum(created for _, created in copies) == 1, "one stage commit")
        doc = await repo.read(owner, account)
        check(doc["version"] == 2 and len(doc["state"]["orders"]) == 1 and doc["state"]["cash"] == "1000", "stage no cash debit")
        checks.append("twelve identical stage requests save one order and risk receipt")
        at = fixture.NOW + timedelta(seconds=1)
        fill = prepare_fill(doc, stage["event"]["order_id"], fixture.quote_fixture(), expected_version=2,
                            frame=fixture.frame_fixture(policy, now=at), now=at)
        check(fill["status"] == "pass", "partial fill risk checked")
        second = prepare_stage(doc, params, expected_version=2, trade_evidence=evidence,
                               frame=fixture.frame_fixture(policy, now=at), now=at)
        check(second["status"] == "pass", "competing stage risk checked")
        keys = [operation_id(2, epoch=doc["epoch"]) for _ in range(2)]
        check(keys[0] != keys[1], "independent competing operation identities")
        outcomes = await asyncio.gather(*(repo.commit(owner, account, operation, {"kind": kind}, result["state"], result["event"],
                                                       reserve_events=recovery_events(result["state"]))
                                           for operation, (kind, result) in zip(keys, (("fixture-fill", fill), ("fixture-competing-stage", second)), strict=True)), return_exceptions=True)
        check(sum(isinstance(item, PaperConflict) for item in outcomes) == 1, "one competing change refused")
        check(sum(isinstance(item, tuple) and item[1] for item in outcomes) == 1, "one competing change saved")
        doc = await repo.read(owner, account)
        check(doc["version"] == 3, "race advances one version")
        winner = fill if doc["state"]["cash"] == "794.35" else second
        check(doc["state"] == winner["state"], "no mixed candidate state")
        checks.append("competing stage and fill preserve exactly one whole risk-checked state")
        denied = prepare_stage(doc, params, expected_version=2, trade_evidence=evidence,
                               frame=fixture.frame_fixture(policy, now=at), now=at)
        check(denied["state"] is None and denied["status"] == "unknown", "stale candidate refused")
        check((await repo.read(owner, account))["state"] == doc["state"], "refusal changes nothing")
        checks.append("stale expected version returns no candidate and leaves stored state exact")
        recover = report.with_suffix(".restart.json")
        recover.write_text(json.dumps(dict(database=name, owner=owner, account=account,
                                          state=doc["state"], version=doc["version"], events=doc["pending_events"])), encoding="utf8")
        child = await asyncio.to_thread(subprocess.run, [sys.executable, "-m", "scripts.verify_paper_risk", "--recover", str(recover.resolve())],
                                        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        check(child.returncode == 0, "fresh process recovery: " + child.stderr)
        checks.append("fresh process reopens exact policy trade evidence sampled peak and decision then projects history")
        result = dict(status="pass", checks=checks, database=name, paper_enabled=False,
                      limitations=["synthetic isolated accounts only", "no production admission or write-time freshness enforcement",
                                   "refused actual observations require future durable composition", "no lifecycle implementation"])
        report.write_text(json.dumps(result, indent=2), encoding="utf8")
        return result
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--recover")
    print(json.dumps(asyncio.run(execute(parser.parse_args())), indent=2))
