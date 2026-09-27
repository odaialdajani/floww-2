"""Verified paper checkpoints restore into a new, frozen account identity.

This never rolls a funded account backwards in place. Old confirmations cannot
target the restored copy. Reconciliation/reopening is a separate service gate;
this module deliberately provides no unblock method.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from bson import BSON
from pymongo.errors import DuplicateKeyError

from services.agent.paper.repository import (
    MAX_DOCUMENT_BYTES,
    MAX_EVENT_BYTES,
    PaperConflict,
    canonical,
    digest,
    scope,
    validate_json,
)


def file_hash(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            value.update(block)
    return value.hexdigest()


def event_valid(event, account, expected_version):
    binding = scope(account["owner"], account["account_id"], account["venue"])
    if (event.get("scope_id") != account["_id"] or event.get("epoch") != account["epoch"]
            or event.get("version") != expected_version or any(event.get(k) != v for k, v in binding.items())):
        raise PaperConflict("Checkpoint event sequence or ownership differs")
    if len(BSON.encode(event)) > MAX_EVENT_BYTES:
        raise PaperConflict("Checkpoint event exceeds the accepted size")


async def export_checkpoint(repository, owner, account_id, directory):
    """Stream a consistent version boundary; pending seeds cover projection races."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    account = await repository.read(owner, account_id)
    if account is None or account.get("recovery_pending"):
        raise PaperConflict("Only an available reconciled account can be checkpointed")
    if account.get("storage_version") != 1 or account["_id"] != digest(scope(owner, account_id, "internal")):
        raise PaperConflict("Unsupported account checkpoint")
    pending = {event["version"]: event for event in account["pending_events"]}
    if len(pending) != len(account["pending_events"]):
        raise PaperConflict("Duplicate pending account versions")
    first_version = account.get("epoch_initial_version", 0) + 1
    next_version = first_version
    count = 0
    event_path = directory / "events.jsonl"
    with event_path.open("w", encoding="utf-8", newline="\n") as output:
        def append(event):
            nonlocal next_version, count
            event_valid(event, account, next_version)
            output.write(canonical(event) + "\n")
            next_version += 1
            count += 1

        cursor = repository.events.find({"scope_id": account["_id"], "epoch": account["epoch"],
                                         "version": {"$lte": account["version"]}}).sort("version", 1)
        async for event in cursor:
            while next_version < event["version"]:
                missing = pending.pop(next_version, None)
                if missing is None:
                    raise PaperConflict("Checkpoint history has a gap; no restore manifest created")
                append(missing)
            matching = pending.pop(event["version"], None)
            if matching is not None and matching != event:
                raise PaperConflict("Projected history conflicts with its pending seed")
            append(event)
        while next_version <= account["version"]:
            missing = pending.pop(next_version, None)
            if missing is None:
                raise PaperConflict("Checkpoint history has a gap; no restore manifest created")
            append(missing)
    if pending:
        raise PaperConflict("Pending history lies beyond the account checkpoint")
    account_path = directory / "account.json"
    account_path.write_text(canonical(account), encoding="utf-8")
    manifest = dict(format="paper-checkpoint-1", owner=owner, account_id=account_id,
                    epoch=account["epoch"], version=account["version"], first_version=first_version,
                    events=count, account_sha256=file_hash(account_path), events_sha256=file_hash(event_path))
    # A failed export leaves no complete manifest and cannot be restored.
    (directory / "manifest.json").write_text(canonical(manifest), encoding="utf-8")
    return manifest


async def restore_frozen_copy(repository, owner, new_account_id, directory):
    """Preserve cash/positions in a fresh epoch; never overwrite the source account."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    account_path = directory / "account.json"
    event_path = directory / "events.jsonl"
    if (manifest.get("format") != "paper-checkpoint-1" or manifest.get("owner") != owner
            or file_hash(account_path) != manifest.get("account_sha256")
            or file_hash(event_path) != manifest.get("events_sha256")):
        raise PaperConflict("Checkpoint identity or file digest differs")
    if account_path.stat().st_size > MAX_DOCUMENT_BYTES * 6:
        raise PaperConflict("Checkpoint account exceeds supported size")
    source = validate_json(json.loads(account_path.read_text(encoding="utf-8")))
    if (source.get("account_id") != manifest["account_id"] or source.get("owner") != owner
            or source.get("epoch") != manifest["epoch"] or source.get("version") != manifest["version"]
            or source.get("storage_version") != 1 or source.get("recovery_pending")):
        raise PaperConflict("Account does not match its checkpoint manifest")
    if (source["_id"] != digest(scope(owner, source["account_id"], "internal"))
            or manifest["first_version"] != source.get("epoch_initial_version", 0) + 1):
        raise PaperConflict("Checkpoint source identity or initial version differs")
    binding = scope(owner, new_account_id, "internal")
    if new_account_id == source["account_id"]:
        raise PaperConflict("Recovery requires a new account identity; in-place rollback is refused")
    expected = manifest["first_version"]
    count = 0
    pending = {event["version"]: event for event in source["pending_events"]}
    if len(pending) != len(source["pending_events"]):
        raise PaperConflict("Duplicate pending checkpoint versions")
    with event_path.open("r", encoding="utf-8") as stream:
        while line := stream.readline(MAX_EVENT_BYTES * 6 + 1):
            if len(line) > MAX_EVENT_BYTES * 6:
                raise PaperConflict("Checkpoint history record exceeds supported size")
            event = validate_json(json.loads(line))
            event_valid(event, source, expected)
            original_pending = pending.pop(expected, None)
            if original_pending is not None and original_pending != event:
                raise PaperConflict("Pending seed differs from checkpoint history")
            expected += 1
            count += 1
    if pending or count != manifest["events"] or expected != source["version"] + 1:
        raise PaperConflict("Checkpoint is incomplete")
    restored = dict(_id=digest(binding), **binding, epoch=str(uuid.uuid4()), version=0,
                    storage_version=1, state=source["state"],
                    initial_digest=digest([source["state"], source.get("reserve_events", 0)]),
                    pending_events=[], reserve_events=source.get("reserve_events", 0), recovery_pending=True,
                    recovery=dict(source_account=source["account_id"], source_epoch=source["epoch"],
                                  source_version=source["version"], manifest_digest=digest(manifest),
                                  event_count=count, original_pending_count=len(source["pending_events"])))
    repository._size(restored)
    try:
        await repository.accounts.insert_one(restored)
    except DuplicateKeyError:
        raise PaperConflict("Recovery target already exists; it was not replaced") from None
    return restored
