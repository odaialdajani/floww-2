"""Unmounted composition of prepared fill transitions and durable account state.

Entry is denied by default. An application composition must supply an independent
trusted admission check covering release, verified proposal, exact human
confirmation, account risk and product lifecycle. No such production composition
or action route is provided by this preparation module.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from services.agent.paper import execution
from services.agent.paper.repository import PaperConflict, validate_json


class PreparedPaperService:
    def __init__(self, repository, *, admission_check=None, clock=None):
        self.repository = repository
        self.admission_check = admission_check
        self.clock = clock or (lambda: datetime.now(UTC))

    async def _existing(self, owner, account, operation, command):
        return await self.repository.receipt(owner, account, operation, command)

    async def _save(self, owner, account, operation, command, state, event):
        receipt, created = await self.repository.commit(
            owner, account, operation, command, state, event,
            reserve_events=execution.recovery_events(state),
        )
        # State and pending history already committed together. Projection is
        # explicit and retryable; a slow/offline projector cannot repeat cash.
        return receipt, created

    async def stage(self, owner, account, operation, parameters, confirmation):
        command = validate_json(dict(kind="stage", parameters=parameters, confirmation=confirmation))
        existing = await self._existing(owner, account, operation, command)
        if existing is not None:
            return existing, False
        if self.admission_check is None:
            raise PaperConflict("Paper admission is disabled until its independent checks pass")
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable")
        # The callback is supplied by trusted server composition, never by a
        # request body or model response. It validates; it cannot silently alter
        # the human-confirmed economics below.
        approved = await self.admission_check(owner, copy.deepcopy(current),
                                              copy.deepcopy(command["parameters"]), copy.deepcopy(command["confirmation"]))
        if approved is not True:
            raise PaperConflict("Paper admission did not explicitly pass its independent checks")
        state, event = execution.stage_order(
            current["state"], **command["parameters"], epoch=current["epoch"], now=self.clock(),
            committed_version=current["version"] + 1,
        )
        return await self._save(owner, account, operation, command, state, event)

    async def quote(self, owner, account, operation, order_id, quote):
        command = validate_json(dict(kind="quote", order_id=order_id, quote=quote))
        existing = await self._existing(owner, account, operation, command)
        if existing is not None:
            return existing, False
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable")
        state, event, changed = execution.fill_order(
            current["state"], command["order_id"], command["quote"], now=self.clock(), committed_version=current["version"] + 1,
        )
        if not changed:
            if event is not None:
                raise PaperConflict("Quote already filled; retrieve the original request receipt")
            # No fill means no accepted operation/receipt. Its identity is not
            # consumed; callers must not present this as a saved order event.
            return event, False
        return await self._save(owner, account, operation, command, state, event)

    async def replenish(self, owner, account, operation):
        command = dict(kind="replenish_exit_capacity")
        existing = await self._existing(owner, account, operation, command)
        if existing is not None:
            return existing, False
        current = await self.repository.read(owner, account)
        if current is None or current["pending_events"]:
            raise PaperConflict("Project pending history before replenishing exit capacity")
        state, event = execution.replenish_exit_capacity(current["state"], now=self.clock())
        return await self._save(owner, account, operation, command, state, event)

    async def cancel(self, owner, account, operation, order_id):
        command = dict(kind="cancel", order_id=order_id)
        existing = await self._existing(owner, account, operation, command)
        if existing is not None:
            return existing, False
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable")
        state, event, changed = execution.cancel_order(
            current["state"], order_id, committed_version=current["version"] + 1,
        )
        if not changed:
            return event, False
        return await self._save(owner, account, operation, command, state, event)

    async def archive(self, owner, account, operation, order_id):
        command = dict(kind="archive", order_id=order_id)
        existing = await self._existing(owner, account, operation, command)
        if existing is not None:
            return existing, False
        current = await self.repository.read(owner, account)
        if current is None or order_id not in current["state"]["orders"]:
            raise PaperConflict("Order unavailable for this owner")
        order = current["state"]["orders"][order_id]
        projected = await self.repository.events.find_one({
            "scope_id": current["_id"], "epoch": current["epoch"], "version": order["last_event_version"],
        })
        if (projected is None or projected["body"].get("order_id") != order_id
                or projected["body"].get("kind") not in ("paper_fill", "paper_order_cancelled")):
            raise PaperConflict("Terminal order history is not yet durably projected")
        state, event = execution.archive_order(current["state"], order_id,
                                               projected_version=projected["version"])
        return await self._save(owner, account, operation, command, state, event)
