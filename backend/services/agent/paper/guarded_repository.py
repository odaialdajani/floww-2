"""Isolated guarded preparation collections with normal immutable event history.

Every observation intent/resolution uses ordinary account versions and events.
No enabled application route uses these collections. Server deadline predicates
mean server expression evaluation time, never final journal-acknowledgement time.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

from bson import BSON

from services.agent.paper.execution import instant
from services.agent.paper.repository import (
    MAX_EVENT_BYTES,
    MAX_RECOVERY_STATE_GROWTH,
    PaperCapacity,
    PaperConflict,
    PaperRepository,
    digest,
    operation_version,
    scope,
    validate_json,
)
from services.agent.paper.risk_assessment import control_of, new_control
from services.agent.paper.risk_assessment import reserved_events as guarded_reserve


class GuardedPaperRepository(PaperRepository):
    def __init__(self, database, **limits):
        super().__init__(database, **limits)
        concern = self.accounts.write_concern
        self.accounts = database.get_collection("agent_paper_guarded_accounts", write_concern=concern)
        self.events = database.get_collection("agent_paper_guarded_events", write_concern=concern)

    async def create(self, owner, account, initial_state, *, venue="internal", reserve_events=None):
        state = validate_json(initial_state)
        if "risk_control" not in state:
            state["risk_control"] = new_control()
        if state["risk_control"] != new_control() or state.get("orders") or state.get("positions"):
            raise PaperConflict("Only a new empty guarded account can be created; no implicit migration")
        required = guarded_reserve(state)
        if reserve_events is not None and reserve_events != required:
            raise PaperConflict("Explicit creation must preserve all observation credits")
        return await super().create(owner, account, state, venue=venue, reserve_events=required)

    def _size(self, doc):
        control_of(doc["state"])
        if doc.get("reserve_events") != guarded_reserve(doc["state"]):
            raise PaperConflict("Stored guarded credits do not reconcile")
        super()._size(doc)

    async def commit(self, owner, account, operation, command, next_state, event_body,
                     *, venue="internal", reserve_events=None, valid_after=None, valid_until=None):
        expected = operation_version(operation)
        command = validate_json(command)
        next_state = validate_json(next_state)
        event_body = validate_json(event_body)
        if not all(isinstance(value, dict) for value in (command, next_state, event_body)):
            raise ValueError("Command, account state and event must be objects")
        required_reserve = guarded_reserve(next_state)
        if reserve_events is not None and reserve_events != required_reserve:
            raise PaperConflict("Guard credits and exit obligations must all remain reserved")
        reserve_events = required_reserve
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
        selector = {**binding, "epoch": doc["epoch"], "version": expected}
        risk_decision = event_body.get("risk_decision", {})
        if risk_decision.get("status") == "pass":
            required_after, required_until = risk_decision["evaluated_at"], risk_decision["valid_until"]
            if ((valid_after is not None and instant(valid_after) != instant(required_after))
                    or (valid_until is not None and instant(valid_until) != instant(required_until))):
                raise PaperConflict("Caller cannot broaden the checked risk decision window")
            valid_after, valid_until = required_after, required_until
        if valid_after is not None or valid_until is not None:
            if valid_after is None or valid_until is None:
                raise ValueError("Both bounds of the server-time window are required")
            earliest, latest = instant(valid_after), instant(valid_until)
            # BSON dates have millisecond precision. Round inward so neither
            # edge admits a time outside the original exact decision window.
            earliest += timedelta(microseconds=(-earliest.microsecond) % 1000)
            latest = latest.replace(microsecond=latest.microsecond // 1000 * 1000)
            if latest <= earliest:
                raise ValueError("A positive millisecond server-time validity window is required")
            selector["$expr"] = {"$and": [{"$gte": ["$$NOW", earliest]}, {"$lt": ["$$NOW", latest]}]}
        result = await self.accounts.update_one(
            selector,
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
        raise PaperConflict("Account version or server-time window no longer matches; retain the unresolved assessment")
