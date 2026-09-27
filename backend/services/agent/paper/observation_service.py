"""Unmounted, default-denied persistence of verified paper account observations."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from services.agent.paper.repository import PaperConflict, operation_version, validate_json
from services.agent.paper.valuation import book_digest, observe


class PreparedObservationService:
    def __init__(self, repository, *, evidence_check=None, clock=None):
        self.repository = repository
        self.evidence_check = evidence_check
        self.clock = clock or (lambda: datetime.now(UTC))

    async def record(self, owner, account, operation, frame):
        command = validate_json(dict(kind="paper_observation", frame=frame))
        existing = await self.repository.receipt(owner, account, operation, command)
        if existing is not None:
            return existing, False
        if self.evidence_check is None:
            raise PaperConflict("Verified observation admission is not configured")
        current = await self.repository.read(owner, account)
        if current is None or current["version"] != operation_version(operation):
            # A same-operation winner may commit between the initial receipt
            # lookup and this account read. Return its existing durable result.
            winner = await self.repository.receipt(owner, account, operation, command)
            if winner is not None:
                return winner, False
            raise PaperConflict("Account changed before observation; obtain fresh inputs")
        if await self.evidence_check(owner, copy.deepcopy(current), copy.deepcopy(command["frame"])) is not True:
            raise PaperConflict("Observation evidence did not independently pass")
        binding = {key: current[key] for key in ("owner", "account_id", "venue", "epoch")}
        previous = current["state"].get("valuation")
        snapshot = observe(current["state"], command["frame"], now=self.clock(), binding=binding, previous=previous)
        if (previous and previous["frame_digest"] == snapshot["frame_digest"]
                and previous["book_digest"] == snapshot["book_digest"]
                and previous.get("effective_digest") == snapshot["effective_digest"]
                and previous.get("saved_version") == current["version"]):
            # No accepted operation/receipt and no refreshed timestamp. The
            # original snapshot ages naturally; unchanged input cannot fill the
            # outbox or pretend to be a fresh saved observation.
            return None, False
        next_state = validate_json(current["state"])
        next_state["checked_at"] = snapshot["observed_at"]
        snapshot["book_digest"] = book_digest(next_state)
        snapshot["saved_version"] = current["version"] + 1
        next_state["valuation"] = snapshot
        event = dict(kind="paper_account_observed", observation=snapshot,
                     previous_session_risk=(previous or {}).get("risk_anchor")
                     if (previous or {}).get("risk", {}).get("session_id") != snapshot["risk"]["session_id"] else None)
        # Omit reserve_events: valuation cannot spend or release exit capacity.
        return await self.repository.commit(owner, account, operation, command, next_state, event)
