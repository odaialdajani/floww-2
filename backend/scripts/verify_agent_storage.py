"""Real local Mongo acceptance checks. No installation, app startup, models or brokers.

Run from backend: python -m scripts.verify_agent_storage --run --report <new-file.json>
Without --run this only probes the already-running local database. Every write uses
new randomly named test databases. Test databases remain for inspection; production
collections are never read, restored into, or removed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bson import BSON, decode_all
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from services.agent.claims import claim_seed
from services.agent.contracts import fact, request_spec
from services.agent.repository import AgentRepository
from services.agent.spend import SpendLedger

PREFIX = "floww_agent_verify_"


def request_id():
    return f"{int(time.time() * 1000)}-{uuid.uuid4()}"


def check(value, label):
    if not value:
        raise AssertionError(label)


def validate_database(name):
    if not re.fullmatch(PREFIX + r"[a-f0-9]{32}", name):
        raise ValueError("Only a freshly allocated verification database is allowed")
    return name


def local_client(port):
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid local database port")
    return AsyncIOMotorClient(
        f"mongodb://127.0.0.1:{port}/?directConnection=true",
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
        socketTimeoutMS=5000,
        tz_aware=True,
    )


async def populate_and_race(database):
    """Use real repository operations and hand-checked expected state."""
    repo = AgentRepository(database)
    await repo.initialize()
    owner, capability = await repo.session()
    other_owner, _ = await repo.session()
    await repo.save_preferences(owner, {"default_horizon": "all"})
    spec = request_spec({"question": "What is SPY's spot price?", "screen": {"ticker": "SPY"}})
    key = request_id()
    copies = await asyncio.gather(*(repo.admit(owner, key, spec) for _ in range(12)))
    check(sum(created for _, created in copies) == 1, "one admission across twelve racing identical requests")
    check(len({doc["turn_id"] for doc, _ in copies}) == 1, "one stable turn identity")
    turn = copies[0][0]
    try:
        await repo.admit(owner, key, {**spec, "question": "different question"})
    except ValueError:
        pass
    else:
        raise AssertionError("changed-body request conflict was accepted")
    check(await repo.read(other_owner, turn["turn_id"]) is None, "owner isolation")
    observed = datetime.now(UTC) - timedelta(seconds=1)
    evidence = fact(
        "Underlying price",
        100,
        "USD",
        ticker="SPY",
        source="synthetic storage acceptance",
        snapshot_id="storage-fixture",
        event_time=observed,
        received_at=observed,
    )
    seed = claim_seed(
        turn_id=turn["turn_id"],
        ticker="SPY",
        issued_at=datetime.now(UTC),
        deadline=datetime.now(UTC) + timedelta(hours=1),
        reference=100,
        target=103,
        invalidation=97,
        direction="up",
        evidence=[evidence],
    )
    await repo.progress(owner, turn["turn_id"], "Synthetic acceptance observation")
    check(
        await repo.finish(owner, turn["turn_id"], "completed", answer={"facts": [evidence]}, claim_seed=seed),
        "atomic completed answer and claim seed",
    )
    final = await repo.read(owner, turn["turn_id"])
    check(final["projection_pending"] and final["events"][-1]["type"] == "done", "recoverable pending claim")

    race, _ = await repo.admit(owner, request_id(), spec)
    winners = await asyncio.gather(
        repo.finish(owner, race["turn_id"], "completed", answer={"facts": [evidence]}),
        repo.finish(owner, race["turn_id"], "cancelled"),
    )
    check(sum(winners) == 1, "one winner for cancel versus completion")
    raced = await repo.read(owner, race["turn_id"])
    check(len(raced["events"]) == 1, "one terminal event")
    check((raced["answer"] is None) == (raced["status"] == "cancelled"), "terminal answer matches winning state")
    unfinished, _ = await repo.admit(owner, request_id(), spec)
    await repo.progress(owner, unfinished["turn_id"], "Interrupted verification job")

    ledger = SpendLedger(repo.budgets, cap_units=100)
    await ledger.initialize()
    reservation_keys = [str(uuid.uuid4()) for _ in range(2)]
    reserved = await asyncio.gather(*(ledger.reserve(k, 80, turn["turn_id"]) for k in reservation_keys))
    check(sum(reserved) == 1, "one reservation wins the final budget allowance")
    uncertain = reservation_keys[reserved.index(True)]
    await ledger.dispatch(uncertain)
    check((await ledger.state())["remaining_units"] == 20, "uncertain dispatched cost retained")
    return {
        "database": database.name,
        "owner": owner,
        "capability": capability,
        "other_owner": other_owner,
        "completed_turn": turn["turn_id"],
        "unfinished_turn": unfinished["turn_id"],
        "claim_id": final["claim_seed"]["claim_id"],
        "reservation": uncertain,
    }


async def verify_recovered(database, state):
    repo = AgentRepository(database)
    await repo.initialize()
    check(await repo.owner(state["capability"]) == state["owner"], "session survives process restart")
    completed = await repo.read(state["owner"], state["completed_turn"])
    check(
        completed["status"] == "completed" and completed["answer"]["facts"][0]["value"] == 100,
        "saved answer survives restart",
    )
    check([event["id"] for event in completed["events"]] == [1, 2], "completed replay cursor survives restart")
    check(await repo.read(state["other_owner"], state["completed_turn"]) is None, "privacy survives restart")
    check(not completed["projection_pending"], "pending claim was projected during restart")
    await repo.project_claims()
    check(await repo.claims.count_documents({"claim_id": state["claim_id"]}) == 1, "claim projection is idempotent")
    interrupted = await repo.read(state["owner"], state["unfinished_turn"])
    check(
        interrupted["status"] == "interrupted" and interrupted["events"][-1]["type"] == "error",
        "unfinished job is interrupted without replay",
    )
    ledger = SpendLedger(repo.budgets, cap_units=100)
    await ledger.initialize()
    await ledger.recover_undispatched()
    budget = await ledger.state()
    check(
        budget["reserved_units"] == 80 and budget["remaining_units"] == 20,
        "restart does not erase uncertain model cost",
    )


async def export_fixture(database, directory):
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for name in sorted(await database.list_collection_names()):
        check(re.fullmatch(r"agent_[a-z_]+", name), "unexpected collection in synthetic test database")
        docs = await database[name].find({}).to_list(length=1001)
        check(len(docs) <= 1000, "bounded acceptance export")
        data = b"".join(BSON.encode(doc) for doc in docs)
        (directory / f"{name}.bson").write_bytes(data)
        manifest[name] = {"count": len(docs), "sha256": hashlib.sha256(data).hexdigest()}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


async def restore_fixture(database, directory, manifest):
    check(not await database.list_collection_names(), "restore target must be empty")
    for name, meta in manifest.items():
        check(re.fullmatch(r"agent_[a-z_]+", name), "invalid restore collection")
        data = (directory / f"{name}.bson").read_bytes()
        check(hashlib.sha256(data).hexdigest() == meta["sha256"], "backup digest differs")
        docs = decode_all(data)
        check(len(docs) == meta["count"], "backup count differs")
        if docs:
            await database[name].insert_many(docs)


async def verify_unique_constraints(repository, state):
    """Force actual duplicate writes while varying every other unique identity."""
    turn = await repository.turns.find_one({"turn_id": state["completed_turn"]})
    session = await repository.sessions.find_one({"owner": state["owner"]})
    preference = await repository.preferences.find_one({"owner": state["owner"]})
    claim = await repository.claims.find_one({"claim_id": state["claim_id"]})
    probes = [
        (repository.turns, turn, {"turn_id": str(uuid.uuid4())}, "owner/request"),
        (repository.turns, turn, {"request_id": request_id()}, "turn identity"),
        (repository.sessions, session, {"owner": str(uuid.uuid4())}, "session capability"),
        (repository.preferences, preference, {}, "preference owner"),
        (repository.claims, claim, {"owner": str(uuid.uuid4())}, "claim identity"),
    ]
    for collection, original, changes, label in probes:
        check(original is not None, "missing unique-index verification record")
        duplicate = {key: value for key, value in original.items() if key != "_id"}
        duplicate.update(changes)
        try:
            await collection.insert_one(duplicate)
        except DuplicateKeyError:
            pass
        else:
            raise AssertionError(f"restored {label} unique index did not reject a duplicate")


async def execute(args):
    client = local_client(args.port)
    try:
        await client.admin.command("ping")
        if args.recover_state:
            state = json.loads(Path(args.recover_state).read_text(encoding="utf-8"))
            await verify_recovered(client[validate_database(state["database"])], state)
            return {"status": "recovered", "process": os.getpid()}
        report = {
            "status": "reachable",
            "driver": {p: importlib.metadata.version(p) for p in ("motor", "pymongo")},
            "server_version": (await client.server_info())["version"],
            "real_mongo": True,
        }
        if not args.run:
            return report
        requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
        for package, installed in report["driver"].items():
            pin = re.search(r"^" + re.escape(package) + r"==([^\s#]+)", requirements, re.MULTILINE)
            check(pin is not None and installed == pin.group(1), f"installed {package} differs from required pin")
        report_path = Path(args.report)
        work = report_path.parent / (report_path.name + ".artifacts")
        work.mkdir(parents=True, exist_ok=False)
        name = PREFIX + uuid.uuid4().hex
        check(name not in await client.list_database_names(), "new test database identity")
        state = await populate_and_race(client[name])
        state_path = work / "synthetic-recovery-state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        client.close()
        child = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                "-m",
                "scripts.verify_agent_storage",
                "--port",
                str(args.port),
                "--recover-state",
                str(state_path.resolve()),
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        check(child.returncode == 0, "new process recovery failed; no acceptance pass")
        recovered = json.loads(child.stdout)
        check(recovered["status"] == "recovered" and recovered["process"] != os.getpid(), "independent process proof")
        client = local_client(args.port)
        backup = work / "backup"
        manifest = await export_fixture(client[name], backup)
        restored_name = PREFIX + uuid.uuid4().hex
        check(restored_name not in await client.list_database_names(), "new restore database identity")
        await restore_fixture(client[restored_name], backup, manifest)
        await verify_recovered(client[restored_name], state)
        # Restored indexes must actually reject the duplicate, not merely exist by name.
        repository = AgentRepository(client[restored_name])
        original = await repository.read(state["owner"], state["completed_turn"])
        duplicate, created = await repository.admit(state["owner"], original["request_id"], original["spec"])
        check(not created and duplicate["turn_id"] == original["turn_id"], "restored idempotency")
        await verify_unique_constraints(repository, state)
        report.update(
            status="passed",
            database=name,
            restored_database=restored_name,
            backup=manifest,
            process_restart=True,
            bson_restore=True,
            limitation="Synthetic records, pinned driver, fresh-process repository recovery and quiescent BSON restore. No application or Mongo crash, full-store equality, production-size backup, provider or model acceptance.",
        )
        return report
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=27017)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--recover-state", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.run and not args.report:
        parser.error("--run requires a new --report file")
    if args.report and Path(args.report).exists():
        parser.error("report already exists; use a new path")
    try:
        report = asyncio.run(execute(args))
        result = 0
    except Exception as exc:
        report = {
            "status": "not_passed",
            "error_type": type(exc).__name__,
            "reason": "Local storage check could not complete. No installation or database startup was attempted.",
        }
        if isinstance(exc, AssertionError):
            report["failed_check"] = str(exc)
        result = 2
    text = json.dumps(report, indent=2)
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
