"""
backend/services/execution_admission.py — required durable admission boundary.

Contract `execution-admission.v1` (S1, additive, default-deny). This module
decides production admission; it never places, cancels, or touches a broker.
All broker transport stays behind the existing separately gated executor.

Required mode inverts the legacy best-effort posture:
- Missing/unusable store, required DDL failure, failed policy/approval/
  revocation writes and failed recovery/census queries REFUSE. Memory is
  never authoritative after a failed durable write (the memory row is purged).
- Unknown recovery counts are not zero. Corrupt rows and partial scans refuse
  as incomplete/unknown instead of asserting a clean census.
- Account policies are keyed by account (schema v2) with explicit scope and
  version. Legacy global v1 rows migrate only through an explicit operator
  call into a named account — never by guessing.

Refusal codes: STORE_UNAVAILABLE, POLICY_STORE_UNAVAILABLE, POLICY_UNSET,
POLICY_CORRUPT, POLICY_EXISTS, APPROVAL_STORE_UNAVAILABLE, RECOVERY_UNKNOWN,
RECOVERY_INCOMPLETE, UNKNOWN_ORDERS_PENDING, plus pass-through submit
reasons (APPROVAL_* etc.).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

ADMISSION_VERSION = "execution-admission.v1"
ACCOUNT_POLICY_V2 = "account-policy.v2"
# Commissioned broker-fact freshness bound: facts older than this versus
# the decision clock refuse STALE_FACTS (server compares, never trusts a
# client "fresh" flag). Documented constant, not a silent default.
FACTS_MAX_AGE_S = 300.0
# Option OSI shape: root + YYMMDD + C/P + strike×1000 (same as lifecycle).
_ORDER_OSI_RE = re.compile(r"^[A-Z0-9.]{1,12}(\d{6})([CP])(\d{8})$")

ACCOUNT_POLICY_V2_DDL = """
    CREATE TABLE IF NOT EXISTS account_policy_v2 (
        account_id VARCHAR PRIMARY KEY, version VARCHAR, scope VARCHAR,
        policy_json VARCHAR, updated_at VARCHAR
    )
"""

_REQUIRED_FIELDS = ("intent_hash", "account_id", "scope", "valid_until",
                    "approved_by", "approved_at")
_TERMINAL = ("FILLED", "REJECTED", "CANCELED")

# Single-process atomicity for approval SELECT+INSERT/UPDATE sequences (S01).
# Threads racing revoke vs restore or same-ID conflicting writes serialize
# here; multi-process writers remain single-writer by deployment boundary
# (same as lifecycle: DuckDB multi-process writers are NOT claimed safe).
_APPROVAL_STORE_LOCK = threading.Lock()

__all__ = [
    "ADMISSION_VERSION",
    "ACCOUNT_POLICY_V2",
    "FACTS_MAX_AGE_S",
    "ACCOUNT_POLICY_V2_DDL",
    "ensure_admission_tables",
    "set_account_policy_required",
    "get_account_policy_required",
    "migrate_account_policy_v1",
    "store_approval_required",
    "revoke_approval_required",
    "census_required",
    "admit_production_entry",
    "order_fingerprint",
    "create_order_approval",
    "verify_order_approval",
    "consume_order_approval",
    "record_placement_attempt",
    "resolve_placement_attempt",
]


def ensure_admission_tables(conn: Any) -> None:
    """Create admission tables (additive; raises on failure — never silent)."""
    from services import public_execution_lifecycle as lc

    lc.ensure_lifecycle_tables(conn)
    conn.execute(ACCOUNT_POLICY_V2_DDL)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# Known account-policy fields with enforcement points (S07). Anything else
# is a probable typo for a ceiling that would otherwise silently enforce
# nothing, so installation refuses BAD_CONTRACT. Real operator values for
# these ceilings remain NAV-ACCOUNT external (UNSET until installed); this
# list admits the field, it never invents a value.
_KNOWN_POLICY_FIELDS = frozenset({
    "max_quantity", "max_notional", "max_positions", "max_daily_loss",
    "today", "min_entry_dte", "allow_unprotected_entry",
    "same_day_cutoff_et", "allowed_products",
})


def _validate_policy_shape(policy: Any) -> tuple[bool, str]:
    if not isinstance(policy, dict):
        return False, "policy must be a dict"
    for field in policy:
        if field not in _KNOWN_POLICY_FIELDS:
            return False, f"unknown policy field: {field}"
    if "max_quantity" in policy:
        try:
            if int(policy["max_quantity"]) <= 0:
                return False, "max_quantity must be positive"
        except (TypeError, ValueError):
            return False, "max_quantity must be an int"
    if "max_notional" in policy:
        try:
            if Decimal(str(policy["max_notional"])) <= 0:
                return False, "max_notional must be positive"
        except (InvalidOperation, ValueError, TypeError):
            return False, "max_notional must be decimal"
    if "max_positions" in policy:
        try:
            if int(policy["max_positions"]) <= 0:
                return False, "max_positions must be positive"
        except (TypeError, ValueError):
            return False, "max_positions must be an int"
    if "allowed_products" in policy and not isinstance(policy["allowed_products"], list):
        return False, "allowed_products must be a list"
    return True, "ok"


def set_account_policy_required(
    conn: Any, account_id: str, policy: dict[str, Any], operator: str,
    scope: str = "account-entry",
) -> dict[str, Any]:
    """Install an account-keyed policy with durable-first semantics.

    The durable write happens BEFORE any memory authority exists. On durable
    failure the memory row is purged and POLICY_STORE_UNAVAILABLE is
    returned — a failed write never leaves a memory-only authority behind.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not str(account_id or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    if not str(operator or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    shape_ok, shape_reason = _validate_policy_shape(policy)
    if not shape_ok:
        return {"ok": False, "reason": f"BAD_CONTRACT:{shape_reason}"}
    try:
        ensure_admission_tables(conn)
        conn.execute(
            "INSERT OR REPLACE INTO account_policy_v2 "
            "(account_id, version, scope, policy_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [str(account_id), ACCOUNT_POLICY_V2, str(scope),
             json.dumps(dict(policy), default=str), _now_iso()],
        )
    except Exception:
        _purge_memory_policy(str(account_id))
        return {"ok": False, "reason": "POLICY_STORE_UNAVAILABLE"}
    _mirror_memory_policy(str(account_id), dict(policy), str(scope))
    return {"ok": True, "version": ACCOUNT_POLICY_V2, "account_id": str(account_id)}


def _mirror_memory_policy(account_id: str, policy: dict[str, Any], scope: str) -> None:
    """Best-effort memory mirror AFTER durable success (never authority alone)."""
    from services import public_execution_lifecycle as lc

    with contextlib.suppress(Exception):
        lc.set_account_policy(
            {"accounts": {account_id: policy}, "scope": scope,
             "mirrored_at": _now_iso()}, "admission-mirror")


def _purge_memory_policy(account_id: str) -> None:
    """Clear memory policy after a failed required write (fail-closed).

    The legacy memory slot is a single global row, so any failed required
    write poisons it entirely: it is cleared regardless of which account was
    targeted, and no memory-only policy can remain as authority.
    """
    from services import public_execution_lifecycle as lc

    with contextlib.suppress(Exception):
        lc.clear_account_policy()


def get_account_policy_required(conn: Any, account_id: str) -> dict[str, Any]:
    """Read the authoritative account policy (durable read, fail-closed).

    Missing row → POLICY_UNSET. Query/DDL failure → POLICY_STORE_UNAVAILABLE
    (unknown is not unset). Corrupt JSON → POLICY_CORRUPT.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not str(account_id or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    try:
        ensure_admission_tables(conn)
        row = conn.execute(
            "SELECT version, scope, policy_json, updated_at FROM account_policy_v2 "
            "WHERE account_id = ?", [str(account_id)]).fetchone()
    except Exception:
        return {"ok": False, "reason": "POLICY_STORE_UNAVAILABLE"}
    if not row:
        return {"ok": False, "reason": "POLICY_UNSET"}
    try:
        policy = json.loads(row[2]) if isinstance(row[2], str) else {}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "POLICY_CORRUPT"}
    if not isinstance(policy, dict):
        return {"ok": False, "reason": "POLICY_CORRUPT"}
    return {"ok": True, "version": row[0], "scope": row[1],
            "policy": policy, "updated_at": row[3] if len(row) > 3 else None}


def migrate_account_policy_v1(
    conn: Any, account_id: str, operator: str,
) -> dict[str, Any]:
    """Explicit one-time migration of a legacy global v1 row into v2.

    Refuses when no v1 row exists (POLICY_UNSET) or a v2 row already exists
    (POLICY_EXISTS — never silently overwrites). The account binding comes
    from the operator argument, never guessed from stored data.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not str(account_id or "").strip() or not str(operator or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    try:
        ensure_admission_tables(conn)
        existing = conn.execute(
            "SELECT account_id FROM account_policy_v2 WHERE account_id = ?",
            [str(account_id)]).fetchone()
        if existing:
            return {"ok": False, "reason": "POLICY_EXISTS"}
        legacy = conn.execute(
            "SELECT policy_json FROM account_policy_v1 "
            "WHERE id = 'active'").fetchone()
        if not legacy or not legacy[0]:
            return {"ok": False, "reason": "POLICY_UNSET"}
    except Exception:
        return {"ok": False, "reason": "POLICY_STORE_UNAVAILABLE"}
    try:
        policy = json.loads(legacy[0]) if isinstance(legacy[0], str) else {}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "POLICY_CORRUPT"}
    if not isinstance(policy, dict):
        return {"ok": False, "reason": "POLICY_CORRUPT"}
    return set_account_policy_required(conn, str(account_id), policy,
                                       str(operator), scope="migrated-v1")


def store_approval_required(
    conn: Any, approval: dict[str, Any], operator: str,
) -> dict[str, Any]:
    """Persist an approval with durable-first semantics (S1).

    Shape-validated, then INSERTed durably BEFORE memory authority. Durable
    failure purges the memory row and returns APPROVAL_STORE_UNAVAILABLE.
    An existing revoked row is never resurrected; a conflicting identity
    (same approval_id, different intent/account/scope/approver/validity
    binding INCLUDING approved_at) refuses APPROVAL_CONFLICT instead of
    resetting durable/memory authority. Approvals are immutable: same-ID
    field mutation never overwrites, it conflicts. SELECT+INSERT runs under
    a single-process lock so threaded revoke/restore races cannot interleave.
    """
    from services import public_execution_lifecycle as lc

    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not isinstance(approval, dict):
        return {"ok": False, "reason": "APPROVAL_INVALID"}
    for field in _REQUIRED_FIELDS:
        if field not in approval:
            return {"ok": False, "reason": "APPROVAL_INVALID"}
    if not str(operator or "").strip():
        return {"ok": False, "reason": "APPROVAL_INVALID"}
    approval_id = str(approval.get("approval_id") or "") or hashlib.sha256(
        json.dumps(approval, sort_keys=True, default=str).encode()).hexdigest()[:16]
    try:
        with _APPROVAL_STORE_LOCK:
            ensure_admission_tables(conn)
            prior = conn.execute(
                "SELECT intent_hash, account_id, scope, revoked, approved_by, "
                "valid_until, approved_at FROM approvals_v1 "
                "WHERE approval_id = ?", [approval_id]).fetchone()
            if prior is not None:
                if bool(prior[3]):
                    return {"ok": False, "reason": "APPROVAL_INVALID",
                            "detail": "approval revoked; re-store cannot resurrect"}
                if (approval.get("intent_hash") != prior[0]
                        or approval.get("account_id") != prior[1]
                        or approval.get("scope") != prior[2]
                        or approval.get("approved_by") != prior[4]
                        or approval.get("valid_until") != prior[5]
                        or approval.get("approved_at") != prior[6]):
                    return {"ok": False, "reason": "APPROVAL_CONFLICT",
                            "detail": "approval_id is immutable; same-ID field "
                                      "mutation refuses instead of overwriting"}
            conn.execute(
                "INSERT OR REPLACE INTO approvals_v1 "
                "(approval_id, intent_hash, account_id, scope, valid_until, "
                "approved_by, approved_at, revoked, approval_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [approval_id, approval.get("intent_hash"), approval.get("account_id"),
                 approval.get("scope"), approval.get("valid_until"),
                 approval.get("approved_by"), approval.get("approved_at"), False,
                 json.dumps({**approval, "approval_id": approval_id}, default=str),
                 _now_iso()],
            )
    except Exception:
        lc._APPROVALS.pop(approval_id, None)
        return {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    row = dict(approval)
    row["approval_id"] = approval_id
    row["revoked"] = False
    row["stored_by"] = str(operator)
    lc._APPROVALS[approval_id] = row
    return {"ok": True, "approval_id": approval_id}


def revoke_approval_required(
    conn: Any, approval_id: str, operator: str,
) -> dict[str, Any]:
    """Revoke with durable-first semantics: failure refuses, memory rolls back.

    Runs under the same single-process approval lock as store so a threaded
    revoke cannot interleave a concurrent re-store SELECT+INSERT.
    """
    from services import public_execution_lifecycle as lc

    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not isinstance(approval_id, str) or not approval_id:
        return {"ok": False, "reason": "unknown-approval"}
    if not str(operator or "").strip():
        return {"ok": False, "reason": "unknown-approval"}
    try:
        with _APPROVAL_STORE_LOCK:
            ensure_admission_tables(conn)
            row = conn.execute(
                "SELECT approval_id FROM approvals_v1 WHERE approval_id = ?",
                [approval_id]).fetchone()
            if not row:
                return {"ok": False, "reason": "unknown-approval"}
            conn.execute("UPDATE approvals_v1 SET revoked = TRUE WHERE approval_id = ?",
                         [approval_id])
    except Exception:
        mem = lc._APPROVALS.get(approval_id)
        if isinstance(mem, dict):
            mem["revoked"] = False
        return {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    rec = lc._APPROVALS.get(approval_id)
    if isinstance(rec, dict):
        rec["revoked"] = True
        rec["revoked_by"] = str(operator)
    else:
        lc._APPROVALS[approval_id] = {"approval_id": approval_id, "revoked": True,
                                      "revoked_by": str(operator)}
    return {"ok": True, "approval_id": approval_id}


def census_required(conn: Any) -> dict[str, Any]:
    """Required recovery census: durable scan with explicit completeness.

    Query/DDL failure → RECOVERY_UNKNOWN (unknown is not zero). Rows whose
    record fails to decode are counted corrupt (never trusted, never dropped
    silently); any corrupt row → complete False. Callers refuse admission on
    unknown or incomplete census.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    try:
        ensure_admission_tables(conn)
        rows = conn.execute(
            "SELECT intent_id, record_json, state FROM execution_intents_v1 "
            "WHERE state NOT IN ('FILLED', 'REJECTED', 'CANCELED')").fetchall() or []
    except Exception:
        return {"ok": False, "reason": "RECOVERY_UNKNOWN"}
    nonterminal = 0
    corrupt = 0
    unknown_states = 0
    for _intent_id, blob, state in rows:
        nonterminal += 1
        if str(state or "") == "UNKNOWN":
            unknown_states += 1
        try:
            rec = json.loads(blob) if isinstance(blob, str) else {}
        except (TypeError, ValueError):
            corrupt += 1
            continue
        if not isinstance(rec, dict) or not rec.get("order_id"):
            corrupt += 1
    return {"ok": True, "nonterminal": nonterminal, "corrupt": corrupt,
            "unknown_states": unknown_states,
            "complete": corrupt == 0, "version": ADMISSION_VERSION}


def _require_single_store(conn: Any) -> dict[str, Any] | None:
    """Enforce one authoritative store across admission and lifecycle.

    The strict approval path reads the lifecycle global handle. If a
    different handle is already registered there, refuse STORE_MISMATCH
    instead of checking one store while owning rows in another. If none is
    registered, adopt the provided handle so both layers share it.
    """
    from services import public_execution_lifecycle as lc

    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if lc._STORE is not None and lc._STORE is not conn:
        return {"ok": False, "reason": "STORE_MISMATCH",
                "detail": "admission handle differs from registered lifecycle store"}
    if lc._STORE is None and not lc.register_store(conn):
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    return None


def admit_production_entry(
    conn: Any, intent: dict[str, Any], ctx: dict[str, Any], broker: Any,
    approval: dict[str, Any] | None = None,
    approval_scope: str = "single-entry",
) -> dict[str, Any]:
    """Required production admission DECISION (never dispatches, never cancels).

    Runs the full strict gate plus required census and account policy, with
    zero broker calls in every path — the returned decision carries the
    broker identity only as `would_place_with_order_id` when admitted.
    Refusals are machine-readable; broker is None-safe (never invoked).
    """
    from services import public_execution_lifecycle as lc

    mismatch = _require_single_store(conn)
    if mismatch is not None:
        return {"decision": "REFUSE", "reason": mismatch.get("reason"),
                "detail": mismatch.get("detail"), "version": ADMISSION_VERSION}
    if not isinstance(intent, dict) or not isinstance(ctx, dict):
        return {"decision": "REFUSE", "reason": "BAD_CONTRACT",
                "version": ADMISSION_VERSION}
    account_id = str(intent.get("account_id") or "")
    pol = get_account_policy_required(conn, account_id)
    if not pol.get("ok"):
        return {"decision": "REFUSE", "reason": pol.get("reason"),
                "version": ADMISSION_VERSION}
    ok, reason = lc.validate_intent(intent, ctx)
    if not ok:
        return {"decision": "REFUSE", "reason": reason,
                "version": ADMISSION_VERSION}
    now = ctx.get("now")
    if not isinstance(now, datetime):
        now = None
    if not lc.verify_approval(intent, approval, scope=approval_scope, now=now):
        return {"decision": "REFUSE", "reason": "APPROVAL_INVALID",
                "version": ADMISSION_VERSION}
    ok_s, reason_s = lc._verify_stored_approval(
        intent, approval, scope=approval_scope, now=now)
    if not ok_s:
        return {"decision": "REFUSE", "reason": reason_s,
                "version": ADMISSION_VERSION}
    gate_reason = lc.preflight_gate(intent, ctx)
    if gate_reason is not None:
        return {"decision": "REFUSE", "reason": gate_reason,
                "version": ADMISSION_VERSION}
    census = census_required(conn)
    if not census.get("ok"):
        return {"decision": "REFUSE", "reason": census.get("reason"),
                "version": ADMISSION_VERSION}
    if not census.get("complete"):
        return {"decision": "REFUSE", "reason": "RECOVERY_INCOMPLETE",
                "version": ADMISSION_VERSION}
    if int(census.get("unknown_states") or 0) > 0:
        return {"decision": "REFUSE", "reason": "UNKNOWN_ORDERS_PENDING",
                "version": ADMISSION_VERSION}
    if int(census.get("nonterminal") or 0) > 0:
        return {"decision": "REFUSE", "reason": "OVERLAP_OPEN_NEEDS_RECONCILE",
                "version": ADMISSION_VERSION}
    ceiling = _enforce_account_ceilings(intent, pol.get("policy") or {})
    if ceiling is not None:
        return {"decision": "REFUSE", "reason": ceiling,
                "version": ADMISSION_VERSION}
    try:
        digest = lc.intent_hash(intent)
    except (TypeError, ValueError) as exc:
        return {"decision": "REFUSE", "reason": f"BAD_CONTRACT:{exc}",
                "version": ADMISSION_VERSION}
    return {"decision": "ADMIT", "reason": None, "version": ADMISSION_VERSION,
            "intent_hash": digest, "account_id": account_id,
            "policy_version": pol.get("version")}


def _enforce_account_ceilings(intent: dict[str, Any], policy: dict[str, Any]) -> str | None:
    """Enforce required account-policy ceilings on one intent (S1 admit path).

    Returns a refusal code or None. Runs AFTER validate_intent, so contract
    shapes are already proven; any residual parse failure still refuses
    (fail-closed) rather than skipping the ceiling.
    """
    from services import public_execution_lifecycle as lc

    try:
        qty = int(intent.get("quantity"))
        contract = intent.get("contract") or {}
        limit = Decimal(str(intent.get("limit_price")))
        mult = Decimal(str(contract.get("multiplier")))
    except Exception:
        return "RISK_FACTS_INCOMPLETE"
    try:
        if policy.get("max_quantity") is not None and qty > int(policy["max_quantity"]):
            return "RISK_QUANTITY_EXCEEDED"
    except (TypeError, ValueError):
        return "RISK_FACTS_INCOMPLETE"
    try:
        if policy.get("max_notional") is not None:
            if limit * Decimal(qty) * mult > Decimal(str(policy["max_notional"])):
                return "RISK_NOTIONAL_EXCEEDED"
    except Exception:
        return "RISK_FACTS_INCOMPLETE"
    allowed = policy.get("allowed_products")
    if allowed is not None:
        # Product derived from the intent contract, never assumed: options
        # carry an explicit CALL/PUT type, anything else is non-option.
        contract = intent.get("contract") or {}
        product = ("OPTION" if str(contract.get("option_type") or "").upper()
                   in ("CALL", "PUT") else "EQUITY")
        if product not in list(allowed or []):
            return "UNSUPPORTED_PRODUCT"
    try:
        if policy.get("max_positions") is not None and lc._open_count() >= int(policy["max_positions"]):
            return "RISK_MAX_POSITIONS_EXCEEDED"
    except (TypeError, ValueError):
        return "RISK_FACTS_INCOMPLETE"
    return None


def _commissioned_expiry_protection(
    intent: dict[str, Any], ctx: dict[str, Any], policy: dict[str, Any],
) -> dict[str, Any] | None:
    """Expiry + protection gates for the executable sequence (S8).

    Returns a REFUSE decision or None (pass). The required account policy
    must carry an explicit expiry floor and an explicit unprotected-entry
    acknowledgment — absent values refuse instead of guessing safety.
    Unverified protection always refuses, even when acknowledged, unless a
    documented mechanism plus verified eligibility exists (none established).
    """
    from services import execution_protection as prot

    contract = intent.get("contract") or {}
    now = ctx.get("now")
    if not isinstance(now, datetime):
        now = datetime.now(UTC)
    if policy.get("min_entry_dte") is None:
        return {"decision": "REFUSE", "reason": "GUARD_UNCONFIGURED",
                "detail": "required policy lacks min_entry_dte",
                "version": ADMISSION_VERSION}
    expiry = prot.entry_expiry_guard(
        str(contract.get("expiry") or ""), now,
        {"min_entry_dte": policy.get("min_entry_dte"),
         "same_day_cutoff_et": policy.get("same_day_cutoff_et", "13:00")})
    if not expiry.get("ok"):
        return {"decision": "REFUSE", "reason": expiry.get("reason"),
                "detail": expiry.get("detail"), "version": ADMISSION_VERSION}
    legs = intent.get("legs") or contract.get("legs")
    order_kind = "SPREAD_LIMIT" if legs else "SINGLE_LEG_LIMIT"
    support = prot.protection_admission(
        "OPTION", order_kind, intent.get("quantity"),
        account_protection_eligible=bool(policy.get("protection_eligible")))
    if not support.get("covered"):
        if policy.get("allow_unprotected_entry") is True:
            return None
        return {"decision": "REFUSE", "reason": "PROTECTION_UNVERIFIED",
                "detail": support.get("detail"), "version": ADMISSION_VERSION}
    return None


def _stored_approval_row(conn: Any, approval_id: str) -> dict[str, Any] | None:
    """Durable stored approval row by ID (None on missing/unreadable).

    Authority reads go through here so presented copies can never confer
    authorship, scope, or validity the durable row does not carry.
    """
    try:
        ensure_admission_tables(conn)
        row = conn.execute(
            "SELECT approval_json, revoked, intent_hash, account_id, scope, "
            "approved_by, valid_until, approved_at FROM approvals_v1 "
            "WHERE approval_id = ?", [approval_id]).fetchone()
    except Exception:
        return None
    if not row:
        return None
    try:
        rec = json.loads(row[0]) if isinstance(row[0], str) else {}
    except (TypeError, ValueError):
        return None
    if not isinstance(rec, dict):
        return None
    if len(row) > 7:
        for field, column in (("intent_hash", row[2]),
                              ("account_id", row[3]), ("scope", row[4]),
                              ("approved_by", row[5]),
                              ("valid_until", row[6]),
                              ("approved_at", row[7])):
            if rec.get(field) != column:
                return None
    rec["revoked"] = bool(row[1]) if len(row) > 1 else bool(rec.get("revoked"))
    rec["approval_id"] = approval_id
    return rec


def _enforce_aggregate_notional(
    intent: dict[str, Any], snapshot: dict[str, Any], policy: dict[str, Any],
) -> dict[str, Any] | None:
    """Existing + proposed notional vs max_notional (S7 aggregate).

    Per-intent ceilings ignore what the account already holds: an
    exposure-900 account admitting a 315 proposal under a 1000 ceiling
    must refuse. Returns a REFUSE decision or None (pass). Unparseable
    intent economics refuse instead of skipping the ceiling.
    """
    from decimal import Decimal

    if not isinstance(policy, dict) or policy.get("max_notional") is None:
        return None
    try:
        qty = Decimal(str(intent.get("quantity")))
        limit = Decimal(str(intent.get("limit_price")))
        mult = Decimal(str((intent.get("contract") or {}).get("multiplier")))
        existing = Decimal(str((snapshot or {}).get("exposure", "0")))
        ceiling = Decimal(str(policy["max_notional"]))
    except Exception:
        return {"decision": "REFUSE", "reason": "RISK_FACTS_INCOMPLETE",
                "detail": "proposed notional unparseable; ceiling skipped "
                          "never",
                "version": ADMISSION_VERSION}
    proposed = limit * qty * mult
    if existing + proposed > ceiling:
        return {"decision": "REFUSE", "reason": "RISK_NOTIONAL_EXCEEDED",
                "detail": f"existing {existing} + proposed {proposed} "
                          f"exceeds max_notional {ceiling}",
                "version": ADMISSION_VERSION}
    return None


def admit_commissioned_entry(
    conn: Any, intent: dict[str, Any], ctx: dict[str, Any], broker: Any,
    approval: dict[str, Any] | None = None,
    approval_scope: str = "single-entry",
    operator_id: str | None = None,
    risk_facts: dict[str, Any] | None = None,
    remote_native: dict[str, Any] | None = None,
    evidence_grade: str = "injected-fixture",
) -> dict[str, Any]:
    """Commissioned admission: S1 authority + operator + risk + remote census.

    Layers on top of `admit_production_entry` (same fail-closed semantics):
    - operator_id must be registered AND allowed for the intent account
      (OPERATOR_UNKNOWN / OPERATOR_UNAUTHORIZED). A bare string proves
      nothing without the registry row.
    - risk_facts (injected verified broker facts) are evaluated against the
      required account policy; missing/incomplete facts and any breach
      refuse. The ledger never runs without facts.
    - remote_native is the verified remote native-workflow census
      ({workflows: [{strategy, status, ...}]}). Absent/unverifiable census
      refuses NATIVE_CENSUS_UNAVAILABLE; any OPEN remote workflow refuses
      OVERLAP_NATIVE. An empty local list proves nothing here.
    - evidence_grade: "injected-fixture" (deterministic tests/fixtures) or
      "server-verified" (server-stamped evidence). Anything else —
      including client-asserted request bodies — refuses EVIDENCE_UNVERIFIED.
      No client flag relaxes this.
    Zero broker calls in every path.
    """
    from services import account_risk_ledger as ledger
    from services import operator_registry as operators

    if conn is None:
        return {"decision": "REFUSE", "reason": "STORE_UNAVAILABLE",
                "version": ADMISSION_VERSION}
    if evidence_grade not in ("injected-fixture", "server-verified"):
        return {"decision": "REFUSE", "reason": "EVIDENCE_UNVERIFIED",
                "detail": "executable admission needs server-verified evidence",
                "version": ADMISSION_VERSION}
    if not isinstance(intent, dict):
        return {"decision": "REFUSE", "reason": "BAD_CONTRACT",
                "version": ADMISSION_VERSION}
    account_id = str(intent.get("account_id") or "")
    auth = operators.authorize_operator(conn, operator_id or "", account_id)
    if not auth.get("ok"):
        return {"decision": "REFUSE", "reason": auth.get("reason"),
                "version": ADMISSION_VERSION}
    base = admit_production_entry(conn, intent, ctx, broker, approval,
                                  approval_scope)
    if base.get("decision") != "ADMIT":
        return base
    if not isinstance(approval, dict) or not isinstance(
            approval.get("approval_id"), str) or not approval["approval_id"]:
        return {"decision": "REFUSE", "reason": "APPROVAL_INVALID",
                "detail": "no presented approval identity",
                "version": ADMISSION_VERSION}
    # The binding reads the DURABLE stored row, never the presented copy:
    # a rewritten approved_by on a copied dict cannot spoof authorship.
    stored = _stored_approval_row(conn, approval["approval_id"])
    if stored is None:
        return {"decision": "REFUSE", "reason": "APPROVAL_STORE_UNAVAILABLE",
                "detail": "stored approval unreadable; failing closed",
                "version": ADMISSION_VERSION}
    if stored.get("approved_by") != auth.get("operator_id"):
        return {"decision": "REFUSE", "reason": "APPROVAL_INVALID",
                "detail": "stored approval author must equal the authorized "
                          "operator",
                "version": ADMISSION_VERSION}
    if not isinstance(risk_facts, dict):
        return {"decision": "REFUSE", "reason": "RISK_FACTS_INCOMPLETE",
                "detail": "no injected broker facts", "version": ADMISSION_VERSION}
    provenance = _check_facts_provenance(risk_facts, account_id, ctx)
    if provenance is not None:
        return provenance
    pol = get_account_policy_required(conn, account_id)
    today = None
    now_dt = ctx.get("now")
    if isinstance(now_dt, datetime):
        today = now_dt.astimezone(UTC).strftime("%Y-%m-%d")
    risk = ledger.evaluate_account_risk(
        risk_facts, pol.get("policy") if pol.get("ok") else {},
        today=today, require_complete_policy=True)
    if not risk.get("ok"):
        return {"decision": "REFUSE", "reason": risk.get("reason"),
                "detail": risk.get("detail"), "version": ADMISSION_VERSION}
    afford = ledger.check_affordability(intent, risk_facts)
    if not afford.get("ok"):
        return {"decision": "REFUSE", "reason": afford.get("reason"),
                "detail": afford.get("detail"), "version": ADMISSION_VERSION}
    required = pol.get("policy") if pol.get("ok") else {}
    aggregate = _enforce_aggregate_notional(
        intent, risk.get("snapshot") or {}, required)
    if aggregate is not None:
        return aggregate
    guard = _commissioned_expiry_protection(intent, ctx, required)
    if guard is not None:
        return guard
    if not isinstance(remote_native, dict) or not isinstance(
            remote_native.get("workflows"), list):
        return {"decision": "REFUSE", "reason": "NATIVE_CENSUS_UNAVAILABLE",
                "version": ADMISSION_VERSION}
    for wf in remote_native["workflows"]:
        # Malformed rows refuse: an unverifiable census is not an empty one.
        if not isinstance(wf, dict) or not str(wf.get("status") or "").strip():
            return {"decision": "REFUSE", "reason": "NATIVE_CENSUS_UNAVAILABLE",
                    "detail": "remote native census has malformed rows",
                    "version": ADMISSION_VERSION}
        if str(wf.get("status") or "").upper() == "OPEN":
            return {"decision": "REFUSE", "reason": "OVERLAP_NATIVE",
                    "detail": f"remote workflow {wf.get('strategy')} OPEN",
                    "version": ADMISSION_VERSION}
    base["operator_id"] = auth.get("operator_id")
    base["risk_snapshot"] = risk.get("snapshot")
    return base


def _check_facts_provenance(
    risk_facts: dict[str, Any], account_id: str, ctx: dict[str, Any],
) -> dict[str, Any] | None:
    """Source/account/clock binding for injected broker facts (S9).

    Returns a REFUSE decision or None (pass). Facts must name their
    account (must equal the intent account — foreign facts refuse),
    their source (missing source refuses), and an asof clock the server
    compares against the decision clock (missing/unparseable refuses;
    older than FACTS_MAX_AGE_S refuses STALE_FACTS). No client freshness
    assertion is trusted.
    """
    facts_account = risk_facts.get("account_id")
    if not isinstance(facts_account, str) or not facts_account.strip():
        return {"decision": "REFUSE", "reason": "RISK_FACTS_INCOMPLETE",
                "detail": "facts missing account_id", "version": ADMISSION_VERSION}
    if facts_account.strip() != str(account_id or ""):
        return {"decision": "REFUSE", "reason": "RISK_FACTS_INCOMPLETE",
                "detail": f"foreign facts for {facts_account.strip()}",
                "version": ADMISSION_VERSION}
    if not str(risk_facts.get("source") or "").strip():
        return {"decision": "REFUSE", "reason": "RISK_FACTS_INCOMPLETE",
                "detail": "facts missing source", "version": ADMISSION_VERSION}
    asof_raw = risk_facts.get("asof")
    try:
        asof = (asof_raw if isinstance(asof_raw, datetime)
                else datetime.fromisoformat(str(asof_raw).strip().replace("Z", "+00:00")))
        if asof.tzinfo is None:
            asof = asof.replace(tzinfo=UTC)
    except (TypeError, ValueError, AttributeError):
        return {"decision": "REFUSE", "reason": "RISK_FACTS_INCOMPLETE",
                "detail": "facts missing/unparseable asof", "version": ADMISSION_VERSION}
    now_dt = ctx.get("now")
    if not isinstance(now_dt, datetime):
        return {"decision": "REFUSE", "reason": "RISK_FACTS_INCOMPLETE",
                "detail": "no decision clock for freshness",
                "version": ADMISSION_VERSION}
    moment = now_dt if now_dt.tzinfo is not None else now_dt.replace(tzinfo=UTC)
    if abs((moment - asof).total_seconds()) > FACTS_MAX_AGE_S:
        return {"decision": "REFUSE", "reason": "STALE_FACTS",
                "detail": f"facts asof {asof.isoformat()} vs decision clock",
                "version": ADMISSION_VERSION}
    return None


def _osi_expiry_iso(symbol: str) -> str | None:
    """Option expiry from an OSI symbol, or None for non-option symbols.

    Returns YYYY-MM-DD for a well-formed option OSI with a real calendar
    date; None for equity tickers and malformed option symbols (expiry
    then stays unknown, never guessed). Same shape as the lifecycle
    cross-check; years are 20YY like listed options.
    """
    match = _ORDER_OSI_RE.match(str(symbol or "").upper().strip())
    if match is None:
        return None
    yymmdd = match.group(1)
    try:
        return datetime.strptime(f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}",
                                 "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _is_malformed_osi(symbol: str) -> bool:
    """An OSI-shaped symbol whose embedded date is not a real calendar day.

    Malformed option symbols refuse BAD_CONTRACT at approval creation
    instead of riding the equity skip-path into a broker rejection.
    """
    text = str(symbol or "").upper().strip()
    return _ORDER_OSI_RE.match(text) is not None and _osi_expiry_iso(text) is None


def _option_order_guards(
    conn: Any, account_id: str, symbol: str,
) -> dict[str, Any] | None:
    """Expiry + protection gates for option order approvals (S8).

    Runs at approval CREATION and again at VERIFICATION (placement), so a
    policy installed, narrowed, or expired between the two still refuses.
    Non-OSI symbols (equities) skip the expiry gate — no expiry concept —
    and stay under kill-switch + fingerprint approval (disclosed
    limitation: equity protection has no verified mechanism in this lane;
    tightening that path is a Nav production-behavior decision).
    Unverified option protection refuses unless the required account
    policy explicitly acknowledges unprotected entry.
    Returns a refusal dict or None (pass).
    """
    from services import execution_protection as prot

    if _is_malformed_osi(symbol):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "option symbol has no valid expiry date"}
    expiry = _osi_expiry_iso(symbol)
    if expiry is None:
        return None
    pol = get_account_policy_required(conn, str(account_id or "").strip())
    if not pol.get("ok"):
        return {"ok": False, "reason": pol.get("reason", "POLICY_STORE_UNAVAILABLE"),
                "detail": "no required account policy for option order"}
    policy = pol.get("policy") or {}
    if policy.get("min_entry_dte") is None:
        return {"ok": False, "reason": "GUARD_UNCONFIGURED",
                "detail": "required policy lacks min_entry_dte"}
    guard = prot.entry_expiry_guard(
        expiry, datetime.now(UTC),
        {"min_entry_dte": policy.get("min_entry_dte"),
         "same_day_cutoff_et": policy.get("same_day_cutoff_et", "13:00")})
    if not guard.get("ok"):
        return {"ok": False, "reason": guard.get("reason"),
                "detail": guard.get("detail")}
    if policy.get("allow_unprotected_entry") is True:
        return None
    return {"ok": False, "reason": "PROTECTION_UNVERIFIED",
            "detail": "no verified protection mechanism; policy does not "
                      "acknowledge unprotected entry"}


def _canon_number(value: Any) -> str:
    """Decimal-exact canonical number (S8 rounding fix).

    Float %.6f formatting collides distinct prices (3.15 vs 3.1500001),
    so a cheaper approval could cover a dearer order. Decimal
    normalization keeps type-juggled equals equal (1 == 1.0 == "1.00")
    while keeping distinct values distinct. Non-finite/unparseable
    renders "none" (creation refuses those before hashing).
    """
    from decimal import Decimal

    if value is None:
        return "none"
    try:
        text = value.strip() if isinstance(value, str) else value
        d = Decimal(str(text))
    except Exception:
        return "none"
    if not d.is_finite():
        return "none"
    if d == 0:
        return "0"
    return format(d.normalize(), "f")


def _derive_instrument(symbol: str, instrument_type: Any) -> str:
    """Canonical instrument with symbol coherence (S8).

    Explicit values must be known and coherent (OSI-valid option symbols
    are OPTION, anything else is never OPTION). Omitted values derive
    deterministically from the symbol — the executable route always
    passes an explicit value, so derivation only comforts direct
    service callers, never executable ambiguity.
    """
    text = str(instrument_type or "").upper().strip()
    if not text:
        return "OPTION" if _osi_expiry_iso(symbol) is not None else "EQUITY"
    return text


def _order_coherence(symbol: str, order_type: str, instrument: str,
                     limit_price: Any, stop_price: Any, side: str,
                     ) -> dict[str, Any] | None:
    """Type/side/instrument/price coherence for order approvals (S8).

    Runs at creation AND verification, so raw-ingested rows that the
    factory would refuse cannot pass verify: unknown types, non-BUY/SELL
    sides, MARKET or mis-declared options, LIMIT-family without limit,
    STOP-family without stop, and incoherent instrument declarations all
    refuse BAD_CONTRACT. Returns a refusal dict or None (pass).
    """
    if str(side or "").upper().strip() not in ("BUY", "SELL"):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": f"side must be BUY or SELL, got {side!r}"}
    if order_type not in ("MARKET", "LIMIT", "STOP", "STOP_LIMIT"):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": f"unknown order_type {order_type!r}"}
    if instrument not in ("EQUITY", "OPTION", "CRYPTO", "BOND"):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": f"unknown instrument_type {instrument!r}"}
    is_option = _osi_expiry_iso(symbol) is not None
    if is_option and instrument != "OPTION":
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "option symbols require instrument_type OPTION"}
    if not is_option and not _is_malformed_osi(symbol) and instrument == "OPTION":
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "non-option symbols cannot declare OPTION"}
    if _is_malformed_osi(symbol):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "option symbol has no valid expiry date"}
    if is_option and order_type not in ("LIMIT", "STOP_LIMIT"):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "option approvals require LIMIT or STOP_LIMIT"}
    if order_type in ("LIMIT", "STOP_LIMIT") and limit_price is None:
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": f"{order_type} approvals require an explicit "
                          "limit price"}
    if order_type in ("STOP", "STOP_LIMIT") and stop_price is None:
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": f"{order_type} approvals require an explicit "
                          "stop price"}
    return None


def order_fingerprint(account_id: str, symbol: str, side: str,
                      quantity: Any, limit_price: Any,
                      stop_price: Any = None,
                      time_in_force: str = "DAY",
                      order_type: str = "LIMIT",
                      instrument_type: Any = None,
                      equity_market_session: Any = None) -> str:
    """Canonical identity for a single-leg order approval (S8).

    Binds account + symbol + side + exact quantity/limit/stop + time in
    force + order type + instrument + equity session, with Decimal-exact
    prices (no rounding collisions). A tampered stop (or TIF), a LIMIT
    approval replayed as MARKET, a re-declared instrument/session, or a
    rounded price never matches a stored approval. Server recomputes
    this from the order body — a caller-supplied hash is never trusted.
    Pre-binding approvals (narrower hash) fail closed on mismatch.
    """
    blob = "|".join([
        str(account_id or "").strip(),
        str(symbol or "").upper().strip(),
        str(side or "").upper().strip(),
        _canon_number(quantity),
        _canon_number(limit_price),
        _canon_number(stop_price),
        str(time_in_force or "DAY").upper().strip(),
        str(order_type or "LIMIT").upper().strip(),
        _derive_instrument(symbol, instrument_type),
        str(equity_market_session or "none").upper().strip(),
    ])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _enforce_order_ceilings(
    conn: Any, account_id: str, quantity: Any, limit_price: Any,
    symbol: str | None = None, instrument: str | None = None,
) -> dict[str, Any] | None:
    """Policy quantity/per-unit-notional/product ceilings for order approvals.

    Runs at creation AND verification, so a narrowing policy (or a
    raw-ingested row minted under looser limits) cannot ride into
    placement. Skips only when no required policy is installed (the
    progressive boundary — the armed route separately refuses UNSET);
    store/query failure refuses instead of skipping. Full
    multiplier-aware notional lives on the intent paths that carry
    vendor multipliers; here limit x quantity is the per-unit bound.
    Product allowlist binds when symbol+instrument are known.
    Returns a refusal dict or None (pass).
    """
    pol = get_account_policy_required(conn, str(account_id or "").strip())
    if pol.get("reason") == "POLICY_UNSET":
        return None
    if not pol.get("ok"):
        return {"ok": False,
                "reason": pol.get("reason", "POLICY_STORE_UNAVAILABLE"),
                "detail": "policy unreadable; failing closed"}
    policy = pol.get("policy") or {}
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "quantity must be a positive number"}
    if not math.isfinite(qty) or qty <= 0:
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "quantity must be a finite positive number"}
    try:
        if (policy.get("max_quantity") is not None
                and qty > float(policy["max_quantity"])):
            return {"ok": False, "reason": "RISK_QUANTITY_EXCEEDED",
                    "detail": f"quantity {qty} exceeds max_quantity "
                             f"{policy['max_quantity']}"}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "RISK_FACTS_INCOMPLETE",
                "detail": "max_quantity unparseable; failing closed"}
    if policy.get("max_notional") is not None and limit_price is not None:
        try:
            bound = float(limit_price) * qty
            if bound > float(policy["max_notional"]):
                return {"ok": False, "reason": "RISK_NOTIONAL_EXCEEDED",
                        "detail": f"order bound {bound} exceeds max_notional "
                                  f"{policy['max_notional']} (per-unit basis)"}
        except (TypeError, ValueError):
            return {"ok": False, "reason": "RISK_FACTS_INCOMPLETE",
                    "detail": "max_notional unparseable; failing closed"}
    allowed = policy.get("allowed_products")
    if allowed is not None and symbol is not None and instrument is not None:
        try:
            products = list(allowed)
        except TypeError:
            return {"ok": False, "reason": "RISK_FACTS_INCOMPLETE",
                    "detail": "allowed_products unparseable; failing closed"}
        if str(instrument) not in products:
            return {"ok": False, "reason": "UNSUPPORTED_PRODUCT",
                    "detail": f"{instrument} not in allowed_products"}
    return None


def create_order_approval(
    conn: Any, account_id: str, symbol: str, side: str, quantity: Any,
    limit_price: Any, operator: str, validity_hours: float = 1.0,
    stop_price: Any = None, time_in_force: str = "DAY",
    order_type: str = "LIMIT", instrument_type: Any = None,
    equity_market_session: Any = None,
) -> dict[str, Any]:
    """Create + store an order-bound approval (server timestamps only).

    Validity window is server-computed (1–24h); client clocks are never
    trusted. Quantity must be finite and positive; limit/stop prices must
    be finite when present. Order type, instrument and session are bound
    into the Decimal-exact fingerprint and constrained by
    `_order_coherence` (unknown types, MARKET/mis-declared options and
    missing required prices refuse). The authoring operator must be
    registered AND allowed for the account (OPERATOR_UNKNOWN /
    OPERATOR_UNAUTHORIZED) — a bare string behind the shared master key
    mints nothing. Required-policy quantity/notional
    ceilings bind at creation; option OSI symbols additionally pass the
    expiry guard and protection acknowledgment (S8). Returns the stored
    row including approval_id.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    try:
        hours = float(validity_hours)
        if not (0 < hours <= 24):
            return {"ok": False, "reason": "BAD_CONTRACT"}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "BAD_CONTRACT"}
    otype = str(order_type or "LIMIT").upper().strip() or "LIMIT"
    symbol_c = str(symbol or "").upper().strip()
    side_c = str(side or "").upper().strip()
    instrument = _derive_instrument(symbol_c, instrument_type)
    session_c = str(equity_market_session
                    or "none").upper().strip() or "none"
    if isinstance(quantity, bool):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "quantity must be a positive number, not a boolean"}
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "quantity must be a positive number"}
    if not math.isfinite(qty) or qty <= 0:
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "quantity must be a finite positive number"}
    for label, price in (("limit_price", limit_price),
                         ("stop_price", stop_price)):
        if price is None:
            continue
        try:
            finite = float(price)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "BAD_CONTRACT",
                    "detail": f"{label} must be a number"}
        if not math.isfinite(finite):
            return {"ok": False, "reason": "BAD_CONTRACT",
                    "detail": f"{label} must be finite"}
    coherent = _order_coherence(symbol_c, otype, instrument, limit_price,
                                stop_price, side_c)
    if coherent is not None:
        return coherent
    now = datetime.now(UTC)
    valid_until = now + timedelta(hours=hours)
    tif = str(time_in_force or "DAY").upper().strip() or "DAY"
    approval = {
        "intent_hash": order_fingerprint(account_id, symbol_c, side_c,
                                         quantity, limit_price, stop_price,
                                         tif, otype, instrument, session_c),
        "account_id": str(account_id or "").strip(),
        "scope": "order-entry",
        "symbol": symbol_c,
        "side": side_c,
        "quantity": _canon_number(quantity),
        "limit_price": _canon_number(limit_price),
        "stop_price": _canon_number(stop_price),
        "time_in_force": tif,
        "order_type": otype,
        "instrument_type": instrument,
        "equity_market_session": session_c,
        "valid_until": valid_until.isoformat(),
        "approved_by": str(operator or "").strip(),
        "approved_at": now.isoformat(),
    }
    if not approval["account_id"] or not approval["symbol"] or not approval["approved_by"]:
        return {"ok": False, "reason": "BAD_CONTRACT"}
    from services import operator_registry as operators

    auth = operators.authorize_operator(
        conn, approval["approved_by"], approval["account_id"])
    if not auth.get("ok"):
        return {"ok": False, "reason": auth.get("reason", "OPERATOR_UNKNOWN"),
                "detail": "authoring operator is not authorized for this account"}
    ceilings = _enforce_order_ceilings(conn, approval["account_id"],
                                       quantity, limit_price,
                                       symbol_c, instrument)
    if ceilings is not None:
        return ceilings
    gate = _option_order_guards(conn, approval["account_id"], approval["symbol"])
    if gate is not None:
        return gate
    stored = store_approval_required(conn, approval, str(operator or "").strip())
    if not stored.get("ok"):
        return stored
    return {"ok": True, **stored}


def verify_order_approval(
    conn: Any, approval_id: str, account_id: str, symbol: str, side: str,
    quantity: Any, limit_price: Any, now: datetime | None = None,
    stop_price: Any = None, time_in_force: str = "DAY",
    order_type: str = "LIMIT", instrument_type: Any = None,
    equity_market_session: Any = None, operator: str | None = None,
) -> dict[str, Any]:
    """Verify an order approval against the recomputed fingerprint.

    Refuses APPROVAL_NOT_STORED (missing/storeless), APPROVAL_INVALID
    (revoked, expired, operator mismatch, or fingerprint mismatch —
    including order-type/instrument/session mismatch, so a LIMIT
    approval never covers a MARKET placement), OPERATOR_UNKNOWN /
    OPERATOR_UNAUTHORIZED (presenter not registered/allowed for the
    account — a shared-key-only string verifies nothing),
    BAD_CONTRACT (presented fields incoherent — the factory's
    type/instrument/price coherence re-runs here, so raw-ingested rows
    it would refuse cannot pass verify), APPROVAL_STORE_UNAVAILABLE
    (query failure), and policy ceiling breaches against CURRENT policy
    (a narrowing between creation and placement refuses). Option OSI
    symbols re-pass the required-policy expiry guard and protection
    acknowledgment against CURRENT policy and server time. `operator`
    is mandatory: the stored approved_by must equal it AND it must be
    authorized for the account — the presenter must be the authorized
    author, with no anonymous verification. Never raises.
    """
    from services import public_execution_lifecycle as lc

    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not isinstance(approval_id, str) or not approval_id:
        return {"ok": False, "reason": "APPROVAL_NOT_STORED"}
    try:
        ensure_admission_tables(conn)
        row = conn.execute(
            "SELECT approval_json, revoked, intent_hash, account_id, scope, "
            "approved_by, valid_until, approved_at FROM approvals_v1 "
            "WHERE approval_id = ?", [approval_id]).fetchone()
    except Exception:
        return {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    if not row:
        return {"ok": False, "reason": "APPROVAL_NOT_STORED"}
    try:
        rec = json.loads(row[0]) if isinstance(row[0], str) else {}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "APPROVAL_NOT_STORED"}
    if not isinstance(rec, dict):
        return {"ok": False, "reason": "APPROVAL_NOT_STORED"}
    if bool(row[1]) if len(row) > 1 else bool(rec.get("revoked")):
        return {"ok": False, "reason": "APPROVAL_INVALID", "detail": "revoked"}
    if len(row) > 7:
        # S08: stored columns must agree with the stored payload — a
        # same-ID raw-row alteration under either side refuses instead
        # of verifying against a half-tampered authority.
        bound = (("intent_hash", row[2]), ("account_id", row[3]),
                 ("scope", row[4]), ("approved_by", row[5]),
                 ("valid_until", row[6]), ("approved_at", row[7]))
        for field, column in bound:
            if rec.get(field) != column:
                return {"ok": False, "reason": "APPROVAL_INVALID",
                        "detail": "stored row diverges from stored payload"}
    if rec.get("scope") != "order-entry" or rec.get("account_id") != str(account_id or "").strip():
        return {"ok": False, "reason": "APPROVAL_INVALID", "detail": "binding mismatch"}
    symbol_c = str(symbol or "").upper().strip()
    side_c = str(side or "").upper().strip()
    otype = str(order_type or "LIMIT").upper().strip() or "LIMIT"
    instrument = _derive_instrument(symbol_c, instrument_type)
    session_c = str(equity_market_session or "none").upper().strip() or "none"
    coherent = _order_coherence(symbol_c, otype, instrument, limit_price,
                                stop_price, side_c)
    if coherent is not None:
        return coherent
    if rec.get("approved_by") != str(operator or "").strip():
        return {"ok": False, "reason": "APPROVAL_INVALID",
                "detail": "presenter is not the stored approver"}
    from services import operator_registry as operators

    auth = operators.authorize_operator(
        conn, str(operator or "").strip(), str(account_id or "").strip())
    if not auth.get("ok"):
        return {"ok": False, "reason": auth.get("reason", "OPERATOR_UNKNOWN"),
                "detail": "presenter is not authorized for this account"}
    want = order_fingerprint(account_id, symbol_c, side_c, quantity,
                             limit_price, stop_price, time_in_force,
                             otype, instrument, session_c)
    if rec.get("intent_hash") != want:
        return {"ok": False, "reason": "APPROVAL_INVALID", "detail": "order fields differ"}
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    valid_until = lc._parse_ts(rec.get("valid_until"))
    approved_at = lc._parse_ts(rec.get("approved_at"))
    if valid_until is None or approved_at is None:
        return {"ok": False, "reason": "APPROVAL_INVALID", "detail": "bad timestamps"}
    if moment > valid_until or approved_at > moment:
        return {"ok": False, "reason": "APPROVAL_INVALID", "detail": "expired"}
    ceilings = _enforce_order_ceilings(conn, str(account_id or ""),
                                       quantity, limit_price,
                                       symbol_c, instrument)
    if ceilings is not None:
        return ceilings
    gate = _option_order_guards(conn, str(account_id or ""),
                                rec.get("symbol") or symbol)
    if gate is not None:
        return gate
    try:
        attempt = conn.execute(
            "SELECT attempted_at, approval_id FROM placement_attempts_v1 "
            "WHERE fingerprint = ? AND resolved_at IS NULL",
            [want]).fetchone()
    except Exception:
        return {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    if attempt is not None:
        return {"ok": False, "reason": "PLACEMENT_OUTCOME_UNKNOWN",
                "detail": {"attempted_at": str(attempt[0]),
                           "approval_id": str(attempt[1]),
                           "guidance": "a prior placement with this exact "
                           "fingerprint failed with unknown outcome; "
                           "reconcile broker state, then resolve via POST "
                           "/api/admission/placement-attempts/resolve"}}
    return {"ok": True, "approval_id": approval_id}


def consume_order_approval(
    conn: Any, approval_id: Any, fingerprint: Any = None,
    operator: Any = None,
) -> dict[str, Any]:
    """Consume an order-entry approval exactly once (S17 single-use).

    The mounted entry calls this AFTER verify_order_approval succeeds and
    BEFORE any broker placement: the r19 verified probe showed a same-ID
    replay within the <=24h validity window otherwise places a second
    order. Consumption is a guarded UPDATE under the S01 store lock —
    exactly one caller wins, every later presenter refuses
    APPROVAL_ALREADY_USED, and a revoked/missing row never consumes.
    Store failures refuse fail-closed (APPROVAL_STORE_UNAVAILABLE) so a
    broken store can never degrade single-use into verify-only. Legacy
    rows with NULL used_at are unconsumed by definition. Consumption is
    never reset or refunded: a failed/refused placement burns the
    approval (fail-closed doctrine — re-approve with a fresh row). Never
    raises.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not isinstance(approval_id, str) or not approval_id:
        return {"ok": False, "reason": "APPROVAL_NOT_STORED"}
    moment = _now_iso()
    try:
        with _APPROVAL_STORE_LOCK:
            ensure_admission_tables(conn)
            row = conn.execute(
                "SELECT revoked, used_at FROM approvals_v1 "
                "WHERE approval_id = ?", [approval_id]).fetchone()
            if row is None:
                return {"ok": False, "reason": "APPROVAL_NOT_STORED"}
            if bool(row[0]):
                return {"ok": False, "reason": "APPROVAL_INVALID",
                        "detail": "revoked"}
            if row[1]:
                return {"ok": False, "reason": "APPROVAL_ALREADY_USED",
                        "detail": {"used_at": str(row[1])}}
            conn.execute(
                "UPDATE approvals_v1 SET used_at = ?, used_by = ?, "
                "used_fingerprint = ?, updated_at = ? "
                "WHERE approval_id = ? AND used_at IS NULL",
                [moment, str(operator or ""), str(fingerprint or ""),
                 moment, approval_id])
    except Exception:
        return {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    return {"ok": True, "approval_id": approval_id, "used_at": moment}


def record_placement_attempt(
    conn: Any, fingerprint: Any, approval_id: Any, account_id: Any,
    error: Any,
) -> dict[str, Any]:
    """Journal a broker placement that FAILED after approval consumption (S17b).

    The burned approval alone cannot stop a retry: the operator creates a
    FRESH approval for the same intent and the route would place again —
    but the first call may have placed despite raising (ambiguous ACK),
    which would make two economic orders. The journal makes the unknown
    outcome explicit: `verify_order_approval` refuses the same fingerprint
    with PLACEMENT_OUTCOME_UNKNOWN until an operator reconciles broker
    state and resolves the attempt. Existing unresolved rows are never
    clobbered (fail-closed audit); a resolved row starts a new cycle.
    Never raises.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    fp = str(fingerprint or "").strip()
    if not fp:
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "fingerprint required"}
    moment = _now_iso()
    try:
        from services import public_execution_lifecycle as lc

        with _APPROVAL_STORE_LOCK:
            lc.ensure_lifecycle_tables(conn)
            row = conn.execute(
                "SELECT resolved_at FROM placement_attempts_v1 "
                "WHERE fingerprint = ?", [fp]).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO placement_attempts_v1 (fingerprint, "
                    "account_id, approval_id, attempted_at, error) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [fp, str(account_id or ""), str(approval_id or ""),
                     moment, str(error or "")[:500]])
            elif row[0]:
                conn.execute(
                    "UPDATE placement_attempts_v1 SET approval_id = ?, "
                    "attempted_at = ?, error = ?, resolved_at = NULL, "
                    "resolved_by = NULL, resolution_note = NULL "
                    "WHERE fingerprint = ?",
                    [str(approval_id or ""), moment,
                     str(error or "")[:500], fp])
            # else: an unresolved attempt is already journaled — keep the
            # original row (first failure wins the audit trail).
    except Exception:
        return {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    return {"ok": True, "fingerprint": fp, "attempted_at": moment}


def resolve_placement_attempt(
    conn: Any, fingerprint: Any, operator: Any, resolution: Any,
) -> dict[str, Any]:
    """Record operator-attested reconciliation of an unknown-outcome attempt.

    The operator states what broker-state verification showed (e.g. "no
    order present for the window" or "existing order oid-... adopted —
    reconcile it, do not resubmit"). Attestation because this service has
    no broker read-back: the claim is the operator's verified statement,
    persisted with identity and time, never an automatic clear (an
    automatic clear would reopen the ambiguous-ACK hole). The presenter
    must be registered AND allowed for the attempt's account. Never raises.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    fp = str(fingerprint or "").strip()
    if not fp:
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "fingerprint required"}
    note = str(resolution or "").strip()
    if not note:
        return {"ok": False, "reason": "BAD_CONTRACT",
                "detail": "resolution_note required: state what broker-state "
                          "verification showed"}
    try:
        from services import operator_registry as operators
        from services import public_execution_lifecycle as lc

        with _APPROVAL_STORE_LOCK:
            lc.ensure_lifecycle_tables(conn)
            row = conn.execute(
                "SELECT account_id, resolved_at FROM placement_attempts_v1 "
                "WHERE fingerprint = ?", [fp]).fetchone()
            if row is None:
                return {"ok": False, "reason": "NO_SUCH_ATTEMPT"}
            if row[1]:
                return {"ok": False, "reason": "ALREADY_RESOLVED"}
            auth = operators.authorize_operator(
                conn, str(operator or "").strip(), str(row[0] or "").strip())
            if not auth.get("ok"):
                return {"ok": False,
                        "reason": auth.get("reason", "OPERATOR_UNKNOWN"),
                        "detail": "resolver is not authorized for this account"}
            moment = _now_iso()
            conn.execute(
                "UPDATE placement_attempts_v1 SET resolved_at = ?, "
                "resolved_by = ?, resolution_note = ? "
                "WHERE fingerprint = ? AND resolved_at IS NULL",
                [moment, str(operator or "").strip(), note[:500], fp])
    except Exception:
        return {"ok": False, "reason": "APPROVAL_STORE_UNAVAILABLE"}
    return {"ok": True, "fingerprint": fp, "resolved_at": moment}
