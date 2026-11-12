"""Unmounted composition of prepared fill transitions and durable account state.

Stage and fill delegate to funded admission: a server-constructed typed source
adapter and lease/stop authority are required, followed by persisted-policy risk
recomputation and guarded begin/resolve commits. The executable quote (including
both positive displayed sizes) comes from the exact request/captured source.
Durable account generation/mode/expiry fences the economic CAS; raw file or
callback changes alone are additional preflight checks. The legacy admission_check alone
cannot authorize either path. No application adapter or action route is mounted.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.agent.paper import execution
from services.agent.paper.admission import PaperAdmissionService
from services.agent.paper.execution_control import claim_of
from services.agent.paper.guarded_repository import GuardedPaperRepository
from services.agent.paper.repository import PaperConflict
from services.agent.paper.risk_assessment import reserved_events as guarded_reserve


class PreparedPaperService:
    def __init__(self, repository, *, admission_check=None, admission_adapter=None, execution_authority=None, clock=None):
        self.repository = repository
        # Retained as a denied compatibility argument; a Boolean cannot supply
        # source, confirmation, ownership, policy or execution authority.
        self.admission_check = admission_check
        self.clock = clock or (lambda: datetime.now(UTC))
        self.admission = PaperAdmissionService(repository, adapter=admission_adapter, authority=execution_authority, clock=self.clock)

    async def _existing(self, owner, account, operation, command):
        return await self.repository.receipt(owner, account, operation, command)

    async def _save(self, owner, account, operation, command, state, event, *, execution_claim=None):
        receipt, created = await self.repository.commit(
            owner, account, operation, command, state, event,
            reserve_events=guarded_reserve(state) if isinstance(self.repository, GuardedPaperRepository) else execution.recovery_events(state),
            **({"execution_claim": execution_claim} if execution_claim is not None else {}),
        )
        # State and pending history already committed together. Projection is
        # explicit and retryable; a slow/offline projector cannot repeat cash.
        return receipt, created

    async def stage(self, owner, account, operation, parameters, confirmation, *, quote=None):
        return await self.admission.execute(owner, account, operation, kind="stage", parameters=parameters,
                                             confirmation=confirmation, quote=quote)

    async def quote(self, owner, account, operation, order_id, quote):
        return await self.admission.execute(owner, account, operation, kind="fill", order_id=order_id, quote=quote)

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
        self.admission.require_execution("reduce")
        command = dict(kind="cancel", order_id=order_id)
        existing = await self._existing(owner, account, operation, command)
        if existing is not None:
            return existing, False
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable")
        claim = claim_of(current, self.admission.authority, "reduce", now=self.clock())
        state, event, changed = execution.cancel_order(
            current["state"], order_id, committed_version=current["version"] + 1,
        )
        if not changed:
            return event, False
        self.admission.require_execution("reduce")
        saved = await self._save(owner, account, operation, command, state, event, execution_claim=claim)
        self.admission.require_execution("reduce")
        return saved

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
