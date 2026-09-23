"""
backend/services/solstice_longevity.py — schema longevity, migration, recovery, ownership (T29).

Bitemporal replay (event time + known-at), additive migrations, provider /
corporate-action revisions, restart/storage safety, retention tiers.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSIONS = {"snapshot": "2", "formula": "gex.v2", "evidence": "solstice.evidence.v2",
                   "patterns": "patterns.v1", "session": "session.v1"}
OWNER = {"metrics": "solstice-quant", "api_contracts": "solstice-platform",
         "ux": "solstice-frontend", "release": "solstice-owner"}


def migrate_snapshot_v1_to_v2(v1: dict[str, Any]) -> dict[str, Any]:
    """Additive migration: unknown-first defaults, raw values preserved."""
    v2 = dict(v1)
    v2.setdefault("schemaVersion", "2")
    v2.setdefault("exposure_basis", "OI")
    v2.setdefault("formula_version", "gex.v2")
    v2.setdefault("source_received_at", None)
    v2.setdefault("quality", {"setup_eligible": False, "reasonCodes": ["MIGRATED_V1"],
                              "trade_side_capability": "none"})
    v2["_migrated_from"] = "1"
    return v2


def revision_record(kind: str, old: str, new: str, reason: str) -> dict[str, Any]:
    """Provider / corporate-action / calendar revision marker (invalidates dependents)."""
    return {"kind": kind, "old": old, "new": new, "reason": reason,
            "effect": "revision_dependent_scenarios_invalid_until_rebuilt"}


RETENTION = {"research_immutable": "licensed_minimum", "display_cache": "50_per_ticker",
             "telemetry": "redacted_outside_git"}
