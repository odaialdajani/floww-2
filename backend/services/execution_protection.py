"""
backend/services/execution_protection.py — protection + expiry admission (S3).

Conservative by contract: protection must cover the actual eligible filled
quantity through a DOCUMENTED supported mechanism, or the intent stays
unverified/refused. No supported mechanism is established for any
product/order combination today, so every combination refuses
PROTECTION_UNVERIFIED with the exact missing capability named — never a
silent pass, never a label that implies coverage.

Expiry safety is policy-driven and explicit: entries need a minimum
distance-to-expiry from the account policy (DTE floor and same-day cutoff
hour). Absent policy values refuse GUARD_UNCONFIGURED rather than guessing
a safe distance. Assignment/exercise exposure is disclosed, never priced.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

PROTECTION_VERSION = "execution-protection.v1"
ET = ZoneInfo("America/New_York")

__all__ = [
    "PROTECTION_VERSION",
    "protection_admission",
    "entry_expiry_guard",
]


def protection_admission(
    product: str, order_type: str, filled_quantity: Any,
    account_protection_eligible: bool = False,
) -> dict[str, Any]:
    """Decide protection coverage for an eligible filled quantity.

    Returns covered quantity 0 with PROTECTION_UNVERIFIED until a documented
    supported mechanism plus verified account eligibility exists for the
    exact combination. A stop is never a guaranteed loss ceiling.
    """
    from services import public_execution_lifecycle as lc

    try:
        qty = int(filled_quantity)
    except (TypeError, ValueError):
        return {"covered": False, "reason": "BAD_CONTRACT",
                "covered_quantity": 0, "version": PROTECTION_VERSION}
    if qty <= 0:
        return {"covered": False, "reason": "BAD_CONTRACT",
                "covered_quantity": 0, "version": PROTECTION_VERSION}
    support = lc.native_protection_support(product, order_type)
    if not support.get("supported"):
        return {"covered": False, "reason": "PROTECTION_UNVERIFIED",
                "detail": f"no documented mechanism for {product}/{order_type}: "
                          f"{support.get('reason')}; account eligible: "
                          f"{bool(account_protection_eligible)}",
                "covered_quantity": 0, "version": PROTECTION_VERSION}
    if not account_protection_eligible:
        return {"covered": False, "reason": "PROTECTION_UNVERIFIED",
                "detail": "mechanism documented but account not verified eligible",
                "covered_quantity": 0, "version": PROTECTION_VERSION}
    return {"covered": True, "reason": None, "covered_quantity": qty,
            "version": PROTECTION_VERSION}


def entry_expiry_guard(
    expiry_iso: str, now: datetime | None, policy: dict[str, Any] | None,
) -> dict[str, Any]:
    """Policy-driven near-expiry entry cutoff (S3, commissioned flow only).

    policy: {min_entry_dte?, same_day_cutoff_et? ("HH:MM"), }.
    - Expiry before/unparseable → EXPIRY_INVALID.
    - No policy or no min_entry_dte → GUARD_UNCONFIGURED (never guessed).
    - DTE below floor → EXPIRY_TOO_NEAR.
    - Same-day (DTE 0) entries at/after cutoff → EXPIRY_TOO_NEAR.
    Assignment/exercise exposure after the cutoff is the operator's
    commissioning input, not modeled here.
    """
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    try:
        exp = datetime.strptime(str(expiry_iso)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"ok": False, "reason": "EXPIRY_INVALID",
                "version": PROTECTION_VERSION}
    if not isinstance(policy, dict) or policy.get("min_entry_dte") is None:
        return {"ok": False, "reason": "GUARD_UNCONFIGURED",
                "version": PROTECTION_VERSION}
    try:
        floor = int(policy["min_entry_dte"])
    except (TypeError, ValueError):
        return {"ok": False, "reason": "GUARD_UNCONFIGURED",
                "version": PROTECTION_VERSION}
    dte = (exp - moment.date()).days
    if dte < 0:
        return {"ok": False, "reason": "EXPIRY_INVALID",
                "version": PROTECTION_VERSION}
    if dte < floor:
        return {"ok": False, "reason": "EXPIRY_TOO_NEAR",
                "detail": f"DTE {dte} below floor {floor}; assignment/exercise "
                          "exposure unresolved", "version": PROTECTION_VERSION}
    if dte == 0:
        cutoff = str(policy.get("same_day_cutoff_et") or "13:00")
        if moment.astimezone(ET).strftime("%H:%M") >= cutoff:
            return {"ok": False, "reason": "EXPIRY_TOO_NEAR",
                    "detail": f"past same-day cutoff {cutoff} ET",
                    "version": PROTECTION_VERSION}
    return {"ok": True, "dte": dte, "version": PROTECTION_VERSION}
