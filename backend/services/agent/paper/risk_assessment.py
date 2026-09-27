"""Pure bounded assessment intents funded before source evaluation.

Only newly created guarded preparation accounts use this contract. Guard event
credits are storage liabilities, not money. They never release existing exits.
"""
from __future__ import annotations

import copy

from bson import BSON

from services.agent.paper import execution
from services.agent.paper.policy import binding_of
from services.agent.paper.repository import PaperCapacity, PaperConflict, digest, operation_version, validate_json
from services.agent.paper.risk import prepare_fill, prepare_stage
from services.agent.paper.valuation import book_digest, observe

CONTROL_VERSION = 1
ENTRY_CREDITS = 2
EXIT_ASSESSMENT_CREDITS = 2 * (execution.EXIT_QUOTES + 1)
MAX_INTENT_BYTES = 56 * 1024
MAX_PENDING_ASSESSMENTS = 1 + execution.MAX_POSITIONS


def new_control():
    return dict(control_version=CONTROL_VERSION, entry_credits=ENTRY_CREDITS, exit_credits={}, pending={})


def control_of(state):
    control = state.get("risk_control")
    if (not isinstance(control, dict) or set(control) != {"control_version", "entry_credits", "exit_credits", "pending"}
            or type(control["control_version"]) is not int or control["control_version"] != CONTROL_VERSION):
        raise PaperConflict("An explicitly created guarded account is required")
    if type(control["entry_credits"]) is not int or not 0 <= control["entry_credits"] <= ENTRY_CREDITS:
        raise PaperConflict("Entry observation credits are invalid")
    if not isinstance(control["exit_credits"], dict) or not isinstance(control["pending"], dict):
        raise PaperConflict("Guarded obligations are invalid")
    if len(control["exit_credits"]) > execution.MAX_ORDERS or len(control["pending"]) > MAX_PENDING_ASSESSMENTS:
        raise PaperCapacity("Guarded assessment capacity reached")
    for value in control["exit_credits"].values():
        if type(value) is not int or not 0 <= value <= EXIT_ASSESSMENT_CREDITS:
            raise PaperConflict("Exit observation credits are invalid")
    return control


def reserved_events(state):
    control = control_of(state)
    return execution.recovery_events(state) + control["entry_credits"] + sum(control["exit_credits"].values())


def observation_basis(state):
    """Keep the exact bounded actual book needed for historical observation.

    No recursively nested guard/control data and no hypothetical candidate book.
    Prior source watermarks and session anchors remain available after restart.
    """
    keys = {"book_version", "currency", "cash", "initial_cash", "realized_result", "positions"}
    basis = {key: copy.deepcopy(state[key]) for key in keys}
    for key in ("epoch", "checked_at"):
        if key in state:
            basis[key] = state[key]
    basis["orders"] = {key: {"status": order["status"], "reserved_cash": order["reserved_cash"]}
                       for key, order in state["orders"].items()}
    previous = state.get("valuation")
    if previous:
        basis["valuation"] = {key: copy.deepcopy(previous[key]) for key in
                              ("binding", "observed_at", "risk", "risk_anchor", "mark_watermarks", "last_complete")
                              if key in previous}
    return validate_json(basis)


def begin(account, request_id, command, *, action, structure_id, now):
    """Return a funded intent, without evaluating prices or calling a checker."""
    account, command = validate_json(account), validate_json(command)
    if account.get("recovery_pending") or account["version"] != operation_version(request_id):
        raise PaperConflict("Account changed or requires recovery before assessment")
    if request_id.split(":", 1)[0] != account["epoch"]:
        raise PaperConflict("Assessment belongs to another recovery")
    state = account["state"]
    source_book = book_digest(state)
    basis = observation_basis(state)
    control = control_of(state)
    if action not in ("entry", "reduce"):
        raise ValueError("Explicit supported assessment action required")
    if len(control["pending"]) >= MAX_PENDING_ASSESSMENTS:
        raise PaperCapacity("Unresolved assessment limit reached")
    if action == "entry":
        if control["pending"]:
            raise PaperConflict("Unresolved observations block increased exposure")
        if control["entry_credits"] < ENTRY_CREDITS:
            raise PaperCapacity("Project history and replenish observation credits before evaluation")
        control["entry_credits"] -= 1
        source = "entry"
    else:
        if structure_id not in state["positions"]:
            raise PaperConflict("A reducing assessment requires known held exposure")
        pending = sum(item["credit_source"] == structure_id for item in control["pending"].values())
        if control["exit_credits"].get(structure_id, 0) < 2 + pending:
            raise PaperCapacity("Protected exit assessment attempts need history projection and replenishment")
        control["exit_credits"][structure_id] -= 1
        source = structure_id
    checked = execution.instant(now)
    if state.get("checked_at") and checked < execution.instant(state["checked_at"]):
        raise PaperConflict("Assessment clock moved backwards")
    intent = dict(intent_version=1, request_id=request_id, command=command, command_digest=digest(command),
                  action=action, structure_id=structure_id, credit_source=source, binding=binding_of(account),
                  input_version=account["version"], assessment_version=account["version"]+1,
                  source_book_digest=source_book, basis=basis,
                  begun_at=checked.isoformat())
    if len(BSON.encode(intent)) > MAX_INTENT_BYTES:
        raise PaperCapacity("Source frame and historical basis exceed prepaid assessment storage")
    control["pending"][request_id] = intent
    state["checked_at"] = checked.isoformat()
    event = dict(kind="paper_risk_assessment_begun", assessment_phase="begun", assessment_id=request_id,
                 original_command_digest=intent["command_digest"], action=action,
                 source_book_digest=intent["source_book_digest"], intent_digest=digest(intent),
                 admission_allowed=False)
    return state, event


def finalize(account, request_id, result, actual, *, now):
    """Resolve only this exact book's intent; preserve every other uncertainty."""
    account = validate_json(account)
    original = control_of(account["state"])
    intent = original["pending"].get(request_id)
    if intent is None or account["version"] != intent["assessment_version"]:
        raise PaperConflict("Assessment book changed; retain unresolved historical evidence")
    if not isinstance(actual, dict):
        raise PaperConflict("No actual observation was captured; keep the unresolved intent")
    observed = execution.instant(actual.get("observed_at"))
    if not execution.instant(intent["begun_at"]) <= observed <= execution.instant(now):
        raise PaperConflict("Actual observation time does not belong to this assessment")
    expected_actual = observe(account["state"], intent["command"].get("frame"), now=observed,
                              binding=binding_of(account), previous=account["state"].get("valuation"))
    if (actual != expected_actual or actual.get("equity") is None or actual.get("unknown_positions")
            or actual.get("risk", {}).get("status") != "observed"):
        raise PaperConflict("Actual observation is incomplete or differs from exact captured evidence; retain intent")
    passed = result["status"] == "pass"
    if passed:
        decision = result.get("decision") or {}
        if (decision.get("binding") != binding_of(account) or decision.get("input_account_version") != account["version"]
                or decision.get("before_book_digest") != book_digest(account["state"])):
            raise PaperConflict("Risk candidate does not match the exact assessed book")
        event = result.get("event") or {}
        if (event.get("kind") not in ("paper_order_staged", "paper_fill")
                or event.get("risk_decision") != decision
                or decision.get("after_book_digest") != book_digest(result["state"])):
            raise PaperConflict("Risk result and proposed economic event differ")
        target = result["state"]["orders"].get(event.get("order_id"))
        side = "buy" if intent["action"] == "entry" else "sell"
        if not target or target.get("side") != side:
            raise PaperConflict("A reducing assessment cannot authorize increased exposure")
        if intent["action"] == "reduce" and target.get("structure_id") != intent["structure_id"]:
            raise PaperConflict("Reducing candidate targets another held structure")
        command = intent["command"]
        decided = execution.instant(decision.get("evaluated_at"))
        if not execution.instant(intent["begun_at"]) <= decided <= execution.instant(now):
            raise PaperConflict("Risk decision time does not belong to this assessment")
        if event["kind"] == "paper_order_staged":
            recomputed = prepare_stage(account, command.get("parameters"), expected_version=account["version"],
                                       trade_evidence=command.get("evidence"), frame=command.get("frame"), now=decided)
        else:
            recomputed = prepare_fill(account, command.get("order_id"), command.get("quote"),
                                      expected_version=account["version"], frame=command.get("frame"), now=decided)
        if recomputed != result:
            raise PaperConflict("Candidate differs from independently recomputed captured command and frame")
    state = validate_json(result["state"] if passed else account["state"])
    control = control_of(state)
    if control["pending"].get(request_id) != intent:
        raise PaperConflict("Candidate changed its durable observation intent")
    source = intent["credit_source"]
    if source == "entry":
        if control["entry_credits"] < 1:
            raise PaperConflict("Resolution lost its prepaid event")
        control["entry_credits"] -= 1
    elif not passed:
        if control["exit_credits"].get(source, 0) < 1:
            raise PaperConflict("Exit observation lost its prepaid resolution event")
        control["exit_credits"][source] -= 1
    del control["pending"][request_id]
    for structure in state["exit_capacity"]:
        if structure not in control["exit_credits"]:
            control["exit_credits"][structure] = EXIT_ASSESSMENT_CREDITS
    state["checked_at"] = execution.instant(now).isoformat()
    snapshot = copy.deepcopy(state.get("valuation") if passed else actual)
    if snapshot is not None:
        # All control/credit edits precede binding the final saved observation.
        snapshot["book_digest"] = book_digest(state)
        snapshot["saved_version"] = account["version"] + 1
        state["valuation"] = snapshot
    body = copy.deepcopy(result.get("event")) if passed else dict(kind="paper_risk_action_refused")
    body.update(assessment_phase="resolved", assessment_id=request_id,
                original_command_digest=intent["command_digest"], assessment_status=result["status"],
                assessment_reason=result.get("reason"), actual_before=actual, admission_allowed=False)
    if passed and body.get("risk_decision"):
        body["risk_decision"]["after_book_digest"] = book_digest(state)
    return state, body


def replenish(state, *, now):
    """Pure replenishment; caller must prove all pending history is projected."""
    state = validate_json(state)
    control = control_of(state)
    if control["pending"]:
        raise PaperConflict("Unresolved observations cannot be reset by replenishment")
    checked = execution.instant(now)
    if state.get("checked_at") and checked < execution.instant(state["checked_at"]):
        raise PaperConflict("Replenishment clock moved backwards")
    control["entry_credits"] = ENTRY_CREDITS
    control["exit_credits"] = {structure: EXIT_ASSESSMENT_CREDITS for structure in state["exit_capacity"]}
    state["checked_at"] = checked.isoformat()
    return state, dict(kind="paper_risk_credits_replenished", admission_allowed=False)
