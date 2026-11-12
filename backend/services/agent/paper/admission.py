"""Server-only internal paper admission and funded durable risk assessment.

Adapters establish executable quote/source/confirmation provenance, never a
risk verdict. Both positive displayed sizes are required on the common service
path. The same-account commit fences durable execution generation and expiry;
OS lease/callback checks add preflight evidence, without atomic file-stop claims.
Immutable bounded artifacts and version-bound begin/resolve receipts reconcile
original work. New entries prepay eight entry-fill ATTEMPTS (the unchanged
MAX_FILLS_PER_ORDER) and existing exit liabilities. Every new immutable fill
parent spends one attempt, including unchanged/refused outcomes; exact retries
spend none. After eight, retain/cancel the working remainder while verified
reductions remain protected. Fresh bounded artifact counts govern admission and
replenishment; the funded state cache never grants or resets that allowance.
No application adapter is installed by default.
"""
from __future__ import annotations

import asyncio
import copy
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from bson import BSON
from pymongo.errors import DuplicateKeyError

from services.agent.paper import execution, risk, risk_assessment
from services.agent.paper.execution_control import PaperExecutionAuthority, claim_of
from services.agent.paper.policy import binding_of, validate_policy
from services.agent.paper.repository import (
    PaperCapacity,
    PaperConflict,
    digest,
    operation_id,
    operation_version,
    scope,
    validate_json,
)
from services.agent.paper.valuation import observe

MAX_ARTIFACTS = 128
MAX_ARTIFACT_BYTES = 64 * 1024


def artifact_liabilities(state, *, entry_attempts=None):
    """Protect every finite fill and funded exit attempt before new exposure.

    Eight distinct immutable entry-fill parents are prepaid, regardless of
    filled/unchanged/refused outcome. Operational callers supply freshly checked
    artifact counts. The persisted field is only their funded read-view cache;
    it cannot authorize another attempt or reset the actual retained history.
    """
    control = risk_assessment.control_of(state)
    attempts = state.get("entry_fill_attempts") if entry_attempts is None else entry_attempts
    if attempts is None:
        if any(order["side"] == "buy" and order["status"] == "working" for order in state["orders"].values()):
            raise PaperConflict("Verified entry-fill attempt snapshot is unavailable")
        attempts = {}
    if (not isinstance(attempts, dict) or len(attempts) > execution.MAX_ORDERS
            or any(type(value) is not int or not 0 <= value <= MAX_ARTIFACTS for value in attempts.values())):
        raise PaperConflict("Verified entry-fill attempt snapshot is invalid")
    entries = sum(max(0, execution.MAX_FILLS_PER_ORDER-attempts.get(order_id, 0))
                  for order_id, order in state["orders"].items() if order["side"] == "buy" and order["status"] == "working")
    return entries, sum(control["exit_credits"].values())


def require_artifact_capacity(state, retained, *, action, kind, entry_attempts):
    entries, exits = artifact_liabilities(state, entry_attempts=entry_attempts)
    if action == "entry" and kind == "stage":
        needed = retained+1+entries+exits+execution.MAX_FILLS_PER_ORDER+risk_assessment.EXIT_ASSESSMENT_CREDITS
    elif action == "entry":
        needed = retained+entries+exits
    else:
        # A reducing capture consumes one of its existing funded exit credits.
        # Entry retry attempts cannot spend this protected allowance.
        needed = retained+exits
    if retained >= MAX_ARTIFACTS or needed > MAX_ARTIFACTS:
        raise PaperCapacity("Retained artifacts must preserve all prepaid fill/exit capacity before new exposure")


@dataclass(frozen=True)
class CapturedInputs:
    frame: dict
    opening_trade_evidence: dict | None
    immutable_source_refs: list[str]
    confirmation_record: dict
    executable_quote: dict | None = None


class TrustedPaperAdapter(Protocol):
    async def capture_verified_inputs(self, *, binding, expected_version, action,
                                      frozen_parameters, quote, confirmation_ref) -> CapturedInputs: ...

    async def verify_admission(self, *, owner, current_account, frozen_parameters,
                               confirmation_record, immutable_source_refs) -> bool: ...


class PaperAdmissionService:
    def __init__(self, repository, *, adapter: TrustedPaperAdapter | None = None, authority: PaperExecutionAuthority | None = None, clock=None, source_timeout_seconds=5):
        self.repository = repository
        self.adapter = adapter
        self.authority = authority
        self.clock = clock or (lambda: datetime.now(UTC))
        if not 0 < source_timeout_seconds <= 30:
            raise ValueError("A bounded source admission timeout is required")
        self.source_timeout_seconds = source_timeout_seconds

    def _require(self, action):
        if (self.adapter is None or not callable(getattr(self.adapter, "capture_verified_inputs", None))
                or not callable(getattr(self.adapter, "verify_admission", None))):
            raise PaperConflict("Trusted paper admission/source/lease composition is not configured")
        self.require_execution(action)

    def require_execution(self, action):
        if not isinstance(self.authority, PaperExecutionAuthority):
            raise PaperConflict("Paper execution lease/stop authority is not configured")
        self.authority.require(action)

    async def bind_execution(self, owner, account, *, expected_generation=0, mode="running", expires_at=None):
        return await self.repository.bind_execution_control(owner, account, self.authority,
                    expected_generation=expected_generation, mode=mode, now=self.clock(), expires_at=expires_at)

    async def set_execution_mode(self, owner, account, mode, *, expected_generation):
        return await self.bind_execution(owner, account, expected_generation=expected_generation, mode=mode)

    async def revoke_execution(self, owner, account, *, expected_generation):
        # Durable revocation is acknowledged BEFORE the caller releases the OS
        # lease. An arbitrary raw file/callback edit is only preflight evidence.
        return await self.set_execution_mode(owner, account, "revoked", expected_generation=expected_generation)

    @staticmethod
    def _executable_quote(quote, terms, now):
        execution._quote(quote, terms, execution.instant(now))
        if any(type(quote.get(side)) is not int or quote[side] <= 0 for side in ("bid_size", "ask_size")):
            raise PaperConflict("Fresh positive two-sided displayed size is required")
        return validate_json(quote)

    async def _source(self, awaitable):
        try:
            return await asyncio.wait_for(awaitable, self.source_timeout_seconds)
        except TimeoutError as exc:
            raise PaperConflict("Paper source admission deadline exceeded") from exc

    async def _current(self, owner, account):
        current = await self.repository.read(owner, account)
        if current is None or current.get("recovery_pending") or current["state"].get("recovery_pending"):
            raise PaperConflict("Paper account unavailable or requires recovery")
        return validate_json(current)

    async def _entry_attempt_counts(self, current):
        """One bounded trusted scan, bound to account/epoch/exact opening order.

        Parent/version uniqueness and immutable content validation count each
        captured fill once, including lost replies and unsuccessful outcomes.
        No request flag, cached counter, credit reset or fill count is authority.
        """
        binding = scope(current["owner"], current["account_id"], "internal")
        orders = {key: value for key, value in current["state"]["orders"].items() if value["side"] == "buy"}
        counts = dict.fromkeys(orders, 0)
        seen = set()
        query = {**binding, "epoch": current["epoch"], "action": "entry", "command.kind": "fill"}
        async for record in self.repository.admissions.find(query).limit(MAX_ARTIFACTS):
            parent = record.get("parent_operation")
            if (record.get("artifact_digest") != digest({key: value for key, value in record.items() if key != "artifact_digest"})
                    or record.get("_id") != digest([binding, parent])
                    or not isinstance(parent, str) or parent.split(":", 1)[0] != current["epoch"]
                    or record.get("starting_version") != operation_version(parent)):
                raise PaperConflict("Retained entry-fill parent changed immutable identity")
            if parent in seen:
                raise PaperConflict("Retained entry-fill parent was duplicated")
            seen.add(parent)
            command = record["command"]
            order_id = command.get("order_id")
            if order_id not in orders:
                continue  # Archived orders cannot create another fill or liability.
            parameters = command.get("parameters") or {}
            if (parameters.get("order_id") != order_id or parameters.get("structure_id") != order_id
                    or parameters.get("side") != "buy"
                    or record.get("structure_id") != order_id
                    or risk.economics(parameters) != risk.economics(orders[order_id])):
                raise PaperConflict("Retained fill attempt differs from its exact opening order")
            counts[order_id] += 1
        return counts

    async def require_entry_fill_attempt(self, owner, account, order_id):
        current = await self._current(owner, account)
        counts = await self._entry_attempt_counts(current)
        if order_id not in counts:
            raise PaperConflict("Opening order is unavailable for an entry-fill attempt")
        if counts[order_id] >= execution.MAX_FILLS_PER_ORDER:
            raise PaperCapacity("The eight prepaid entry-fill attempts are exhausted; cancel or retain the remainder")
        return counts

    async def _verify(self, current, artifact):
        command = artifact["command"]
        approved = await self._source(self.adapter.verify_admission(
            owner=current["owner"], current_account=copy.deepcopy(current),
            frozen_parameters=copy.deepcopy(command.get("parameters")),
            confirmation_record=copy.deepcopy(artifact["confirmation_record"]),
            immutable_source_refs=copy.deepcopy(artifact["immutable_source_refs"]),
        ))
        if approved is not True:
            raise PaperConflict("Independent paper source/confirmation admission did not explicitly pass")

    async def execute(self, owner, account, operation, *, kind, parameters=None, order_id=None,
                      quote=None, confirmation=None):
        if kind not in ("stage", "fill"):
            raise ValueError("Supported paper action required")
        request = validate_json(dict(kind=kind, parameters=parameters, order_id=order_id,
                                     quote=quote, confirmation=confirmation))
        operation_version(operation)
        if not hasattr(self.repository, "admissions"):
            raise PaperConflict("Guarded paper admission storage is required")
        binding = scope(owner, account, "internal")
        key = digest([binding, operation])
        artifact = await self.repository.admissions.find_one({"_id": key})
        if artifact is not None:
            if artifact["request_digest"] != digest(request):
                raise PaperConflict("Admission parent already belongs to different instructions")
            return await self.resume(owner, account, operation)
        current = await self._current(owner, account)
        if current["version"] != operation_version(operation) or operation.split(":", 1)[0] != current["epoch"]:
            raise PaperConflict("Admission version or recovery epoch changed; do not create a replacement retry")
        if (current["state"].get("checked_at")
                and execution.instant(self.clock()) < execution.instant(current["state"]["checked_at"])):
            raise PaperConflict("Paper assessment clock moved backwards; no source event may return")
        terms = parameters if kind == "stage" else current["state"]["orders"].get(order_id)
        if not isinstance(terms, dict):
            raise PaperConflict("Paper order is unavailable")
        terms = validate_json(terms)
        if kind == "fill" and isinstance(request["quote"], dict):
            quote_key = digest([request["quote"].get("contract_id"), request["quote"].get("source_id")])
            if any(item["quote_key"] == quote_key for item in terms.get("fills", [])):
                raise PaperConflict("Quote already filled; retrieve the original admission receipt")
        action = "entry" if terms.get("side") == "buy" else "reduce"
        self._require(action)
        execution_claim = claim_of(current, self.authority, action, now=self.clock())
        if request["quote"] is not None:
            self._executable_quote(request["quote"], terms, self.clock())
        entry_attempts = await self._entry_attempt_counts(current)
        if kind == "fill" and action == "entry" and entry_attempts[order_id] >= execution.MAX_FILLS_PER_ORDER:
            raise PaperCapacity("The eight prepaid entry-fill attempts are exhausted; cancel or retain the remainder")
        control = risk_assessment.control_of(current["state"])
        if action == "entry":
            if control["pending"]:
                raise PaperConflict("Unresolved observations block new exposure")
            if control["entry_credits"] < risk_assessment.ENTRY_CREDITS:
                raise PaperCapacity("Project history and replenish observation credits before capture")
        validate_policy(current["state"].get("risk_policy"), binding_of(current), now=self.clock())
        captured = await self._source(self.adapter.capture_verified_inputs(
            binding=binding_of(current), expected_version=current["version"], action=action,
            frozen_parameters=copy.deepcopy(terms), quote=copy.deepcopy(request["quote"]),
            confirmation_ref=copy.deepcopy(request["confirmation"]),
        ))
        if not isinstance(captured, CapturedInputs):
            raise PaperConflict("Trusted source adapter must return data-only captured inputs")
        verified_quote = captured.executable_quote
        if verified_quote is None or request["quote"] is not None and verified_quote != request["quote"]:
            raise PaperConflict("Captured executable quote differs from its exact verified request")
        verified_quote = self._executable_quote(verified_quote, terms, self.clock())
        command = validate_json(dict(kind=kind, parameters=terms,
                                     order_id=order_id, quote=verified_quote, frame=captured.frame,
                                     evidence=captured.opening_trade_evidence))
        refs = captured.immutable_source_refs
        if not isinstance(refs, list) or not refs or any(not isinstance(x, str) or not 1 <= len(x) <= 200 for x in refs):
            raise PaperConflict("Immutable verified source references are required")
        artifact = validate_json(dict(
            _id=key, **binding, epoch=current["epoch"], parent_operation=operation,
            starting_version=current["version"], execution_claim=execution_claim, policy_digest=current["state"]["risk_policy"]["digest"],
            request_digest=digest(request), command=command, action=action,
            structure_id=terms.get("structure_id"), immutable_source_refs=refs,
            confirmation_record=captured.confirmation_record,
            resolve_operation=operation_id(current["version"] + 1,
                                           str(uuid.uuid5(uuid.NAMESPACE_URL, key + ":resolve")), epoch=current["epoch"]),
        ))
        artifact["artifact_digest"] = digest(artifact)
        if len(BSON.encode(artifact)) > MAX_ARTIFACT_BYTES:
            raise PaperCapacity("Captured admission artifact exceeds bounded storage")
        await self._verify(current, artifact)
        self._require(action)
        retained = await self.repository.admissions.count_documents(binding, limit=MAX_ARTIFACTS)
        require_artifact_capacity(current["state"], retained, action=action, kind=kind, entry_attempts=entry_attempts)
        try:
            await self.repository.admissions.insert_one(artifact)
        except DuplicateKeyError:
            saved = await self.repository.admissions.find_one({"_id": key})
            if saved != artifact:
                raise PaperConflict("Concurrent admission capture differs; retain the original artifact") from None
        return await self.resume(owner, account, operation)

    async def resume(self, owner, account, operation):
        key = digest([scope(owner, account, "internal"), operation])
        artifact = await self.repository.admissions.find_one({"_id": key})
        if artifact is None:
            raise PaperConflict("Original admission artifact is unavailable; do not recapture")
        if artifact["artifact_digest"] != digest({k: v for k, v in artifact.items() if k != "artifact_digest"}):
            raise PaperConflict("Immutable admission artifact changed")
        begin_command = dict(kind="paper_admission_begin", parent_operation=operation,
                             artifact_digest=artifact["artifact_digest"])
        resolve_command = dict(kind="paper_admission_resolve", parent_operation=operation,
                               artifact_digest=artifact["artifact_digest"])
        # Receipt lookup precedes every side effect, including source recapture.
        resolved = await self.repository.receipt(owner, account, artifact["resolve_operation"], resolve_command)
        if resolved is not None:
            return self._outcome(resolved, False)
        self._require(artifact["action"])
        current = await self._current(owner, account)
        if claim_of(current, self.authority, artifact["action"], now=self.clock()) != artifact["execution_claim"]:
            raise PaperConflict("Durable execution generation changed; retain original admission")
        await self._verify(current, artifact)
        begun = await self.repository.receipt(owner, account, operation, begin_command)
        if begun is None:
            if current["version"] != artifact["starting_version"]:
                winner = await self.repository.receipt(owner, account, artifact["resolve_operation"], resolve_command)
                if winner is not None:
                    return self._outcome(winner, False)
                raise PaperConflict("Admission parent changed before funding; reconcile the original operation")
            state, event = risk_assessment.begin(
                current, operation, artifact["command"], action=artifact["action"],
                structure_id=artifact["structure_id"], now=self.clock(),
            )
            # This new artifact has already consumed its attempt. Cache only
            # freshly derived immutable history, in the funded metadata write.
            counts = await self._entry_attempt_counts(current)
            if (artifact["action"] == "entry" and artifact["command"]["kind"] == "fill"
                    and counts[artifact["command"]["order_id"]] > execution.MAX_FILLS_PER_ORDER):
                raise PaperCapacity("Retained entry-fill attempts exceed the eight-attempt allowance")
            state["entry_fill_attempts"] = counts
            self._require(artifact["action"])
            await self.repository.commit(owner, account, operation, begin_command, state, event,
                                         execution_claim=artifact["execution_claim"])
        current = await self._current(owner, account)
        if current["version"] != artifact["starting_version"] + 1:
            winner = await self.repository.receipt(owner, account, artifact["resolve_operation"], resolve_command)
            if winner is not None:
                return self._outcome(winner, False)
            raise PaperConflict("Assessment book changed; reconciliation required, no replacement operation")
        self._require(artifact["action"])
        await self._verify(current, artifact)
        command, now = artifact["command"], self.clock()
        actual = observe(current["state"], command["frame"], now=now, binding=binding_of(current),
                         previous=current["state"].get("valuation"))
        if command["kind"] == "stage":
            result = risk.prepare_stage(current, command["parameters"], expected_version=current["version"],
                                        trade_evidence=command["evidence"], frame=command["frame"], now=now)
        else:
            result = risk.prepare_fill(current, command["order_id"], command["quote"],
                                       expected_version=current["version"], frame=command["frame"], now=now)
        try:
            state, event = risk_assessment.finalize(current, operation, result, actual, now=now)
        except PaperConflict as exc:
            raise PaperConflict("Paper risk valuation remains unresolved: " + str(exc)) from exc
        self._require(artifact["action"])
        receipt, created = await self.repository.commit(
            owner, account, artifact["resolve_operation"], resolve_command, state, event,
            execution_claim=artifact["execution_claim"],
        )
        self._require(artifact["action"])
        return self._outcome(receipt, created)

    @staticmethod
    def _outcome(receipt, created):
        body = receipt["body"]
        if body["assessment_status"] == "unchanged":
            return None, False
        if body["assessment_status"] != "pass":
            raise PaperConflict("Paper risk admission refused: " + str(body.get("assessment_reason")))
        return receipt, created

    async def replenish(self, owner, account):
        self._require("reduce")
        await self.repository.project(owner, account)
        current = await self._current(owner, account)
        if current["pending_events"]:
            raise PaperConflict("All saved assessment history must be projected before replenishment")
        state, event = risk_assessment.replenish(current["state"], now=self.clock())
        retained = await self.repository.admissions.count_documents(scope(owner, account, "internal"), limit=MAX_ARTIFACTS)
        counts = await self._entry_attempt_counts(current)
        entries, exits = artifact_liabilities(state, entry_attempts=counts)
        state["entry_fill_attempts"] = counts
        if retained+entries+exits > MAX_ARTIFACTS:
            raise PaperCapacity("Projection cannot recreate artifact liabilities beyond retained capacity")
        operation = operation_id(current["version"], str(uuid.uuid5(uuid.NAMESPACE_URL,
                                 current["epoch"] + ":replenish:" + str(current["version"]))), epoch=current["epoch"])
        self._require("reduce")
        return await self.repository.commit(owner, account, operation,
                                            dict(kind="paper_risk_replenish"), state, event)
