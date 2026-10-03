"""
backend/routes/execution_admission.py — UNMOUNTED admission route patch (S2).

PROPOSAL for Zed's review, not mounted in server.py: authenticated
default-off admission/approval/policy/operator/risk endpoints backed by
`services.execution_admission` (+ operator registry + risk ledger). No
broker construction, no placement, no cancellation anywhere in this file.
Zed alone reviews/integrates the mount after the refusal matrix passes;
do NOT mount without that review. Mounting must not weaken the existing
FLOWW_ENABLE_LIVE_PUBLIC gate or the authenticated-cancellation path.

Tested via a test-local FastAPI app (see
backend/tests/solstice/test_s18_commissioned.py); production openapi.json
is untouched while unmounted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from auth import require_api_key

router = APIRouter(prefix="/admission", tags=["execution_admission"])
__all__ = ["router"]


def _store_conn() -> Any | None:
    try:
        from services.duckdb_engine import db as eng

        return eng.conn if hasattr(eng, "conn") else None
    except Exception:
        return None


def _parse_now(value: Any) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value.strip():
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail={
                "error": "bad_now",
                "message": "ctx.now must be ISO-8601",
            }) from None
    else:
        moment = datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


@router.post("/policies")
async def set_policy(body: dict[str, Any], _: bool = Depends(require_api_key)) -> dict[str, Any]:
    """Install an account-keyed policy (durable-first, fails closed)."""
    from services import execution_admission as adm

    out = adm.set_account_policy_required(
        _store_conn(), body.get("account_id"), body.get("policy"),
        body.get("operator"), body.get("scope", "account-entry"))
    if not out.get("ok"):
        raise HTTPException(status_code=503, detail=out)
    return out


@router.post("/approvals")
async def store_approval(body: dict[str, Any], _: bool = Depends(require_api_key)) -> dict[str, Any]:
    """Persist a server-validated approval (durable-first, revocable)."""
    from services import execution_admission as adm

    out = adm.store_approval_required(
        _store_conn(), body.get("approval"), body.get("operator"))
    if not out.get("ok"):
        raise HTTPException(status_code=503, detail=out)
    return out


@router.post("/approvals/{approval_id}/revoke")
async def revoke_approval(
    approval_id: str, body: dict[str, Any], _: bool = Depends(require_api_key),
) -> dict[str, Any]:
    """Revoke a stored approval (durable-first; failure refuses)."""
    from services import execution_admission as adm

    out = adm.revoke_approval_required(_store_conn(), approval_id, body.get("operator"))
    if not out.get("ok"):
        status = 404 if out.get("reason") == "unknown-approval" else 503
        raise HTTPException(status_code=status, detail=out)
    return out


@router.post("/operators")
async def register_operator(
    body: dict[str, Any], _: bool = Depends(require_api_key),
) -> dict[str, Any]:
    """Bind a named operator to explicit allowed accounts."""
    from services import operator_registry as operators

    out = operators.register_operator(
        _store_conn(), body.get("operator_id"),
        body.get("allowed_accounts"), body.get("created_by"))
    if not out.get("ok"):
        status = 409 if out.get("reason") == "OPERATOR_EXISTS" else 503
        raise HTTPException(status_code=status, detail=out)
    return out


@router.post("/risk/evaluate")
async def evaluate_risk(body: dict[str, Any], _: bool = Depends(require_api_key)) -> dict[str, Any]:
    """Evaluate the account risk ledger from injected broker facts (pure)."""
    from services import account_risk_ledger as ledger

    return ledger.evaluate_account_risk(
        body.get("facts"), body.get("policy") or {}, body.get("today"))


@router.post("/decision")
async def admission_decision(
    body: dict[str, Any], _: bool = Depends(require_api_key),
) -> dict[str, Any]:
    """Commissioned admission decision (never dispatches, never cancels).

    Requires primed preflight context (deterministic lifecycle preflight);
    without it the decision is STALE_PREFLIGHT by design.
    """
    from services import execution_admission as adm

    ctx = dict(body.get("ctx") or {})
    ctx["now"] = _parse_now(ctx.get("now"))
    return adm.admit_commissioned_entry(
        _store_conn(), body.get("intent"), ctx, broker=None,
        approval=body.get("approval"),
        approval_scope=body.get("approval_scope", "single-entry"),
        operator_id=body.get("operator_id"),
        risk_facts=body.get("risk_facts"),
        remote_native=body.get("remote_native"))
