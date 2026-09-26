"""Opt-in real-store paper preparation checks; synthetic isolated accounts only.

Run with --run --report <new report path>. No server startup, provider, model,
order or production-account access. Synthetic databases remain for inspection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from bson import BSON
from motor.motor_asyncio import AsyncIOMotorClient

from services.agent.paper.recovery import export_checkpoint, restore_frozen_copy
from services.agent.paper.repository import (
    MAX_EVENT_BYTES,
    MAX_RECOVERY_STATE_GROWTH,
    RESERVED_EVENT_BYTES,
    RESTORE_HEADROOM_BYTES,
    PaperCapacity,
    PaperConflict,
    PaperRepository,
    digest,
    operation_id,
)

PREFIX = "floww_paper_verify_"


def check(value, label):
    if not value:
        raise AssertionError(label)


def client():
    return AsyncIOMotorClient("mongodb://127.0.0.1:27017/?directConnection=true",
                             serverSelectionTimeoutMS=2000, socketTimeoutMS=5000, tz_aware=True)


def test_database(name):
    if not re.fullmatch(PREFIX + r"[a-f0-9]{32}", name):
        raise ValueError("Only an isolated synthetic verification database is allowed")
    return name


async def refuses(call, expected, label):
    try:
        await call
    except expected:
        return label
    raise AssertionError(label)


async def execute(args):
    connection = client()
    try:
        await connection.admin.command("ping")
        if args.recover:
            state = json.loads(Path(args.recover).read_text(encoding="utf-8"))
            repo = PaperRepository(connection[test_database(state["database"])])
            await repo.initialize()
            owner, account = state["owner"], state["account"]
            before = await repo.read(owner, account)
            check(before["version"] == 1 and before["state"]["cash"] == "794.35", "cash recovered exactly")
            check(len(before["pending_events"]) == 1, "atomic pending event survived process exit")
            await repo.project(owner, account)
            await repo.project(owner, account)
            after = await repo.read(owner, account)
            check(after["state"] == before["state"] and after["version"] == 1, "projection cannot change cash")
            check(not after["pending_events"], "pending projection recovered")
            check(await repo.events.count_documents({"scope_id": after["_id"]}) == 1, "one durable history event")
            return {"status": "recovered", "process": os.getpid()}

        if not args.run:
            return {"status": "reachable", "paper_enabled": False}
        report_path = Path(args.report)
        if report_path.exists():
            raise ValueError("Refuse to overwrite earlier verification evidence")
        work = report_path.parent / (report_path.name + ".artifacts")
        work.mkdir(parents=True, exist_ok=False)
        name = test_database(PREFIX + uuid.uuid4().hex)
        check(name not in await connection.list_database_names(), "fresh isolated database")
        database = connection[name]
        repo = PaperRepository(database)
        await repo.initialize()
        owner, account, other = (str(uuid.uuid4()) for _ in range(3))
        state = {"cash": "1000.00", "positions": {}, "reservations": {}}
        created_account = await repo.create(owner, account, state)
        epoch = created_account["epoch"]
        await repo.create(owner, account, state)
        checks = []
        checks.append(await refuses(repo.create(owner, account, {**state, "cash": "999.00"}),
                                     PaperConflict, "changed initial cash refused"))
        check(await repo.read(other, account) is None, "owner read isolation")
        checks.append("owner read isolation")
        key = operation_id(0, epoch=epoch)
        command = {"kind": "synthetic_fill", "quantity": 1, "price": "2.05", "fee": "0.65"}
        next_state = {"cash": "794.35", "positions": {"synthetic-option": 1}, "reservations": {}}
        event = {"kind": "synthetic_fill", "cash_change": "-205.65"}
        copies = await asyncio.gather(*(repo.commit(owner, account, key, command, next_state, event) for _ in range(12)))
        check(sum(created for _, created in copies) == 1, "one of twelve identical commits wins")
        check(len({item["_id"] for item, _ in copies}) == 1, "identical requests return same saved receipt")
        checks += ["twelve concurrent duplicate commits apply once", "stable receipt identity"]
        checks.append(await refuses(repo.commit(owner, account, key, {**command, "quantity": 2}, next_state, event),
                                     PaperConflict, "changed command with same identity refused"))
        checks.append(await refuses(repo.commit(other, account, operation_id(0, epoch=epoch), command, next_state, event),
                                     PaperConflict, "owner mutation isolation"))
        recovery = {"database": name, "owner": owner, "account": account}
        state_path = work / "synthetic-state.json"
        state_path.write_text(json.dumps(recovery), encoding="utf-8")
        child = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "scripts.verify_paper_storage", "--recover", str(state_path.resolve())],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
        )
        check(child.returncode == 0, "independent recovery process failed: " + child.stderr[-2000:])
        restored = json.loads(child.stdout)
        check(restored["status"] == "recovered" and restored["process"] != os.getpid(), "fresh process recovered")
        checks.append("fresh process reads committed cash and projects pending history once")
        duplicate, created = await repo.commit(owner, account, key, command, next_state, event)
        check(not created and duplicate["_id"] == copies[0][0]["_id"], "projected duplicate remains idempotent")
        checks.append("duplicate after projection does not repeat cash change")
        # Reproduce a mismatched raw backup rollback while newer history survives.
        # This is deliberately confined to a fresh synthetic database.
        good_account = await repo.read(owner, account)
        await repo.accounts.update_one({"_id": good_account["_id"]}, {"$set": {"version": 0, "state": state}})
        checks.append(await refuses(repo.commit(owner, account, key, command, next_state, event),
                                     PaperConflict, "old backup cannot return newer success against older cash"))
        checks.append(await refuses(repo.commit(owner, account, operation_id(0, epoch=epoch), command, next_state, event),
                                     PaperConflict, "old backup cannot accept fresh work over newer history"))
        await repo.accounts.replace_one({"_id": good_account["_id"]}, good_account)
        # A recovery epoch invalidates old confirmations even when versions match.
        new_epoch = str(uuid.uuid4())
        await repo.accounts.update_one({"_id": good_account["_id"]}, {"$set": {"epoch": new_epoch}})
        checks.append(await refuses(repo.commit(owner, account, operation_id(1, epoch=epoch), command, next_state, event),
                                     PaperConflict, "earlier recovery epoch cannot change restored account"))
        await repo.accounts.replace_one({"_id": good_account["_id"]}, good_account)
        # Pruning a receipt cannot turn its old version-bound request into a new fill.
        await repo.events.delete_one({"_id": duplicate["_id"]})
        checks.append(await refuses(repo.commit(owner, account, key, command, next_state, event),
                                     PaperConflict, "retired operation cannot reapply after history removal"))
        account2 = str(uuid.uuid4())
        created_second = await repo.create(owner, account2, {"cash": "100.00", "reserved": "0.00"})
        epoch = created_second["epoch"]
        results = await asyncio.gather(*(
            repo.commit(owner, account2, operation_id(0, epoch=epoch), {"reserve": "80.00", "order": str(i)},
                        {"cash": "100.00", "reserved": "80.00"}, {"kind": "reserve"}) for i in range(2)
        ), return_exceptions=True)
        check(sum(isinstance(r, tuple) and r[1] for r in results) == 1, "one version-race winner")
        check(sum(isinstance(r, PaperConflict) for r in results) == 1, "loser explicitly refuses stale state")
        checks.append("competing reservations cannot both consume last buying power")
        limited = PaperRepository(database, pending_limit=1)
        checks.append(await refuses(limited.commit(owner, account2, operation_id(1, epoch=epoch), {"step": 2},
                                                   {"cash": "0"}, {"kind": "test"}),
                                     PaperCapacity, "pending event cap retains existing account"))
        await repo.project(owner, account2)
        # Force crash-window equivalent: history exists but account queue still holds it.
        changed, _ = await repo.commit(owner, account2, operation_id(1, epoch=epoch), {"step": 2},
                                       {"cash": "100.00", "reserved": "0.00"}, {"kind": "cancel"})
        await repo.events.insert_one(changed)
        await repo.project(owner, account2)
        check(await repo.events.count_documents({"_id": changed["_id"]}) == 1, "projection crash window")
        checks.append("crash after history insert before queue cleanup recovers once")
        small = PaperRepository(database, document_limit=1024)
        checks.append(await refuses(small.commit(owner, account2, operation_id(2, epoch=epoch), {"step": 3},
                                                 {"large": "x" * 1100}, {"kind": "large"}),
                                     PaperCapacity, "document limit refuses without mutation"))
        check((await repo.read(owner, account2))["version"] == 2, "refusal preserves version")
        # Mongo event conflict must never silently clear the account's recovery record.
        pending, _ = await repo.commit(owner, account2, operation_id(2, epoch=epoch), {"step": 3},
                                       {"cash": "100.00"}, {"kind": "retained"})
        await repo.events.insert_one({**pending, "body": {"kind": "conflicting"}})
        checks.append(await refuses(repo.project(owner, account2), PaperConflict, "conflicting history refuses projection"))
        check(len((await repo.read(owner, account2))["pending_events"]) == 1, "conflict retains recovery event")
        checks.append("history conflict retains pending recovery and cash")
        # Reserve event capacity before admitting obligations; consume that
        # reservation when reducing them, without deleting pending history.
        reserve_repo = PaperRepository(database, pending_limit=4)
        reserved_account = str(uuid.uuid4())
        reserved = await reserve_repo.create(owner, reserved_account, {"cash": "100"}, reserve_events=2)
        reserved_epoch = reserved["epoch"]
        for version in range(2):
            await reserve_repo.commit(owner, reserved_account, operation_id(version, epoch=reserved_epoch),
                                      {"step": version}, {"cash": "100"}, {"kind": "saved"})
        checks.append(await refuses(reserve_repo.commit(owner, reserved_account, operation_id(2, epoch=reserved_epoch),
                                                        {"kind": "entry"}, {"cash": "10"}, {"kind": "entry"}),
                                     PaperCapacity, "entry cannot consume reserved exit capacity"))
        await reserve_repo.commit(owner, reserved_account, operation_id(2, epoch=reserved_epoch),
                                  {"kind": "close"}, {"cash": "100"}, {"kind": "close"}, reserve_events=1)
        await reserve_repo.commit(owner, reserved_account, operation_id(3, epoch=reserved_epoch),
                                  {"kind": "cancel"}, {"cash": "100"}, {"kind": "cancel"}, reserve_events=0)
        retained = await reserve_repo.read(owner, reserved_account)
        check(len(retained["pending_events"]) == 4 and retained["reserve_events"] == 0, "reserved recovery used once")
        checks.append("reserved close and cancellation complete at normal capacity limit")
        # Streaming checkpoint merges already projected records and pending seeds.
        source_id, target_id = str(uuid.uuid4()), str(uuid.uuid4())
        source = await repo.create(owner, source_id, {"cash": "1000.00", "positions": {"first": 1}})
        for version, cash in ((0, "900.00"), (1, "850.00")):
            await repo.commit(owner, source_id, operation_id(version, epoch=source["epoch"]), {"step": version},
                              {"cash": cash, "positions": {"first": 1}}, {"kind": "synthetic", "cash": cash})
            if version == 0:
                await repo.project(owner, source_id)
        checkpoint = work / "checkpoint"
        manifest = await export_checkpoint(repo, owner, source_id, checkpoint)
        check(manifest["events"] == 2, "checkpoint includes pending and projected events")
        before_restore = await repo.read(owner, source_id)
        recovered = await restore_frozen_copy(repo, owner, target_id, checkpoint)
        check(recovered["state"] == before_restore["state"] and recovered["epoch"] != before_restore["epoch"],
              "restored values preserved under fresh identity")
        check(recovered["recovery_pending"], "restored admission remains frozen")
        check(await repo.read(owner, source_id) == before_restore, "source account not changed by restore")
        checks.append("verified checkpoint restores exact state into fresh frozen account")
        checks.append(await refuses(repo.commit(owner, target_id, operation_id(0, epoch=recovered["epoch"]),
                                                {"kind": "entry"}, {"cash": "1"}, {"kind": "entry"}),
                                     PaperConflict, "restored account cannot admit unreconciled work"))
        checks.append(await refuses(restore_frozen_copy(repo, owner, source_id, checkpoint),
                                     PaperConflict, "in-place account rollback refused"))
        checks.append(await refuses(restore_frozen_copy(repo, owner, target_id, checkpoint),
                                     PaperConflict, "existing restore target cannot be overwritten"))
        checks.append(await refuses(restore_frozen_copy(repo, other, str(uuid.uuid4()), checkpoint),
                                     PaperConflict, "checkpoint owner isolation"))
        corrupt = work / "corrupt-checkpoint"
        shutil.copytree(checkpoint, corrupt)
        with (corrupt / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("{}\n")
        checks.append(await refuses(restore_frozen_copy(repo, owner, str(uuid.uuid4()), corrupt),
                                     PaperConflict, "changed backup content refused before restore"))
        # Worst allowed recovery event plus worst allowed state growth fit the
        # reservation, including BSON array/key overhead at the document edge.
        edge_id = str(uuid.uuid4())
        edge = await repo.create(owner, edge_id, {"cash": "100"}, reserve_events=1)
        edge_limit = len(BSON.encode(edge)) + RESERVED_EVENT_BYTES + RESTORE_HEADROOM_BYTES
        edge_repo = PaperRepository(database, document_limit=edge_limit)
        edge_key = operation_id(0, epoch=edge["epoch"])
        body = {"kind": "boundary", "payload": ""}
        stub = dict(_id=digest([edge["_id"], edge_key]), scope_id=edge["_id"], owner=owner,
                    account_id=edge_id, venue="internal", epoch=edge["epoch"], operation_id=edge_key,
                    command_digest=digest({"edge": True}), version=1,
                    recorded_at=datetime.now(UTC).isoformat(), body=body)
        body["payload"] = "x" * (MAX_EVENT_BYTES - len(BSON.encode(stub)))
        next_edge = {"cash": "100", "payload": ""}
        overhead = len(BSON.encode({"state": next_edge})) - len(BSON.encode({"state": edge["state"]}))
        next_edge["payload"] = "x" * (MAX_RECOVERY_STATE_GROWTH - overhead)
        edge_event, _ = await edge_repo.commit(owner, edge_id, edge_key, {"edge": True}, next_edge, body,
                                               reserve_events=0)
        check(MAX_EVENT_BYTES - 6 <= len(BSON.encode(edge_event)) <= MAX_EVENT_BYTES, "maximum event exercised")
        edge_saved = await edge_repo.read(owner, edge_id)
        check(len(BSON.encode(edge_saved)) + RESTORE_HEADROOM_BYTES <= edge_limit, "reserved growth fits")
        checks.append("maximum recovery event and state growth fit reserved BSON capacity")
        # Escaped JSON may use six characters for one legal stored byte.
        escape_id = str(uuid.uuid4())
        escaped = await repo.create(owner, escape_id, {"cash": "100", "text": "\x01" * 30000})
        await repo.commit(owner, escape_id, operation_id(0, epoch=escaped["epoch"]), {"escape": True},
                          escaped["state"], {"text": "\x01" * 30000})
        escape_dir = work / "escaped-checkpoint"
        await export_checkpoint(repo, owner, escape_id, escape_dir)
        escape_copy = await restore_frozen_copy(repo, owner, str(uuid.uuid4()), escape_dir)
        check(escape_copy["state"] == escaped["state"], "escaped strings preserved")
        checks.append("valid sixfold escaped checkpoint roundtrips exactly")
        # An empty-queue account at its full admitted size still has space for
        # the frozen restore provenance envelope.
        near_id = str(uuid.uuid4())
        template_id = str(uuid.uuid4())
        template = await repo.create(owner, template_id, {"cash": "100", "payload": ""})
        near_limit = 16384
        filler = near_limit - RESTORE_HEADROOM_BYTES - len(BSON.encode(template))
        near_repo = PaperRepository(database, document_limit=near_limit)
        near = await near_repo.create(owner, near_id, {"cash": "100", "payload": "x" * filler})
        check(len(BSON.encode(near)) + RESTORE_HEADROOM_BYTES == near_limit, "exact admission boundary")
        near_dir = work / "near-cap-checkpoint"
        await export_checkpoint(near_repo, owner, near_id, near_dir)
        near_copy = await restore_frozen_copy(near_repo, owner, str(uuid.uuid4()), near_dir)
        check(near_copy["state"] == near["state"] and len(BSON.encode(near_copy)) <= near_limit,
              "restore envelope fits near-cap checkpoint")
        checks.append("full admitted account fits frozen restore envelope")
        concurrent_id = str(uuid.uuid4())
        concurrent = await repo.create(owner, concurrent_id, {"cash": "100"})
        for version in range(2):
            await repo.commit(owner, concurrent_id, operation_id(version, epoch=concurrent["epoch"]),
                              {"step": version}, {"cash": "90" if version == 0 else "80"}, {"step": version})
        concurrent_dir = work / "concurrent-checkpoint"
        await asyncio.gather(export_checkpoint(repo, owner, concurrent_id, concurrent_dir),
                             repo.project(owner, concurrent_id))
        concurrent_copy = await restore_frozen_copy(repo, owner, str(uuid.uuid4()), concurrent_dir)
        check(concurrent_copy["state"]["cash"] == "80", "concurrent projection checkpoint remains consistent")
        checks.append("checkpoint and projection race preserves the exact saved boundary")
        result = {"status": "passed", "real_mongo": True, "database": name, "checks": checks,
                  "paper_enabled": False, "orders_sent": 0, "accounting_acceptance": False,
                  "limits": "Synthetic storage proof only; no full paper lifecycle or crash-durability claim."}
        report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report", default="paper-storage-verification.json")
    parser.add_argument("--recover")
    print(json.dumps(asyncio.run(execute(parser.parse_args())), indent=2))
