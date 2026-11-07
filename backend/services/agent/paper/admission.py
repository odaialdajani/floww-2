"""Server-only internal paper admission and funded durable risk assessment.

Adapters establish source and confirmation provenance, never a risk verdict.
No application adapter is installed by default. Immutable bounded artifacts and
version-bound begin/resolve receipts make retries reconcile the original work.
"""
from __future__ import annotations

import asyncio
import copy
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from bson import BSON
from pymongo.errors import DuplicateKeyError

from services.agent.paper import execution, risk, risk_assessment
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
from services.execution_lease import MULTIPROCESS_SAFE, heartbeat_lease

MAX_ARTIFACTS = 128
MAX_ARTIFACT_BYTES = 64 * 1024


@dataclass(frozen=True)
class CapturedInputs:
    frame: dict
    opening_trade_evidence: dict | None
    immutable_source_refs: list[str]
    confirmation_record: dict


class TrustedPaperAdapter(Protocol):
    async def capture_verified_inputs(self, *, binding, expected_version, action,
                                      frozen_parameters, quote, confirmation_ref) -> CapturedInputs: ...

    async def verify_admission(self, *, owner, current_account, frozen_parameters,
                               confirmation_record, immutable_source_refs) -> bool: ...


@dataclass(frozen=True)
class PaperExecutionAuthority:
    """Constructor-only authority over an already acquired same-host lease.

    The server supplies the stop reader; request/model JSON cannot instantiate
    this object or change its policy. reduce_only preserves verified exits.
    """
    lease_path: str
    lease_token: str
    stop_reader: Callable[[], str]
    ttl_seconds: float = 120

    def require(self, action):
        if not MULTIPROCESS_SAFE or not callable(self.stop_reader):
            raise PaperConflict("Paper execution lease/stop authority is unavailable")
        mode = self.stop_reader()
        if mode not in ("running", "reduce_only") or (mode == "reduce_only" and action == "entry"):
            raise PaperConflict("Paper execution is stopped or paused for new exposure")
        if heartbeat_lease(self.lease_path, self.lease_token, self.ttl_seconds).get("ok") is not True:
            raise PaperConflict("Paper execution lease was lost; reconciliation required")


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
        command = validate_json(dict(kind=kind, parameters=terms,
                                     order_id=order_id, quote=request["quote"], frame=captured.frame,
                                     evidence=captured.opening_trade_evidence))
        refs = captured.immutable_source_refs
        if not isinstance(refs, list) or not refs or any(not isinstance(x, str) or not 1 <= len(x) <= 200 for x in refs):
            raise PaperConflict("Immutable verified source references are required")
        artifact = validate_json(dict(
            _id=key, **binding, epoch=current["epoch"], parent_operation=operation,
            starting_version=current["version"], policy_digest=current["state"]["risk_policy"]["digest"],
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
        if await self.repository.admissions.count_documents(binding, limit=MAX_ARTIFACTS) >= MAX_ARTIFACTS:
            raise PaperCapacity("Retained admission artifact capacity reached; preserve reconciliation evidence")
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
            self._require(artifact["action"])
            await self.repository.commit(owner, account, operation, begin_command, state, event)
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
        operation = operation_id(current["version"], str(uuid.uuid5(uuid.NAMESPACE_URL,
                                 current["epoch"] + ":replenish:" + str(current["version"]))), epoch=current["epoch"])
        self._require("reduce")
        return await self.repository.commit(owner, account, operation,
                                            dict(kind="paper_risk_replenish"), state, event)
