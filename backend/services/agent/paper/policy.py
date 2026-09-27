"""Explicit, immutable paper policy records; no account or action admission.

Trusted composition must verify owner acceptance. These pure helpers neither
authenticate a request nor save state. A caller must commit the returned policy
transition with the existing account-version check. No policy value has a default.
"""

from __future__ import annotations

import copy

from services.agent.paper.accounting import exact
from services.agent.paper.execution import instant
from services.agent.paper.repository import PaperConflict, canonical, digest, identity, scope, validate_json

MAX_POLICY_BYTES = 8192
LIMITS = {"per_trade_max_loss", "daily_loss_limit", "observed_drawdown_limit", "max_committed_exposure"}
SEMANTICS = {
    "account_mode": "long_only_cash",
    "exposure_basis": "marked_holdings_pending_debits_and_cost_buffers",
    "loss_boundary": "strict_less_than",
    "exposure_boundary": "less_than_or_equal",
    "peak_coverage": "sampled_only",
    "breach_behavior": "current_observation_only",
    "risk_reduction": "allow_verified_reduction_with_known_costs",
    "buffer_basis": "linear_per_unit",
    "closing_reservation": "included_in_exit_cost_buffer",
}


def binding_of(value):
    if not isinstance(value, dict):
        raise ValueError("Exact account ownership binding required")
    result = {**scope(value.get("owner"), value.get("account_id"), value.get("venue")),
              "epoch": identity(value.get("epoch"))}
    return result


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("A bounded evidence identity is required")
    return value


def evidence_ids(values):
    if not isinstance(values, list) or not 1 <= len(values) <= 16:
        raise ValueError("Explicit bounded acceptance or verification evidence is required")
    checked = [label(value) for value in values]
    if len(set(checked)) != len(checked):
        raise ValueError("Repeated evidence identities are ambiguous")
    return checked


def policy_body(body):
    body = validate_json(body)
    if not isinstance(body, dict) or set(body) != {*SEMANTICS, "currency", "limits", "valuation"}:
        raise ValueError("Every supported policy field must be explicitly supplied")
    if body["currency"] != "USD" or any(body[key] != value for key, value in SEMANTICS.items()):
        raise ValueError("Unsupported or unspecified paper policy semantics")
    if not isinstance(body["limits"], dict) or set(body["limits"]) != LIMITS:
        raise ValueError("Every account limit must be explicitly supplied")
    for value in body["limits"].values():
        exact(value, nonnegative=True)
    settings = body["valuation"]
    if not isinstance(settings, dict) or set(settings) != {"mark_method", "max_mark_age_seconds", "max_spread"}:
        raise ValueError("Every valuation setting must be explicitly supplied")
    if settings["mark_method"] not in ("bid", "midpoint"):
        raise ValueError("Unsupported valuation method")
    if type(settings["max_mark_age_seconds"]) is not int or not 1 <= settings["max_mark_age_seconds"] <= 300:
        raise ValueError("Unsupported valuation age")
    exact(settings["max_spread"], nonnegative=True)
    return body


def create_policy(binding, body, *, policy_id, policy_version, effective_at, accepted_at,
                  accepted_by, acceptance_evidence, now, verify_acceptance):
    """Record an explicit acceptance only after a trusted independent check."""
    binding = validate_json(binding)
    if binding != binding_of(binding):
        raise ValueError("Exact policy owner/account/venue/recovery binding required")
    if type(policy_version) is not int or not 1 <= policy_version < 2**63:
        raise ValueError("A positive policy version is required")
    accepted, effective, checked = instant(accepted_at), instant(effective_at), instant(now)
    if accepted > checked or effective < accepted:
        raise ValueError("Policy acceptance time is invalid")
    if accepted_by != binding["owner"]:
        raise PaperConflict("Policy acceptance belongs to another owner")
    record = dict(record_version=1, binding=binding, policy_id=identity(policy_id), policy_version=policy_version,
                  effective_at=effective.isoformat(), accepted_at=accepted.isoformat(), accepted_by=accepted_by,
                  acceptance_evidence=evidence_ids(acceptance_evidence), body=policy_body(body))
    if not callable(verify_acceptance) or verify_acceptance(copy.deepcopy(record)) is not True:
        raise PaperConflict("Independent owner acceptance did not pass")
    record["digest"] = digest(record)
    if len(canonical(record).encode()) > MAX_POLICY_BYTES:
        raise ValueError("Policy record exceeds its supported size")
    return record


def validate_policy(record, binding, *, now):
    """Validate a stored trusted record; a digest is not an authentication proof."""
    record = validate_json(record)
    required = {"record_version", "binding", "policy_id", "policy_version", "effective_at", "accepted_at",
                "accepted_by", "acceptance_evidence", "body", "digest"}
    if (not isinstance(record, dict) or set(record) != required or type(record["record_version"]) is not int
            or record["record_version"] != 1):
        raise ValueError("Complete supported policy record required")
    body = {key: value for key, value in record.items() if key != "digest"}
    if digest(body) != record["digest"] or len(canonical(record).encode()) > MAX_POLICY_BYTES:
        raise PaperConflict("Stored policy content changed")
    expected = binding_of(binding)
    if record["binding"] != expected or record["accepted_by"] != expected["owner"]:
        raise PaperConflict("Policy belongs to another account or recovery")
    identity(record["policy_id"])
    if type(record["policy_version"]) is not int or not 1 <= record["policy_version"] < 2**63:
        raise ValueError("Unsupported policy version")
    evidence_ids(record["acceptance_evidence"])
    if not instant(record["accepted_at"]) <= instant(record["effective_at"]) <= instant(now):
        raise PaperConflict("Policy is not effective at the decision time")
    policy_body(record["body"])
    return record


def valuation_policy(record):
    """Translate the chosen policy into the existing observation input fields."""
    return {**record["body"]["valuation"], "policy_id": f"{record['policy_id']}:{record['policy_version']}",
            "daily_loss_limit": record["body"]["limits"]["daily_loss_limit"],
            "drawdown_limit": record["body"]["limits"]["observed_drawdown_limit"],
            "max_gross_exposure": record["body"]["limits"]["max_committed_exposure"]}


def prepare_policy_change(account, record, *, expected_version, expected_policy_digest, now):
    """Pure version-bound change; retained observations and loss anchors are kept."""
    account = validate_json(account)
    if (not isinstance(account, dict) or account.get("recovery_pending") or type(expected_version) is not int
            or account["version"] != expected_version):
        raise PaperConflict("Account changed or needs recovery before changing policy")
    if account["state"].get("epoch") not in (None, account["epoch"]):
        raise PaperConflict("Book and account recovery differ")
    record = validate_policy(record, binding_of(account), now=now)
    prior = account["state"].get("risk_policy")
    if prior is None:
        if expected_policy_digest is not None or record["policy_version"] != 1:
            raise PaperConflict("First policy must have its initial version")
    else:
        prior = validate_policy(prior, binding_of(account), now=now)
        if (expected_policy_digest != prior["digest"] or record["policy_id"] != prior["policy_id"]
                or record["policy_version"] != prior["policy_version"] + 1):
            raise PaperConflict("Policy change does not follow the current immutable version")
    state = validate_json(account["state"])
    if state.get("checked_at") is not None and instant(now) < instant(state["checked_at"]):
        raise PaperConflict("Policy clock moved backwards")
    state["risk_policy"] = record
    state["checked_at"] = instant(now).isoformat()
    # Never discard valuation/risk_anchor: a new policy requires explicit
    # reconciliation rather than resetting same-session loss or peak history.
    return state, dict(kind="paper_policy_recorded", policy=record, previous_digest=expected_policy_digest,
                       input_account_version=expected_version, admission_allowed=False)
