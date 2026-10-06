"""Admit registered stored metric conventions; no calculator or provider access."""
from datetime import datetime

from domain.exposure_metrics import METRIC_REGISTRY
from services.agent.contracts import instant
from services.solstice_window import window_observation

METRIC_IDS = {"vex": "vex_net_1volpt", "charm": "charm_net_1pct_year_v1"}


def metric_evidence(raw, screen, now):
    def refuse(reason):
        return None, ["RECORDED_METRIC_" + reason + ": no recomputed/live Greek substitute"]

    metric = screen.get("metric")
    definition = METRIC_REGISTRY[METRIC_IDS[metric]]
    grid = raw.get("grid") or {}
    meta = grid.get(metric + "_meta")
    if not isinstance(meta, dict) or meta.get("record_version") != "metric-record.v1":
        return refuse("ENVELOPE_INCOMPLETE")
    if screen.get("recordedMetricVersion") not in (None, meta["record_version"]):
        return refuse("ENVELOPE_CONFLICT")
    if (raw.get("replay") is not True or raw.get("recorded_snapshot_id") != screen.get("snapshotId")
            or raw.get("snapshotId") != screen.get("snapshotId")):
        return refuse("SNAPSHOT_CONFLICT")
    model = meta.get("model")
    models = model.split("+") if isinstance(model, str) else []
    allowed = definition.get("models") or [definition.get("model")]
    weight = "OI" if metric == "vex" else {"OI":"OI", "VOLUME_SCALP":"VOLUME", "VOLUME_FALLBACK_OI_UNKNOWN":"VOLUME"}.get(raw.get("exposure_basis"))
    if (meta.get("metric_id") != METRIC_IDS[metric] or meta.get("unit") != definition["units"]
            or meta.get("formula_version") != definition["version"] or raw.get("formula_version") != definition["version"]
            or meta.get("exposure_basis") != definition["basis"] or meta.get("weight_basis") != weight
            or not models or len(set(models)) != len(models) or not set(models) <= set(allowed)):
        return refuse("CONVENTION_CONFLICT")
    if meta.get("data_source") != raw.get("data_source") or not meta.get("data_source"):
        return refuse("PROVENANCE_CONFLICT")
    if meta.get("map_query") != raw.get("map_query") or meta.get("scope") != {"strikes":grid.get("strikes"),"expiries":grid.get("expiries")}:
        return refuse("SCOPE_CONFLICT")
    observation, reason = window_observation(raw)
    if reason or any(instant(meta.get(k)) != instant(raw.get(v)) or instant(meta.get(k)) is None
                    for k,v in (("event_time","event_time"),("fetched_at","fetched_at"),("available_at","asof"))):
        return refuse("SOURCE_CLOCK_INVALID")
    if datetime.fromisoformat(observation["available_at"]) > now:
        return refuse("SOURCE_CLOCK_INVALID")
    counters = ("quarantined", "invalid_type", "missing_vanna_inputs" if metric == "vex" else "missing_charm_inputs")
    if any(not isinstance(meta.get(k), int) or isinstance(meta[k], bool) or meta[k] < 0 for k in counters):
        return refuse("COVERAGE_UNDECLARED")
    if meta.get("status") not in {"ok", "partial"}:
        return refuse(str(meta.get("reason") or "NO_COVERAGE"))
    return meta, []
