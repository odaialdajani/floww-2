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
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

INTENT_VERSION = "execution-intent.v1"
RISK_POLICY = "research_barriers.v1"
ET = ZoneInfo("America/New_York")
FRESHNESS_DEFAULT_S = 30

_OSI_RE = re.compile(r"^[A-Z0-9\.]{1,12}(\d{6})([CP])(\d{8})$")

_INTENTS: dict[str, dict[str, Any]] = {}
_NATIVE_WORKFLOWS: list[dict[str, Any]] = []
_PREFLIGHT_CACHE: dict[str, dict[str, Any]] = {}

__all__ = [
    "INTENT_VERSION",
    "PREFLIGHT_TTL_S",
    "intent_hash",
    "validate_intent",
    "create_approval",
    "verify_approval",
    "submit",
    "reconcile",
    "reconcile_all",
    "replace",
    "preflight",
    "protection_status",
    "is_entry_pause",
    "cancel_allowed_during_pause",
    "register_native_workflow",
]


def _reset_for_tests() -> None:
    _INTENTS.clear()
    _NATIVE_WORKFLOWS.clear()
    _PREFLIGHT_CACHE.clear()


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
    if is_entry_pause(now):
        return False, "ENTRY_PAUSE"
    return True, "ok"


def create_approval(
    intent_hash_hex: str,
    account_id: str,
    scope: str,
    valid_until: datetime,
    approved_by: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Server-validated operator approval bound to the immutable intent hash."""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=UTC)
    approval_id = hashlib.sha256(
        f"{intent_hash_hex}|{account_id}|{scope}|{valid_until.isoformat()}".encode()
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


def _open_records(exclude_id: str | None = None) -> list[dict[str, Any]]:
    terminal = {"FILLED", "REJECTED", "CANCELED"}
    out = []
    for intent_id, rec in _INTENTS.items():
        if exclude_id is not None and intent_id == exclude_id:
            continue
        if str(rec.get("state") or "") not in terminal:
            out.append(rec)
    return out


async def _maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable):
        return await value
    return value


PREFLIGHT_TTL_S = 60


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
        key = intent_hash(intent) + "|" + _ctx_fingerprint(ctx)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"BAD_CONTRACT:{exc}"}
    now_epoch = _now_epoch(ctx.get("now"))
    cached = _PREFLIGHT_CACHE.get(key)
    if cached is not None and (now_epoch - float(cached.get("at_epoch", 0.0))) < PREFLIGHT_TTL_S:
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
    out = {"ok": True, "estimate": estimate, "intent_hash": key, "cached": False}
    _PREFLIGHT_CACHE[key] = {"receipt": dict(out), "at_epoch": now_epoch}
    return out


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
    approval_scope: str = "single-entry",
) -> dict[str, Any]:
    """Deterministic submit: validate → approval → idempotent ownership → placement.

    `armed=False` (default) refuses before any broker access. Retries reuse the
    original broker orderId + payload. Ambiguous transport is preserved as
    UNKNOWN for reconciliation, never guessed. Production callers pass
    `require_approval=True` with a server-validated approval; tests default to
    validation-only so intent logic stays pinnable without an approval desk.
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
    try:
        digest = intent_hash(intent)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"BAD_CONTRACT:{exc}"}
    intent_id = f"in_{digest[:12]}"
    existing = _INTENTS.get(intent_id)
    if existing is not None and existing.get("order_id"):
        return {"ok": True, "intent_id": intent_id, "order_id": existing["order_id"],
                "status": existing.get("state", "OPEN"), "duplicate": True}
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
    try:
        receipt = await _maybe_await(broker.place_order(**payload))
    except Exception as exc:
        _INTENTS[intent_id]["state"] = "UNKNOWN"
        _INTENTS[intent_id]["error"] = f"{type(exc).__name__}: {exc}"
        return {"ok": False, "reason": "AMBIGUOUS_NEEDS_RECONCILE",
                "intent_id": intent_id, "order_id": order_id}
    status = str((receipt or {}).get("status") or "UNKNOWN").upper()
    _INTENTS[intent_id]["state"] = status if status in (
        "OPEN", "PENDING", "PARTIAL", "FILLED", "REJECTED", "CANCELED") else "ACKNOWLEDGED"
    _INTENTS[intent_id]["receipt"] = receipt
    return {"ok": True, "intent_id": intent_id, "order_id": order_id,
            "status": _INTENTS[intent_id]["state"]}


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
    status = str((observed or {}).get("status") or "UNKNOWN").upper()
    if status not in ("OPEN", "PENDING", "PARTIAL", "FILLED", "REJECTED", "CANCELED", "UNKNOWN"):
        status = "UNKNOWN"
    rec["state"] = status
    rec["observed"] = observed
    return {"intent_id": intent_id, "order_id": rec["order_id"], "status": status,
            "filled": (status == "FILLED")}


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


def protection_status(intent_id: str) -> dict[str, Any]:
    """Conservative protection truth: only verified-complete protection counts."""
    rec = _INTENTS.get(intent_id)
    if rec is None:
        return {"protected": False, "reason": "unknown-intent"}
    # No bracket/OCO linkage has been verified in this lane; never overstate.
    return {"protected": False, "reason": "no-verified-protection", "state": rec.get("state")}
