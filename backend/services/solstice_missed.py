"""
backend/services/solstice_missed.py — missed-opportunity + session-review system (T25).

Causal opportunity denominator: every eligible wall encounter recorded BEFORE
outcome. Bottleneck taxonomy. Retrospective high/low labeling prohibited.
At most three prioritized research actions per review.
"""

from __future__ import annotations

from typing import Any

BOTTLENECKS = ("source_coverage", "detection_latency", "wrong_horizon",
               "permission_gate", "contract_rejection", "ui_comprehension",
               "late_user_action", "fill_quality")


def record_encounter(store: list, encounter: dict[str, Any]) -> None:
    """Store pre-outcome encounter (wall, rule, quote, exit plan all causal)."""
    store.append({**encounter, "outcome": None, "bottleneck": None})


def resolve_encounter(encounter: dict, outcome: dict[str, Any]) -> dict[str, Any]:
    """Attach realistic option outcome (executable quotes + exits, never day high/low)."""
    encounter = dict(encounter)
    encounter["outcome"] = outcome.get("label", "indeterminate")
    encounter["bottleneck"] = outcome.get("bottleneck")
    return encounter


def session_review(encounters: list[dict]) -> dict[str, Any]:
    """One short review: defects vs strategy vs usability vs costs + ≤3 questions."""
    by_bottleneck: dict[str, int] = {}
    for e in encounters:
        b = e.get("bottleneck") or "pending"
        by_bottleneck[b] = by_bottleneck.get(b, 0) + 1
    questions = []
    for b, n in sorted(by_bottleneck.items(), key=lambda kv: -kv[1])[:3]:
        questions.append(f"Reduce '{b}' bottleneck ({n} encounters): exact evidence + next experiment?")
    return {"n_encounters": len(encounters), "by_bottleneck": by_bottleneck,
            "research_questions": questions[:3],
            "note": "observed underlying moves are not executable option trades"}
