"""Opt-in isolated storage/capacity proof for prepaid observation assessments."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.verify_paper_storage import check, client, test_database
from services.agent.paper.execution import new_book
from services.agent.paper.guarded_repository import GuardedPaperRepository
from services.agent.paper.policy import binding_of, create_policy, prepare_policy_change
from services.agent.paper.recovery import export_checkpoint, restore_frozen_copy
from services.agent.paper.repository import PaperCapacity, PaperConflict, PaperRepository, operation_id
from services.agent.paper.risk import prepare_fill, prepare_stage
from services.agent.paper.risk_assessment import begin, finalize, replenish
from services.agent.paper.valuation import current_observation, observe

fixture_path = Path(__file__).resolve().parents[2] / "tests" / "test_agent_paper_risk.py"
spec = importlib.util.spec_from_file_location("guard_fixture", fixture_path)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
BASE = datetime.now(UTC)
fixture.NOW = BASE


def clock():
    return datetime.now(UTC)


def frame(policy, *, bid="1.90", ask="2.00"):
    result = fixture.frame_fixture(policy, now=clock(), bid=bid, ask=ask)
    result["session"].update(session_id="synthetic-"+BASE.date().isoformat(),
                             opened_at=(BASE-timedelta(minutes=30)).isoformat(),
                             closed_at=(BASE+timedelta(hours=6)).isoformat())
    result["session_open"].update(session_id=result["session"]["session_id"], observed_at=result["session"]["opened_at"])
    return result


async def execute(args):
    connection = client()
    try:
        await connection.admin.command("ping")
        if args.recover:
            saved = json.loads(Path(args.recover).read_text(encoding="utf8"))
            repo = GuardedPaperRepository(connection[test_database(saved["database"])])
            doc = await repo.read(saved["owner"], saved["account"])
            check(doc["state"] == saved["state"] and doc["pending_events"] == saved["events"], "exact guarded restart")
            await repo.project(saved["owner"], saved["account"])
            current = await repo.read(saved["owner"], saved["account"])
            check(current["state"] == saved["state"] and not current["pending_events"], "projection retains guarded state")
            history = await repo.events.find({"scope_id": doc["_id"], "version": {"$gte": saved["events"][0]["version"]}}).sort("version", 1).to_list(length=200)
            check(history == saved["events"], "exact guarded decision history")
            return dict(status="recovered", process=os.getpid())
        if not args.run or not args.report:
            raise ValueError("Explicit --run and fresh report path required")
        report = Path(args.report)
        if any(path.exists() for path in (report, report.with_suffix(".restart.json"), report.with_suffix(".checkpoint"))):
            raise ValueError("Refuse to replace earlier complete or partial verification evidence")
        name = test_database("floww_paper_verify_"+uuid.uuid4().hex)
        check(name not in await connection.list_database_names(), "fresh isolated database")
        repo = GuardedPaperRepository(connection[name])
        await repo.initialize()
        owner, account = str(uuid.uuid4()), str(uuid.uuid4())
        checks = []

        async def setup(selected):
            await repo.create(owner, selected, new_book("1000", currency="USD"))
            doc = await repo.read(owner, selected)
            _, template = fixture.policy_fixture()
            policy = create_policy(binding_of(doc), template["body"], policy_id=str(uuid.uuid4()), policy_version=1,
                                   effective_at=BASE, accepted_at=BASE, accepted_by=owner, acceptance_evidence=["synthetic-only"],
                                   now=clock(), verify_acceptance=lambda _: True)
            state, event = prepare_policy_change(doc, policy, expected_version=0, expected_policy_digest=None, now=clock())
            await repo.commit(owner, selected, operation_id(0, epoch=doc["epoch"]), {"kind": "fixture-policy"}, state, event)
            return await repo.read(owner, selected), policy

        async def funded(selected, command, *, action="entry", structure=None):
            doc = await repo.read(owner, selected)
            request = operation_id(doc["version"], epoch=doc["epoch"])
            state, event = begin(doc, request, command, action=action, structure_id=structure, now=clock())
            receipt, _ = await repo.commit(owner, selected, request, {"kind": "fixture-begin", "command": command}, state, event)
            return await repo.read(owner, selected), request, receipt

        async def finish(selected, doc, request, result, source_frame):
            checked = clock()
            actual = observe(doc["state"], source_frame, now=checked, binding=binding_of(doc), previous=doc["state"].get("valuation"))
            state, event = finalize(doc, request, result, actual, now=checked)
            try:
                await repo.commit(owner, selected, operation_id(doc["version"], epoch=doc["epoch"]),
                                  {"kind": "fixture-resolution", "assessment": request}, state, event)
            except PaperConflict:
                server = await connection.admin.command("hello")
                print(json.dumps({"diagnostic": "resolution-refused", "current_version": (await repo.read(owner, selected))["version"],
                                  "expected_version": doc["version"], "decision": event.get("risk_decision"),
                                  "client_now": clock().isoformat(), "server_now": server["localTime"].isoformat()}), file=sys.stderr)
                raise
            return await repo.read(owner, selected)

        async def refreshed(selected):
            await repo.project(owner, selected)
            doc = await repo.read(owner, selected)
            check(not doc["pending_events"], "exact projection before refresh")
            state, event = replenish(doc["state"], now=clock())
            await repo.commit(owner, selected, operation_id(doc["version"], epoch=doc["epoch"]), {"kind": "fixture-refresh"}, state, event)
            return await repo.read(owner, selected)

        doc, policy = await setup(account)
        check(await PaperRepository(connection[name]).read(owner, account) is None, "legacy collection isolation")
        checks.append("legacy account services cannot find the newly created guarded account")
        params = fixture.parameters()
        evidence = fixture.evidence_fixture(doc, policy, params)
        source_frame = frame(policy)
        doc, request, _ = await funded(account, {"frame": source_frame, "parameters": params, "evidence": evidence})
        stage = prepare_stage(doc, params, expected_version=doc["version"], trade_evidence=evidence, frame=source_frame, now=clock())
        check(stage["status"] == "pass", "funded entry candidate")
        doc = await finish(account, doc, request, stage, source_frame)
        structure = stage["event"]["structure_id"]
        await refreshed(account)
        source_frame = frame(policy)
        entry_quote = fixture.quote_fixture(now=clock(), size=2)
        doc, request, _ = await funded(account, {"frame": source_frame, "order_id": stage["event"]["order_id"], "quote": entry_quote})
        filled = prepare_fill(doc, stage["event"]["order_id"], entry_quote,
                              expected_version=doc["version"], frame=source_frame, now=clock())
        check(filled["status"] == "pass", "funded full fill")
        doc = await finish(account, doc, request, filled, source_frame)
        check(doc["state"]["cash"] == "588.70", "exact cash after filled entry")
        doc = await refreshed(account)
        while len(doc["pending_events"])+doc["reserve_events"] < repo.pending_limit:
            await repo.commit(owner, account, operation_id(doc["version"], epoch=doc["epoch"]),
                              {"kind": "fixture-pressure", "version": doc["version"]}, doc["state"], {"kind": "fixture-pressure"})
            doc = await repo.read(owner, account)
        check(len(doc["pending_events"])+doc["reserve_events"] == 128, "ordinary event capacity full")
        source_frame = frame(policy, bid="3.00", ask="3.10")
        doc, request, _ = await funded(account, {"frame": source_frame, "parameters": params, "evidence": evidence})
        refusal = prepare_stage(doc, params, expected_version=doc["version"], trade_evidence=evidence, frame=source_frame, now=clock())
        check(refusal["status"] == "refuse", "high-mark new exposure refused")
        doc = await finish(account, doc, request, refusal, source_frame)
        check(doc["state"]["valuation"]["risk_anchor"]["observed_peak_equity"] == "1188.70", "actual refused high persisted")
        check(current_observation(doc, now=clock())["status"] == "current", "final observation book binding")
        check(len(doc["pending_events"])+doc["reserve_events"] == 128, "refusal uses only prepaid event credits")
        checks.append("full ordinary event capacity still saves refused-entry actual equity1188.70 and sampled high")
        closing = {**params, "side": "sell", "quantity": 1, "limit": "0.40", "structure_id": structure}
        source_frame = frame(policy, bid="0.50", ask="0.60")
        doc, request, _ = await funded(account, {"frame": source_frame, "parameters": closing}, action="reduce", structure=structure)
        close = prepare_stage(doc, closing, expected_version=doc["version"], trade_evidence=None, frame=source_frame, now=clock())
        check(close["status"] == "pass", "reducing close permitted after known loss")
        doc = await finish(account, doc, request, close, source_frame)
        source_frame = frame(policy, bid="0.50", ask="0.60")
        exit_quote = fixture.quote_fixture(now=clock(), bid="0.50", ask="0.60", source="close", size=1)
        doc, request, _ = await funded(account, {"frame": source_frame, "order_id": close["event"]["order_id"], "quote": exit_quote}, action="reduce", structure=structure)
        close_fill = prepare_fill(doc, close["event"]["order_id"], exit_quote,
                                  expected_version=doc["version"], frame=source_frame, now=clock())
        check(close_fill["status"] == "pass", "reducing fill permitted at storage cap")
        doc = await finish(account, doc, request, close_fill, source_frame)
        check(doc["state"]["cash"] == "633.05", "exact reducing cash")
        check(len(doc["pending_events"])+doc["reserve_events"] == 128, "exit uses its own prepaid assessment and execution credits")
        check(doc["state"]["valuation"]["risk_anchor"]["observed_peak_equity"] == "1188.70", "earlier refused peak retained through exit")
        checks.append("full capacity permits funded close stage and fill with cash633.05 while retaining earlier actual high")
        restart = report.with_suffix(".restart.json")
        restart.write_text(json.dumps(dict(database=name, owner=owner, account=account, state=doc["state"], events=doc["pending_events"])), encoding="utf8")
        child = await asyncio.to_thread(subprocess.run, [sys.executable, "-m", "scripts.verify_paper_guard", "--recover", str(restart.resolve())],
                                       cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        check(child.returncode == 0, "exact fresh guarded restart: "+child.stderr)
        checks.append("fresh process recovers exact guarded cash peak credits and all pending/projected event bodies")

        interrupted = str(uuid.uuid4())
        isolated, second_policy = await setup(interrupted)
        source_frame = frame(second_policy)
        isolated, request, _ = await funded(interrupted, {"frame": source_frame})
        # Simulate a failed post-begin write; no subsequent source evaluation or
        # economic mutation is permitted to erase the durable unresolved intent.
        original_collection = repo.accounts
        class FailedWrite:
            def __getattr__(self, key):
                return getattr(original_collection, key)
            async def update_one(self, *_, **__):
                raise OSError("synthetic storage failure after acknowledged intent")
        repo.accounts = FailedWrite()
        try:
            try:
                await repo.commit(owner, interrupted, operation_id(isolated["version"], epoch=isolated["epoch"]),
                                  {"kind": "fixture-failed-resolution"}, isolated["state"], {"kind": "fixture-failed-resolution"})
                raise AssertionError("injected failure did not propagate")
            except OSError:
                pass
        finally:
            repo.accounts = original_collection
        isolated = await repo.read(owner, interrupted)
        check(request in isolated["state"]["risk_control"]["pending"], "failed resolution preserves intent")
        try:
            begin(isolated, operation_id(isolated["version"], epoch=isolated["epoch"]), {"frame": source_frame},
                  action="entry", structure_id=None, now=clock())
            raise AssertionError("unresolved entry incorrectly allowed")
        except PaperConflict:
            pass
        directory = report.with_suffix(".checkpoint")
        await export_checkpoint(repo, owner, interrupted, directory)
        restored = await restore_frozen_copy(repo, owner, str(uuid.uuid4()), directory)
        check(restored["recovery_pending"] and restored["state"]["risk_control"] == isolated["state"]["risk_control"], "frozen restore retains unresolved intent")
        checks.append("failed resolution leaves funded intent and blocks new exposure; normal checkpoint/frozen restore preserves it exactly")

        # Two distinct acknowledged begin attempts may contend, but only one
        # can spend the original two-credit balance at the same account version.
        racing = str(uuid.uuid4())
        raced, race_policy = await setup(racing)
        requests = [operation_id(raced["version"], epoch=raced["epoch"]) for _ in range(2)]
        commands = [{"frame": frame(race_policy), "case": i} for i in range(2)]
        transitions = [begin(raced, request, command, action="entry", structure_id=None, now=clock())
                       for request, command in zip(requests, commands, strict=True)]
        outcomes = await asyncio.gather(*(repo.commit(owner, racing, request, command, state, event)
                                          for request, command, (state, event) in zip(requests, commands, transitions, strict=True)),
                                        return_exceptions=True)
        check(sum(isinstance(item, PaperConflict) for item in outcomes) == 1, "one competing begin conflicts")
        check(sum(isinstance(item, tuple) and item[1] for item in outcomes) == 1, "one begin funded once")
        raced = await repo.read(owner, racing)
        check(len(raced["state"]["risk_control"]["pending"]) == 1 and raced["state"]["risk_control"]["entry_credits"] == 1,
              "race keeps one exact unresolved intent and resolution credit")
        checks.append("two distinct entry assessments at one version fund exactly one durable intent")

        # A deliberately smaller store can fund the observation but cannot
        # fund a new position's complete execution and observation obligations.
        # The pending intent still has space to save a known refusal afterward.
        bounded = GuardedPaperRepository(connection[name], pending_limit=40)
        selected = str(uuid.uuid4())
        limited, limited_policy = await setup(selected)
        source_frame = frame(limited_policy)
        limited_evidence = fixture.evidence_fixture(limited, limited_policy, params)
        limited, limited_request, _ = await funded(selected, {"frame": source_frame, "parameters": params, "evidence": limited_evidence})
        candidate = prepare_stage(limited, params, expected_version=limited["version"], trade_evidence=limited_evidence,
                                  frame=source_frame, now=clock())
        check(candidate["status"] == "pass", "economic risk passes before storage capacity check")
        checked = clock()
        actual = observe(limited["state"], source_frame, now=checked, binding=binding_of(limited), previous=limited["state"].get("valuation"))
        next_state, event = finalize(limited, limited_request, candidate, actual, now=checked)
        operation = operation_id(limited["version"], epoch=limited["epoch"])
        try:
            await bounded.commit(owner, selected, operation, {"kind": "fixture-capacity-candidate"}, next_state, event)
            raise AssertionError("unfunded new obligations accepted")
        except PaperCapacity:
            pass
        check((await bounded.read(owner, selected))["state"] == limited["state"], "capacity refusal leaves acknowledged intent exact")
        next_state, event = finalize(limited, limited_request,
                                     {"status": "refuse", "reason": "synthetic store cannot fund new obligations"}, actual, now=clock())
        await bounded.commit(owner, selected, operation, {"kind": "fixture-capacity-refusal"}, next_state, event)
        limited = await bounded.read(owner, selected)
        check(not limited["state"]["orders"] and not limited["state"]["risk_control"]["pending"], "funded refusal leaves no order")
        check(limited["state"]["valuation"]["equity"] == "1000", "funded actual observation retained")
        checks.append("insufficient new-position storage preserves the intent and its prepaid observation-only refusal path")

        # Use an available account for exact server-predicate checks, without
        # claiming journal acknowledgement or lock-wait time semantics.
        timed = str(uuid.uuid4())
        current, _ = await setup(timed)
        for start, end in ((clock()-timedelta(seconds=2), clock()-timedelta(seconds=1)),
                           (clock()+timedelta(seconds=10), clock()+timedelta(seconds=20))):
            try:
                await repo.commit(owner, timed, operation_id(current["version"], epoch=current["epoch"]),
                                  {"kind": "fixture-expired-or-future"}, current["state"], {"kind": "fixture-no-economic-change"},
                                  valid_after=start, valid_until=end)
                raise AssertionError("out-of-window write accepted")
            except PaperConflict:
                pass
            check((await repo.read(owner, timed))["version"] == current["version"], "window failure changes nothing")
        await repo.commit(owner, timed, operation_id(current["version"], epoch=current["epoch"]),
                          {"kind": "fixture-current-window"}, current["state"], {"kind": "fixture-no-economic-change"},
                          valid_after=clock()-timedelta(seconds=1), valid_until=clock()+timedelta(seconds=10))
        checks.append("actual server predicates reject expired/future windows and accept a current window without claiming acknowledgement-time freshness")
        result = dict(status="pass", checks=checks, paper_enabled=False, database=name,
                      limitations=["new isolated synthetic guarded collections only", "bounded prepaid attempts; projection required to replenish",
                                   "no mounted controller or automatic historical reconciliation", "server expression time is not final journal acknowledgement time",
                                   "owner policy values and product lifecycle remain unapproved/unimplemented"])
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
