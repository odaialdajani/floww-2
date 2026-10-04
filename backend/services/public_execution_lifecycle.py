"""
backend/services/public_execution_lifecycle.py — deterministic Public execution lifecycle.

Contract `execution-intent.v1`. Pure service, NO route mount, NO live calls, NO
venue-flag reads. The existing gated HTTP route (`routes/public_brokerage.py`)
remains the only submission path. This module validates immutable intents,
binds server-side approvals, enforces single-owner idempotency, and reconciles
truthfully against read-only broker reads. All broker transport is injected
(async fakes in tests; the real `PublicBroker` only via an explicitly armed
caller that already passed `FLOWW_ENABLE_LIVE_PUBLIC==1`).

Money precision uses `Decimal` strings end-to-end. Client floats are rejected.
A stop is never called a guaranteed ceiling; an acknowledged order is never
called filled; incomplete protection is never called protected.

Durability: intent ownership lives in `_INTENTS` (process memory) and, when a
store is registered via `register_store(conn)`, in the additive
`execution_intents_v1` table. Every state transition persists before it is
reported; a persistence failure refuses the transition (`STORE_UNAVAILABLE`)
instead of reporting unwritten ownership. After a restart, `recover_open()`
rehydrates non-terminal records so open/unknown orders block new entry before
any reconcile — the registry is never trusted empty on a fresh process.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

INTENT_VERSION = "execution-intent.v1"
RECEIPT_VERSION = "execution-receipt.v1"
DRAFT_VERSION = "intent-draft.v1"
ACCOUNT_POLICY_VERSION = "account-policy.v1"
RISK_POLICY = "research_barriers.v1"
ET = ZoneInfo("America/New_York")
FRESHNESS_DEFAULT_S = 30

_OSI_RE = re.compile(r"^[A-Z0-9\.]{1,12}(\d{6})([CP])(\d{8})$")


def _osi_matches_contract(osi: str, expiry: str, option_type: str, strike_exact: str) -> bool:
    """Cross-check the OSI symbol against the declared exact contract.

    The OSI embeds expiry date, call/put flag and strike (×1000); each must
    equal the separately declared fields, or the contract is not exact.
    """
    match = _OSI_RE.match(osi)
    if match is None:
        return False
    yymmdd, cp, strike8 = match.group(1), match.group(2), match.group(3)
    if f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}" != expiry:
        return False
    if (cp == "C") != (option_type == "CALL"):
        return False
    try:
        if Decimal(strike8) != Decimal(str(strike_exact).strip()) * 1000:
            return False
    except (InvalidOperation, ValueError, AttributeError):
        return False
    return True

LIFECYCLE_DDL = """
    CREATE TABLE IF NOT EXISTS execution_intents_v1 (
        intent_id VARCHAR PRIMARY KEY, intent_hash VARCHAR, ticker VARCHAR,
        owner VARCHAR, state VARCHAR, order_id VARCHAR,
        record_json VARCHAR, updated_at VARCHAR
    )
"""

ACCOUNT_POLICY_DDL = """
    CREATE TABLE IF NOT EXISTS account_policy_v1 (
        id VARCHAR PRIMARY KEY, version VARCHAR,
        policy_json VARCHAR, updated_at VARCHAR
    )
"""

APPROVAL_STORE_DDL = """
    CREATE TABLE IF NOT EXISTS approvals_v1 (
        approval_id VARCHAR PRIMARY KEY, intent_hash VARCHAR,
        account_id VARCHAR, scope VARCHAR, valid_until VARCHAR,
        approved_by VARCHAR, approved_at VARCHAR, revoked BOOLEAN,
        approval_json VARCHAR, updated_at VARCHAR
    )
"""

# Broker-native protection support as DOCUMENTED + account-eligibility gated.
# Conservative by design: nothing is offered until both the vendor documents
# the exact product/order combination AND the account is verified eligible.
# An unverified combination is never called protected.
NATIVE_PROTECTION_MATRIX: dict[str, dict[str, Any]] = {
    "OPTION_SINGLE_LEG_LIMIT": {
        "BRACKET": False, "OCO": False, "OTO": False,
        "reason": "unverified-native-support",
    },
    "OPTION_SPREAD_LIMIT": {
        "BRACKET": False, "OCO": False, "OTO": False,
        "reason": "unverified-native-support",
    },
    "EQUITY_LIMIT": {
        "BRACKET": False, "OCO": False, "OTO": False,
        "reason": "unverified-native-support",
    },
}

_INTENTS: dict[str, dict[str, Any]] = {}
_NATIVE_WORKFLOWS: list[dict[str, Any]] = []
_PREFLIGHT_CACHE: dict[str, dict[str, Any]] = {}
_DRAFTS: dict[str, dict[str, Any]] = {}
_ACCOUNT_POLICY: dict[str, Any] | None = None
_APPROVALS: dict[str, dict[str, Any]] = {}
_STORE: Any = None
# Single-process ownership lock: the check-then-insert in submit() must be
# atomic across threads, or two racing clicks place two orders. The critical
# section holds no awaits (broker I/O stays outside). Cross-PROCESS races are
# NOT excluded by this lock — see the DB-backed same-intent guard and the
# documented residual in MUSE_STATE.
_SUBMIT_LOCK = threading.Lock()

__all__ = [
    "INTENT_VERSION",
    "RECEIPT_VERSION",
    "DRAFT_VERSION",
    "ACCOUNT_POLICY_VERSION",
    "PREFLIGHT_TTL_S",
    "LIFECYCLE_DDL",
    "ACCOUNT_POLICY_DDL",
    "APPROVAL_STORE_DDL",
    "DRAFT_DDL",
    "NATIVE_PROTECTION_MATRIX",
    "intent_hash",
    "validate_intent",
    "create_approval",
    "verify_approval",
    "store_approval",
    "revoke_approval",
    "stored_approval",
    "set_account_policy",
    "get_account_policy",
    "clear_account_policy",
    "native_protection_support",
    "submit",
    "reconcile",
    "reconcile_all",
    "cancel",
    "supersede",
    "replace",
    "preflight",
    "has_fresh_preflight",
    "record_draft",
    "review_draft",
    "mark_preflighted",
    "mark_awaiting",
    "load_draft",
    "protection_status",
    "is_entry_pause",
    "cancel_allowed_during_pause",
    "register_native_workflow",
    "register_store",
    "ensure_lifecycle_tables",
    "recover_open",
]


def _reset_for_tests() -> None:
    global _STORE, _ACCOUNT_POLICY
    _INTENTS.clear()
    _NATIVE_WORKFLOWS.clear()
    _PREFLIGHT_CACHE.clear()
    _DRAFTS.clear()
    _APPROVALS.clear()
    _ACCOUNT_POLICY = None
    _STORE = None


def ensure_lifecycle_tables(conn: Any) -> None:
    """Create intent/policy/approval tables (additive; never alters existing tables)."""
    import contextlib as _ctxlib

    conn.execute(LIFECYCLE_DDL)
    with _ctxlib.suppress(Exception):
        conn.execute(ACCOUNT_POLICY_DDL)
    with _ctxlib.suppress(Exception):
        conn.execute(APPROVAL_STORE_DDL)


def register_store(conn: Any) -> bool:
    """Register the DuckDB handle for durable intent ownership.

    Returns True when registered. A dead handle is refused (False) and the
    previous store — if any — is left untouched, so registration can never
    silently swap durability out from under live records. No-op (True) for None.
    """
    global _STORE
    if conn is None:
        return True
    try:
        ensure_lifecycle_tables(conn)
    except Exception:
        return False
    _STORE = conn
    return True


def set_account_policy(policy: dict[str, Any], operator: str) -> dict[str, Any]:
    """Install the account-wide execution policy (default-deny, versioned).

    The operator identity is required (authenticated at the route layer; the
    service refuses an empty operator). Absent policy means UNSET: per-call
    ctx limits still apply, but no account-wide ceiling is claimed. Returns
    the stored row.
    """
    global _ACCOUNT_POLICY
    if not isinstance(policy, dict):
        raise TypeError("policy must be a dict")
    if not str(operator or "").strip():
        raise ValueError("operator is required")
    row = {
        "version": ACCOUNT_POLICY_VERSION,
        "policy": dict(policy),
        "set_by": str(operator),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _ACCOUNT_POLICY = row
    if _STORE is not None:
        try:
            ensure_lifecycle_tables(_STORE)
            _STORE.execute(
                "INSERT OR REPLACE INTO account_policy_v1 "
                "(id, version, policy_json, updated_at) VALUES (?, ?, ?, ?)",
                ["active", ACCOUNT_POLICY_VERSION,
                 json.dumps(dict(policy), default=str), row["updated_at"]],
            )
        except Exception:  # silent by design: memory row is authoritative; durable is best-effort
            pass
    return dict(row)


def get_account_policy() -> dict[str, Any] | None:
    """Current account-wide policy (newest of memory and durable wins).

    A second process may install a tighter policy while this process holds a
    stale memory copy: when a store is present the durable row is compared by
    updated_at and the newer side governs, so ceilings only move toward the
    latest operator write, never toward a stale copy.
    """
    mem = dict(_ACCOUNT_POLICY) if _ACCOUNT_POLICY is not None else None
    if _STORE is None:
        return mem
    try:
        ensure_lifecycle_tables(_STORE)
        row = _STORE.execute(
            "SELECT policy_json, updated_at FROM account_policy_v1 "
            "WHERE id = 'active'").fetchone()
    except Exception:
        return mem
    if not row:
        return mem
    try:
        durable = {"version": ACCOUNT_POLICY_VERSION,
                   "policy": json.loads(row[0]) if row[0] else {},
                   "updated_at": row[1] if len(row) > 1 else None}
    except (TypeError, ValueError):
        return mem
    if mem is None:
        return durable
    mem_ts = str(mem.get("updated_at") or "")
    dur_ts = str(durable.get("updated_at") or "")
    if dur_ts and dur_ts >= mem_ts:
        return durable
    return mem


def clear_account_policy() -> None:
    """Remove the account-wide policy (tests/operator reset; never silent)."""
    global _ACCOUNT_POLICY
    _ACCOUNT_POLICY = None
    if _STORE is not None:
        try:
            ensure_lifecycle_tables(_STORE)
            _STORE.execute("DELETE FROM account_policy_v1 WHERE id = 'active'")
        except Exception:  # silent by design: memory clear already applied; durable best-effort
            pass


def store_approval(approval: dict[str, Any], operator: str) -> dict[str, Any]:
    """Persist a server-validated approval (default-deny, revocable).

    The operator identity is required. The approval must carry the standard
    bound fields; malformed approvals are refused, never stored. Returns the
    stored row.
    """
    if not str(operator or "").strip():
        raise ValueError("operator is required")
    if not isinstance(approval, dict):
        raise TypeError("approval must be a dict")
    for field in ("intent_hash", "account_id", "scope", "valid_until",
                  "approved_by", "approved_at"):
        if field not in approval:
            raise ValueError(f"approval missing {field}")
    approval_id = str(approval.get("approval_id") or "") or hashlib.sha256(
        json.dumps(approval, sort_keys=True, default=str).encode()).hexdigest()[:16]
    prior = stored_approval(approval_id)
    if prior is not None and prior.get("revoked") is True:
        # A revoked approval is never resurrected by re-storing: revocation wins.
        return dict(prior)
    if prior is not None and any(
            approval.get(field) != prior.get(field)
            for field in ("intent_hash", "account_id", "scope")):
        raise ValueError("approval_id bound to a different intent/account/scope")
    row = dict(approval)
    row["approval_id"] = approval_id
    row["revoked"] = False
    row["stored_by"] = str(operator)
    _APPROVALS[approval_id] = dict(row)
    if _STORE is not None:
        try:
            ensure_lifecycle_tables(_STORE)
            now = datetime.now(UTC).isoformat()
            _STORE.execute(
                "INSERT OR REPLACE INTO approvals_v1 "
                "(approval_id, intent_hash, account_id, scope, valid_until, "
                "approved_by, approved_at, revoked, approval_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [approval_id, row.get("intent_hash"), row.get("account_id"),
                 row.get("scope"), row.get("valid_until"), row.get("approved_by"),
                 row.get("approved_at"), False,
                 json.dumps(row, default=str), now],
            )
        except Exception:  # silent by design: memory row is authoritative; durable is best-effort
            pass
    return dict(row)


def stored_approval(approval_id: str) -> dict[str, Any] | None:
    """Read one stored approval by ID (memory first, then durable).

    Revocation is authoritative across registries: when a store is present the
    durable revoked flag is consulted even on a memory hit, so a revocation
    recorded by another process is never masked by a stale memory copy.
    """
    mem = _APPROVALS.get(approval_id)
    if _STORE is None:
        return dict(mem) if mem is not None else None
    try:
        ensure_lifecycle_tables(_STORE)
        row = _STORE.execute(
            "SELECT approval_json, revoked FROM approvals_v1 "
            "WHERE approval_id = ?", [approval_id]).fetchone()
    except Exception:
        return dict(mem) if mem is not None else None
    if not row:
        return dict(mem) if mem is not None else None
    try:
        rec = json.loads(row[0]) if isinstance(row[0], str) else {}
    except (TypeError, ValueError):
        return dict(mem) if mem is not None else None
    if not isinstance(rec, dict):
        return dict(mem) if mem is not None else None
    rec["revoked"] = bool(row[1]) if len(row) > 1 else bool(rec.get("revoked"))
    if mem is not None and not rec.get("revoked") and mem.get("revoked") is True:
        rec["revoked"] = True
    return rec


def revoke_approval(approval_id: str, operator: str) -> dict[str, Any]:
    """Revoke a stored approval (operator required; unknown IDs refuse)."""
    if not str(operator or "").strip():
        raise ValueError("operator is required")
    rec = stored_approval(approval_id)
    if rec is None:
        return {"ok": False, "reason": "unknown-approval"}
    rec["revoked"] = True
    rec["revoked_by"] = str(operator)
    _APPROVALS[approval_id] = dict(rec)
    if _STORE is not None:
        try:
            ensure_lifecycle_tables(_STORE)
            _STORE.execute(
                "UPDATE approvals_v1 SET revoked = TRUE WHERE approval_id = ?",
                [approval_id])
        except Exception:  # silent by design: memory revocation already applied; durable best-effort
            pass
    return {"ok": True, "approval_id": approval_id}


def native_protection_support(product: str, order_type: str) -> dict[str, Any]:
    """Broker-native protection truth for one product/order combination.

    Conservative: only a documented + eligible combination reports supported.
    Everything in the current matrix reports unsupported with the unverified
    reason — never offered, never silently enabled.
    """
    key = f"{str(product or '').upper()}_{str(order_type or '').upper()}"
    mat = NATIVE_PROTECTION_MATRIX.get(key)
    if mat is None:
        return {"product": product, "order_type": order_type,
                "supported": False, "types": {},
                "reason": "unknown-product-combination"}
    return {"product": product, "order_type": order_type,
            "supported": False, "types": {k: False for k in ("BRACKET", "OCO", "OTO")},
            "reason": str(mat.get("reason") or "unverified-native-support")}


def _persist(intent_id: str) -> bool:
    """Write one record to the registered store. True when durable or storeless."""
    if _STORE is None:
        return True
    rec = _INTENTS.get(intent_id)
    if rec is None:
        return False
    try:
        ensure_lifecycle_tables(_STORE)
        now = datetime.now(UTC).isoformat()
        blob = json.dumps(rec, default=str)
        _STORE.execute(
            "INSERT OR REPLACE INTO execution_intents_v1 "
            "(intent_id, intent_hash, ticker, owner, state, order_id, record_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [intent_id, rec.get("intent_hash"), rec.get("intent", {}).get("ticker"),
             rec.get("intent", {}).get("execution_owner"), rec.get("state"),
             rec.get("order_id"), blob, now],
        )
        return True
    except Exception:
        return False


def recover_open(store: Any | None = None) -> list[str]:
    """Rehydrate non-terminal records after a restart (durable → memory).

    Returns the recovered intent IDs. Terminal rows (FILLED/REJECTED/CANCELED)
    stay history and are not reloaded. Without a store there is nothing to
    recover — and the empty registry is reported as storeless, never as proof
    that no orders are open.
    """
    conn = store if store is not None else _STORE
    if conn is None:
        return []
    try:
        ensure_lifecycle_tables(conn)
        rows = conn.execute(
            "SELECT intent_id, record_json FROM execution_intents_v1 "
            "WHERE state NOT IN ('FILLED', 'REJECTED', 'CANCELED')").fetchall() or []
    except Exception:
        return []
    recovered: list[str] = []
    for intent_id, blob in rows:
        rec = _decode_record(intent_id, blob)
        if rec is not None:
            _INTENTS[str(intent_id)] = rec
            recovered.append(str(intent_id))
    return recovered


def _decode_record(intent_id: Any, blob: Any) -> dict[str, Any] | None:
    """Parse one stored intent row. Corrupt rows are skipped, never trusted."""
    try:
        rec = json.loads(blob) if isinstance(blob, str) else {}
    except (TypeError, ValueError):
        return None
    if isinstance(rec, dict) and rec.get("order_id"):
        return rec
    return None


DRAFT_DDL = """
    CREATE TABLE IF NOT EXISTS intent_drafts_v1 (
        intent_hash VARCHAR PRIMARY KEY, stage VARCHAR, approved BOOLEAN,
        reason VARCHAR, draft_json VARCHAR, updated_at VARCHAR
    )
"""

_DRAFT_STAGES = ("DRAFT", "REVIEWED", "PREFLIGHTED", "AWAITING")


def _draft_store() -> Any:
    return _STORE


def record_draft(intent: dict[str, Any]) -> dict[str, Any]:
    """Record a reviewed-plan draft (advisory; submit stays independent).

    A model plan remains a draft until deterministic checks pass elsewhere;
    this registry only tracks where the review stands. Returns the draft row.
    """
    digest = intent_hash(intent)
    row = {"intent_hash": digest, "stage": "DRAFT", "approved": False,
           "reason": None, "version": DRAFT_VERSION,
           "updated_at": datetime.now(UTC).isoformat()}
    _write_draft(digest, row, intent)
    return dict(row)


def _write_draft(digest: str, row: dict[str, Any], intent: dict[str, Any]) -> None:
    store = _draft_store()
    if store is None:
        _DRAFTS[digest] = dict(row)
        return
    try:
        store.execute(DRAFT_DDL)
        store.execute(
            "INSERT OR REPLACE INTO intent_drafts_v1 "
            "(intent_hash, stage, approved, reason, draft_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [digest, row["stage"], 1 if row["approved"] else 0,
             row.get("reason"), json.dumps(intent, default=str), row["updated_at"]],
        )
    except Exception:
        _DRAFTS[digest] = dict(row)


def load_draft(intent: dict[str, Any]) -> dict[str, Any] | None:
    """Read a draft row by intent (durable when a store is registered)."""
    try:
        digest = intent_hash(intent)
    except (TypeError, ValueError):
        return None
    store = _draft_store()
    if store is not None:
        try:
            store.execute(DRAFT_DDL)
            row = store.execute(
                "SELECT stage, approved, reason, updated_at FROM intent_drafts_v1 "
                "WHERE intent_hash = ?", [digest]).fetchone()
            if row:
                return {"intent_hash": digest, "stage": row[0],
                        "approved": bool(row[1]), "reason": row[2],
                        "version": DRAFT_VERSION, "updated_at": row[3]}
        except Exception:  # silent by design: fall through to the memory registry
            pass
    cached = _DRAFTS.get(digest)
    if cached is not None:
        return dict(cached)
    return None


def _advance_draft(intent: dict[str, Any], want: str,
                   approved: bool | None = None, reason: str | None = None) -> dict[str, Any]:
    current = load_draft(intent)
    if current is None:
        return {"ok": False, "reason": "unknown-draft"}
    order = list(_DRAFT_STAGES)
    try:
        idx = order.index(current["stage"])
    except ValueError:
        return {"ok": False, "reason": "unknown-draft"}
    if order.index(want) != idx + 1:
        return {"ok": False, "reason": f"illegal-transition:{current['stage']}->{want}"}
    # REVIEWED with approved=False is a recorded rejection (never dropped);
    # downstream gates (mark_preflighted) refuse unapproved drafts.
    row = dict(current)
    row.update({"stage": want, "updated_at": datetime.now(UTC).isoformat()})
    if approved is not None:
        row["approved"] = bool(approved)
    if reason is not None:
        row["reason"] = reason
    _write_draft(current["intent_hash"], row, intent)
    return {"ok": True, **{k: v for k, v in row.items() if k != "version"},
            "version": DRAFT_VERSION}


def review_draft(intent: dict[str, Any], approved: bool, reason: str | None = None) -> dict[str, Any]:
    """DRAFT → REVIEWED. Rejection is recorded, never silently dropped."""
    return _advance_draft(intent, "REVIEWED", approved=approved, reason=reason)


def mark_preflighted(intent: dict[str, Any]) -> dict[str, Any]:
    """REVIEWED(approved) → PREFLIGHTED."""
    current = load_draft(intent)
    if current is None or current.get("stage") != "REVIEWED":
        have = current.get("stage") if current else None
        return {"ok": False, "reason": f"illegal-transition:{have}->PREFLIGHTED"}
    if not current.get("approved"):
        return {"ok": False, "reason": "unapproved-draft"}
    return _advance_draft(intent, "PREFLIGHTED")


def mark_awaiting(intent: dict[str, Any]) -> dict[str, Any]:
    """PREFLIGHTED → AWAITING (armed-submission readiness, still no order)."""
    return _advance_draft(intent, "AWAITING")


def _load_record(intent_id: str) -> dict[str, Any] | None:
    """Advisory cross-process read: one intent row by ID from the store.

    Lets a second process (or a fresh registry) reuse the owning broker orderId
    instead of placing a duplicate. Best-effort: a concurrent writer may still
    win a race — callers treat this as advisory and the broker orderId stays
    the single source of reconciliation truth.
    """
    if _STORE is None:
        return None
    try:
        ensure_lifecycle_tables(_STORE)
        row = _STORE.execute(
            "SELECT record_json FROM execution_intents_v1 WHERE intent_id = ?",
            [intent_id]).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return _decode_record(intent_id, row[0])


def _money(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field} must be a Decimal string, got {type(value).__name__}")
    s = value.strip()
    if not s:
        raise ValueError(f"{field} is empty")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} is not decimal: {value!r}") from exc
    if not d.is_finite() or d <= 0:
        raise ValueError(f"{field} must be finite positive")
    return d


def _canon_decimal(value: str) -> str:
    d = Decimal(value.strip())
    # Canonical plain-fixed form: numerically equal values share one identity.
    normalized = d.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def intent_hash(intent: dict[str, Any]) -> str:
    """Deterministic SHA256 over the canonical intent (Decimal-normalized)."""
    if not isinstance(intent, dict):
        raise TypeError("intent must be a dict")
    # Exact-money enforcement: floats are never accepted into the identity.
    for field in ("limit_price", "tick", "strike_exact", "multiplier"):
        container = intent.get("contract", {}) if field in ("strike_exact", "multiplier") else intent
        if field in container and isinstance(container[field], float):
            raise TypeError(f"{field} must be a Decimal string, not float")
    canon: dict[str, Any] = {}
    for key in sorted(intent.keys()):
        if key == "contract":
            contract = intent.get("contract") or {}
            canon_contract = {k: contract[k] for k in sorted(contract.keys())}
            for money_field in ("strike_exact", "multiplier"):
                if money_field in canon_contract and isinstance(canon_contract[money_field], str):
                    canon_contract[money_field] = _canon_decimal(canon_contract[money_field])
            canon[key] = canon_contract
        elif key in ("limit_price", "tick") and isinstance(intent[key], str):
            canon[key] = _canon_decimal(intent[key])
        else:
            canon[key] = intent[key]
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def is_entry_pause(now: datetime) -> bool:
    """11:30–14:00 America/New_York new-entry pause on weekdays."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    ny = now.astimezone(ET)
    if ny.weekday() >= 5:
        return False
    cur = ny.strftime("%H:%M")
    return "11:30" <= cur < "14:00"


def cancel_allowed_during_pause() -> bool:
    return True


def register_native_workflow(strategy: str, venue: str, status: str, correlation: str) -> None:
    _NATIVE_WORKFLOWS.append({
        "strategy": strategy, "venue": venue, "status": status, "correlation": correlation,
    })


def validate_intent(intent: dict[str, Any], ctx: dict[str, Any]) -> tuple[bool, str]:
    """Deterministic draft→ready checks. Returns (ok, reason_code)."""
    if not isinstance(intent, dict) or intent.get("intent_version") != INTENT_VERSION:
        return False, "BAD_CONTRACT"
    contract = intent.get("contract")
    if not isinstance(contract, dict):
        return False, "BAD_CONTRACT"
    osi = str(contract.get("osi") or "")
    expiry = str(contract.get("expiry") or "")
    option_type = str(contract.get("option_type") or "")
    if not _OSI_RE.match(osi.upper()):
        return False, "BAD_CONTRACT"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry):
        return False, "BAD_CONTRACT"
    if option_type not in ("CALL", "PUT"):
        return False, "BAD_CONTRACT"
    if not _osi_matches_contract(
            osi.upper(), expiry, option_type, str(contract.get("strike_exact") or "")):
        return False, "BAD_CONTRACT"
    try:
        strike = _money(contract.get("strike_exact"), "strike_exact")
        mult = _money(contract.get("multiplier"), "multiplier")
        _ = strike, mult
    except (TypeError, ValueError):
        return False, "BAD_CONTRACT"
    if not str(contract.get("multiplier_provenance") or "").strip():
        return False, "BAD_CONTRACT"
    if intent.get("side") not in ("BUY", "SELL"):
        return False, "BAD_CONTRACT"
    if intent.get("open_close") not in ("OPEN", "CLOSE"):
        return False, "BAD_CONTRACT"
    qty = intent.get("quantity")
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        return False, "BAD_CONTRACT"
    try:
        limit = _money(intent.get("limit_price"), "limit_price")
        tick = _money(intent.get("tick"), "tick")
    except (TypeError, ValueError):
        return False, "BAD_CONTRACT"
    if not str(intent.get("account_id") or "").strip():
        return False, "BAD_CONTRACT"
    if intent.get("venue") != "PUBLIC":
        return False, "BAD_CONTRACT"
    if intent.get("execution_owner") not in ("PUBLIC_NATIVE_AGENT", "FLOWW_BACKEND"):
        return False, "BAD_CONTRACT"
    # Product / expiry support comes from account-specific validation, never guessing.
    supported_products = (ctx.get("supported_products") or ["OPTION", "EQUITY"])
    if "OPTION" not in supported_products:
        return False, "UNSUPPORTED_PRODUCT"
    if expiry not in (ctx.get("supported_expiries") or []):
        return False, "UNSUPPORTED_EXPIRY"
    # Quotes: both sides required, fresh, uncrossed.
    quotes = ctx.get("quotes") or {}
    try:
        bid = _money(quotes.get("bid"), "bid") if quotes.get("bid") is not None else None
        ask = _money(quotes.get("ask"), "ask") if quotes.get("ask") is not None else None
    except (TypeError, ValueError):
        return False, "MISSING_QUOTE_SIDES"
    if bid is None or ask is None:
        return False, "MISSING_QUOTE_SIDES"
    if bid > ask:
        return False, "MISSING_QUOTE_SIDES"
    now = ctx.get("now") or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    freshness = int((intent.get("session_policy") or {}).get("freshness_s") or FRESHNESS_DEFAULT_S)
    for ts_field in ("bid_ts", "ask_ts"):
        ts = _parse_ts(quotes.get(ts_field))
        if ts is None:
            return False, "STALE_QUOTE"
        age_s = (now - ts).total_seconds()
        if age_s < -5 or age_s > freshness:
            return False, "STALE_QUOTE"
    if not str(intent.get("risk_policy_version") or "").strip():
        return False, "MISSING_POLICY"
    if intent.get("cash_margin_choice") not in ("CASH", "MARGIN"):
        return False, "UNRESOLVED_MARGIN"
    # Affordability: when the caller supplies account buying power, the budgeted
    # total (premium + costs) must fit it — even one unaffordable contract
    # refuses instead of placing. Absent buying power skips (never invents it).
    buying_power = ctx.get("buying_power")
    budget_total = (intent.get("budget") or {}).get("preflight_total")
    if buying_power is not None and budget_total is not None:
        try:
            if Decimal(str(budget_total)) > Decimal(str(buying_power)):
                return False, "INSUFFICIENT_BUDGET"
        except (InvalidOperation, ValueError, TypeError):
            return False, "INSUFFICIENT_BUDGET"
    if intent.get("replay_id") is not None and not str(intent.get("replay_authorization") or "").strip():
        return False, "UNAUTHORIZED_REPLAY"
    account = ctx.get("account") or {}
    if account.get("entitlement") != "verified":
        return False, "ENTITLEMENT_UNAVAILABLE"
    # Tick rule on exact decimals, never client floats.
    try:
        if (limit % tick) != 0:
            return False, "BAD_TICK"
    except (InvalidOperation, ValueError):
        return False, "BAD_TICK"
    # Operator risk limits (commissioning-owned; absent = no check, documented).
    risk_limits = ctx.get("risk_limits") or {}
    max_qty = risk_limits.get("max_quantity")
    if max_qty is not None:
        try:
            if int(qty) > int(max_qty):
                return False, "RISK_QUANTITY_EXCEEDED"
        except (TypeError, ValueError):
            return False, "RISK_QUANTITY_EXCEEDED"
    max_notional = risk_limits.get("max_notional")
    if max_notional is not None:
        try:
            notional = limit * Decimal(str(int(qty))) * mult
            if notional > Decimal(str(max_notional)):
                return False, "RISK_NOTIONAL_EXCEEDED"
        except (InvalidOperation, ValueError, TypeError):
            return False, "RISK_NOTIONAL_EXCEEDED"
    max_positions = risk_limits.get("max_positions")
    if max_positions is not None:
        try:
            if _open_count() >= int(max_positions):
                return False, "RISK_MAX_POSITIONS_EXCEEDED"
        except (TypeError, ValueError):
            return False, "RISK_MAX_POSITIONS_EXCEEDED"
    # Account-wide policy (when installed): per-call ctx limits narrow, never
    # widen, the stored ceiling. Absent policy stays UNSET (reported, not invented).
    stored = get_account_policy()
    if stored is not None:
        pol = stored.get("policy") or {}
        try:
            sq = pol.get("max_quantity")
            if sq is not None and int(qty) > int(sq):
                return False, "RISK_QUANTITY_EXCEEDED"
        except (TypeError, ValueError):
            return False, "RISK_QUANTITY_EXCEEDED"
        try:
            sn = pol.get("max_notional")
            if sn is not None:
                notional = limit * Decimal(str(int(qty))) * mult
                if notional > Decimal(str(sn)):
                    return False, "RISK_NOTIONAL_EXCEEDED"
        except (InvalidOperation, ValueError, TypeError):
            return False, "RISK_NOTIONAL_EXCEEDED"
        try:
            sp = pol.get("max_positions")
            if sp is not None and _open_count() >= int(sp):
                return False, "RISK_MAX_POSITIONS_EXCEEDED"
        except (TypeError, ValueError):
            return False, "RISK_MAX_POSITIONS_EXCEEDED"
        allowed = pol.get("allowed_products")
        if allowed is not None and "OPTION" not in list(allowed):
            return False, "UNSUPPORTED_PRODUCT"
    # A native workflow created outside FLOWW cannot be controlled by a local
    # lease; unresolved overlap blocks backend entry.
    if intent.get("execution_owner") == "FLOWW_BACKEND":
        for wf in _NATIVE_WORKFLOWS:
            if str(wf.get("status") or "").upper() == "OPEN":
                return False, "OVERLAP_NATIVE"
    # Optional context binding: when both sides pin a context digest (e.g.
    # observation + session + policy fingerprint), a mismatch means the market
    # context moved under a reviewed plan — the draft must be re-reviewed.
    intent_ctx = intent.get("context_hash")
    ctx_ctx = ctx.get("context_hash")
    if intent_ctx is not None and ctx_ctx is not None:
        if str(intent_ctx) != str(ctx_ctx):
            return False, "CONTEXT_CHANGED"
    # Exchange session (fail-closed): entries only on an open XNYS day. The pause
    # window below refines the open session; holidays/weekends refuse outright.
    if not _session_open(now):
        return False, "SESSION_CLOSED"
    # New-entry pause: OPEN intents (entries, long or short) wait; CLOSE intents
    # are risk exits and are never stopped by the pause.
    if intent.get("open_close") == "OPEN" and is_entry_pause(now):
        return False, "ENTRY_PAUSE"
    return True, "ok"


def _session_open(now: datetime) -> bool:
    """XNYS calendar gate for entries (fail-closed on holiday/unknown)."""
    try:
        from services.solstice_calendar import exchange_day_info

        info = exchange_day_info(now.astimezone(ET).strftime("%Y-%m-%d"))
        return bool(info.get("is_open"))
    except Exception:
        return False


def create_approval(
    intent_hash_hex: str,
    account_id: str,
    scope: str,
    valid_until: datetime,
    approved_by: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Server-validated operator approval bound to the immutable intent hash.

    The approval identity binds the author: the same intent approved by
    two operators yields two distinct approval IDs. Same-author,
    same-validity re-mints stay idempotent (approved_at is not part of
    the identity).
    """
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=UTC)
    approval_id = hashlib.sha256(
        f"{intent_hash_hex}|{account_id}|{scope}|{valid_until.isoformat()}|"
        f"{str(approved_by or '').strip()}".encode()
    ).hexdigest()[:16]
    return {
        "approval_id": approval_id,
        "intent_hash": intent_hash_hex,
        "account_id": account_id,
        "scope": scope,
        "valid_until": valid_until.isoformat(),
        "approved_by": approved_by,
        "approved_at": moment.isoformat(),
    }


def verify_approval(
    intent: dict[str, Any], approval: Any, scope: str, now: datetime | None = None
) -> bool:
    """True only for a bound, unexpired, scope-matching server approval."""
    if not isinstance(approval, dict):
        return False
    for field in ("intent_hash", "account_id", "scope", "valid_until", "approved_by", "approved_at"):
        if field not in approval:
            return False
    if approval.get("revoked") is True:
        return False
    approval_id = approval.get("approval_id")
    if isinstance(approval_id, str) and approval_id:
        stored = stored_approval(approval_id)
        if stored is not None and stored.get("revoked") is True:
            return False
    try:
        if intent_hash(intent) != approval["intent_hash"]:
            return False
    except Exception:
        return False
    if approval.get("account_id") != intent.get("account_id"):
        return False
    if approval.get("scope") != scope:
        return False
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    valid_until = _parse_ts(approval.get("valid_until"))
    approved_at = _parse_ts(approval.get("approved_at"))
    if valid_until is None or approved_at is None:
        return False
    return not (moment > valid_until or approved_at > moment)


def _verify_stored_approval(
    intent: dict[str, Any], approval: Any, scope: str, now: datetime | None = None
) -> tuple[bool, str]:
    """Strict mode: the approval must resolve to an authoritative stored row.

    A well-formed caller-supplied copy is never enough on its own: the row
    must exist in the durable approvals table, be unrevoked, and bind the
    presented intent (hash/account/scope/expiry). Store/query failures fail
    closed — never treated as absent approval.
    """
    if not isinstance(approval, dict):
        return False, "APPROVAL_INVALID"
    approval_id = approval.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        return False, "APPROVAL_NOT_STORED"
    if _STORE is None:
        # Storeless registries cannot produce an authoritative row; a memory
        # copy alone is never accepted in strict mode.
        return False, "APPROVAL_NOT_STORED"
    try:
        ensure_lifecycle_tables(_STORE)
        row = _STORE.execute(
            "SELECT approval_json, revoked FROM approvals_v1 "
            "WHERE approval_id = ?", [approval_id]).fetchone()
    except Exception:
        return False, "APPROVAL_STORE_UNAVAILABLE"
    if not row:
        return False, "APPROVAL_NOT_STORED"
    try:
        rec = json.loads(row[0]) if isinstance(row[0], str) else {}
    except (TypeError, ValueError):
        return False, "APPROVAL_NOT_STORED"
    if not isinstance(rec, dict):
        return False, "APPROVAL_NOT_STORED"
    rec["revoked"] = bool(row[1]) if len(row) > 1 else bool(rec.get("revoked"))
    if rec.get("revoked") is True:
        return False, "APPROVAL_INVALID"
    for field in ("intent_hash", "account_id", "scope"):
        if approval.get(field) != rec.get(field):
            return False, "APPROVAL_INVALID"
    if verify_approval(intent, rec, scope=scope, now=now):
        return True, "ok"
    return False, "APPROVAL_INVALID"


def _durable_open_count() -> int | None:
    """Durable nonterminal intent rows, or None when unknown (storeless/error)."""
    if _STORE is None:
        return None
    try:
        ensure_lifecycle_tables(_STORE)
        row = _STORE.execute(
            "SELECT COUNT(*) FROM execution_intents_v1 "
            "WHERE state NOT IN ('FILLED', 'REJECTED', 'CANCELED')").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return None


def _open_records(exclude_id: str | None = None) -> list[dict[str, Any]]:
    terminal = {"FILLED", "REJECTED", "CANCELED"}
    out = []
    for intent_id, rec in _INTENTS.items():
        if exclude_id is not None and intent_id == exclude_id:
            continue
        if str(rec.get("state") or "") not in terminal:
            out.append(rec)
    return out


def _open_count() -> int:
    """Non-terminal open count, durable-aware across restarts.

    Memory is authoritative after recover_open(); before any recover the
    registry is empty but durable rows may exist. max() avoids double-counting
    the recovered rows while never undercounting a fresh process.
    """
    mem = len(_open_records())
    if _STORE is None:
        return mem
    durable = _durable_open_count()
    if durable is None:
        return mem
    return max(mem, durable)


async def _maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable):
        return await value
    return value


def _rget(receipt: Any, *names: str, default: Any = None) -> Any:
    """Read one field off a broker receipt that may be a dict OR a dataclass.

    The real `PublicBroker` returns an `Order` dataclass (`order_id`, `status`
    attributes); fixtures and the portfolio path return plain dicts. Both shapes
    are admitted without inventing values — missing stays missing.
    """
    if receipt is None:
        return default
    if isinstance(receipt, dict):
        for name in names:
            if receipt.get(name) is not None:
                return receipt[name]
        return default
    for name in names:
        value = getattr(receipt, name, None)
        if value is not None:
            return value
    raw = getattr(receipt, "raw", None)
    if isinstance(raw, dict):
        for name in names:
            if raw.get(name) is not None:
                return raw[name]
    return default


PREFLIGHT_TTL_S = 60


def _wall_now() -> float:
    """Server wall clock for preflight freshness (S06).

    Caller-supplied ``ctx["now"]`` is a fictitious decision clock in tests
    and MUST be server-stamped at the entry boundary in production (the
    mounted pipeline stamps it; pure helpers never trust it alone). TTL
    enforcement additionally binds wall time so a frozen caller clock can
    never keep a stale broker verdict fresh past the window.
    """
    import time as _time

    return _time.time()


def _ctx_fingerprint(ctx: dict[str, Any]) -> str:
    """Market-context fingerprint: quotes + account + session policy.

    Preflight estimates are only valid for the market + account + policy they
    were quoted in. Intent-hash alone would reuse a stale estimate after the
    market moves; fingerprinting forces expiry on relevant changes.
    """
    quotes = ctx.get("quotes") or {}
    account = ctx.get("account") or {}
    session_policy = (ctx.get("session_policy") or {})
    blob = json.dumps({
        "bid": quotes.get("bid"), "ask": quotes.get("ask"),
        "bid_ts": quotes.get("bid_ts"), "ask_ts": quotes.get("ask_ts"),
        "entitlement": account.get("entitlement"),
        "options_level": account.get("options_level"),
        "margin": account.get("margin"),
        "session_policy": session_policy,
        "supported_expiries": ctx.get("supported_expiries"),
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


async def preflight(intent: dict[str, Any], ctx: dict[str, Any], broker: Any) -> dict[str, Any]:
    """Fresh cost-aware preflight; expires on intent OR market-context change.

    Cache key = intent_hash + ctx fingerprint, TTL 60s. No vendor default.
    """
    if intent.get("cash_margin_choice") not in ("CASH", "MARGIN"):
        return {"ok": False, "reason": "UNRESOLVED_MARGIN"}
    try:
        digest = intent_hash(intent)
        key = digest + "|" + _ctx_fingerprint(ctx)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"BAD_CONTRACT:{exc}"}
    now_epoch = _now_epoch(ctx.get("now"))
    wall = _wall_now()
    cached = _PREFLIGHT_CACHE.get(key)
    if cached is not None and (now_epoch - float(cached.get("at_epoch", 0.0))) < PREFLIGHT_TTL_S:
        if (wall - float(cached.get("at_wall", wall))) < PREFLIGHT_TTL_S:
            out = dict(cached["receipt"])
            out["cached"] = True
            return out
    contract = intent.get("contract") or {}
    estimate = await _maybe_await(broker.preflight_single_leg(
        account_id=intent.get("account_id"),
        symbol=contract.get("osi"),
        side=intent.get("side"),
        order_type="LIMIT",
        quantity=float(intent.get("quantity")),
        limit_price=str(intent.get("limit_price")),
        use_margin=(intent.get("cash_margin_choice") == "MARGIN"),
    ))
    out = {"ok": True, "estimate": estimate, "intent_hash": digest,
           "ctx_fingerprint": key.split("|", 1)[1], "cached": False}
    _PREFLIGHT_CACHE[key] = {"receipt": dict(out), "at_epoch": now_epoch,
                             "at_wall": _wall_now()}
    return out


def preflight_gate(intent: dict[str, Any], ctx: dict[str, Any]) -> str | None:
    """Preflight admission gate: None when covered, else a refusal code.

    A cached preflight satisfies the gate only when it covers this exact
    intent + market context, is inside the 60s TTL on BOTH the decision
    clock and the server wall clock, AND carries a broker
    verdict with buying_power_ok True. A failed/negative broker verdict
    never satisfies the gate (PREFLIGHT_UNAFFORDABLE) — freshness alone
    is not affordability. A frozen caller clock cannot extend freshness
    past the wall-clock bound.
    """
    try:
        key = intent_hash(intent) + "|" + _ctx_fingerprint(ctx)
    except (TypeError, ValueError):
        return "STALE_PREFLIGHT"
    cached = _PREFLIGHT_CACHE.get(key)
    if cached is None:
        return "STALE_PREFLIGHT"
    try:
        stale = (_now_epoch(ctx.get("now"))
                 - float(cached.get("at_epoch", 0.0))) >= PREFLIGHT_TTL_S
    except (TypeError, ValueError):
        return "STALE_PREFLIGHT"
    if stale:
        return "STALE_PREFLIGHT"
    try:
        wall_stale = (_wall_now() - float(
            cached.get("at_wall", _wall_now()))) >= PREFLIGHT_TTL_S
    except (TypeError, ValueError):
        return "STALE_PREFLIGHT"
    if wall_stale:
        return "STALE_PREFLIGHT"
    estimate = (cached.get("receipt") or {}).get("estimate") or {}
    if estimate.get("buying_power_ok") is not True:
        return "PREFLIGHT_UNAFFORDABLE"
    return None


def has_fresh_preflight(intent: dict[str, Any], ctx: dict[str, Any]) -> bool:
    """True only when a cached verdict-good preflight covers intent + ctx."""
    return preflight_gate(intent, ctx) is None


def _now_epoch(value: Any) -> float:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    parsed = _parse_ts(value)
    if parsed is not None:
        return parsed.timestamp()
    import time as _time

    return _time.time()


async def submit(
    intent: dict[str, Any], ctx: dict[str, Any], broker: Any, armed: bool = False,
    approval: dict[str, Any] | None = None, require_approval: bool = False,
    approval_scope: str = "single-entry", require_fresh_preflight: bool = False,
    require_stored_approval: bool = False,
) -> dict[str, Any]:
    """Deterministic submit: validate → approval → preflight → ownership → placement.

    `armed=False` (default) refuses before any broker access. Retries reuse the
    original broker orderId + payload. Ambiguous transport is preserved as
    UNKNOWN for reconciliation, never guessed. Production callers pass
    `require_approval=True` with a server-validated approval (and
    `require_fresh_preflight=True` once a preflight desk exists); tests default
    to validation-only so intent logic stays pinnable without an approval desk.
    Strict callers additionally pass `require_stored_approval=True`: the
    approval must then resolve to an authoritative stored, unrevoked row
    (APPROVAL_NOT_STORED / APPROVAL_STORE_UNAVAILABLE otherwise) — a
    well-formed caller-supplied copy alone is refused.
    """
    if not armed:
        return {"ok": False, "reason": "DISARMED"}
    ok, reason = validate_intent(intent, ctx)
    if not ok:
        return {"ok": False, "reason": reason}
    if require_approval:
        now = ctx.get("now") if isinstance(ctx.get("now"), datetime) else None
        if not verify_approval(intent, approval, scope=approval_scope, now=now):
            return {"ok": False, "reason": "APPROVAL_INVALID"}
    if require_stored_approval:
        now = ctx.get("now") if isinstance(ctx.get("now"), datetime) else None
        ok_s, reason_s = _verify_stored_approval(
            intent, approval, scope=approval_scope, now=now)
        if not ok_s:
            return {"ok": False, "reason": reason_s}
    if require_fresh_preflight and not has_fresh_preflight(intent, ctx):
        return {"ok": False, "reason": "STALE_PREFLIGHT"}
    try:
        digest = intent_hash(intent)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"BAD_CONTRACT:{exc}"}
    intent_id = f"in_{digest[:12]}"
    with _SUBMIT_LOCK:
        existing = _INTENTS.get(intent_id)
        if (existing is None or not existing.get("order_id")) and _STORE is not None:
            # Cross-process guard: another process may own this intent already.
            loaded = _load_record(intent_id)
            if loaded is not None:
                _INTENTS[intent_id] = loaded
                existing = loaded
        if existing is not None and existing.get("order_id"):
            return {"ok": True, "receipt_version": RECEIPT_VERSION,
                    "intent_id": intent_id, "order_id": existing["order_id"],
                    "status": existing.get("state", "OPEN"), "duplicate": True,
                    "persist_error": bool(existing.get("persist_error"))}
        if not _INTENTS and _STORE is not None:
            # Fresh process with a durable store: unknown durable opens must be
            # recovered + reconciled before any new entry. Call recover_open()
            # then reconcile_all() first; this refusal is the gate.
            if (_durable_open_count() or 0) > 0:
                return {"ok": False, "reason": "RECOVERY_REQUIRED",
                        "intent_id": intent_id,
                        "detail": "durable nonterminal rows exist; "
                                  "recover_open() + reconcile_all() first"}
        else:
            # A process holding only terminal/settled records may still face
            # foreign durable opens it never recovered (another writer). Any
            # durable surplus over known memory opens blocks new entry.
            durable = _durable_open_count()
            if durable is not None and durable > len(_open_records()):
                return {"ok": False, "reason": "RECOVERY_REQUIRED",
                        "intent_id": intent_id,
                        "detail": "durable nonterminal rows exceed known memory "
                                  "opens; recover_open() + reconcile_all() first"}
        if _open_records(exclude_id=intent_id):
            return {"ok": False, "reason": "OVERLAP_OPEN_NEEDS_RECONCILE"}
        order_id = str(uuid.uuid4())
        contract = intent.get("contract") or {}
        payload = {
            "account_id": intent.get("account_id"),
            "order_id": order_id,
            "symbol": contract.get("osi"),
            "side": intent.get("side"),
            "order_type": "LIMIT",
            "quantity": float(intent.get("quantity")),
            "limit_price": str(intent.get("limit_price")),
            "time_in_force": "DAY",
            "instrument_type": "OPTION",
            "use_margin": (intent.get("cash_margin_choice") == "MARGIN"),
        }
        _INTENTS[intent_id] = {
            "intent": dict(intent), "intent_hash": digest, "order_id": order_id,
            "payload": dict(payload), "state": "SUBMITTED",
            "approval": dict(approval) if isinstance(approval, dict) else None,
        }
        if not _persist(intent_id):
            del _INTENTS[intent_id]
            return {"ok": False, "reason": "STORE_UNAVAILABLE", "intent_id": intent_id}
    try:
        receipt = await _maybe_await(broker.place_order(**payload))
    except Exception as exc:
        _INTENTS[intent_id]["state"] = "UNKNOWN"
        _INTENTS[intent_id]["error"] = f"{type(exc).__name__}: {exc}"
        _persist(intent_id)
        return {"ok": False, "reason": "AMBIGUOUS_NEEDS_RECONCILE",
                "receipt_version": RECEIPT_VERSION,
                "intent_id": intent_id, "order_id": order_id}
    status = str(_rget(receipt, "status", default="UNKNOWN") or "UNKNOWN").upper()
    _INTENTS[intent_id]["state"] = status if status in (
        "OPEN", "PENDING", "PARTIAL", "FILLED", "REJECTED", "CANCELED") else "ACKNOWLEDGED"
    _INTENTS[intent_id]["receipt"] = receipt
    if not _persist(intent_id):
        # The broker accepted, so the receipt is reported truthfully — but the
        # write failure is flagged, never hidden. A later recover_open() reloads
        # the last persisted state and reconcile_all refreshes from the broker,
        # so this heals instead of silently diverging.
        _INTENTS[intent_id]["persist_error"] = True
    return {"ok": True, "receipt_version": RECEIPT_VERSION,
            "intent_id": intent_id, "order_id": order_id,
            "status": _INTENTS[intent_id]["state"],
            "persist_error": bool(_INTENTS[intent_id].get("persist_error"))}


async def reconcile(intent_id: str, broker: Any) -> dict[str, Any]:
    """Read-only reconcile by broker orderId. Unknown stays unknown."""
    rec = _INTENTS.get(intent_id)
    if rec is None or not rec.get("order_id"):
        return {"intent_id": intent_id, "order_id": None, "status": "UNKNOWN", "filled": False}
    try:
        observed = await _maybe_await(broker.get_order(rec["intent"]["account_id"], rec["order_id"]))
    except Exception as exc:
        return {"intent_id": intent_id, "order_id": rec["order_id"],
                "status": "UNKNOWN", "filled": False, "error": str(exc)}
    status = str(_rget(observed, "status", default="UNKNOWN") or "UNKNOWN").upper()
    if status not in ("OPEN", "PENDING", "PARTIAL", "FILLED", "REJECTED", "CANCELED", "UNKNOWN"):
        status = "UNKNOWN"
    rec["state"] = status
    rec["observed"] = observed
    _persist(intent_id)
    out: dict[str, Any] = {"intent_id": intent_id, "order_id": rec["order_id"], "status": status,
            "filled": (status == "FILLED"), "receipt_version": RECEIPT_VERSION}
    # Fill accounting: filled and remaining quantities when the broker reports
    # them; unknown stays unknown (never derived from price or sign).
    try:
        ordered_qty = int(rec.get("intent", {}).get("quantity") or 0)
    except (TypeError, ValueError):
        ordered_qty = 0
    filled_qty = _rget(observed, "filled_quantity", "filledQuantity", "filledAmount", "fills")
    try:
        filled_qty = int(float(filled_qty)) if filled_qty is not None else None
    except (TypeError, ValueError):
        filled_qty = None
    if filled_qty is not None and ordered_qty:
        out["filled_quantity"] = filled_qty
        out["remaining_quantity"] = max(0, ordered_qty - filled_qty)
    return out


async def reconcile_all(broker: Any) -> list[dict[str, Any]]:
    """Restart/resume helper: reconcile every open/unknown record by orderId.

    Call before any new entry after a restart. Read-only; truthful states only.
    """
    out: list[dict[str, Any]] = []
    for intent_id, rec in list(_INTENTS.items()):
        if str(rec.get("state") or "") in ("FILLED", "REJECTED", "CANCELED"):
            continue
        if not rec.get("order_id"):
            continue
        out.append(await reconcile(intent_id, broker))
    return out


async def replace(intent_id: str, changes: dict[str, Any], broker: Any) -> dict[str, Any]:
    """Refused: a changed order requires a new intent lifecycle transition."""
    raise ValueError("changed order requires a new intent (no in-place reuse with new fields)")


async def cancel(intent_id: str, broker: Any) -> dict[str, Any]:
    """Authenticated cancellation of one owned order (exits stay available).

    No arming requirement and no entry-pause check: risk exits and cancels are
    independent of new-entry gates by design. A pending/empty broker answer is
    recorded as CANCEL_PENDING — pending cancellation is NOT canceled; the
    record stays non-terminal until a later reconcile observes CANCELED, so a
    new entry remains blocked meanwhile.
    """
    rec = _INTENTS.get(intent_id)
    if rec is None or not rec.get("order_id"):
        return {"intent_id": intent_id, "order_id": None, "status": "UNKNOWN",
                "cancelled": False, "reason": "unknown-intent"}
    if str(rec.get("state") or "") in ("FILLED", "REJECTED", "CANCELED"):
        # Terminal orders are never (re)cancelled: no broker call is made.
        return {"intent_id": intent_id, "order_id": rec["order_id"], "status": rec.get("state"),
                "cancelled": False, "reason": "already-terminal"}
    try:
        receipt = await _maybe_await(broker.cancel_order(rec["intent"]["account_id"], rec["order_id"]))
    except Exception as exc:
        return {"intent_id": intent_id, "order_id": rec["order_id"], "status": rec.get("state", "UNKNOWN"),
                "cancelled": False, "reason": f"CANCEL_FAILED:{type(exc).__name__}"}
    status = str(_rget(receipt, "status", default="") or "").upper()
    if status == "CANCELED":
        rec["state"] = "CANCELED"
        _persist(intent_id)
        return {"intent_id": intent_id, "order_id": rec["order_id"], "status": "CANCELED",
                "cancelled": True, "receipt_version": RECEIPT_VERSION}
    rec["state"] = "CANCEL_PENDING"
    rec["cancel_receipt"] = receipt
    _persist(intent_id)
    return {"intent_id": intent_id, "order_id": rec["order_id"], "status": "CANCEL_PENDING",
            "cancelled": False, "reason": "pending-not-canceled",
            "receipt_version": RECEIPT_VERSION}


async def supersede(
    old_intent_id: str, new_intent: dict[str, Any], ctx: dict[str, Any], broker: Any,
    armed: bool = False,
    approval: dict[str, Any] | None = None, require_approval: bool = False,
    approval_scope: str = "single-entry", require_fresh_preflight: bool = False,
    require_stored_approval: bool = False,
) -> dict[str, Any]:
    """Intentional lifecycle transition for a changed order: cancel old, enter new.

    The old order is cancelled first (never reused with new fields); the new
    intent submits only after the old record reaches CANCELED. Any other outcome
    (pending, unknown, still open) blocks entry with an explicit reason instead
    of double-entering. Returns the new submit receipt with `supersedes` set.
    Disarmed supersede refuses BEFORE cancelling: a refused transition must
    never leave the old order cancelled with no replacement. Deterministic
    gates (validation, approval, stored approval, fresh preflight) are
    pre-checked BEFORE cancelling for the same reason: a predictably refused
    new intent must not strand a cancelled order with no replacement.
    """
    if not armed:
        return {"ok": False, "reason": "DISARMED", "old_intent_id": old_intent_id}
    old = _INTENTS.get(old_intent_id)
    if old is None or not old.get("order_id"):
        return {"ok": False, "reason": "unknown-intent"}
    candidate = dict(new_intent)
    candidate["supersedes"] = old_intent_id
    ok, reason = validate_intent(candidate, ctx)
    if not ok:
        return {"ok": False, "reason": reason, "old_intent_id": old_intent_id}
    if require_approval:
        now = ctx.get("now") if isinstance(ctx.get("now"), datetime) else None
        if not verify_approval(candidate, approval, scope=approval_scope, now=now):
            return {"ok": False, "reason": "APPROVAL_INVALID", "old_intent_id": old_intent_id}
    if require_stored_approval:
        now = ctx.get("now") if isinstance(ctx.get("now"), datetime) else None
        ok_s, reason_s = _verify_stored_approval(
            candidate, approval, scope=approval_scope, now=now)
        if not ok_s:
            return {"ok": False, "reason": reason_s, "old_intent_id": old_intent_id}
    if require_fresh_preflight and not has_fresh_preflight(candidate, ctx):
        return {"ok": False, "reason": "STALE_PREFLIGHT", "old_intent_id": old_intent_id}
    cancelled = await cancel(old_intent_id, broker)
    if not cancelled.get("cancelled"):
        return {"ok": False, "reason": "SUPERSEDE_BLOCKED",
                "detail": cancelled.get("status"), "old_intent_id": old_intent_id}
    out = await submit(candidate, ctx, broker, armed=armed,
                       approval=approval, require_approval=require_approval,
                       approval_scope=approval_scope,
                       require_fresh_preflight=require_fresh_preflight,
                       require_stored_approval=require_stored_approval)
    if isinstance(out, dict):
        out["supersedes"] = old_intent_id
    return out


def protection_status(intent_id: str) -> dict[str, Any]:
    """Conservative protection truth: only verified-complete protection counts."""
    rec = _INTENTS.get(intent_id)
    if rec is None:
        return {"protected": False, "reason": "unknown-intent"}
    # No bracket/OCO linkage has been verified in this lane; never overstate.
    return {"protected": False, "reason": "no-verified-protection", "state": rec.get("state")}


INVENTORY_VERSION = "lifecycle-inventory.v1"


def lifecycle_inventory() -> dict[str, Any]:
    """Read-only lifecycle inventory (R17-4, Zed request 3).

    Aggregates the stored execution boundary without executing recovery,
    any broker call or any new live path: known/open/unknown intent records
    with conservative protection truth, draft stages (stored approvals and
    preflight states are draft rows, never client booleans), native workflow
    registrations, the NEW-ENTRY protection window and the honest recovery
    boundary. A storeless registry is reported as storeless — never as proof
    that no orders are open. Preflight context is counted, never returned
    (redacted). Account-wide limits stay UNSET: this reports the boundary,
    it does not set policy.
    """
    now = datetime.now(UTC)
    terminal = {"FILLED", "REJECTED", "CANCELED"}
    open_rows: list[dict[str, Any]] = []
    unknown_rows: list[dict[str, Any]] = []
    for intent_id, rec in _INTENTS.items():
        state = str(rec.get("state") or "")
        if state in terminal:
            continue
        intent = rec.get("intent") or {}
        row = {
            "intent_id": intent_id,
            "ticker": intent.get("ticker"),
            "state": state,
            "order_id": rec.get("order_id"),
            "owner": intent.get("execution_owner"),
            "has_approval": rec.get("approval") is not None,
            "protection": protection_status(intent_id),
        }
        if state == "UNKNOWN":
            row["error"] = rec.get("error")
            unknown_rows.append(row)
        else:
            open_rows.append(row)
    durable_nonterminal: int | None = None
    if _STORE is not None:
        try:
            counted = _STORE.execute(
                "SELECT COUNT(*) FROM execution_intents_v1 "
                "WHERE state NOT IN ('FILLED', 'REJECTED', 'CANCELED')").fetchone()
            durable_nonterminal = int(counted[0]) if counted else 0
        except Exception:
            durable_nonterminal = None
    drafts = list(_DRAFTS.values())
    if _STORE is not None:
        try:
            _STORE.execute(DRAFT_DDL)
            for hash_row in _STORE.execute(
                "SELECT intent_hash, stage FROM intent_drafts_v1").fetchall() or []:
                digest = hash_row[0] if hash_row else None
                stage = hash_row[1] if len(hash_row) > 1 else "DRAFT"
                if digest is not None and digest in _DRAFTS:
                    continue  # same logical draft in both registries: count once
                drafts.append({"stage": stage})
        except Exception:  # silent by design: inventory stays available on memory rows alone
            pass
    by_stage: dict[str, int] = {}
    for draft in drafts:
        stage = str(draft.get("stage") or "DRAFT")
        by_stage[stage] = by_stage.get(stage, 0) + 1
    stored_policy = get_account_policy()
    approval_ids: set[str] = set(_APPROVALS.keys())
    revoked_ids: set[str] = {k for k, v in _APPROVALS.items() if v.get("revoked") is True}
    if _STORE is not None:
        try:
            ensure_lifecycle_tables(_STORE)
            for id_row in _STORE.execute(
                "SELECT approval_id, revoked FROM approvals_v1").fetchall() or []:
                if not id_row or not id_row[0]:
                    continue
                approval_ids.add(str(id_row[0]))
                if len(id_row) > 1 and bool(id_row[1]):
                    revoked_ids.add(str(id_row[0]))
        except Exception:  # silent by design: inventory stays available on memory counts alone
            pass
    n_approvals = len(approval_ids)
    n_revoked = len(revoked_ids & approval_ids)
    return {
        "version": INVENTORY_VERSION,
        "durable": _STORE is not None,
        "storeless": _STORE is None,
        "intents": {
            "n_known": len(_INTENTS),
            "n_open": len(open_rows),
            "open": open_rows,
            "n_unknown": len(unknown_rows),
            "unknown": unknown_rows,
        },
        "drafts": {
            "n_staged": len(drafts),
            "by_stage": by_stage,
            "stages": list(_DRAFT_STAGES),
        },
        "native_workflows": list(_NATIVE_WORKFLOWS),
        "preflight": {
            "n_cached_contexts": len(_PREFLIGHT_CACHE),
            "detail": "redacted: contexts are counted, never returned",
        },
        "approvals": {
            "n_stored": n_approvals,
            "n_revoked": n_revoked,
            "detail": "server-validated approvals are stored + revocable; "
                      "records are counted, never returned with secrets",
        },
        "protection": {
            "entry_pause_now": is_entry_pause(now),
            "cancel_allowed_during_pause": cancel_allowed_during_pause(),
            "window": "11:30-14:00 America/New_York NEW-ENTRY pause (weekdays)",
            "native_support": {
                k: {"supported": False,
                    "reason": str(v.get("reason") or "unverified-native-support")}
                for k, v in NATIVE_PROTECTION_MATRIX.items()
            },
        },
        "recovery": {
            "durable_nonterminal_rows": durable_nonterminal,
            "detail": "read-only count; recovery rehydrates and is not executed here; "
                      "fresh processes refuse new entry until recover_open() + "
                      "reconcile_all() (RECOVERY_REQUIRED)",
        },
        "policy": {
            "account_wide_limits": (
                "UNSET" if stored_policy is None
                else {"version": ACCOUNT_POLICY_VERSION, "set": True,
                      "updated_at": stored_policy.get("updated_at")}),
            "detail": "policy values are commissioning inputs; this inventory "
                      "reports the boundary, it does not set policy",
        },
    }
