"""B13 authenticated workspace portability: owner isolation + revisions.

Discovery: no user principal available (deployment key is not a user), so
account-sync records unavailable; local layouts continue. Mutations require
principal+owner match; cross-owner denied; conflicts via revision compare.
"""
from __future__ import annotations


def discover_identity(context: dict) -> dict:
    """Record available/degraded/unavailable principal verdict only."""
    principal = (context or {}).get("principal")
    if isinstance(principal, dict) and principal.get("user_id"):
        return {"status": "available", "principal": principal["user_id"]}
    return {"status": "unavailable", "reason": "no user principal; deployment key is not a user"}


def check_owner(principal: dict, owner: str, resource_owner: str) -> bool:
    """Deny cross-owner; supplied owner ID alone never suffices."""
    if not isinstance(principal, dict) or not principal.get("user_id"):
        return False
    if not owner or owner != resource_owner:
        return False
    return principal["user_id"] == owner


def apply_revision(stored: dict, incoming: dict):
    """Optimistic revisions: stale incoming conflicts, never overwrites."""
    if incoming.get("revision", 0) <= stored.get("revision", 0):
        return {"status": "conflict", "stored_revision": stored.get("revision", 0)}
    merged = {**stored, **incoming}
    return {"status": "ok", "workspace": merged}
