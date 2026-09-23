"""
backend/services/capability_manifest.py — measured capability manifest + coverage (T26).

Unknown-first: every measurement starts null. Operational observations live
outside git; this module defines schema, reason codes, and per-feature gates.
"""

from __future__ import annotations

from typing import Any

REASON_CODES = ("SOURCE_TIME_UNKNOWN", "QUOTE_SKEW", "STALE_INPUT", "PARTIAL_CHAIN",
                "UNKNOWN_EXPECTED_UNIVERSE", "GREEK_PAIR_MIXED", "VOLUME_REBASE",
                "OI_REVISION", "THROTTLED", "PROVIDER_CHANGED", "CLOCK_UNCERTAIN")

_manifest: dict[str, Any] = {}


def record(endpoint: str, instrument_family: str, bucket: str, obs: dict[str, Any]) -> None:
    """Store one observation period (in-memory; persisted observations stay out of git)."""
    _manifest.setdefault(endpoint, {}).setdefault(instrument_family, {})[bucket] = {
        "sample_count": obs.get("sample_count"), "ages_ms": obs.get("ages_ms"),
        "coverage": obs.get("coverage"), "reasons": obs.get("reasons", []),
        "uncertainty": obs.get("uncertainty", "censored"),
    }


def get_manifest() -> dict[str, Any]:
    return {"measurements": _manifest or "all_null_unknown_first",
            "reason_codes": list(REASON_CODES),
            "policy": "unknown-first; censored polling; per-feature age/skew gates"}


def coverage_report(requested: set, returned: set, usable: set) -> dict[str, Any]:
    """Expected vs requested vs returned vs usable — independent denominators."""
    return {"expected_unknown": True,  # expected universe often unknowable
            "requested": len(requested), "returned": len(returned), "usable": len(usable),
            "missing": sorted(requested - returned),
            "unusable": sorted(returned - usable)}
