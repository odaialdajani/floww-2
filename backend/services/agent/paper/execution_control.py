"""Server-owned durable execution fence for the internal paper account.

An OS lease/callback is an additional preflight check, not an atomic database
revocation. Supported bind/mode/revoke operations journal the account control
first; the same-account economic CAS compares that exact generation/identity
and its Mongo server-time expiry. A later revocation cannot undo a prior CAS.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from services.agent.paper.execution import instant
from services.agent.paper.repository import PaperConflict, digest, validate_json
from services.execution_lease import MULTIPROCESS_SAFE, heartbeat_lease, read_lease

MODES = {"running", "reduce_only", "stopped", "revoked"}
IDENTITY_FIELDS = ("lease_scope", "executor_owner", "token_digest", "os_fence", "authority_id")
CONTROL_FIELDS = {"control_version", "generation", "mode", "expires_at", *IDENTITY_FIELDS}


@dataclass(frozen=True)
class PaperExecutionAuthority:
    """Constructor-only holder of an already acquired same-host OS lease."""
    lease_path: str
    lease_token: str
    stop_reader: Callable[[], str]
    ttl_seconds: float = 120

    def descriptor(self):
        if (not MULTIPROCESS_SAFE
                or heartbeat_lease(self.lease_path, self.lease_token, self.ttl_seconds).get("ok") is not True):
            raise PaperConflict("Paper execution lease was lost; reconciliation required")
        lease = read_lease(self.lease_path)
        if (not lease.get("present") or lease.get("expired") or type(lease.get("fence")) is not int
                or heartbeat_lease(self.lease_path, self.lease_token, self.ttl_seconds).get("ok") is not True):
            raise PaperConflict("Paper execution lease identity is unavailable")
        identity = dict(lease_scope=digest(str(Path(self.lease_path).resolve())), executor_owner=lease["owner"],
                        token_digest=digest(self.lease_token), os_fence=lease["fence"])
        return {**identity, "authority_id": digest(identity)}

    def require(self, action):
        if not callable(self.stop_reader):
            raise PaperConflict("Paper execution stop preflight is unavailable")
        mode = self.stop_reader()
        if mode not in ("running", "reduce_only") or (mode == "reduce_only" and action == "entry"):
            raise PaperConflict("Paper execution is stopped or paused for new exposure")
        self.descriptor()


def validate_control(control):
    control = validate_json(control)
    if (not isinstance(control, dict) or set(control) != CONTROL_FIELDS
            or control["control_version"] != 1 or type(control["control_version"]) is not int
            or type(control["generation"]) is not int or not 1 <= control["generation"] < 2**63
            or type(control["os_fence"]) is not int or control["os_fence"] < 1
            or control["mode"] not in MODES):
        raise PaperConflict("Complete durable paper execution authority is required")
    if control["authority_id"] != digest({key: control[key] for key in IDENTITY_FIELDS if key != "authority_id"}):
        raise PaperConflict("Durable paper execution identity changed")
    instant(control["expires_at"])
    return control


def claim_of(account, authority, action, *, now):
    if not isinstance(authority, PaperExecutionAuthority):
        raise PaperConflict("Explicit paper execution authority is required")
    control = validate_control(account.get("execution_control"))
    identity = authority.descriptor()
    if account.get("execution_generation") != control["generation"]:
        raise PaperConflict("Durable execution monotonic generation is unavailable")
    if any(control[key] != identity[key] for key in IDENTITY_FIELDS):
        raise PaperConflict("Durable paper executor owner or fence differs")
    if (control["mode"] not in ("running", "reduce_only")
            or action == "entry" and control["mode"] != "running"
            or instant(now) >= instant(control["expires_at"])):
        raise PaperConflict("Durable paper execution authority is stopped, revoked or expired")
    return control


def next_control(previous, authority, expected_generation, mode, *, now, expires_at=None):
    if not isinstance(authority, PaperExecutionAuthority) or mode not in MODES:
        raise PaperConflict("Server-owned durable execution control is required")
    generation = validate_control(previous)["generation"] if previous is not None else 0
    if type(expected_generation) is not int or expected_generation != generation:
        raise PaperConflict("Durable execution generation changed; reload without replay")
    identity = authority.descriptor()
    if previous is not None:
        if identity["lease_scope"] != previous["lease_scope"]:
            raise PaperConflict("Executor takeover must use the same scoped OS lease")
        if identity["authority_id"] != previous["authority_id"] and identity["os_fence"] <= previous["os_fence"]:
            raise PaperConflict("Executor takeover must advance the existing OS fence")
    checked = instant(now)
    deadline = checked+timedelta(seconds=authority.ttl_seconds)
    if expires_at is not None:
        requested = instant(expires_at)
        if requested > deadline:
            raise PaperConflict("Durable execution expiry cannot exceed the held lease period")
        deadline = requested
    if mode in ("stopped", "revoked"):
        deadline = checked
    return validate_control(dict(control_version=1, generation=generation+1, mode=mode,
                                 expires_at=deadline.isoformat(), **identity))
