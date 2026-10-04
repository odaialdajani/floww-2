"""
backend/services/operator_registry.py — account-bound operator identity (S2).

Contract note: the HTTP layer authenticates with the deployment master key
(`require_api_key`). A named operator string alone is not identity — this
registry binds a registered operator to explicit allowed accounts, durably
first, so admission can refuse OPERATOR_UNAUTHORIZED instead of trusting a
client assertion. Per-operator API keys remain a commissioning input.

Refusals: STORE_UNAVAILABLE, OPERATOR_STORE_UNAVAILABLE, OPERATOR_UNKNOWN,
OPERATOR_UNAUTHORIZED (account not allowed), OPERATOR_EXISTS.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

OPERATOR_REGISTRY_VERSION = "operator-registry.v1"

OPERATOR_DDL = """
    CREATE TABLE IF NOT EXISTS operators_v1 (
        operator_id VARCHAR PRIMARY KEY, allowed_accounts VARCHAR,
        created_by VARCHAR, updated_at VARCHAR
    )
"""

__all__ = [
    "OPERATOR_REGISTRY_VERSION",
    "OPERATOR_DDL",
    "register_operator",
    "remove_operator",
    "authorize_operator",
    "list_operators",
]


def _tables(conn: Any) -> None:
    from services import public_execution_lifecycle as lc

    lc.ensure_lifecycle_tables(conn)
    conn.execute(OPERATOR_DDL)


def register_operator(
    conn: Any, operator_id: str, allowed_accounts: list[str], created_by: str,
) -> dict[str, Any]:
    """Register an operator with explicit allowed accounts (durable-first).

    Refuses on store failure (no memory authority is kept here at all —
    this registry is durable-only by design). Duplicate registration refuses
    OPERATOR_EXISTS instead of silently overwriting scope.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not str(operator_id or "").strip() or not str(created_by or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    accounts = sorted({str(a).strip() for a in (allowed_accounts or []) if str(a).strip()})
    if not accounts:
        return {"ok": False, "reason": "BAD_CONTRACT"}
    try:
        _tables(conn)
        if conn.execute(
            "SELECT operator_id FROM operators_v1 WHERE operator_id = ?",
            [str(operator_id)]).fetchone():
            return {"ok": False, "reason": "OPERATOR_EXISTS"}
        conn.execute(
            "INSERT INTO operators_v1 "
            "(operator_id, allowed_accounts, created_by, updated_at) "
            "VALUES (?, ?, ?, ?)",
            [str(operator_id), json.dumps(accounts),
             str(created_by), datetime.now(UTC).isoformat()],
        )
    except Exception:
        return {"ok": False, "reason": "OPERATOR_STORE_UNAVAILABLE"}
    return {"ok": True, "operator_id": str(operator_id),
            "allowed_accounts": accounts}


def remove_operator(conn: Any, operator_id: str) -> dict[str, Any]:
    """Remove an operator binding (durable delete).

    Unknown IDs refuse OPERATOR_UNKNOWN (never a silent no-op success);
    after removal the operator authorizes as UNKNOWN everywhere. There
    is no memory copy in this registry, so nothing else needs purging.
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not str(operator_id or "").strip():
        return {"ok": False, "reason": "OPERATOR_UNKNOWN"}
    try:
        _tables(conn)
        row = conn.execute(
            "SELECT operator_id FROM operators_v1 WHERE operator_id = ?",
            [str(operator_id)]).fetchone()
        if not row:
            return {"ok": False, "reason": "OPERATOR_UNKNOWN"}
        conn.execute("DELETE FROM operators_v1 WHERE operator_id = ?",
                     [str(operator_id)])
    except Exception:
        return {"ok": False, "reason": "OPERATOR_STORE_UNAVAILABLE"}
    return {"ok": True, "operator_id": str(operator_id)}


def authorize_operator(conn: Any, operator_id: str, account_id: str) -> dict[str, Any]:
    """Bind check: registered operator AND account in its allowlist.

    Unknown operator → OPERATOR_UNKNOWN. Known operator, foreign account →
    OPERATOR_UNAUTHORIZED. Query failure → OPERATOR_STORE_UNAVAILABLE
    (unknown is not unauthorized and not authorized — it refuses distinctly).
    """
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    if not str(operator_id or "").strip() or not str(account_id or "").strip():
        return {"ok": False, "reason": "OPERATOR_UNKNOWN"}
    try:
        _tables(conn)
        row = conn.execute(
            "SELECT allowed_accounts FROM operators_v1 WHERE operator_id = ?",
            [str(operator_id)]).fetchone()
    except Exception:
        return {"ok": False, "reason": "OPERATOR_STORE_UNAVAILABLE"}
    if not row:
        return {"ok": False, "reason": "OPERATOR_UNKNOWN"}
    try:
        allowed = json.loads(row[0]) if isinstance(row[0], str) else []
    except (TypeError, ValueError):
        return {"ok": False, "reason": "OPERATOR_STORE_UNAVAILABLE"}
    if str(account_id) in list(allowed or []):
        return {"ok": True, "operator_id": str(operator_id),
                "account_id": str(account_id)}
    return {"ok": False, "reason": "OPERATOR_UNAUTHORIZED"}


def list_operators(conn: Any) -> dict[str, Any]:
    """Operator IDs only (allowlists stay out of listings)."""
    if conn is None:
        return {"ok": False, "reason": "STORE_UNAVAILABLE"}
    try:
        _tables(conn)
        rows = conn.execute("SELECT operator_id FROM operators_v1").fetchall() or []
    except Exception:
        return {"ok": False, "reason": "OPERATOR_STORE_UNAVAILABLE"}
    return {"ok": True, "operators": sorted(str(r[0]) for r in rows if r and r[0])}
