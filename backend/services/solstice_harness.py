"""
backend/services/solstice_harness.py — ticket/session engineering harness (T24).

Resumable per-ticket work packets: objective, non-goals, base/head SHA,
allowed paths, invariants, failing evidence, acceptance commands, gates,
artifacts, migration/rollback, next action. Unknown commands stay unknown.
"""

from __future__ import annotations

from typing import Any

REQUIRED_GATES = ("pytest_targeted", "silent_except_audit", "ruff")


def packet(ticket: str, objective: str, base_sha: str, allowed_paths: list[str],
           invariants: list[str], acceptance: list[str], **kw: Any) -> dict[str, Any]:
    return {"ticket": ticket, "objective": objective, "non_goals": kw.get("non_goals", []),
            "base_sha": base_sha, "head_sha": None, "allowed_paths": allowed_paths,
            "invariants": invariants, "failing_evidence": kw.get("failing_evidence"),
            "acceptance_commands": acceptance, "required_gates": list(REQUIRED_GATES),
            "artifacts": [], "migration_rollback": kw.get("migration_rollback", "additive_reversible"),
            "status": "observed", "next_action": kw.get("next_action", "")}


def receipt(packet: dict, results: dict[str, Any]) -> dict[str, Any]:
    """observed → proposed → verified | blocked."""
    p = dict(packet)
    p["results"] = results
    p["status"] = "verified" if results.get("passed") else ("blocked" if results.get("blocked") else "proposed")
    return p
