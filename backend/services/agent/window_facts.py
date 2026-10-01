"""Validate the recorded interval envelope without recomputing exposure or Greeks."""
from datetime import datetime

from services.agent.contracts import instant
from services.solstice_window import GREEK_CONVENTION, check_window_comparability, window_observation


def window_evidence(raw, screen, now):
    def refuse(code):
        return None, ["WINDOW_" + code + ": comparable stored activity unavailable; no live or session-volume substitute"]

    section = ((raw.get("metrics") or {}).get("grids") or {}).get("window") or {}
    if section.get("status") == "unavailable":
        return refuse(str(section.get("reason") or "NO_BASELINE"))
    comparison, baseline = section.get("comparison"), raw.get("window_baseline")
    if not isinstance(comparison, dict) or not isinstance(baseline, dict):
        return refuse("RECORD_ENVELOPE_INCOMPLETE")
    previous_id = comparison.get("previous_snapshot_id")
    if (not previous_id or previous_id != screen.get("windowBaselineId") or previous_id == raw.get("snapshotId")
            or previous_id != baseline.get("snapshotId") or previous_id != baseline.get("recorded_snapshot_id")
            or raw.get("recorded_snapshot_id") != screen.get("snapshotId")
            or baseline.get("replay") is not True or raw.get("replay") is not True):
        return refuse("SNAPSHOT_CONFLICT")
    before, preason = window_observation(baseline)
    current, creason = window_observation(raw)
    if preason or creason:
        return refuse(preason or creason)
    reason, _ = check_window_comparability(before, current)
    if reason:
        return refuse(reason)
    if comparison.get("previous") != before or comparison.get("current") != current:
        return refuse("IDENTITY_CONFLICT")
    if (comparison.get("volume_correction_policy") != "refuse-retraction" or section.get("greek_convention") != GREEK_CONVENTION
            or section.get("interval") != {"start": before["asof"], "end": current["asof"]}):
        return refuse("CONVENTION_CONFLICT")
    if screen.get("windowInterval") is not None and screen["windowInterval"] != section.get("interval"):
        return refuse("INTERVAL_CONFLICT")
    available = [instant(s["available_at"]) for s in (before, current)]
    if not available[0] < available[1] or datetime.fromisoformat(available[1]) > now:
        return refuse("AVAILABLE_AT_CONFLICT")
    for observation in (raw, baseline):
        coverage = observation.get("contract_coverage") or {}
        if (coverage.get("truncated") is not False or coverage.get("requested") != coverage.get("returned")
                or coverage.get("returned") != len(observation.get("contracts") or [])):
            return refuse("POPULATION_PARTIAL")
    return section, []
