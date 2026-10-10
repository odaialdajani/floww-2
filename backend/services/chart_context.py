"""B24 server-resolved chart AI context: bind focus/query/scope/cursor generation.

Client numbers untrusted; no trade recommendations/orders or hidden data.
Pane removal/focus races cannot re-admit stale context.
"""
from __future__ import annotations


def bind_context(*, focus, query, scope, cursor, generation) -> dict:
    """Create a server-resolvable descriptor; refuses incomplete binding."""
    if not focus or not query or not scope or cursor is None or generation is None:
        return {"status": "refused", "reason": "incomplete binding"}
    return {"status": "bound", "focus": focus, "query": query, "scope": scope,
            "cursor": cursor, "generation": generation}


def resolve_context(descriptor: dict, current: dict) -> dict:
    """Admit only exact generation + compatible scope; stale races refused."""
    if not isinstance(descriptor, dict) or descriptor.get("status") != "bound":
        return {"status": "refused", "reason": "unbound"}
    if descriptor.get("generation") != current.get("generation"):
        return {"status": "refused", "reason": "stale generation"}
    if descriptor.get("scope") != current.get("scope"):
        return {"status": "refused", "reason": "scope mismatch"}
    if current.get("pane_removed"):
        return {"status": "refused", "reason": "pane removed"}
    return {"status": "admitted", "focus": descriptor["focus"]}
