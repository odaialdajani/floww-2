"""Atomic bounded paper state and recoverable immutable events.

This is storage preparation, not an enabled paper venue. A future service must
validate economics, ownership, confirmation, risk and lifecycle before calling
commit. No broker or network-order capability is imported here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime

from bson import BSON
from pymongo.errors import DuplicateKeyError
from pymongo.write_concern import WriteConcern

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_PENDING_EVENTS = 128
MAX_EVENT_BYTES = 64 * 1024
MAX_RECOVERY_STATE_GROWTH = 64 * 1024
RESERVED_EVENT_BYTES = MAX_EVENT_BYTES + MAX_RECOVERY_STATE_GROWTH + 64
RESTORE_HEADROOM_BYTES = 2048
MAX_VERSION = 2**63 - 2


class PaperConflict(ValueError):
    """Identity differs, state moved, or a retired operation cannot be replayed."""


class PaperCapacity(ValueError):
    """Refuse a mutation rather than discard a position or recovery record."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Canonical UUID identity required")
    return value


def scope(owner, account, venue):
    identity(owner)
    identity(account)
    if venue != "internal":
        raise ValueError("Only the internal preparation venue exists")
    return dict(owner=owner, account_id=account, venue=venue)


def operation_id(expected_version, nonce=None, *, epoch):
    if type(expected_version) is not int or not 0 <= expected_version <= MAX_VERSION:
        raise ValueError("Invalid expected account version")
    return f"{identity(epoch)}:{expected_version}:{identity(nonce) if nonce else uuid.uuid4()}"


def operation_version(operation):
    if not isinstance(operation, str) or not re.fullmatch(r"[a-f0-9-]{36}:(?:0|[1-9][0-9]{0,18}):[a-f0-9-]{36}", operation):
        raise ValueError("A version-bound operation identity is required")
    epoch, version, nonce = operation.split(":", 2)
    version = int(version)
    operation_id(version, nonce, epoch=epoch)
    return version


def validate_json(value):
    """Detached JSON values only; BSON must not reinterpret caller dictionaries."""
    def visit(item, depth=0):
        if depth > 24:
            raise ValueError("Paper value nesting exceeds limit")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or not key or "." in key or key.startswith("$") or "\x00" in key:
                    raise ValueError("Invalid paper field name")
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
        elif item is not None and type(item) not in (str, bool, int):
            # Monetary values are exact decimal strings; binary floats never
            # enter the account document, including through nested events.
            raise ValueError("Paper values require exact JSON integers or strings")
        elif type(item) is int and not -(2**63) <= item < 2**63:
            raise ValueError("Paper integer exceeds storage range")

    visit(value)
    return json.loads(canonical(value))


class PaperRepository:
    def __init__(self, database, *, document_limit=MAX_DOCUMENT_BYTES, pending_limit=MAX_PENDING_EVENTS):
        if type(document_limit) is not int or not 1024 <= document_limit <= MAX_DOCUMENT_BYTES:
            raise ValueError("Invalid account document limit")
        if type(pending_limit) is not int or not 1 <= pending_limit <= MAX_PENDING_EVENTS:
            raise ValueError("Invalid pending event limit")
        # Journal acknowledgement is required even on the accepted standalone
        # deployment. Failures propagate; there is no memory fallback.
        concern = WriteConcern(w=1, j=True)
        self.accounts = database.get_collection("agent_paper_accounts", write_concern=concern)
        self.events = database.get_collection("agent_paper_events", write_concern=concern)
        self.document_limit = document_limit
        self.pending_limit = pending_limit

    async def initialize(self):
        await self.accounts.create_index([("owner", 1), ("account_id", 1), ("venue", 1)], unique=True)
        await self.events.create_index([("scope_id", 1), ("epoch", 1), ("version", 1)], unique=True)
        await self.events.create_index([("scope_id", 1), ("operation_id", 1)], unique=True)

    async def create(self, owner, account, initial_state, *, venue="internal", reserve_events=0):
        binding = scope(owner, account, venue)
        initial_state = validate_json(initial_state)
        if not isinstance(initial_state, dict):
            raise ValueError("Account state must be an object")
        doc = dict(_id=digest(binding), **binding, version=0, state=initial_state,
                   epoch=str(uuid.uuid4()), initial_digest=digest([initial_state, reserve_events]),
                   pending_events=[], storage_version=1, reserve_events=reserve_events)
        self._size(doc)
        try:
            await self.accounts.insert_one(doc)
            return copy.deepcopy(doc)
        except DuplicateKeyError:
            existing = await self.read(owner, account, venue=venue)
            if existing is None or existing["initial_digest"] != doc["initial_digest"]:
                raise PaperConflict("Account identity already has different starting settings") from None
            return existing

    async def read(self, owner, account, *, venue="internal"):
        return await self.accounts.find_one(scope(owner, account, venue))

    async def receipt(self, owner, account, operation, command, *, venue="internal"):
        operation_version(operation)
        doc = await self.read(owner, account, venue=venue)
        if doc is None or doc.get("recovery_pending"):
            raise PaperConflict("Paper account unavailable or awaiting recovery")
        if operation.split(":", 1)[0] != doc["epoch"]:
            raise PaperConflict("Operation belongs to an earlier account recovery")
        return await self._receipt(doc, operation, digest(validate_json(command)))

    def _size(self, doc):
        reserved = doc.get("reserve_events", 0)
        if type(reserved) is not int or not 0 <= reserved < self.pending_limit:
            raise PaperCapacity("Invalid recovery event reservation")
        if len(doc["pending_events"]) + reserved > self.pending_limit:
            raise PaperCapacity("Keep event capacity for existing obligations")
        restore_headroom = 0 if doc.get("recovery_pending") else RESTORE_HEADROOM_BYTES
        if len(BSON.encode(doc)) + reserved * RESERVED_EVENT_BYTES + restore_headroom > self.document_limit:
            raise PaperCapacity("Account document limit reached; existing state retained")

    async def _receipt(self, doc, operation, command_digest):
        event = next((e for e in doc["pending_events"] if e["operation_id"] == operation), None)
        if event is None:
            event = await self.events.find_one({"scope_id": doc["_id"], "operation_id": operation})
        if event is not None and event["version"] > doc["version"]:
            raise PaperConflict("Saved history is ahead of this account; recovery is required")
        if event is not None and event["command_digest"] != command_digest:
            raise PaperConflict("Operation identity already belongs to different instructions")
        return event

    async def commit(self, owner, account, operation, command, next_state, event_body,
                     *, venue="internal", reserve_events=None):
        expected = operation_version(operation)
        command = validate_json(command)
        next_state = validate_json(next_state)
        event_body = validate_json(event_body)
        if not all(isinstance(value, dict) for value in (command, next_state, event_body)):
            raise ValueError("Command, account state and event must be objects")
        binding = scope(owner, account, venue)
        command_digest = digest(command)
        doc = await self.accounts.find_one(binding)
        if doc is None:
            raise PaperConflict("Paper account unavailable for this owner")
        if doc.get("recovery_pending"):
            raise PaperConflict("Restored account requires reconciliation before any change")
        if operation.split(":", 1)[0] != doc["epoch"]:
            raise PaperConflict("Operation belongs to an earlier account recovery; obtain a new confirmation")
        receipt = await self._receipt(doc, operation, command_digest)
        if receipt is not None:
            return receipt, False
        if doc["version"] != expected:
            raise PaperConflict("Account changed or operation retired; reload without replaying it")
        newer_history = await self.events.find_one(
            {"scope_id": doc["_id"], "epoch": doc["epoch"], "version": {"$gt": doc["version"]}}
        )
        if newer_history is not None:
            raise PaperConflict("Saved history is ahead of this account; recovery is required")
        if len(doc["pending_events"]) >= self.pending_limit:
            raise PaperCapacity("Saved history must recover before accepting another change")
        event = dict(_id=digest([doc["_id"], operation]), scope_id=doc["_id"], **binding,
                     epoch=doc["epoch"],
                     operation_id=operation, command_digest=command_digest, version=expected + 1,
                     recorded_at=datetime.now(UTC).isoformat(), body=event_body)
        if len(BSON.encode(event)) > MAX_EVENT_BYTES:
            raise PaperCapacity("Paper event exceeds storage limit")
        candidate = {**doc, "state": next_state, "version": expected + 1,
                     "reserve_events": doc.get("reserve_events", 0) if reserve_events is None else reserve_events,
                     "pending_events": [*doc["pending_events"], event]}
        consumed = doc.get("reserve_events", 0) - candidate["reserve_events"]
        if consumed > 0:
            growth = len(BSON.encode({"state": next_state})) - len(BSON.encode({"state": doc["state"]}))
            if growth > consumed * MAX_RECOVERY_STATE_GROWTH:
                raise PaperCapacity("Recovery state growth exceeds its reserved capacity")
        self._size(candidate)
        result = await self.accounts.update_one(
            {**binding, "epoch": doc["epoch"], "version": expected},
            {"$set": {"state": next_state, "version": expected + 1,
                      "reserve_events": candidate["reserve_events"]}, "$push": {"pending_events": event}},
        )
        if result.modified_count == 1:
            return copy.deepcopy(event), True
        current = await self.accounts.find_one(binding)
        if current is not None and current["epoch"] != doc["epoch"]:
            raise PaperConflict("Account recovery changed while saving; obtain a new confirmation")
        receipt = await self._receipt(current, operation, command_digest) if current else None
        if receipt is not None:
            return receipt, False
        raise PaperConflict("Another account change won; no automatic replay")

    async def project(self, owner, account, *, venue="internal"):
        """A lost reply or crash may repeat projection; account cash is untouched."""
        binding = scope(owner, account, venue)
        doc = await self.accounts.find_one(binding)
        if doc is None:
            raise PaperConflict("Paper account unavailable for this owner")
        projected = 0
        for event in doc["pending_events"][:self.pending_limit]:
            if (event["scope_id"] != doc["_id"] or event["epoch"] != doc["epoch"]
                    or any(event[k] != v for k, v in binding.items())):
                raise PaperConflict("Saved event ownership differs from account")
            try:
                await self.events.insert_one(event)
            except DuplicateKeyError:
                existing = await self.events.find_one({"_id": event["_id"]})
                if existing != event:
                    raise PaperConflict("Saved history conflicts with the pending account event") from None
            # No whole-document replacement: a concurrent new event survives.
            removed = await self.accounts.update_one(
                {**binding, "epoch": doc["epoch"]}, {"$pull": {"pending_events": {"_id": event["_id"]}}}
            )
            if removed.matched_count == 0:
                raise PaperConflict("Account recovery changed during history projection")
            projected += 1
        return projected
