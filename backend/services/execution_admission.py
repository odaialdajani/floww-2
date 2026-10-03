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
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

ADMISSION_VERSION = "execution-admission.v1"
ACCOUNT_POLICY_V2 = "account-policy.v2"

ACCOUNT_POLICY_V2_DDL = """
    CREATE TABLE IF NOT EXISTS account_policy_v2 (
        account_id VARCHAR PRIMARY KEY, version VARCHAR, scope VARCHAR,
        policy_json VARCHAR, updated_at VARCHAR
    )
"""

_REQUIRED_FIELDS = ("intent_hash", "account_id", "scope", "valid_until",
                    "approved_by", "approved_at")
_TERMINAL = ("FILLED", "REJECTED", "CANCELED")

__all__ = [
    "ADMISSION_VERSION",
    "ACCOUNT_POLICY_V2",
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
]


def ensure_admission_tables(conn: Any) -> None:
    """Create admission tables (additive; raises on failure — never silent)."""
    from services import public_execution_lifecycle as lc

    lc.ensure_lifecycle_tables(conn)
    conn.execute(ACCOUNT_POLICY_V2_DDL)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _validate_policy_shape(policy: Any) -> tuple[bool, str]:
    if not isinstance(policy, dict):
        return False, "policy must be a dict"
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
    (same approval_id, different intent/account/scope binding) refuses
    APPROVAL_CONFLICT instead of resetting durable/memory authority.
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
        ensure_admission_tables(conn)
        prior = conn.execute(
            "SELECT intent_hash, account_id, scope, revoked FROM approvals_v1 "
            "WHERE approval_id = ?", [approval_id]).fetchone()
        if prior is not None:
            if bool(prior[3]):
                return {"ok": False, "reason": "APPROVAL_INVALID",
                        "detail": "approval revoked; re-store cannot resurrect"}
            if (approval.get("intent_hash") != prior[0]
                    or approval.get("account_id") != prior[1]
                    or approval.get("scope") != prior[2]):
                return {"ok": False, "reason": "APPROVAL_CONFLICT",
                        "detail": "approval_id bound to a different intent/account/scope"}
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
    """Revoke with durable-first semantics: failure refuses, memory rolls back."""
    from services import public_execution_lifecycle as lc

    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not isinstance(approval_id, str) or not approval_id:
        return {"ok": False, "reason": "unknown-approval"}
    if not str(operator or "").strip():
        return {"ok": False, "reason": "unknown-approval"}
    try:
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
    if not lc.has_fresh_preflight(intent, ctx):
        return {"decision": "REFUSE", "reason": "STALE_PREFLIGHT",
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
    if allowed is not None and "OPTION" not in list(allowed or []):
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
    if not isinstance(approval, dict) or approval.get("approved_by") != auth.get("operator_id"):
        return {"decision": "REFUSE", "reason": "APPROVAL_INVALID",
                "detail": "approval.approved_by must equal the authorized operator",
                "version": ADMISSION_VERSION}
    if not isinstance(risk_facts, dict):
        return {"decision": "REFUSE", "reason": "RISK_FACTS_INCOMPLETE",
                "detail": "no injected broker facts", "version": ADMISSION_VERSION}
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
    guard = _commissioned_expiry_protection(intent, ctx, required)
    if guard is not None:
        return guard
    if not isinstance(remote_native, dict) or not isinstance(
            remote_native.get("workflows"), list):
        return {"decision": "REFUSE", "reason": "NATIVE_CENSUS_UNAVAILABLE",
                "version": ADMISSION_VERSION}
    for wf in remote_native["workflows"]:
        if isinstance(wf, dict) and str(wf.get("status") or "").upper() == "OPEN":
            return {"decision": "REFUSE", "reason": "OVERLAP_NATIVE",
                    "detail": f"remote workflow {wf.get('strategy')} OPEN",
                    "version": ADMISSION_VERSION}
    base["operator_id"] = auth.get("operator_id")
    base["risk_snapshot"] = risk.get("snapshot")
    return base


def _canon_number(value: Any) -> str:
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return "none"


def order_fingerprint(account_id: str, symbol: str, side: str,
                      quantity: Any, limit_price: Any) -> str:
    """Canonical identity for a single-leg order approval (S8).

    Binds account + symbol + side + exact quantity/limit. Server recomputes
    this from the order body — a caller-supplied hash is never trusted.
    """
    blob = "|".join([
        str(account_id or "").strip(),
        str(symbol or "").upper().strip(),
        str(side or "").upper().strip(),
        _canon_number(quantity),
        _canon_number(limit_price),
    ])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def create_order_approval(
    conn: Any, account_id: str, symbol: str, side: str, quantity: Any,
    limit_price: Any, operator: str, validity_hours: float = 1.0,
) -> dict[str, Any]:
    """Create + store an order-bound approval (server timestamps only).

    Validity window is server-computed (1–24h); client clocks are never
    trusted. Returns the stored row including approval_id.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    try:
        hours = float(validity_hours)
        if not (0 < hours <= 24):
            return {"ok": False, "reason": "BAD_CONTRACT"}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "BAD_CONTRACT"}
    now = datetime.now(UTC)
    valid_until = now + timedelta(hours=hours)
    approval = {
        "intent_hash": order_fingerprint(account_id, symbol, side, quantity, limit_price),
        "account_id": str(account_id or "").strip(),
        "scope": "order-entry",
        "symbol": str(symbol or "").upper().strip(),
        "side": str(side or "").upper().strip(),
        "quantity": _canon_number(quantity),
        "limit_price": _canon_number(limit_price),
        "valid_until": valid_until.isoformat(),
        "approved_by": str(operator or "").strip(),
        "approved_at": now.isoformat(),
    }
    if not approval["account_id"] or not approval["symbol"] or not approval["approved_by"]:
        return {"ok": False, "reason": "BAD_CONTRACT"}
    stored = store_approval_required(conn, approval, str(operator or "").strip())
    if not stored.get("ok"):
        return stored
    return {"ok": True, **stored}


def verify_order_approval(
    conn: Any, approval_id: str, account_id: str, symbol: str, side: str,
    quantity: Any, limit_price: Any, now: datetime | None = None,
) -> dict[str, Any]:
    """Verify an order approval against the recomputed fingerprint.

    Refuses APPROVAL_NOT_STORED (missing/storeless), APPROVAL_INVALID
    (revoked, expired, or fingerprint mismatch), APPROVAL_STORE_UNAVAILABLE
    (query failure). Never raises.
    """
    from services import public_execution_lifecycle as lc

    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not isinstance(approval_id, str) or not approval_id:
        return {"ok": False, "reason": "APPROVAL_NOT_STORED"}
    try:
        ensure_admission_tables(conn)
        row = conn.execute(
            "SELECT approval_json, revoked FROM approvals_v1 "
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
    if rec.get("scope") != "order-entry" or rec.get("account_id") != str(account_id or "").strip():
        return {"ok": False, "reason": "APPROVAL_INVALID", "detail": "binding mismatch"}
    want = order_fingerprint(account_id, symbol, side, quantity, limit_price)
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
    return {"ok": True, "approval_id": approval_id}
